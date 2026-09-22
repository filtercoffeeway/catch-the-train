import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from catchthetrain.bart import Bart, one_or_many

TZ = ZoneInfo("America/Los_Angeles")


def test_one_or_many():
    assert one_or_many(None) == []
    assert one_or_many({"a": 1}) == [{"a": 1}]
    assert one_or_many([1, 2]) == [1, 2]


def test_sched_parses_single_and_multi_leg_trips():
    payload = {"root": {"schedule": {"request": {"trip": [
        {"@origTimeMin": "9:52 AM", "@origTimeDate": "09/21/2026 ", "@destTimeMin": "10:25 AM",
         "@destTimeDate": "09/21/2026 ", "leg": {"@trainHeadStation": "Richmond"}},
        {"@origTimeMin": "11:58 PM", "@origTimeDate": "09/21/2026 ", "@destTimeMin": "12:31 AM",
         "@destTimeDate": "09/22/2026 ", "leg": [{"@trainHeadStation": "Daly City"}, {"@trainHeadStation": "SFO"}]},
    ]}}}}
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(req.url.params)
        return httpx.Response(200, json=payload)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await Bart("k", TZ, http).depart("UCTY", "CIVC", datetime(2026, 9, 21, 9, 40, tzinfo=TZ))

    trips = asyncio.run(run())
    assert seen["time"] == "9:40am" and seen["date"] == "09/21/2026" and seen["cmd"] == "depart"
    assert trips[0].depart == datetime(2026, 9, 21, 9, 52, tzinfo=TZ)
    assert trips[0].heads == ["Richmond"]
    assert trips[1].arrive == datetime(2026, 9, 22, 0, 31, tzinfo=TZ)
    assert trips[1].heads == ["Daly City", "SFO"]
