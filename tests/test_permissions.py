from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from db.database import Database
from utils.permissions import PermissionDenied, is_allowed


@pytest.fixture
async def db(tmp_path):
    d = Database(str(tmp_path / "p.db"))
    await d.init()
    return d


def _interaction(*, guild_id=1, owner_id=100, user_id=200, role_ids=()):
    user = SimpleNamespace(
        id=user_id,
        roles=[SimpleNamespace(id=r) for r in role_ids],
    )
    guild = SimpleNamespace(id=guild_id, owner_id=owner_id)
    interaction = SimpleNamespace(guild=guild, user=user)
    # is_allowed 内で isinstance(user, Member) を見るためモンキーパッチ
    return interaction


@pytest.fixture(autouse=True)
def patch_member_check(monkeypatch):
    # is_allowed の isinstance(Member) を常に True にする
    import utils.permissions as perm

    monkeypatch.setattr(perm.discord, "Member", SimpleNamespace, raising=False)


async def test_default_owner_only(db):
    """既定はオーナーのみ。"""
    # オーナーは OK
    interaction = _interaction(owner_id=1, user_id=1)
    assert await is_allowed(db, interaction, "list") is True
    # 一般ユーザーは拒否
    interaction = _interaction(owner_id=1, user_id=2)
    with pytest.raises(PermissionDenied):
        await is_allowed(db, interaction, "list")


async def test_explicit_everyone(db):
    await db.set_permission(1, "list", "everyone")
    interaction = _interaction(owner_id=1, user_id=2)
    assert await is_allowed(db, interaction, "list") is True


async def test_owner_mode_allow(db):
    await db.set_permission(1, "list", "owner")
    interaction = _interaction(owner_id=999, user_id=999)
    assert await is_allowed(db, interaction, "list") is True


async def test_owner_mode_deny(db):
    await db.set_permission(1, "list", "owner")
    interaction = _interaction(owner_id=999, user_id=1)
    with pytest.raises(PermissionDenied):
        await is_allowed(db, interaction, "list")


async def test_role_mode_allow(db):
    await db.set_permission(1, "list", "role", [10, 20])
    interaction = _interaction(role_ids=(20,))
    assert await is_allowed(db, interaction, "list") is True


async def test_role_mode_deny(db):
    await db.set_permission(1, "list", "role", [10, 20])
    interaction = _interaction(role_ids=(99,))
    with pytest.raises(PermissionDenied):
        await is_allowed(db, interaction, "list")


async def test_role_mode_no_roles_configured(db):
    await db.set_permission(1, "list", "role", [])
    interaction = _interaction(role_ids=(10,))
    with pytest.raises(PermissionDenied):
        await is_allowed(db, interaction, "list")


async def test_dm_denied(db):
    interaction = SimpleNamespace(guild=None, user=SimpleNamespace(id=1, roles=[]))
    with pytest.raises(PermissionDenied):
        await is_allowed(db, interaction, "list")
