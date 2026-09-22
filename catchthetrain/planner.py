"""Combines train schedules with a user's drive and walk times into leave-by times."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from .bart import Bart, Trip
from .profile import Profile


@dataclass(frozen=True)
class Option:
    station: str  # station where the car is / will be parked
    trip: Trip
    drive: timedelta
    leave: datetime  # leave home (to office) or leave office (to home)
    arrive: datetime  # at office (to office) or at home (to home)


def drop_dominated(opts: list[Option]) -> list[Option]:
    """Remove options beaten by another that leaves no earlier and arrives no later."""
    def beats(p: Option, o: Option) -> bool:
        return p.leave >= o.leave and p.arrive <= o.arrive and (p.leave, p.arrive) != (o.leave, o.arrive)
    return [o for o in opts if not any(beats(p, o) for p in opts)]


class Planner:
    def __init__(self, bart: Bart):
        self.bart = bart

    async def to_office(self, p: Profile, now: datetime, count: int) -> tuple[list[Option], list[str]]:
        """The next `count` ways to the office you can still make, soonest leave time first."""
        results = await asyncio.gather(
            *(self._office_from(p, st, now) for st in p.home_stations), return_exceptions=True)
        opts, errs = _collect(results)
        opts = sorted(drop_dominated(opts), key=lambda o: o.leave)
        return opts[:count], errs

    async def _office_from(self, p: Profile, st: str, now: datetime) -> list[Option]:
        drive = p.drive[st]
        trips = await self.bart.depart(st, p.office_station, now + drive + p.park_walk + p.buffer)
        opts = []
        for t in trips:
            leave = t.depart - p.park_walk - p.buffer - drive
            if leave >= now:
                opts.append(Option(st, t, drive, leave, t.arrive + p.office_walk))
        return opts

    async def to_office_by(self, p: Profile, deadline: datetime, now: datetime) -> tuple[list[Option], list[str]]:
        """Ways to reach the office in the 30 minutes before `deadline`, latest leave time first."""
        results = await asyncio.gather(
            *(self._office_by_from(p, st, deadline, now) for st in p.home_stations), return_exceptions=True)
        opts, errs = _collect(results)
        return sorted(drop_dominated(opts), key=lambda o: o.leave, reverse=True), errs

    async def _office_by_from(self, p: Profile, st: str, deadline: datetime, now: datetime) -> list[Option]:
        earliest = deadline - timedelta(minutes=30)
        drive = p.drive[st]
        trips = await self.bart.arrive(st, p.office_station, deadline - p.office_walk)
        opts = []
        for t in trips:
            at_office = t.arrive + p.office_walk
            if not earliest <= at_office <= deadline:
                continue
            leave = t.depart - p.park_walk - p.buffer - drive
            if leave >= now:
                opts.append(Option(st, t, drive, leave, at_office))
        return opts

    async def to_home(self, p: Profile, leave_at: datetime, st: str, count: int) -> list[Option]:
        """The next `count` trains home after leave_at, with the car parked at station st."""
        at_platform = leave_at + p.office_walk + p.buffer
        trips = await self.bart.depart(p.office_station, st, at_platform)
        trips = [t for t in trips if t.depart >= at_platform][:count]
        drive = p.drive[st]
        return [
            Option(st, t, drive, t.depart - p.office_walk - p.buffer, t.arrive + p.park_walk + drive)
            for t in trips
        ]


def _collect(results: list) -> tuple[list[Option], list[str]]:
    opts, errs = [], []
    for r in results:
        if isinstance(r, BaseException):
            errs.append(str(r))
        else:
            opts.extend(r)
    return opts, errs
