"""通知の集計ロジックを Discord 抜きで検証する。

`_send_to_channel` をモックに置き換えて、対象抽出と
配信回数だけを検証する。
"""
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


def _profile(uid, **kw):
    base = dict(
        user_id=uid, name=f"u{uid}", twitter_id=None,
        birth_month=4, birth_day=15,
        start_year=2020, start_month=4, start_day=15,
    )
    base.update(kw)
    return UserProfile(**base)


def _make_cog(db):
    """tasks.loop の自動起動を避けるため、__init__ をスキップして手で組み立てる。"""
    cog = AnniversaryCog.__new__(AnniversaryCog)
    cog.bot = SimpleNamespace()
    cog.db = db
    cog._send_to_channel = AsyncMock()  # type: ignore[attr-defined]
    return cog


async def test_run_for_date_no_target(db):
    cog = _make_cog(db)
    result = await cog.run_for_date(date(2026, 1, 1))
    assert result == {"birthdays": 0, "anniversaries": 0, "channels": 0}
    cog._send_to_channel.assert_not_called()


async def test_run_for_date_hits(db):
    await db.upsert_profile(_profile(1, birth_month=5, birth_day=5))
    await db.upsert_profile(_profile(2, start_year=2020, start_month=5, start_day=5))
    await db.set_channel(100, 999)
    await db.set_channel(101, 998)

    cog = _make_cog(db)
    result = await cog.run_for_date(date(2026, 5, 5))
    assert result["birthdays"] == 1
    assert result["anniversaries"] == 1
    assert result["channels"] == 2
    # 2 チャンネル分呼ばれる
    assert cog._send_to_channel.await_count == 2
    # notify_absent が kwargs で渡されている (既定 False)
    kwargs = cog._send_to_channel.await_args.kwargs
    assert kwargs.get("notify_absent") is False


async def test_anniversary_year_calc(db):
    """current_year - start_year が引数として正しく流れるか"""
    await db.upsert_profile(_profile(1, start_year=2018, start_month=5, start_day=5,
                                     birth_month=1, birth_day=1))  # 5/5 は誕生日にヒットしない
    await db.set_channel(1, 1)

    cog = _make_cog(db)
    result = await cog.run_for_date(date(2026, 5, 5))
    assert result["anniversaries"] == 1
    # 第3引数 (current_year) を確認
    args = cog._send_to_channel.await_args.args
    assert args[2] == 2026


async def test_notify_absent_passed_through(db):
    """DB の notify_absent 設定が send_to_channel に伝わること"""
    await db.upsert_profile(_profile(1, birth_month=5, birth_day=5))
    await db.set_channel(10, 100)
    await db.set_notify_absent(10, True)

    cog = _make_cog(db)
    await cog.run_for_date(date(2026, 5, 5))
    kwargs = cog._send_to_channel.await_args.kwargs
    assert kwargs.get("notify_absent") is True
