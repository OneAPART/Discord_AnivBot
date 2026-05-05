import pytest

from db.database import Database, UserProfile


@pytest.fixture
async def db(tmp_path):
    path = tmp_path / "test.db"
    d = Database(str(path))
    await d.init()
    return d


def _profile(guild_id=1, user_id=1, **overrides) -> UserProfile:
    base = dict(
        guild_id=guild_id,
        user_id=user_id,
        name=f"u{user_id}",
        twitter_id=f"@u{user_id}",
        birth_month=4,
        birth_day=15,
        start_year=2020,
        start_month=4,
        start_day=15,
    )
    base.update(overrides)
    return UserProfile(**base)


async def test_upsert_and_get_per_guild(db):
    await db.upsert_profile(_profile(guild_id=1, user_id=10, name="g1"))
    await db.upsert_profile(_profile(guild_id=2, user_id=10, name="g2"))

    p1 = await db.get_profile(1, 10)
    p2 = await db.get_profile(2, 10)
    assert p1.name == "g1"
    assert p2.name == "g2"
    # 別サーバーには存在しない
    assert await db.get_profile(3, 10) is None


async def test_update_does_not_leak_between_guilds(db):
    await db.upsert_profile(_profile(guild_id=1, user_id=10, name="orig1"))
    await db.upsert_profile(_profile(guild_id=2, user_id=10, name="orig2"))
    await db.upsert_profile(_profile(guild_id=1, user_id=10, name="updated1"))
    assert (await db.get_profile(1, 10)).name == "updated1"
    assert (await db.get_profile(2, 10)).name == "orig2"


async def test_delete(db):
    await db.upsert_profile(_profile(guild_id=1, user_id=10))
    assert await db.delete_profile(1, 10) is True
    assert await db.get_profile(1, 10) is None
    assert await db.delete_profile(1, 10) is False


async def test_find_birthday_per_guild(db):
    await db.upsert_profile(_profile(guild_id=1, user_id=1, birth_month=5, birth_day=5))
    await db.upsert_profile(_profile(guild_id=2, user_id=2, birth_month=5, birth_day=5))
    rows = await db.find_birthdays(1, 5, 5)
    assert {r.user_id for r in rows} == {1}
    rows = await db.find_birthdays(2, 5, 5)
    assert {r.user_id for r in rows} == {2}
    rows = await db.find_birthdays(3, 5, 5)
    assert rows == []


async def test_list_profiles_per_guild(db):
    for uid in (1, 2, 3):
        await db.upsert_profile(_profile(guild_id=1, user_id=uid))
    await db.upsert_profile(_profile(guild_id=2, user_id=99))

    g1 = await db.list_profiles(1)
    assert {p.user_id for p in g1} == {1, 2, 3}

    g1_filter = await db.list_profiles(1, user_ids=[1, 2, 99])
    assert {p.user_id for p in g1_filter} == {1, 2}  # 99 は別ギルド

    assert await db.list_profiles(1, user_ids=[]) == []


async def test_set_get_channel(db):
    await db.set_channel(100, 200)
    assert await db.get_channel(100) == 200
    assert await db.all_channels() == [(100, 200, False, "twitter")]


async def test_avatar_source(db):
    # channel 未設定なら LookupError
    with pytest.raises(LookupError):
        await db.set_avatar_source(1, "discord")
    await db.set_channel(1, 2)
    assert await db.get_avatar_source(1) == "twitter"  # 既定
    await db.set_avatar_source(1, "discord")
    assert await db.get_avatar_source(1) == "discord"
    assert await db.all_channels() == [(1, 2, False, "discord")]
    with pytest.raises(ValueError):
        await db.set_avatar_source(1, "invalid")


async def test_notify_absent(db):
    with pytest.raises(LookupError):
        await db.set_notify_absent(1, True)
    await db.set_channel(1, 2)
    assert await db.get_notify_absent(1) is False
    await db.set_notify_absent(1, True)
    assert await db.get_notify_absent(1) is True


async def test_permission_crud(db):
    await db.set_permission(1, "list", "role", [10, 20, 30])
    p = await db.get_permission(1, "list")
    assert p.mode == "role"
    assert p.role_ids == [10, 20, 30]

    await db.set_permission(1, "list", "everyone", [])
    p = await db.get_permission(1, "list")
    assert p.mode == "everyone"
    assert p.role_ids == []

    with pytest.raises(ValueError):
        await db.set_permission(1, "list", "invalid")
