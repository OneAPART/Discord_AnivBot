"""通知集計ロジックのテスト（Discord 部分はモック）。"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from db.database import Database, UserProfile
from cogs.anniversary_cog import AnniversaryCog


@pytest.fixture
async def db(tmp_path):
    d = Database(str(tmp_path / "n.db"))
    await d.init()
    return d


def _profile(guild_id, user_id, **kw):
    base = dict(
        guild_id=guild_id, user_id=user_id, name=f"u{user_id}", twitter_id=None,
        birth_month=4, birth_day=15,
        start_year=2020, start_month=4, start_day=15,
    )
    base.update(kw)
    return UserProfile(**base)


def _make_cog(db):
    cog = AnniversaryCog.__new__(AnniversaryCog)
    cog.bot = SimpleNamespace()
    cog.db = db
    cog._send_to_channel = AsyncMock()
    return cog


async def test_no_channels(db):
    cog = _make_cog(db)
    result = await cog.run_for_date(date(2026, 5, 5))
    assert result == {"birthdays": 0, "anniversaries": 0, "channels": 0}


async def test_only_matching_guild_is_notified(db):
    """guild=1 にだけ対象がいる -> guild=2 のチャンネルには通知が飛ばない。"""
    await db.upsert_profile(_profile(1, 10, birth_month=5, birth_day=5))
    await db.upsert_profile(_profile(2, 20, birth_month=12, birth_day=31))
    await db.set_channel(1, 100)
    await db.set_channel(2, 200)

    cog = _make_cog(db)
    result = await cog.run_for_date(date(2026, 5, 5))
    assert result["birthdays"] == 1
    assert result["anniversaries"] == 0
    assert result["channels"] == 1
    cog._send_to_channel.assert_awaited_once()
    args = cog._send_to_channel.await_args.args
    assert args[0] == 1  # guild_id


async def test_isolated_per_guild(db):
    """同一ユーザー ID が複数ギルドに登録されていても、それぞれのギルドにのみ通知。"""
    await db.upsert_profile(_profile(1, 10, birth_month=5, birth_day=5))
    await db.upsert_profile(_profile(2, 10, birth_month=5, birth_day=5))
    await db.set_channel(1, 100)
    await db.set_channel(2, 200)

    cog = _make_cog(db)
    result = await cog.run_for_date(date(2026, 5, 5))
    assert result["birthdays"] == 2
    assert result["channels"] == 2
    assert cog._send_to_channel.await_count == 2


async def test_notify_absent_passed_through(db):
    await db.upsert_profile(_profile(10, 1, birth_month=5, birth_day=5))
    await db.set_channel(10, 100)
    await db.set_notify_absent(10, True)

    cog = _make_cog(db)
    await cog.run_for_date(date(2026, 5, 5))
    kwargs = cog._send_to_channel.await_args.kwargs
    assert kwargs.get("notify_absent") is True


async def test_anniversary_year_calc(db):
    await db.upsert_profile(_profile(1, 1, start_year=2018, start_month=5, start_day=5,
                                     birth_month=1, birth_day=1))
    await db.set_channel(1, 1)
    cog = _make_cog(db)
    result = await cog.run_for_date(date(2026, 5, 5))
    assert result["anniversaries"] == 1
    args = cog._send_to_channel.await_args.args
    assert args[2] == 2026  # current_year
