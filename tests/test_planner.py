import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from catchthetrain import alerts
from catchthetrain.bart import Trip
from catchthetrain.planner import Planner
from catchthetrain.profile import Profile

TZ = ZoneInfo("America/Los_Angeles")
MIN = timedelta(minutes=1)
NOW = datetime(2026, 9, 21, 9, 30, tzinfo=TZ)


P = Profile(
    home_stations=("UCTY",), office_station="CIVC", drive={"UCTY": 20 * MIN},
    park_walk=7 * MIN, office_walk=10 * MIN, buffer=3 * MIN, days=frozenset({1}),  # Tuesdays
    morning=(time(9, 30), time(10, 30)), evening=(time(15), time(16, 30)), lead=10 * MIN,
)


def hm(h, m):
    return NOW.replace(hour=h, minute=m)


class FakeBart:
    def __init__(self):
        self.trips = {
            "UCTY": [(hm(9, 58), hm(10, 30)), (hm(10, 13), hm(10, 45)), (hm(10, 28), hm(11, 0))],
            "CIVC": [(hm(15, 5), hm(15, 40)), (hm(15, 20), hm(15, 55))],
        }

    async def depart(self, orig, dest, at, after=4):
        return [Trip(orig, dest, d, a, ["Richmond"]) for d, a in self.trips[orig] if d >= at]


def planner():
    return Planner(FakeBart())


def test_to_office_leave_time_math():
    opts, errs = asyncio.run(planner().to_office(P, NOW, 4))
    assert errs == []
    # 9:58 train: 9:58 - 3 buffer - 7 walk - 20 drive = 9:28, already past at 9:30.
    assert [(o.station, o.leave, o.arrive) for o in opts] == [
        ("UCTY", hm(9, 43), hm(10, 55)), ("UCTY", hm(9, 58), hm(11, 10))]


def test_to_office_skips_trains_you_cannot_make():
    opts, _ = asyncio.run(planner().to_office(P, hm(9, 45), 1))
    assert opts[0].trip.depart == hm(10, 28)


def test_to_home():
    opts = asyncio.run(planner().to_home(P, hm(14, 50), "UCTY", 4))
    # Need to be on the platform by 14:50 + 10 walk + 3 buffer = 15:03 → 15:05 train; home = 15:40 + 7 + 20.
    assert [(o.leave, o.arrive) for o in opts] == [(hm(14, 52), hm(16, 7)), (hm(15, 7), hm(16, 22))]


def test_alert_due_only_within_lead_and_once():
    opts, _ = asyncio.run(planner().to_office(P, hm(9, 20), 4))
    start, end, lead = hm(9, 30), hm(10, 30), 10 * MIN
    # Leave-bys are 9:28 (before the window), 9:43, 9:58. At 9:30 the 9:43 one is 13 min away → not yet.
    assert alerts.due("office", opts, hm(9, 30), start, end, lead, set()) is None
    o = alerts.due("office", opts, hm(9, 34), start, end, lead, set())
    assert o.leave == hm(9, 43)
    assert alerts.due("office", opts, hm(9, 35), start, end, lead, {alerts.key("office", o)}) is None
    # Missed it: at 9:49 the 9:58 option is next and gets its own alert.
    assert alerts.due("office", opts, hm(9, 49), start, end, lead, {alerts.key("office", o)}).leave == hm(9, 58)


def test_alert_ignores_options_outside_window():
    opts, _ = asyncio.run(planner().to_office(P, hm(9, 20), 4))
    assert alerts.due("office", opts, hm(9, 34), hm(9, 45), hm(10, 30), 10 * MIN, set()) is None


def test_alert_windows_only_on_commute_days_and_near_the_window():
    tue = NOW + timedelta(days=1)
    at = lambda day, h, m: day.replace(hour=h, minute=m)  # noqa: E731
    assert alerts.open_windows(P, at(NOW, 9, 45)) == []  # Monday: not a commute day
    assert alerts.open_windows(P, at(tue, 9, 19)) == []  # before 9:30 minus the 10 min lead
    assert [w[0] for w in alerts.open_windows(P, at(tue, 9, 20))] == ["office"]
    assert alerts.open_windows(P, at(tue, 12, 0)) == []
    assert [w[0] for w in alerts.open_windows(P, at(tue, 16, 30))] == ["home"]
    assert alerts.open_windows(P, at(tue, 16, 31)) == []
