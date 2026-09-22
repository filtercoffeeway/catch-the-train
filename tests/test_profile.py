import pytest

from catchthetrain.profile import Profile, fmt_days, parse_days, parse_minutes, parse_window

DRAFT = {
    "home": ["UCTY", "WARM"], "office": "CIVC", "drive": {"UCTY": 12, "WARM": 18},
    "park_walk": 5, "office_walk": 10, "days": [1], "morning": ["09:30", "10:30"], "evening": ["15:00", "16:30"],
}


def test_profile_json_round_trip_fills_defaults():
    p = Profile.from_json(DRAFT)
    assert p.buffer.total_seconds() == 180 and p.lead.total_seconds() == 600
    assert p.to_json() == {**DRAFT, "buffer": 3, "lead": 10}


def test_parse_days():
    assert parse_days("tue") == [1]
    assert parse_days("Tue, Thu") == [1, 3]
    assert parse_days("mon-wed,fri") == [0, 1, 2, 4]
    assert parse_days("weekdays") == [0, 1, 2, 3, 4]
    assert parse_days("tuesday") == [1]
    for bad in ("", "tues-", "fri-mon", "xyz", "mon--fri"):
        with pytest.raises(ValueError):
            parse_days(bad)
    assert fmt_days([0, 1, 2, 3, 4]) == "Mon–Fri" and fmt_days([1, 3]) == "Tue, Thu"


def test_parse_window():
    assert parse_window("7:30-9:30", False) == ["07:30", "09:30"]
    assert parse_window("5 to 6:30", True) == ["17:00", "18:30"]
    assert parse_window("11:30am – 1pm", True) == ["11:30", "13:00"]
    assert parse_window("9.30-10.30", False) == ["09:30", "10:30"]
    assert parse_window("3-4.30", True) == ["15:00", "16:30"]
    for dash in "‐‑‒–—−~":
        assert parse_window(f"3:00{dash}4:30", True) == ["15:00", "16:30"], dash
    for bad in ("9:30", "10-9", "6-11", "soon-later"):
        with pytest.raises(ValueError):
            parse_window(bad, False)


def test_parse_minutes():
    assert parse_minutes("7") == 7 and parse_minutes("15 min") == 15 and parse_minutes("0") == 0
    for bad in ("", "-3", "ten", "500"):
        with pytest.raises(ValueError):
            parse_minutes(bad)
