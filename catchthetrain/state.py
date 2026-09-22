"""Per-user storage in SQLite: commute settings plus where the car is and today's alert progress."""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field, fields
from datetime import date

from .profile import Profile

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    chat_id    INTEGER PRIMARY KEY,
    profile    TEXT,                         -- Profile JSON; NULL until setup finishes
    state      TEXT NOT NULL DEFAULT '{}',   -- State JSON
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


@dataclass
class State:
    station: str = ""  # where the car is parked
    alerts_on: bool = True
    day: str = ""  # the date `done` and `alerted` belong to
    done: list[str] = field(default_factory=list)  # directions acknowledged or skipped today
    alerted: list[str] = field(default_factory=list)  # alert keys already sent today


class Store:
    def __init__(self, path: str):
        # Autocommit: every write is a single statement. The bot runs on one event loop thread.
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(SCHEMA)

    # ---- profiles ----

    def profile(self, chat: int) -> Profile | None:
        row = self.db.execute("SELECT profile FROM users WHERE chat_id = ?", (chat,)).fetchone()
        return _profile(chat, row[0]) if row else None

    def profiles(self) -> list[tuple[int, Profile]]:
        rows = self.db.execute("SELECT chat_id, profile FROM users WHERE profile IS NOT NULL").fetchall()
        return [(chat, p) for chat, raw in rows if (p := _profile(chat, raw))]

    def save_profile(self, chat: int, p: Profile) -> None:
        self.db.execute(
            "INSERT INTO users (chat_id, profile) VALUES (?, ?) "
            "ON CONFLICT (chat_id) DO UPDATE SET profile = excluded.profile",
            (chat, json.dumps(p.to_json())))

    def user_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM users WHERE profile IS NOT NULL").fetchone()[0]

    def delete(self, chat: int) -> None:
        self.db.execute("DELETE FROM users WHERE chat_id = ?", (chat,))

    # ---- state ----

    def load(self, chat: int) -> State:
        row = self.db.execute("SELECT state FROM users WHERE chat_id = ?", (chat,)).fetchone()
        try:
            raw = json.loads(row[0]) if row else {}
        except ValueError:
            raw = {}
        known = {f.name for f in fields(State)}
        return State(**{k: v for k, v in raw.items() if k in known})

    def today(self, chat: int, day: date) -> State:
        """Load state, resetting the per-day fields if it belongs to another day."""
        st = self.load(chat)
        if st.day != day.isoformat():
            st.day, st.done, st.alerted = day.isoformat(), [], []
        return st

    def save(self, chat: int, st: State) -> None:
        self.db.execute(
            "INSERT INTO users (chat_id, state) VALUES (?, ?) "
            "ON CONFLICT (chat_id) DO UPDATE SET state = excluded.state",
            (chat, json.dumps(asdict(st))))


def _profile(chat: int, raw: str | None) -> Profile | None:
    if raw is None:
        return None
    try:
        return Profile.from_json(json.loads(raw))
    except (ValueError, KeyError, TypeError) as e:
        log.error("chat %s: bad profile: %s", chat, e)
        return None
