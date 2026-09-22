"""Settings loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time, timedelta
from zoneinfo import ZoneInfo

from .timeparse import parse_clock

# Parking-lot addresses for drive-time lookups. Override with STATION_ADDR_<CODE>.
_STATION_ADDR = {
    "UCTY": "Union City BART Station, 10 Union Square, Union City, CA 94587",
    "WARM": "Warm Springs/South Fremont BART Station, 45193 Warm Springs Blvd, Fremont, CA 94539",
}

_STATION_NAME = {
    "UCTY": "Union City", "WARM": "Warm Springs",
    "CIVC": "Civic Center", "POWL": "Powell St", "MONT": "Montgomery St", "EMBR": "Embarcadero",
}

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass(frozen=True)
class Config:
    telegram_token: str
    allowed_chat: int
    maps_key: str
    bart_key: str
    home_addr: str
    home_stations: list[str]
    office_station: str
    park_walk: timedelta  # parking lot -> platform
    office_walk: timedelta  # office <-> platform
    buffer: timedelta  # slack for parking, fare gates, etc.
    drive: timedelta  # home <-> station drive (fixed until the Routes API is enabled)
    alert_morning: tuple[time, time]  # window of leave-home times to alert for
    alert_evening: tuple[time, time]  # window of leave-office times to alert for
    alert_lead: timedelta  # how long before a leave-by time to alert
    alert_days: frozenset[int]  # weekdays (Mon=0) that get alerts
    state_file: str
    tz: ZoneInfo


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, "").strip() or default


def _required(key: str) -> str:
    v = env(key)
    if not v:
        raise SystemExit(f"missing required env var {key}")
    return v


def _minutes(key: str, default: int) -> timedelta:
    try:
        return timedelta(minutes=int(env(key, str(default))))
    except ValueError:
        raise SystemExit(f"{key} must be an integer (minutes)") from None


def _window(key: str, default: str, pm_if_bare: bool) -> tuple[time, time]:
    parts = env(key, default).split("-")
    clocks = [parse_clock(p, pm_if_bare) for p in parts]
    if len(clocks) != 2 or None in clocks:
        raise SystemExit(f"{key} must look like 9:30-10:30")
    (h1, m1), (h2, m2) = clocks
    return time(h1, m1), time(h2, m2)


def parse_days(s: str) -> frozenset[int] | None:
    """'tue', 'tue,thu' or 'mon-fri' -> weekday numbers (Mon=0); None if malformed."""
    days: set[int] = set()
    for part in s.lower().replace(" ", "").split(","):
        ends = [d[:3] for d in part.split("-")]
        if not 1 <= len(ends) <= 2 or any(d not in DAY_NAMES for d in ends):
            return None
        a, b = DAY_NAMES.index(ends[0]), DAY_NAMES.index(ends[-1])
        if b < a:
            return None
        days.update(range(a, b + 1))
    return frozenset(days)


def _days(key: str, default: str) -> frozenset[int]:
    days = parse_days(env(key, default))
    if days is None:
        raise SystemExit(f"{key} must look like tue or mon-fri or tue,thu")
    return days


def load() -> Config:
    return Config(
        telegram_token=_required("TELEGRAM_TOKEN"),
        allowed_chat=int(env("TELEGRAM_CHAT_ID", "0")),
        maps_key=env("GOOGLE_MAPS_KEY"),
        bart_key=env("BART_KEY", "MW9S-E7SL-26DU-VV8V"),  # BART's public key; register your own
        home_addr=env("HOME_ADDR"),
        home_stations=[s.strip() for s in env("HOME_STATIONS", "UCTY").upper().split(",") if s.strip()],
        office_station=env("OFFICE_STATION", "CIVC").upper(),
        park_walk=_minutes("PARK_WALK_MIN", 7),
        office_walk=_minutes("OFFICE_WALK_MIN", 10),
        buffer=_minutes("BUFFER_MIN", 3),
        drive=_minutes("DRIVE_MIN", 20),
        alert_morning=_window("ALERT_MORNING", "9:30-10:30", pm_if_bare=False),
        alert_evening=_window("ALERT_EVENING", "3:00-4:30", pm_if_bare=True),
        alert_lead=_minutes("ALERT_LEAD_MIN", 10),
        alert_days=_days("ALERT_DAYS", "mon-fri"),
        state_file=env("STATE_FILE", "catchthetrain-state.json"),
        tz=ZoneInfo("America/Los_Angeles"),
    )


def station_address(code: str) -> str:
    return env(f"STATION_ADDR_{code}") or _STATION_ADDR.get(code) or f"{code} BART Station, CA"


def station_name(code: str) -> str:
    return _STATION_NAME.get(code, code)


def known_parking_station(code: str) -> bool:
    return code in _STATION_ADDR or bool(env(f"STATION_ADDR_{code}"))
