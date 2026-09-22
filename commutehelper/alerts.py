"""Decides when a time-to-leave alert is due."""
from __future__ import annotations

from datetime import datetime, timedelta

from .planner import Option


def key(direction: str, o: Option) -> str:
    return f"{direction}|{o.station}|{o.trip.depart:%H:%M}"


def due(direction: str, opts: list[Option], now: datetime, start: datetime, end: datetime,
        lead: timedelta, already: set[str]) -> Option | None:
    """The next catchable option leaving within [start, end], if its leave time is within `lead`
    and it hasn't been alerted yet. Missing a train rolls over to the next one."""
    upcoming = sorted((o for o in opts if o.leave >= now and start <= o.leave <= end), key=lambda o: o.leave)
    if not upcoming:
        return None
    o = upcoming[0]
    if o.leave - now > lead or key(direction, o) in already:
        return None
    return o
