"""Persists small bits of state: where the car is parked and today's alert progress."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import date

log = logging.getLogger(__name__)


@dataclass
class State:
    station: str = ""
    alerts_on: bool = True
    day: str = ""  # the date `done` and `alerted` belong to
    done: list[str] = field(default_factory=list)  # directions acknowledged or skipped today
    alerted: list[str] = field(default_factory=list)  # alert keys already sent today


class Store:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> State:
        try:
            with open(self.path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return State()
        known = {f.name for f in fields(State)}
        return State(**{k: v for k, v in raw.items() if k in known})

    def today(self, day: date) -> State:
        """Load state, resetting the per-day fields if it belongs to another day."""
        st = self.load()
        if st.day != day.isoformat():
            st.day, st.done, st.alerted = day.isoformat(), [], []
        return st

    def save(self, st: State) -> None:
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(asdict(st), f)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except OSError as e:
            log.error("save state: %s", e)
