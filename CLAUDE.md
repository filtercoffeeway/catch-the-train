# CatchTheTrain

Telegram bot: time-to-leave alerts for a drive + BART commute. See README.md for layout and env vars.

## Deployment
- Runs on **bravo** (Raspberry Pi) as systemd service `catchthetrain`, deployed 2026-09-23. Fleet conventions: `/Users/mahesh/Documents/projects/PiFleet/PI_FLEET.md`.
- Redeploy: `deploy/deploy.sh bravo`. Logs: `ssh bravo journalctl -u catchthetrain`.
- One poller per bot token: stop the Pi service before running the bot locally.
- Secrets in `/etc/catchthetrain/env` on the Pi; DB in `/var/lib/catchthetrain/`.
