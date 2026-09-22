"""Combines train schedules and drive times into leave-by times."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from .bart import Bart, Trip
from .config import Config, station_address
from .maps import Maps


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
    def __init__(self, cfg: Config, bart: Bart, maps: Maps):
        self.cfg, self.bart, self.maps = cfg, bart, maps

    async def to_office(self, now: datetime, count: int) -> tuple[list[Option], list[str]]:
        """The next `count` ways to the office you can still make, soonest leave time first."""
        results = await asyncio.gather(
            *(self._office_from(st, now) for st in self.cfg.home_stations), return_exceptions=True)
        opts, errs = _collect(results)
        opts = sorted(drop_dominated(opts), key=lambda o: o.leave)
        return opts[:count], errs

    async def _office_from(self, st: str, now: datetime) -> list[Option]:
        c = self.cfg
        drive_now = await self.maps.drive_time(c.home_addr, station_address(st), now)
        trips = await self.bart.depart(st, c.office_station, now + drive_now + c.park_walk + c.buffer)
        opts = []
        for t in trips:
            at_lot = t.depart - c.park_walk - c.buffer
            drive = await self.maps.drive_time(c.home_addr, station_address(st), at_lot - drive_now)
            leave = at_lot - drive
            if leave >= now:
                opts.append(Option(st, t, drive, leave, t.arrive + c.office_walk))
        return opts

    async def to_office_by(self, deadline: datetime, now: datetime) -> tuple[list[Option], list[str]]:
        """Ways to reach the office in the 30 minutes before `deadline`, latest leave time first."""
        results = await asyncio.gather(
            *(self._office_by_from(st, deadline, now) for st in self.cfg.home_stations), return_exceptions=True)
        opts, errs = _collect(results)
        return sorted(drop_dominated(opts), key=lambda o: o.leave, reverse=True), errs

    async def _office_by_from(self, st: str, deadline: datetime, now: datetime) -> list[Option]:
        c = self.cfg
        earliest = deadline - timedelta(minutes=30)
        trips = await self.bart.arrive(st, c.office_station, deadline - c.office_walk)
        opts = []
        for t in trips:
            at_office = t.arrive + c.office_walk
            if not earliest <= at_office <= deadline:
                continue
            at_lot = t.depart - c.park_walk - c.buffer
            drive = await self.maps.drive_time(c.home_addr, station_address(st), at_lot - timedelta(minutes=15))
            leave = at_lot - drive
            if leave >= now:
                opts.append(Option(st, t, drive, leave, at_office))
        return opts

    async def to_home(self, leave_at: datetime, st: str, count: int) -> list[Option]:
        """The next `count` trains home after leave_at, with the car parked at station st."""
        c = self.cfg
        at_platform = leave_at + c.office_walk + c.buffer
        trips = await self.bart.depart(c.office_station, st, at_platform)
        trips = [t for t in trips if t.depart >= at_platform][:count]
        drives = await asyncio.gather(
            *(self.maps.drive_time(station_address(st), c.home_addr, t.arrive + c.park_walk) for t in trips))
        return [
            Option(st, t, d, t.depart - c.office_walk - c.buffer, t.arrive + c.park_walk + d)
            for t, d in zip(trips, drives)
        ]


def _collect(results: list) -> tuple[list[Option], list[str]]:
    opts, errs = [], []
    for r in results:
        if isinstance(r, BaseException):
            errs.append(str(r))
        else:
            opts.extend(r)
    return opts, errs
