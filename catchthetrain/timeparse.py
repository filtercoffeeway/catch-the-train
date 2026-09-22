"""Clock parsing and formatting helpers."""
from __future__ import annotations

from datetime import datetime, timedelta


def parse_clock(s: str, pm_if_bare: bool = False) -> tuple[int, int] | None:
    """Parse 9:45, 945, 9:45am, 18:10, 6:10pm, 6pm into (hour, minute).

    If pm_if_bare, a bare hour 1-11 is treated as PM (for evening times).
    """
    s = s.strip().lower()
    suffix = ""
    if s.endswith(("am", "pm")):
        suffix, s = s[-2:], s[:-2].strip()
    if ":" in s:
        hs, ms = s.split(":", 1)
    elif len(s) >= 3:
        hs, ms = s[:-2], s[-2:]
    else:
        hs, ms = s, "0"
    if not (hs.isdigit() and ms.isdigit()):
        return None
    h, m = int(hs), int(ms)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    if suffix == "pm" and h < 12:
        h += 12
    elif suffix == "am" and h == 12:
        h = 0
    elif not suffix and pm_if_bare and 1 <= h <= 11:
        h += 12
    return h, m


def at(day: datetime, h: int, m: int) -> datetime:
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def next_weekday(d: datetime) -> datetime:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def fmt_t(t: datetime) -> str:
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def mins(d: timedelta) -> int:
    return round(d.total_seconds() / 60)
