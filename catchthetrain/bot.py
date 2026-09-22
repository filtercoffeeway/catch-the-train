"""Telegram commands, buttons and time-to-leave alerts."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from . import alerts
from .config import Config, known_parking_station, station_name
from .planner import Option, Planner
from .state import Store
from .timeparse import at, fmt_t, mins, next_weekday, parse_clock

log = logging.getLogger(__name__)

HELP = """🚆 Catch The Train
/tooffice — when to leave home (next train or next 4)
/tooffice 9:45 — must reach office by 9:45
/tohome — when to leave the office
/tohome 6:15 — leaving the office at 6:15 PM
/park UCTY — set where your car is parked
/alerts — alert status; /alerts off, /alerts on
/chatid — show this chat's id"""

COMMANDS = [
    BotCommand("tooffice", "When to leave home"),
    BotCommand("tohome", "When to leave the office"),
    BotCommand("park", "Set station where car is parked"),
    BotCommand("alerts", "Time-to-leave alerts on/off"),
    BotCommand("help", "Usage"),
]

CHECKING = "⏳ Checking trains and traffic…"
LIVE_WINDOW = timedelta(minutes=90)
# Direction of travel at the boarding station, for BART real-time departures.
LIVE_DIR = {"office": "n", "home": "s"}


def keyboard(*buttons: tuple[str, str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=data) for text, data in buttons]])


def choose_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return keyboard(("Next available", prefix.format(n=1)), ("Next 4 options", prefix.format(n=4)))


class CommuteBot:
    def __init__(self, cfg: Config, planner: Planner, store: Store):
        self.cfg, self.planner, self.store = cfg, planner, store

    def register(self, app: Application) -> None:
        app.add_handler(CommandHandler("chatid", self.chatid))
        app.add_handler(CommandHandler(["start", "help"], self.help))
        app.add_handler(CommandHandler(["tooffice", "office", "morning", "m"], self.tooffice))
        app.add_handler(CommandHandler(["tohome", "home", "evening", "e"], self.tohome))
        app.add_handler(CommandHandler("park", self.park))
        app.add_handler(CommandHandler("alerts", self.alerts_cmd))
        app.add_handler(CallbackQueryHandler(self.button))
        app.add_handler(MessageHandler(filters.COMMAND, self.unknown))
        app.job_queue.run_repeating(self.alert_tick, interval=60, first=10)

    def now(self) -> datetime:
        return datetime.now(self.cfg.tz)

    async def _allowed(self, update: Update) -> bool:
        chat = update.effective_chat.id
        if self.cfg.allowed_chat == 0:
            await update.effective_message.reply_text(f"Bot is locked. Set TELEGRAM_CHAT_ID={chat} and restart.")
            return False
        if chat != self.cfg.allowed_chat:
            log.info("ignoring chat %s", chat)
            return False
        return True

    # ---- commands ----

    async def chatid(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(f"Chat id: {update.effective_chat.id}")

    async def help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._allowed(update):
            await update.message.reply_text(HELP)

    async def unknown(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._allowed(update):
            await update.message.reply_text("Unknown command. /help")

    async def tooffice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._allowed(update):
            return
        for a in ctx.args:
            if hm := parse_clock(a):
                msg = await update.message.reply_text(CHECKING)
                text, kb = await self._office_by(*hm)
                await msg.edit_text(text, reply_markup=kb)
                return
        await update.message.reply_text("🏢 To office — which trains?", reply_markup=choose_keyboard("to|office|{n}"))

    async def tohome(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._allowed(update):
            return
        station, hhmm, when = "", "", ""
        for a in ctx.args:
            if known_parking_station(a.upper()):
                station = a.upper()
            elif hm := parse_clock(a, pm_if_bare=True):
                hhmm, when = f"{hm[0]:02d}{hm[1]:02d}", f" leaving {fmt_t(at(self.now(), *hm))}"
        await update.message.reply_text(
            f"🏠 To home{when} — which trains?", reply_markup=choose_keyboard(f"to|home|{{n}}|{station}|{hhmm}"))

    async def park(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._allowed(update):
            return
        st = self.store.load()
        if not ctx.args:
            await update.message.reply_text(f"Car is at: {station_name(st.station) if st.station else 'unknown'}")
            return
        st.station = ctx.args[0].upper()
        self.store.save(st)
        await update.message.reply_text(f"OK, car parked at {station_name(st.station)}")

    async def alerts_cmd(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._allowed(update):
            return
        st = self.store.today(self.now().date())
        if ctx.args and ctx.args[0].lower() in ("on", "off"):
            st.alerts_on = ctx.args[0].lower() == "on"
            self.store.save(st)
        c = self.cfg
        (ms, me), (es, ee) = c.alert_morning, c.alert_evening
        today = lambda d: "done for today" if d in st.done else "active today"  # noqa: E731
        await update.message.reply_text(
            f"🔔 Alerts are {'ON' if st.alerts_on else 'OFF'} (weekdays, {mins(c.alert_lead)} min before leave-by)\n"
            f"• Morning: leave home {_t(ms)}–{_t(me)} — {today('office')}\n"
            f"• Evening: leave office {_t(es)}–{_t(ee)} — {today('home')}\n"
            f"Turn {'off: /alerts off' if st.alerts_on else 'on: /alerts on'}")

    # ---- buttons ----

    async def button(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        if not await self._allowed(update):
            return
        match q.data.split("|"):
            case ["to", "office", n]:
                await q.edit_message_text(CHECKING)
                text, kb = await self._office(int(n))
                await q.edit_message_text(text, reply_markup=kb)
            case ["to", "home", n, station, hhmm]:
                await q.edit_message_text(CHECKING)
                text, kb = await self._home(int(n), station, hhmm)
                await q.edit_message_text(text, reply_markup=kb)
            case ["go", direction, *station]:
                self._mark_done(direction, station[0] if station else "")
                note = (f"✅ Have a good trip! No more morning alerts today. Car at {station_name(station[0])}."
                        if direction == "office" and station else "✅ Safe travels! No more alerts for this trip today.")
                await q.edit_message_text(f"{q.message.text}\n\n{note}")
            case ["skip", direction]:
                self._mark_done(direction, "")
                period = "morning" if direction == "office" else "evening"
                await q.edit_message_text(f"{q.message.text}\n\n🔕 OK, no more {period} alerts today.")
            case _:
                log.warning("unknown callback %r", q.data)

    def _mark_done(self, direction: str, station: str) -> None:
        st = self.store.today(self.now().date())
        if direction not in st.done:
            st.done.append(direction)
        if station:
            st.station = station
        self.store.save(st)

    # ---- plans ----

    async def _office(self, n: int) -> tuple[str, InlineKeyboardMarkup | None]:
        opts, errs = await self.planner.to_office(self.now(), n)
        head = "🏢 Next train to the office" if n == 1 else f"🏢 Next {n} ways to the office"
        return await self._render("office", head, opts, errs, "Later options:")

    async def _office_by(self, h: int, m: int) -> tuple[str, InlineKeyboardMarkup | None]:
        now = self.now()
        deadline = at(now, h, m)
        if deadline < now:
            deadline = at(next_weekday(now), h, m)
        opts, errs = await self.planner.to_office_by(deadline, now)
        head = f"🏢 {deadline:%a %b} {deadline.day} — reach office by {fmt_t(deadline)}"
        return await self._render("office", head, opts, errs, "Earlier options:")

    async def _home(self, n: int, station: str, hhmm: str) -> tuple[str, InlineKeyboardMarkup | None]:
        now = self.now()
        st = station or self.store.load().station or self.cfg.home_stations[0]
        leave_at = at(now, int(hhmm[:2]), int(hhmm[2:])) if hhmm else now
        opts, errs = [], []
        try:
            opts = await self.planner.to_home(leave_at, st, n)
        except Exception as e:  # noqa: BLE001 — surface API failures to the user
            errs.append(str(e))
        head = f"🏠 Heading home — car at {station_name(st)} ({st})"
        return await self._render("home", head, opts, errs, "Later options:")

    async def _render(self, direction: str, head: str, opts: list[Option], errs: list[str],
                      more: str) -> tuple[str, InlineKeyboardMarkup | None]:
        lines = [head, ""]
        if not opts:
            lines.append("No train you can still catch in that window.")
        for i, o in enumerate(opts):
            if i == 0:
                lines.append(self._detail(direction, o, "⭐ Leave"))
                if len(opts) > 1:
                    lines += ["", more]
            else:
                lines.append(self._line(direction, o))
        if opts:
            lines.append(await self._live(direction, opts[0]))
        lines += [f"⚠️ {e}" for e in errs]
        kb = keyboard(("🚗 I'm leaving", f"go|{direction}|{opts[0].station}" if direction == "office"
                       else "go|home")) if opts else None
        return "\n".join(x for x in lines if x is not None).strip(), kb

    def _detail(self, direction: str, o: Option, lead: str) -> str:
        c, t = self.cfg, o.trip
        heads = " → ".join(t.heads)
        if direction == "office":
            return (f"{lead} home {fmt_t(o.leave)}\n"
                    f"  🚗 {mins(o.drive)} min → {station_name(o.station)}, 🚶 {mins(c.park_walk)} min to platform\n"
                    f"  🚆 {fmt_t(t.depart)} → {station_name(c.office_station)} {fmt_t(t.arrive)} ({heads})\n"
                    f"  🏢 Office ~{fmt_t(o.arrive)}")
        return (f"{lead} office {fmt_t(o.leave)}\n"
                f"  🚆 {station_name(t.orig)} {fmt_t(t.depart)} → {station_name(o.station)} {fmt_t(t.arrive)} ({heads})\n"
                f"  🚗 {mins(o.drive)} min drive → home ~{fmt_t(o.arrive)}")

    def _line(self, direction: str, o: Option) -> str:
        if direction == "office":
            return f"• Leave {fmt_t(o.leave)} → {o.station} {fmt_t(o.trip.depart)} train → office {fmt_t(o.arrive)}"
        return f"• Leave {fmt_t(o.leave)} → {fmt_t(o.trip.depart)} train → home ~{fmt_t(o.arrive)}"

    async def _live(self, direction: str, o: Option) -> str | None:
        """Real-time departures at the boarding station when the train is close."""
        if o.trip.depart - self.now() > LIVE_WINDOW:
            return None
        try:
            s = await self.planner.bart.live_summary(o.trip.orig, LIVE_DIR[direction], o.trip.heads)
        except Exception as e:  # noqa: BLE001 — live data is optional
            log.warning("live: %s", e)
            return None
        return f"\n📡 Live at {station_name(o.trip.orig)} — {s}" if s else None

    # ---- time-to-leave alerts ----

    async def alert_tick(self, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        c = self.cfg
        now = self.now()
        if not c.allowed_chat or now.weekday() >= 5:
            return
        for direction, (ws, we) in (("office", c.alert_morning), ("home", c.alert_evening)):
            start, end = at(now, ws.hour, ws.minute), at(now, we.hour, we.minute)
            if not start - c.alert_lead <= now <= end:
                continue
            st = self.store.today(now.date())
            if not st.alerts_on or direction in st.done:
                continue
            try:
                if direction == "office":
                    opts, _ = await self.planner.to_office(now, 4)
                else:
                    opts = await self.planner.to_home(now, st.station or c.home_stations[0], 4)
            except Exception:
                log.exception("alert planning (%s)", direction)
                continue
            st = self.store.today(now.date())  # re-read: a button press may have landed while planning
            if direction in st.done:
                continue
            o = alerts.due(direction, opts, now, start, end, c.alert_lead, set(st.alerted))
            if not o:
                continue
            left = mins(o.leave - now)
            title = f"⏰ Leave {'home' if direction == 'office' else 'office'} " + (f"in {left} min" if left > 0 else "now")
            go = f"go|office|{o.station}" if direction == "office" else "go|home"
            await ctx.bot.send_message(
                c.allowed_chat, f"{title}\n\n{self._detail(direction, o, '👉 Leave')}",
                reply_markup=keyboard(("🚗 I'm leaving", go), ("🔕 Not today", f"skip|{direction}")))
            st.alerted.append(alerts.key(direction, o))
            self.store.save(st)


def _t(t) -> str:
    return fmt_t(datetime(2000, 1, 1, t.hour, t.minute))
