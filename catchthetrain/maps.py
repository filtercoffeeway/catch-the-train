"""Google Routes API client for traffic-aware drive times."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
# Alerts re-plan every minute; caching keeps Routes API usage (and cost) low.
CACHE_TTL_S = 600
BUCKET_S = 900


class MapsError(Exception):
    pass


class FixedDrive:
    """Constant drive time, used instead of the Routes API for now."""

    def __init__(self, d: timedelta):
        self.d = d

    async def drive_time(self, frm: str, to: str, depart: datetime) -> timedelta:
        return self.d


class Maps:
    def __init__(self, key: str, http: httpx.AsyncClient):
        self.key, self.http = key, http
        self._cache: dict[tuple, tuple[float, timedelta]] = {}

    async def drive_time(self, frm: str, to: str, depart: datetime) -> timedelta:
        """Traffic-aware driving duration when leaving at `depart` (past times use current traffic)."""
        future = depart > datetime.now(timezone.utc) + timedelta(minutes=1)
        key = (frm, to, int(depart.timestamp()) // BUCKET_S if future else None)
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[1]

        body: dict = {
            "origin": {"address": frm},
            "destination": {"address": to},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        }
        if future:
            body["departureTime"] = depart.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = await self.http.post(ROUTES_URL, json=body, headers={
            "X-Goog-Api-Key": self.key,
            "X-Goog-FieldMask": "routes.duration",
        })
        if r.status_code != 200:
            raise MapsError(f"Routes API: HTTP {r.status_code}: {r.text[:300]}")
        routes = r.json().get("routes") or []
        if not routes:
            raise MapsError(f"Routes API: no route ({r.text[:200]})")
        d = timedelta(seconds=int(routes[0]["duration"].rstrip("s")))
        self._cache[key] = (time.monotonic(), d)
        return d
