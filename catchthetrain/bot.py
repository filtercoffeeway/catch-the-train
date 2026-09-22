"""Telegram commands, buttons, the setup wizard and time-to-leave alerts."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from telegram import BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from . import alerts
from .config import Config
from .planner import Option, Planner
from .profile import Profile, fmt_days
from .settings import EDIT_STEPS, FIELDS, SETUP_STEPS, summary
from .state import Store
from .stations import find, station_name
from .timeparse import at, fmt_t, mins, next_day, parse_clock

log = logging.getLogger(__name__)

HELP = """🚆 Catch The Train
/tooffice — when to leave home (next train or next 4)
/tooffice 9:45 — must reach the office by 9:45
/tohome — when to leave the office
/tohome 6:15 — leaving the office at 6:15 PM
/park UCTY — set where your car is parked
/alerts — alert status; /alerts off, /alerts on
/settings — view or change your commute
/forget — delete your data"""

WELCOME = """👋 Hi! I work out when to leave for a drive + BART commute, and nudge you when it's time to go.

First, a few questions about your commute (/cancel to stop)."""

COMMANDS = [
    BotCommand("tooffice", "When to leave home"),
    BotCommand("tohome", "When to leave the office"),
    BotCommand("park", "Set station where car is parked"),
    BotCommand("alerts", "Time-to-leave alerts on/off"),
    BotCommand("settings", "View or change your commute"),
    BotCommand("help", "Usage"),
]

CHECKING = "⏳ Checking trains…"
LIVE_WINDOW = timedelta(minutes=90)
PRIVATE = filters.ChatType.PRIVATE


def keyboard(*buttons: tuple[str, str], cols: int = 2) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text, callback_data=data) for text, data in buttons]
    return InlineKeyboardMarkup([row[i:i + cols] for i in range(0, len(row), cols)])


def choose_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return keyboard(("Next available", prefix.format(n=1)), ("Next 4 options", prefix.format(n=4)))


class CommuteBot:
    def __init__(self, cfg: Config, planner: Planner, store: Store):
        self.cfg, self.planner, self.store = cfg, planner, store

    def register(self, app: Application) -> None:
        def cmd(names, callback) -> None:
            app.add_handler(CommandHandler(names, callback, filters=PRIVATE))

        cmd("start", self.start)
        cmd("help", self.help)
        cmd("setup", self.setup)
        cmd("settings", self.settings)
        cmd("cancel", self.cancel)
        cmd("forget", self.forget)
        cmd(["tooffice", "office", "morning", "m"], self.tooffice)
        cmd(["tohome", "home", "evening", "e"], self.tohome)
        cmd("park", self.park)
        cmd("alerts", self.alerts_cmd)
        app.add_handler(CallbackQueryHandler(self.button))
        app.add_handler(MessageHandler(PRIVATE & filters.COMMAND, self.unknown))
        app.add_handler(MessageHandler(PRIVATE & filters.TEXT, self.on_text))
        app.job_queue.run_repeating(self.alert_tick, interval=60, first=10)

    def now(self) -> datetime:
        return datetime.now(self.cfg.tz)

    async def _profile(self, update: Update) -> Profile | None:
        p = self.store.profile(update.effective_chat.id)
        if p is None:
            await update.effective_message.reply_text("First, tell me about your commute: /setup")
        return p

    def _car(self, chat: int, p: Profile, station: str = "") -> str:
        """Station to route home to: the one asked for, else where the car was left, else the first home station."""
        return next(s for s in (station, self.store.load(chat).station, p.home_stations[0]) if s in p.home_stations)

    # ---- commands ----

    async def start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if self.store.profile(update.effective_chat.id):
            await update.message.reply_text(HELP)
        else:
            await self.setup(update, ctx)

    async def help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(HELP)

    async def unknown(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Unknown command. /help")

    async def tooffice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not (p := await self._profile(update)):
            return
        for a in ctx.args:
            if hm := parse_clock(a):
                msg = await update.message.reply_text(CHECKING)
                text, kb = await self._office_by(p, *hm)
                await msg.edit_text(text, reply_markup=kb)
                return
        await update.message.reply_text("🏢 To office — which trains?", reply_markup=choose_keyboard("to|office|{n}"))

    async def tohome(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not (p := await self._profile(update)):
            return
        station, hhmm, when = "", "", ""
        for a in ctx.args:
            if a.upper() in p.home_stations:
                station = a.upper()
            elif hm := parse_clock(a, pm_if_bare=True):
                hhmm, when = f"{hm[0]:02d}{hm[1]:02d}", f" leaving {fmt_t(at(self.now(), *hm))}"
        await update.message.reply_text(
            f"🏠 To home{when} — which trains?", reply_markup=choose_keyboard(f"to|home|{{n}}|{station}|{hhmm}"))

    async def park(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not (p := await self._profile(update)):
            return
        chat = update.effective_chat.id
        st = self.store.load(chat)
        if not ctx.args:
            await update.message.reply_text(f"Car is at: {station_name(st.station) if st.station else 'unknown'}")
            return
        hits = [c for c in find(" ".join(ctx.args)) if c in p.home_stations]
        if len(hits) != 1:
            await update.message.reply_text(f"Pick one of your home stations: {', '.join(p.home_stations)}")
            return
        st.station = hits[0]
        self.store.save(chat, st)
        await update.message.reply_text(f"OK, car parked at {station_name(st.station)}")

    async def alerts_cmd(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not (p := await self._profile(update)):
            return
        chat = update.effective_chat.id
        st = self.store.today(chat, self.now().date())
        if ctx.args and ctx.args[0].lower() in ("on", "off"):
            st.alerts_on = ctx.args[0].lower() == "on"
            self.store.save(chat, st)
        (ms, me), (es, ee) = p.morning, p.evening
        today = lambda d: "done for today" if d in st.done else "active today"  # noqa: E731
        await update.message.reply_text(
            f"🔔 Alerts are {'ON' if st.alerts_on else 'OFF'} ({fmt_days(p.days)}, {mins(p.lead)} min before leave-by)\n"
            f"• Morning: leave home {fmt_t(ms)}–{fmt_t(me)} — {today('office')}\n"
            f"• Evening: leave office {fmt_t(es)}–{fmt_t(ee)} — {today('home')}\n"
            f"Turn {'off: /alerts off' if st.alerts_on else 'on: /alerts on'}. Change times in /settings")

    async def forget(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Delete your commute settings and alert history?", reply_markup=keyboard(("🗑 Yes, delete", "forget")))

    # ---- setup wizard ----

    async def setup(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat.id
        p = self.store.profile(chat)
        if p is None and self.store.user_count() >= self.cfg.max_users:
            await update.message.reply_text("Sorry, this bot is full right now. Please try again later.")
            return
        await update.message.reply_text(WELCOME if p is None else "Let's go through your commute (/cancel to stop).")
        await self._wizard(chat, ctx, SETUP_STEPS, p)

    async def settings(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not (p := await self._profile(update)):
            return
        await update.message.reply_text(
            f"⚙️ Your commute\n{summary(p.to_json())}\n\nTap a setting to change it, or /setup to go through all.",
            reply_markup=keyboard(*((f.label, f"set|{f.key}") for f in FIELDS.values())))

    async def cancel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        cancelled = ctx.user_data.pop("wizard", None)
        await update.message.reply_text("OK, cancelled. Nothing was changed." if cancelled else "Nothing to cancel.")

    async def on_text(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat.id
        if "wizard" in ctx.user_data:
            await self._answer(chat, ctx, update.message.text)
        elif self.store.profile(chat) is None:
            await update.message.reply_text("Send /start to set up your commute.")
        else:
            await update.message.reply_text("I only understand commands. /help")

    async def _wizard(self, chat: int, ctx: ContextTypes.DEFAULT_TYPE, steps: list[str], p: Profile | None) -> None:
        """Ask `steps` one at a time. Answers build a draft that's saved only after the last one."""
        ctx.user_data["wizard"] = {"steps": list(steps), "draft": p.to_json() if p else {}, "new": p is None}
        await self._ask(chat, ctx)

    async def _ask(self, chat: int, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        w = ctx.user_data["wizard"]
        f = FIELDS[w["steps"][0]]
        text = f.ask(w["draft"])
        buttons = [(s, f"w|{f.key}|{s}") for s in f.suggest]
        if f.known(w["draft"]):
            text += f"\n\nNow: {f.show(w['draft'])}"
            buttons.append(("Keep current", f"w|{f.key}|"))
        await ctx.bot.send_message(chat, text, reply_markup=keyboard(*buttons, cols=4) if buttons else None)

    async def _answer(self, chat: int, ctx: ContextTypes.DEFAULT_TYPE, text: str | None) -> None:
        """Apply an answer to the current question (None keeps the current value), then ask the next."""
        w = ctx.user_data["wizard"]
        f = FIELDS[w["steps"][0]]
        if text is not None:
            try:
                w["draft"].update(f.parse(text.strip(), w["draft"]))
            except ValueError as e:
                log.info("chat %s: rejected %s answer %r: %s", chat, f.key, text, e)
                await ctx.bot.send_message(chat, f"⚠️ {e}")
                return
        w["steps"].pop(0)
        if w["steps"]:
            await self._ask(chat, ctx)
            return
        del ctx.user_data["wizard"]
        p = Profile.from_json(w["draft"])
        self.store.save_profile(chat, p)
        msg = f"✅ Saved.\n{summary(p.to_json())}"
        if w["new"]:
            msg += f"\n\nYou're set up! Change anything with /settings.\n\n{HELP}"
        await ctx.bot.send_message(chat, msg)

    async def _wizard_button(self, q: CallbackQuery, ctx: ContextTypes.DEFAULT_TYPE, key: str, value: str) -> None:
        w = ctx.user_data.get("wizard")
        if not w or w["steps"][0] != key:
            await q.answer("That question has expired.")
            return
        await q.answer()
        await q.edit_message_text(f"{q.message.text}\n\n→ {value or 'kept'}")
        await self._answer(q.message.chat.id, ctx, value or None)

    # ---- buttons ----

    async def button(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        data = q.data.split("|")
        if data[0] == "w" and len(data) == 3:
            await self._wizard_button(q, ctx, data[1], data[2])
            return
        await q.answer()
        chat = q.message.chat.id
        if data == ["forget"]:
            self.store.delete(chat)
            ctx.user_data.pop("wizard", None)
            await q.edit_message_text("🗑 Deleted. Send /start any time to set up again.")
            return
        if data[0] in ("go", "skip"):
            self._mark_done(chat, data[1], data[2] if len(data) > 2 else "")
            await q.edit_message_text(f"{q.message.text}\n\n{_done_note(*data)}")
            return
        p = self.store.profile(chat)
        if p is None:
            await q.edit_message_text("First, tell me about your commute: /setup")
            return
        match data:
            case ["set", key] if key in FIELDS:
                await self._wizard(chat, ctx, EDIT_STEPS.get(key, [key]), p)
            case ["to", "office", n]:
                await q.edit_message_text(CHECKING)
                text, kb = await self._office(p, int(n))
                await q.edit_message_text(text, reply_markup=kb)
            case ["to", "home", n, station, hhmm]:
                await q.edit_message_text(CHECKING)
                text, kb = await self._home(chat, p, int(n), station, hhmm)
                await q.edit_message_text(text, reply_markup=kb)
            case _:
                log.warning("unknown callback %r", q.data)

    def _mark_done(self, chat: int, direction: str, station: str) -> None:
        st = self.store.today(chat, self.now().date())
        if direction not in st.done:
            st.done.append(direction)
        if station:
            st.station = station
        self.store.save(chat, st)

    # ---- plans ----

    async def _office(self, p: Profile, n: int) -> tuple[str, InlineKeyboardMarkup | None]:
        opts, errs = await self.planner.to_office(p, self.now(), n)
        head = "🏢 Next train to the office" if n == 1 else f"🏢 Next {n} ways to the office"
        return await self._render(p, "office", head, opts, errs, "Later options:")

    async def _office_by(self, p: Profile, h: int, m: int) -> tuple[str, InlineKeyboardMarkup | None]:
        now = self.now()
        deadline = at(now, h, m)
        if deadline < now:
            deadline = at(next_day(now, p.days), h, m)
        opts, errs = await self.planner.to_office_by(p, deadline, now)
        head = f"🏢 {deadline:%a %b} {deadline.day} — reach office by {fmt_t(deadline)}"
        return await self._render(p, "office", head, opts, errs, "Earlier options:")

    async def _home(self, chat: int, p: Profile, n: int, station: str,
                    hhmm: str) -> tuple[str, InlineKeyboardMarkup | None]:
        now = self.now()
        st = self._car(chat, p, station)
        leave_at = at(now, int(hhmm[:2]), int(hhmm[2:])) if hhmm else now
        opts, errs = [], []
        try:
            opts = await self.planner.to_home(p, leave_at, st, n)
        except Exception as e:  # noqa: BLE001 — surface API failures to the user
            errs.append(str(e))
        head = f"🏠 Heading home — car at {station_name(st)} ({st})"
        return await self._render(p, "home", head, opts, errs, "Later options:")

    async def _render(self, p: Profile, direction: str, head: str, opts: list[Option], errs: list[str],
                      more: str) -> tuple[str, InlineKeyboardMarkup | None]:
        lines = [head, ""]
        if not opts:
            lines.append("No train you can still catch in that window.")
        for i, o in enumerate(opts):
            if i == 0:
                lines.append(self._detail(p, direction, o, "⭐ Leave"))
                if len(opts) > 1:
                    lines += ["", more]
            else:
                lines.append(self._line(direction, o))
        if opts:
            lines.append(await self._live(opts[0]))
        lines += [f"⚠️ {e}" for e in errs]
        kb = keyboard(("🚗 I'm leaving", f"go|{direction}|{opts[0].station}" if direction == "office"
                       else "go|home")) if opts else None
        return "\n".join(x for x in lines if x is not None).strip(), kb

    def _detail(self, p: Profile, direction: str, o: Option, lead: str) -> str:
        t = o.trip
        heads = " → ".join(t.heads)
        if direction == "office":
            return (f"{lead} home {fmt_t(o.leave)}\n"
                    f"  🚗 {mins(o.drive)} min → {station_name(o.station)}, 🚶 {mins(p.park_walk)} min to platform\n"
                    f"  🚆 {fmt_t(t.depart)} → {station_name(p.office_station)} {fmt_t(t.arrive)} ({heads})\n"
                    f"  🏢 Office ~{fmt_t(o.arrive)}")
        return (f"{lead} office {fmt_t(o.leave)}\n"
                f"  🚆 {station_name(t.orig)} {fmt_t(t.depart)} → {station_name(o.station)} {fmt_t(t.arrive)} ({heads})\n"
                f"  🚗 {mins(o.drive)} min drive → home ~{fmt_t(o.arrive)}")

    def _line(self, direction: str, o: Option) -> str:
        if direction == "office":
            return f"• Leave {fmt_t(o.leave)} → {o.station} {fmt_t(o.trip.depart)} train → office {fmt_t(o.arrive)}"
        return f"• Leave {fmt_t(o.leave)} → {fmt_t(o.trip.depart)} train → home ~{fmt_t(o.arrive)}"

    async def _live(self, o: Option) -> str | None:
        """Real-time departures at the boarding station when the train is close."""
        if o.trip.depart - self.now() > LIVE_WINDOW:
            return None
        try:
            s = await self.planner.bart.live_summary(o.trip.orig, o.trip.heads)
        except Exception as e:  # noqa: BLE001 — live data is optional
            log.warning("live: %s", e)
            return None
        return f"\n📡 Live at {station_name(o.trip.orig)} — {s}" if s else None

    # ---- time-to-leave alerts ----

    async def alert_tick(self, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Runs every minute. Only users inside one of their alert windows cost a BART lookup."""
        now = self.now()
        for chat, p in self.store.profiles():
            for direction, start, end in alerts.open_windows(p, now):
                try:
                    await self._alert(ctx, chat, p, direction, start, end, now)
                except Forbidden:
                    log.info("chat %s blocked the bot; turning its alerts off", chat)
                    st = self.store.load(chat)
                    st.alerts_on = False
                    self.store.save(chat, st)
                except Exception:
                    log.exception("alert %s for chat %s", direction, chat)

    async def _alert(self, ctx: ContextTypes.DEFAULT_TYPE, chat: int, p: Profile, direction: str,
                     start: datetime, end: datetime, now: datetime) -> None:
        st = self.store.today(chat, now.date())
        if not st.alerts_on or direction in st.done:
            return
        if direction == "office":
            opts, _ = await self.planner.to_office(p, now, 4)
        else:
            opts = await self.planner.to_home(p, now, self._car(chat, p), 4)
        st = self.store.today(chat, now.date())  # re-read: a button press may have landed while planning
        if direction in st.done:
            return
        o = alerts.due(direction, opts, now, start, end, p.lead, set(st.alerted))
        if not o:
            return
        left = mins(o.leave - now)
        title = f"⏰ Leave {'home' if direction == 'office' else 'office'} " + (f"in {left} min" if left > 0 else "now")
        go = f"go|office|{o.station}" if direction == "office" else "go|home"
        await ctx.bot.send_message(
            chat, f"{title}\n\n{self._detail(p, direction, o, '👉 Leave')}",
            reply_markup=keyboard(("🚗 I'm leaving", go), ("🔕 Not today", f"skip|{direction}")))
        st.alerted.append(alerts.key(direction, o))
        self.store.save(chat, st)


def _done_note(action: str, direction: str, station: str = "") -> str:
    if action == "skip":
        return f"🔕 OK, no more {'morning' if direction == 'office' else 'evening'} alerts today."
    if direction == "office" and station:
        return f"✅ Have a good trip! No more morning alerts today. Car at {station_name(station)}."
    return "✅ Safe travels! No more alerts for this trip today."
