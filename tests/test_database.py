import pytest

from db.database import Database, UserProfile


@pytest.fixture
async def db(tmp_path):
    path = tmp_path / "test.db"
    d = Database(str(path))
    await d.init()
    return d


def _profile(user_id=1, **overrides) -> UserProfile:
    base = dict(
        user_id=user_id,
        name=f"user{user_id}",
        twitter_id=f"@u{user_id}",
        birth_month=4,
        birth_day=15,
        start_year=2020,
        start_month=4,
        start_day=15,
    )
    base.update(overrides)
    return UserProfile(**base)


async def test_upsert_and_get(db):
    await db.upsert_profile(_profile(1))
    p = await db.get_profile(1)
    assert p is not None
    assert p.name == "user1"
    assert p.twitter_id == "@u1"

    # update
    await db.upsert_profile(_profile(1, name="renamed"))
    p2 = await db.get_profile(1)
    assert p2.name == "renamed"


async def test_get_missing(db):
    assert await db.get_profile(999) is None


async def test_find_birthdays_and_anniversaries(db):
    await db.upsert_profile(_profile(1, birth_month=4, birth_day=15))
    await db.upsert_profile(_profile(2, birth_month=4, birth_day=15))
    await db.upsert_profile(_profile(3, birth_month=5, birth_day=1))

    rows = await db.find_birthdays(4, 15)
    assert {r.user_id for r in rows} == {1, 2}

    rows = await db.find_anniversaries(4, 15)
    assert {r.user_id for r in rows} == {1, 2, 3}


async def test_set_get_channel(db):
    await db.set_channel(100, 200)
    assert await db.get_channel(100) == 200
    await db.set_channel(100, 201)
    assert await db.get_channel(100) == 201
    assert await db.all_channels() == [(100, 201, False)]


async def test_notify_absent(db):
    # 未設定サーバーへの設定はエラー
    with pytest.raises(LookupError):
        await db.set_notify_absent(1, True)

    await db.set_channel(1, 2)
    assert await db.get_notify_absent(1) is False  # default
    await db.set_notify_absent(1, True)
    assert await db.get_notify_absent(1) is True
    assert await db.all_channels() == [(1, 2, True)]
    await db.set_notify_absent(1, False)
    assert await db.get_notify_absent(1) is False


async def test_permission_crud(db):
    await db.set_permission(1, "list", "role", [10, 20, 30])
    p = await db.get_permission(1, "list")
    assert p is not None
    assert p.mode == "role"
    assert p.role_ids == [10, 20, 30]

    await db.set_permission(1, "list", "everyone", [])
    p = await db.get_permission(1, "list")
    assert p.mode == "everyone"
    assert p.role_ids == []

    with pytest.raises(ValueError):
        await db.set_permission(1, "list", "invalid")


async def test_list_profiles_filter(db):
    for i in (1, 2, 3):
        await db.upsert_profile(_profile(i))
    all_p = await db.list_profiles()
    assert len(all_p) == 3
    only12 = await db.list_profiles(user_ids=[1, 2])
    assert {p.user_id for p in only12} == {1, 2}
    assert await db.list_profiles(user_ids=[]) == []
