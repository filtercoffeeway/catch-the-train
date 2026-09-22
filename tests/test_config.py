from catchthetrain.config import parse_days


def test_parse_days():
    cases = [
        ("tue", {1}), ("Tue,Thu", {1, 3}), ("mon-fri", {0, 1, 2, 3, 4}),
        ("tuesday", {1}), ("mon-wed, fri", {0, 1, 2, 4}),
    ]
    for s, want in cases:
        assert parse_days(s) == want, s


def test_parse_days_rejects_junk():
    for s in ("", "tues-", "fri-mon", "xyz", "mon--fri"):
        assert parse_days(s) is None, s
