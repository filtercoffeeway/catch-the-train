"""A user's commute settings, and parsers for the answers that fill them in."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import time, timedelta

from .timeparse import mins, parse_clock

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MAX_WINDOW = timedelta(hours=4)
# Settings the setup wizard doesn't ask about; editable later in /settings.
DEFAULTS = {"buffer": 3, "lead": 10}


@dataclass(frozen=True)
class Profile:
    home_stations: tuple[str, ...]  # stations you can drive to and park at
    office_station: str
    drive: dict[str, timedelta]  # home -> each home station
    park_walk: timedelta  # parking lot -> platform
    office_walk: timedelta  # office <-> platform
    buffer: timedelta  # slack for parking, fare gates, etc.
    days: frozenset[int]  # commute days (Mon=0): alerts fire on these
    morning: tuple[time, time]  # window of leave-home times to alert for
    evening: tuple[time, time]  # window of leave-office times to alert for
    lead: timedelta  # how long before a leave-by time to alert

    def to_json(self) -> dict:
        return {
            "home": list(self.home_stations), "office": self.office_station,
            "drive": {s: mins(d) for s, d in self.drive.items()},
            "park_walk": mins(self.park_walk), "office_walk": mins(self.office_walk), "buffer": mins(self.buffer),
            "days": sorted(self.days),
            "morning": [t.strftime("%H:%M") for t in self.morning],
            "evening": [t.strftime("%H:%M") for t in self.evening],
            "lead": mins(self.lead),
        }

    @classmethod
    def from_json(cls, d: dict) -> Profile:
        d = {**DEFAULTS, **d}
        m = lambda k: timedelta(minutes=d[k])  # noqa: E731
        window = lambda k: (time.fromisoformat(d[k][0]), time.fromisoformat(d[k][1]))  # noqa: E731
        return cls(
            home_stations=tuple(d["home"]), office_station=d["office"],
            drive={s: timedelta(minutes=v) for s, v in d["drive"].items()},
            park_walk=m("park_walk"), office_walk=m("office_walk"), buffer=m("buffer"),
            days=frozenset(d["days"]), morning=window("morning"), evening=window("evening"), lead=m("lead"),
        )


def parse_minutes(s: str, hi: int = 120) -> int:
    m = re.fullmatch(r"(\d{1,3})\s*(m|min|mins|minutes)?", s.strip().lower())
    if not m or int(m[1]) > hi:
        raise ValueError(f"Send a number of minutes from 0 to {hi}, like 10.")
    return int(m[1])


def parse_days(s: str) -> list[int]:
    """'tue', 'tue,thu', 'mon-fri' or 'weekdays' -> weekday numbers (Mon=0)."""
    s = s.lower().replace(" ", "").replace("weekdays", "mon-fri")
    days: set[int] = set()
    for part in s.split(","):
        ends = [d[:3] for d in part.split("-")]
        if not 1 <= len(ends) <= 2 or any(d not in DAY_NAMES for d in ends):
            raise ValueError("Send days like tue, tue,thu or mon-fri.")
        a, b = DAY_NAMES.index(ends[0]), DAY_NAMES.index(ends[-1])
        if b < a:
            raise ValueError("Send day ranges in order, like mon-fri.")
        days.update(range(a, b + 1))
    return sorted(days)


def parse_window(s: str, pm_if_bare: bool) -> list[str]:
    """'7:30-9:30' -> ['07:30', '09:30']; with pm_if_bare, '5-6:30' -> ['17:00', '18:30']."""
    # Phone keyboards send all sorts of dashes (– — ‑ −); treat them all as "-".
    s = "".join("-" if unicodedata.category(c) == "Pd" or c in "−~" else c for c in s)
    parts = re.split(r"\s*(?:-|\bto\b)\s*", s.strip().lower())
    clocks = [parse_clock(p, pm_if_bare) for p in parts]
    if len(clocks) != 2 or None in clocks:
        raise ValueError("Send a time range like 7:30-9:30.")
    start, end = (time(h, m) for h, m in clocks)
    span = timedelta(hours=end.hour - start.hour, minutes=end.minute - start.minute)
    if span <= timedelta(0):
        raise ValueError("The range has to end after it starts.")
    if span > MAX_WINDOW:
        raise ValueError(f"Keep the range to {mins(MAX_WINDOW) // 60} hours or less.")
    return [start.strftime("%H:%M"), end.strftime("%H:%M")]


def fmt_days(days) -> str:
    days = sorted(days)
    if days == list(range(5)):
        return "Mon–Fri"
    return ", ".join(DAY_NAMES[d].capitalize() for d in days)
