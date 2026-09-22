from catchthetrain.timeparse import parse_clock


def test_parse_clock():
    cases = [
        ("9:45", False, (9, 45)), ("945", False, (9, 45)), ("6:10pm", False, (18, 10)),
        ("6:15", True, (18, 15)), ("18:10", True, (18, 10)), ("6pm", False, (18, 0)),
        ("12am", False, (0, 0)), ("3:00", True, (15, 0)),
    ]
    for s, pm, want in cases:
        assert parse_clock(s, pm) == want, s


def test_parse_clock_rejects_words():
    for s in ("tomorrow", "FRMT", "25:00", "9:75", ""):
        assert parse_clock(s) is None, s
