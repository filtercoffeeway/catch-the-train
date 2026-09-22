from datetime import date

from catchthetrain.profile import Profile
from catchthetrain.state import Store
from tests.test_profile import DRAFT


def test_profiles_and_state_are_per_user(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    p = Profile.from_json(DRAFT)
    store.save_profile(1, p)
    store.save_profile(2, p)
    assert store.profile(1) == p and store.profile(3) is None
    assert [c for c, _ in store.profiles()] == [1, 2] and store.user_count() == 2

    st = store.today(1, date(2026, 9, 22))
    st.done.append("office")
    st.station = "WARM"
    store.save(1, st)
    assert store.today(1, date(2026, 9, 22)).done == ["office"]
    assert store.today(2, date(2026, 9, 22)).done == []
    # A new day clears today's progress but remembers where the car is.
    next_day = store.today(1, date(2026, 9, 23))
    assert next_day.done == [] and next_day.station == "WARM"

    store.delete(1)
    assert store.profile(1) is None and store.user_count() == 1


def test_state_before_setup_does_not_count_as_a_user(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.save(5, store.load(5))
    assert store.user_count() == 0 and store.profiles() == []
