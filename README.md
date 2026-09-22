# Catch The Train (@CatchTheTrainBot)

Telegram bot that tells you when to leave home (morning) and the office
(evening) for a drive + BART commute, and nudges you on weekdays when it's
time to go. Trains come from BART's Legacy API; drive times come from Google's
traffic-aware Routes API (currently a fixed drive time set by `DRIVE_MIN` in `.env`, default 20 min).

## Layout
```
catchthetrain/
  __main__.py   entry point: wires everything together
  config.py     env-based config, station addresses/names
  bart.py       BART schedule + real-time departures client
  maps.py       Google Routes API drive-time client (cached)
  planner.py    leave-by calculations for both directions
  alerts.py     decides when a time-to-leave alert is due
  state.py      car location + today's alert progress (JSON file)
  bot.py        commands, buttons, alert job, message formatting
tests/
deploy/         systemd unit
```

## Setup
1. **Telegram**: message @BotFather → `/newbot` → copy the token.
2. **Google** (not needed while the drive time is fixed via `DRIVE_MIN`): enable **Routes API** in Cloud Console; create an API key restricted to it.
3. **BART** (optional): register your own key at api.bart.gov (defaults to the public key).
4. `cp .env.example .env` and fill it in, then `make venv && make run`.
5. Send `/chatid` to the bot, put the id in `TELEGRAM_CHAT_ID`, restart. The bot ignores all other chats.

## Commands
| Command | Meaning |
|---|---|
| `/tooffice` | Buttons: **Next available** / **Next 4 options** — when to leave home |
| `/tooffice 9:45` | Must reach office by 9:45 |
| `/tohome` | Buttons: **Next available** / **Next 4 options** — when to leave the office |
| `/tohome 6:15` | Leaving the office at 6:15 PM |
| `/park UCTY` | Set where the car is parked |
| `/alerts` | Alert status; `/alerts off` / `/alerts on` |

`/morning` and `/evening` still work as aliases.

## Time-to-leave alerts
On weekdays the bot checks every minute during the alert windows and sends
**⏰ Leave home in N min** about `ALERT_LEAD_MIN` before each leave-by time
that falls in the window:

- **Morning** (`ALERT_MORNING`, default 9:30–10:30): leave-home times.
- **Evening** (`ALERT_EVENING`, default 3:00–4:30 PM): leave-office times,
  routed to the station where your car is parked.

Each alert has **🚗 I'm leaving** and **🔕 Not today** buttons; either one stops
that direction's alerts for the day. If you ignore an alert you get another one
for the next train. "I'm leaving" in the morning also records which station
the car is at, so evening plans route you back to it.

## How the math works
- **To office**: leave home = train departure − parking-to-platform walk − buffer − drive time
  (traffic predicted for that time). Options from every station in `HOME_STATIONS` are compared,
  and ones beaten by another that lets you leave later for the same or earlier arrival are dropped.
- **To home**: leave office = train departure − office-to-platform walk − buffer;
  home ETA = train arrival + walk to car + drive time.

## Deploy (Linux / OCI Ampere / Raspberry Pi)
```bash
rsync -a --exclude .venv --exclude .env ./ server:/opt/catchthetrain/
ssh server 'cd /opt/catchthetrain && python3 -m venv .venv && .venv/bin/pip install .'
scp .env server:/etc/catchthetrain.env
ssh server 'sudo cp /opt/catchthetrain/deploy/catchthetrain.service /etc/systemd/system/ \
  && sudo systemctl daemon-reload && sudo systemctl enable --now catchthetrain'
```
The bot polls Telegram, so no inbound ports need to be open.
