import pytest

from catchthetrain.stations import find, parse_stations


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
    with pytest.raises(ValueError, match="could be"):
        parse_stations("berkeley")
    with pytest.raises(ValueError, match="don't know"):
        parse_stations("gotham")
