"""Clock parsing and formatting helpers."""
from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, time, timedelta


def parse_clock(s: str, pm_if_bare: bool = False) -> tuple[int, int] | None:
    """Parse 9:45, 9.45, 945, 9:45am, 18:10, 6:10pm, 6pm into (hour, minute).

    If pm_if_bare, a bare hour 1-11 is treated as PM (for evening times).
    """
    s = s.strip().lower().replace(".", ":")  # 9.45 is common on phone keyboards
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


def next_day(d: datetime, days: Collection[int]) -> datetime:
    """The first day after d that is one of `days` (Mon=0); the next day if `days` is empty."""
    for i in range(1, 8):
        if (d + timedelta(days=i)).weekday() in days:
            return d + timedelta(days=i)
    return d + timedelta(days=1)


def fmt_t(t: datetime | time) -> str:
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def mins(d: timedelta) -> int:
    return round(d.total_seconds() / 60)
