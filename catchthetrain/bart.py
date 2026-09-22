"""Small client for BART's Legacy API (schedules + real-time departures)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://api.bart.gov/api/"


class BartError(Exception):
    pass


@dataclass(frozen=True)
class Trip:
    orig: str
    dest: str
    depart: datetime
    arrive: datetime
    heads: list[str]  # train head station per leg; more than one means a transfer


def one_or_many(v: Any) -> list:
    """BART's XML->JSON output is an object for one element and a list for many."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _bart_clock(t: datetime) -> str:
    return f"{t.hour % 12 or 12}:{t.minute:02d}{'am' if t.hour < 12 else 'pm'}"


class Bart:
    def __init__(self, key: str, tz: tzinfo, http: httpx.AsyncClient):
        self.key, self.tz, self.http = key, tz, http

    async def _get(self, endpoint: str, params: dict) -> dict:
        r = await self.http.get(BASE_URL + endpoint, params={**params, "key": self.key, "json": "y"})
        if r.status_code != 200:
            raise BartError(f"BART {endpoint}: HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def _parse(self, date: str, clock: str) -> datetime:
        t = datetime.strptime(f"{date.strip()} {clock.strip()}", "%m/%d/%Y %I:%M %p")
        return t.replace(tzinfo=self.tz)

    async def depart(self, orig: str, dest: str, at: datetime, after: int = 4) -> list[Trip]:
        """Trips leaving orig at/after `at`, plus up to `after` later ones."""
        return await self._sched("depart", orig, dest, at, 0, after)

    async def arrive(self, orig: str, dest: str, at: datetime, before: int = 4) -> list[Trip]:
        """Trips arriving at dest by `at`, plus up to `before` earlier ones."""
        return await self._sched("arrive", orig, dest, at, before, 0)

    async def _sched(self, cmd: str, orig: str, dest: str, at: datetime, before: int, after: int) -> list[Trip]:
        at = at.astimezone(self.tz)
        data = await self._get("sched.aspx", {
            "cmd": cmd, "orig": orig, "dest": dest,
            "date": at.strftime("%m/%d/%Y"), "time": _bart_clock(at), "b": before, "a": after,
        })
        root = data.get("root", {})
        raw = one_or_many(root.get("schedule", {}).get("request", {}).get("trip"))
        if not raw:
            raise BartError(f"BART returned no trips {orig}→{dest} ({str(root.get('message', ''))[:200]})")
        trips = []
        for r in raw:
            try:
                dep = self._parse(r["@origTimeDate"], r["@origTimeMin"])
                arr = self._parse(r["@destTimeDate"], r["@destTimeMin"])
            except (KeyError, ValueError) as e:
                log.warning("skip trip, bad time: %s", e)
                continue
            heads = [leg.get("@trainHeadStation", "") for leg in one_or_many(r.get("leg"))]
            trips.append(Trip(orig, dest, dep, arr, heads))
        return trips

    async def live_summary(self, orig: str, direction: str, heads: list[str]) -> str:
        """One-line summary of real-time departures at orig ("n"/"s"), limited to matching trains."""
        data = await self._get("etd.aspx", {"cmd": "etd", "orig": orig, "dir": direction})
        parts = []
        for station in one_or_many(data.get("root", {}).get("station")):
            for etd in one_or_many(station.get("etd")):
                dest = etd.get("destination", "")
                if not _matches_head(dest, etd.get("abbreviation", ""), heads):
                    continue
                times = []
                for est in one_or_many(etd.get("estimate")):
                    m = est.get("minutes", "")
                    m = m if m == "Leaving" else f"{m}m"
                    delay = int(est.get("delay") or 0)
                    if delay >= 60:
                        m += f" (+{delay // 60} late)"
                    times.append(m)
                if times:
                    parts.append(f"{dest}: {', '.join(times)}")
        return " | ".join(parts)


def _matches_head(dest: str, abbr: str, heads: list[str]) -> bool:
    if not heads:
        return True
    d = dest.lower()
    for h in heads:
        h = h.strip().lower()
        if h and (h == abbr.lower() or h in d or d in h):
            return True
    return False
