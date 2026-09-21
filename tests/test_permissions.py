from types import SimpleNamespace
from unittest.mock import Mock

import discord
import pytest

from db.database import Database
from utils.permissions import PermissionDenied, is_allowed


@pytest.fixture
async def db(tmp_path):
    d = Database(str(tmp_path / "p.db"))
    await d.init()
    return d


def _interaction(*, guild_id=1, owner_id=100, user_id=200, role_ids=()):
    user = Mock(
        spec=discord.Member,
        id=user_id,
        roles=[SimpleNamespace(id=r) for r in role_ids],
    )
    guild = SimpleNamespace(id=guild_id, owner_id=owner_id)
    interaction = SimpleNamespace(guild=guild, user=user)
    return interaction


@pytest.mark.parametrize("command_name", ["show", "list", "unknown"])
async def test_default_owner_only(db, command_name):
    """profile 以外の既定はオーナーのみ。"""
    # オーナーは OK
    interaction = _interaction(owner_id=1, user_id=1)
    assert await is_allowed(db, interaction, command_name) is True
    # 一般ユーザーは拒否
    interaction = _interaction(owner_id=1, user_id=2)
    with pytest.raises(PermissionDenied):
        await is_allowed(db, interaction, command_name)


async def test_default_profile_everyone(db):
    assert await is_allowed(db, _interaction(), "profile") is True
    assert await db.get_permission(1, "profile") is None


@pytest.mark.parametrize("command_name", ["profile", "list"])
async def test_explicit_everyone(db, command_name):
    await db.set_permission(1, command_name, "everyone")
    interaction = _interaction(owner_id=1, user_id=2)
    assert await is_allowed(db, interaction, command_name) is True


@pytest.mark.parametrize("command_name", ["profile", "list"])
async def test_owner_mode_allow(db, command_name):
    await db.set_permission(1, command_name, "owner")
    interaction = _interaction(owner_id=999, user_id=999)
    assert await is_allowed(db, interaction, command_name) is True


@pytest.mark.parametrize("command_name", ["profile", "list"])
async def test_owner_mode_deny(db, command_name):
    await db.set_permission(1, command_name, "owner")
    interaction = _interaction(owner_id=999, user_id=1)
    with pytest.raises(PermissionDenied):
        await is_allowed(db, interaction, command_name)


@pytest.mark.parametrize("command_name", ["profile", "list"])
async def test_role_mode_allow(db, command_name):
    await db.set_permission(1, command_name, "role", [10, 20])
    interaction = _interaction(role_ids=(20,))
    assert await is_allowed(db, interaction, command_name) is True


@pytest.mark.parametrize("command_name", ["profile", "list"])
async def test_role_mode_deny(db, command_name):
    await db.set_permission(1, command_name, "role", [10, 20])
    interaction = _interaction(role_ids=(99,))
    with pytest.raises(PermissionDenied):
        await is_allowed(db, interaction, command_name)


@pytest.mark.parametrize("command_name", ["profile", "list"])
async def test_role_mode_no_roles_configured(db, command_name):
    await db.set_permission(1, command_name, "role", [])
    interaction = _interaction(role_ids=(10,))
    with pytest.raises(PermissionDenied):
        await is_allowed(db, interaction, command_name)


@pytest.mark.parametrize("command_name", ["profile", "list"])
async def test_dm_denied(db, command_name):
    interaction = SimpleNamespace(guild=None, user=SimpleNamespace(id=1, roles=[]))
    with pytest.raises(PermissionDenied):
        await is_allowed(db, interaction, command_name)


async def test_non_member_denied(db):
    interaction = _interaction()
    interaction.user = Mock(spec=discord.User, id=200)
    with pytest.raises(PermissionDenied):
        await is_allowed(db, interaction, "profile")


async def test_profile_permissions_are_guild_specific(db):
    await db.set_permission(1, "profile", "owner")
    with pytest.raises(PermissionDenied):
        await is_allowed(db, _interaction(guild_id=1), "profile")
    assert await is_allowed(db, _interaction(guild_id=2), "profile") is True
