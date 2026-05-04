from db.database import UserProfile
from cogs.profile_cog import _sort_key


def _p(name, **kw):
    base = dict(
        user_id=1, name=name, twitter_id=None,
        birth_month=None, birth_day=None,
        start_year=None, start_month=None, start_day=None,
    )
    base.update(kw)
    return UserProfile(**base)


def test_sort_by_name():
    profiles = [_p("Charlie"), _p("alice"), _p("Bob")]
    profiles.sort(key=_sort_key("name"))
    assert [p.name for p in profiles] == ["alice", "Bob", "Charlie"]


def test_sort_by_birthday():
    profiles = [
        _p("a", birth_month=12, birth_day=1),
        _p("b", birth_month=1, birth_day=15),
        _p("c", birth_month=1, birth_day=1),
        _p("d"),  # 未設定は最後
    ]
    profiles.sort(key=_sort_key("birthday"))
    assert [p.name for p in profiles] == ["c", "b", "a", "d"]


def test_sort_by_anniversary():
    profiles = [
        _p("new", start_year=2023, start_month=1, start_day=1),
        _p("old", start_year=2010, start_month=6, start_day=1),
        _p("mid", start_year=2018, start_month=1, start_day=1),
    ]
    profiles.sort(key=_sort_key("anniversary"))
    assert [p.name for p in profiles] == ["old", "mid", "new"]
