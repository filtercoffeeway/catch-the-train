import pytest

from catchthetrain.profile import Profile
from catchthetrain.settings import FIELDS, SETUP_STEPS


def fill(answers: dict, draft: dict | None = None) -> dict:
    draft = dict(draft or {})
    for key, text in answers.items():
        draft.update(FIELDS[key].parse(text, draft))
    return draft


def test_setup_answers_build_a_profile():
    answers = dict(zip(SETUP_STEPS, [
        "Union City, Warm Springs", "civic center", "12, 18", "5", "10", "tue", "9:30-10:30", "3-4:30"]))
    p = Profile.from_json(fill(answers))
    assert p.home_stations == ("UCTY", "WARM") and p.office_station == "CIVC"
    assert {s: d.seconds // 60 for s, d in p.drive.items()} == {"UCTY": 12, "WARM": 18}
    assert p.days == {1} and p.evening[0].hour == 15


def test_office_cannot_be_a_home_station():
    with pytest.raises(ValueError):
        fill({"home": "UCTY", "office": "Union City"})


def test_drive_needs_one_number_per_home_station():
    with pytest.raises(ValueError, match="2 numbers"):
        fill({"home": "UCTY, WARM", "drive": "12"})


def test_changing_home_stations_asks_for_drive_again():
    d = fill({"home": "UCTY", "drive": "12"})
    assert FIELDS["drive"].known(d)
    d = fill({"home": "UCTY, WARM"}, d)
    assert not FIELDS["drive"].known(d)
