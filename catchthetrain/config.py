"""Bot-wide settings loaded from environment variables. Each user's commute lives in their Profile."""
from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Config:
    telegram_token: str
    bart_key: str
    db_path: str
    max_users: int  # new sign-ups are refused beyond this
    tz: ZoneInfo


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, "").strip() or default


def _required(key: str) -> str:
    v = env(key)
    if not v:
        raise SystemExit(f"missing required env var {key}")
    return v


def load() -> Config:
    try:
        max_users = int(env("MAX_USERS", "50"))
    except ValueError:
        raise SystemExit("MAX_USERS must be an integer") from None
    return Config(
        telegram_token=_required("TELEGRAM_TOKEN"),
        bart_key=env("BART_KEY", "MW9S-E7SL-26DU-VV8V"),  # BART's public key; register your own
        db_path=env("DB_PATH", "catchthetrain.db"),
        max_users=max_users,
        tz=ZoneInfo("America/Los_Angeles"),  # all of BART is in Pacific time
    )
