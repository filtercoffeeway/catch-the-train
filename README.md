# Catch The Train (@CatchTheTrainBot)

Telegram bot for drive + BART commuters. It tells you when to leave home (morning)
and the office (evening), and nudges you on your office days when it's time to go.
Anyone can message the bot, set up their own commute in chat, and get their own alerts.

Trains come from BART's Legacy API. Drive and walk times are the minutes each user
enters during setup.

## How it works
```
 Telegram  ◄── long polling (outbound HTTPS only) ──  bot process (Raspberry Pi / VM)
                                                        ├─ handlers: commands, buttons, setup wizard
                                                        ├─ alert job: every minute, per user
                                                        ├─ planner  ──► BART schedule + real-time API
                                                        └─ SQLite: one row per user (settings + today's state)
```
- **Polling, not webhooks**: the bot asks Telegram for new messages, so it needs no
  public IP, open port or TLS certificate.
- **Per-user settings** (`Profile`): home stations with a drive time for each, office
  station, walks, buffer, commute days, and morning/evening alert windows. Collected
  by a chat wizard and stored as JSON in SQLite.
- **Alerts cost nothing outside their windows**: the alert job runs every minute, but
  only users on a commute day and inside an alert window get a BART lookup. A user
  stops being checked for the rest of that window once they tap **I'm leaving** or
  **Not today**.

## Layout
```
catchthetrain/
  __main__.py   entry point: wires everything together
  config.py     bot-wide env config (token, BART key, DB path, user cap)
  profile.py    a user's commute settings + answer parsers
  settings.py   setup wizard questions and the /settings summary
  stations.py   BART station catalog, lookup by code or name
  bart.py       BART schedule + real-time departures client
  planner.py    leave-by calculations for both directions
  alerts.py     which alert windows are open, and when an alert is due
  state.py      SQLite store: profiles, car location, today's alert progress
  bot.py        commands, buttons, wizard, alert job, message formatting
tests/
deploy/         systemd unit
```

## Using the bot
Send `/start`. The bot asks for:
1. Home station(s): where you drive and park, up to 3 (e.g. `Union City, Warm Springs`)
2. Office station
3. Drive time from home to each home station
4. Walk from parking to the platform, and from the platform to the office
5. Commute days (`tue`, `tue,thu`, `mon-fri`)
6. Morning and evening alert windows (e.g. `7:30-9:30`, `5-6:30`)

Stations can be given by code or name (`civic center`, `CIVC`). Typos and ambiguous
names get a "Did you mean…?" reply with one-tap buttons.

| Command | Meaning |
|---|---|
| `/tooffice` | Buttons: **Next available** / **Next 4 options** — when to leave home |
| `/tooffice 9:45` | Must reach office by 9:45 |
| `/tohome` | Buttons: **Next available** / **Next 4 options** — when to leave the office |
| `/tohome 6:15` | Leaving the office at 6:15 PM |
| `/park UCTY` | Set where the car is parked |
| `/alerts` | Alert status; `/alerts off` / `/alerts on` |
| `/settings` | Show your commute; tap a setting to change it |
| `/setup` | Go through all the questions again |
| `/cancel` | Stop the setup questions without saving |
| `/forget` | Delete your data |

## Time-to-leave alerts
On your commute days, the bot sends **⏰ Leave home in N min** about the alert
lead time (default 10 min) before each leave-by time in your window:

- **Morning**: leave-home times inside your morning window.
- **Evening**: leave-office times inside your evening window, routed to the
  station where your car is parked.

Each alert has **🚗 I'm leaving** and **🔕 Not today** buttons. Either one stops
that direction's alerts for the day. If you ignore an alert, you get another one
for the next train. "I'm leaving" in the morning also records which station the
car is at, so evening plans route you back to it. If a user blocks the bot, their
alerts are turned off.

## How the math works
- **To office**: leave home = train departure − parking-to-platform walk − buffer − drive time.
  Options from each home station are compared, and ones beaten by another that lets
  you leave later for the same or earlier arrival are dropped.
- **To home**: leave office = train departure − office-to-platform walk − buffer;
  home ETA = train arrival + walk to car + drive time.

## Running it
1. **Telegram**: message @BotFather → `/newbot` → copy the token.
2. **BART** (optional): register your own key at api.bart.gov (defaults to the public key).
3. `cp .env.example .env`, set `TELEGRAM_TOKEN`, then `make venv && make run`.

| Env var | Default | Meaning |
|---|---|---|
| `TELEGRAM_TOKEN` | required | Bot token from @BotFather |
| `BART_KEY` | BART's public key | BART API key |
| `DB_PATH` | `catchthetrain.db` | SQLite file with all users' data |
| `MAX_USERS` | `50` | New sign-ups are refused beyond this many users |

Only run one copy per bot token: Telegram lets only one process poll at a time.

## Deploy (Raspberry Pi / Linux)
Currently runs on **bravo** as `catchthetrain.service` (see Deployment in CLAUDE.md).
```bash
deploy/deploy.sh bravo             # rerunnable: code, venv, unit, restart
deploy/deploy.sh bravo --seed-db   # first deploy only: also copy the local DB
```
| Piece | Location on the Pi |
|---|---|
| Code + venv | `/opt/catchthetrain` (owner: `catchthetrain` user) |
| Secrets | `/etc/catchthetrain/env` (mode 600, root; created from local `.env` once, never overwritten) |
| Database | `/var/lib/catchthetrain/catchthetrain.db` |

```bash
ssh bravo journalctl -u catchthetrain -f      # logs
ssh bravo sudo systemctl restart catchthetrain
ssh bravo sudo systemctl stop catchthetrain   # stop (do this before running the bot anywhere else)
```
### Shipping a code change
From the repo root on the Mac:
```bash
make test && deploy/deploy.sh bravo
```
Tests run first; the deploy is skipped if any fail. It syncs the code, reinstalls into the venv,
restarts the service and prints `active` / `enabled`. Secrets and the database are left alone.

Then check it on the Pi and try it in Telegram (tests don't cover Telegram or BART):
```bash
ssh bravo journalctl -u catchthetrain -n 30 --no-pager   # startup errors
ssh bravo journalctl -u catchthetrain -f                 # follow live while testing
```
- Don't `make run` locally while bravo's copy is running (two pollers on one token give `409 Conflict`).
  To test locally, `ssh bravo sudo systemctl stop catchthetrain` first, then redeploy afterwards.
- New or changed env var: edit `/etc/catchthetrain/env` on the Pi (`ssh bravo sudo nano /etc/catchthetrain/env`),
  then `ssh bravo sudo systemctl restart catchthetrain`. The deploy script never rewrites that file.

Back up `catchthetrain.db` to keep users' settings.
