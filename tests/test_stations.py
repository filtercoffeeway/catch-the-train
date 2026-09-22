import pytest

from catchthetrain.stations import StationError, close_matches, find, parse_stations


def test_find_by_code_name_part_and_alias():
    assert find("ucty") == ["UCTY"]
    assert find("Union City") == ["UCTY"]
    assert find("civic center") == ["CIVC"]
    assert find("South Fremont") == ["WARM"]
    assert find("fremont") == ["FRMT"]  # exact name beats "Warm Springs/South Fremont"
    assert find("Montgomery Street") == ["MONT"]
    assert find("powell") == ["POWL"]
    assert find("SFO") == ["SFIA"]
    assert sorted(find("berkeley")) == ["DBRK", "NBRK"]
    assert find("nowhere") == []


def test_parse_stations():
    assert parse_stations("Union City, WARM") == ["UCTY", "WARM"]
    assert parse_stations("ucty warm") == ["UCTY", "WARM"]
    assert parse_stations("UCTY and ucty") == ["UCTY"]
    with pytest.raises(ValueError, match="don't know"):
        parse_stations("gotham")


def test_typos_suggest_the_station():
    assert close_matches("civc center") == ["CIVC"]
    assert close_matches("uniom city") == ["UCTY"]
    assert sorted(close_matches("berkly")) == ["DBRK", "NBRK"]
    assert close_matches("gotham") == []


def fixes(text: str) -> list[tuple[str, str]]:
    with pytest.raises(StationError) as e:
        parse_stations(text)
    return e.value.fixes


def test_bad_answers_come_with_corrected_answers():
    assert fixes("civc center") == [("Civic Center/UN Plaza", "CIVC")]
    # The rest of the answer is kept, so tapping the fix sends a complete, valid answer.
    assert fixes("union city, warm sprngs") == [("Warm Springs/South Fremont", "UCTY, WARM")]
    assert fixes("uniom city, warm sprngs") == [("Union City", "UCTY, WARM")]  # both typos fixed in one tap
    assert parse_stations("UCTY, WARM") == ["UCTY", "WARM"]
    assert sorted(fixes("berkeley")) == [("Downtown Berkeley", "DBRK"), ("North Berkeley", "NBRK")]
    assert fixes("gotham") == []
