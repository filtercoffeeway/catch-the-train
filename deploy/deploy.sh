#!/usr/bin/env bash
# Deploy CatchTheTrain to a Pi over ssh. Rerunnable.
#   deploy/deploy.sh bravo            code, venv, unit, restart
#   deploy/deploy.sh bravo --seed-db  also copy the local catchthetrain.db (only if the Pi has none)
# /etc/catchthetrain/env is created from the local .env on first run and never overwritten.
set -euo pipefail

HOST=${1:?usage: deploy.sh <host> [--seed-db]}
SEED_DB=${2:-}
cd "$(dirname "$0")/.."

ssh "$HOST" 'id catchthetrain >/dev/null 2>&1 || sudo useradd --system --home-dir /var/lib/catchthetrain --shell /usr/sbin/nologin catchthetrain
  sudo install -d -o catchthetrain -g catchthetrain /opt/catchthetrain
  sudo install -d -o catchthetrain -g catchthetrain -m 750 /var/lib/catchthetrain'

rsync -a --delete --rsync-path='sudo rsync' \
  --exclude .venv --exclude .git --exclude .idea --exclude .env --exclude '*.db*' \
  --exclude '*.egg-info' --exclude __pycache__ --exclude .pytest_cache --exclude '*state.json*' \
  ./ "$HOST":/opt/catchthetrain/
ssh "$HOST" 'sudo chown -R catchthetrain:catchthetrain /opt/catchthetrain'

if ! ssh "$HOST" 'sudo test -f /etc/catchthetrain/env'; then
  echo "creating /etc/catchthetrain/env from local .env"
  grep -E '^(TELEGRAM_TOKEN|BART_KEY|MAX_USERS)=' .env |
    ssh "$HOST" 'sudo install -d -m 755 /etc/catchthetrain && sudo install -m 600 -o root -g root /dev/stdin /etc/catchthetrain/env'
fi

if [ "$SEED_DB" = "--seed-db" ]; then
  if ssh "$HOST" 'sudo test -e /var/lib/catchthetrain/catchthetrain.db'; then
    echo "Pi already has a database; not overwriting" >&2
  else
    tmp=$(mktemp -d)
    sqlite3 catchthetrain.db ".backup $tmp/catchthetrain.db"
    rsync -a --rsync-path='sudo rsync' "$tmp/catchthetrain.db" "$HOST":/var/lib/catchthetrain/
    ssh "$HOST" 'sudo chown catchthetrain:catchthetrain /var/lib/catchthetrain/catchthetrain.db'
    rm -r "$tmp"
  fi
fi

ssh "$HOST" 'cd /opt/catchthetrain
  sudo -u catchthetrain python3 -m venv .venv
  sudo -u catchthetrain .venv/bin/pip install -q --upgrade .
  sudo cp deploy/catchthetrain.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable catchthetrain
  sudo systemctl restart catchthetrain
  sleep 3
  systemctl is-active catchthetrain; systemctl is-enabled catchthetrain'
