from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest
from discord import app_commands

from cogs.config_cog import ConfigCog
from cogs.profile_cog import ProfileCog
from db.database import Database, UserProfile
from ui.modals import ProfileModal
from utils.permissions import PermissionDenied


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "profiles.db"))
    await database.init()
    return database


def _member(user_id=200, role_ids=(), *, bot=False):
    return Mock(
        spec=discord.Member,
        id=user_id,
        roles=[SimpleNamespace(id=role_id) for role_id in role_ids],
        bot=bot,
        display_name=f"user{user_id}",
    )


def _interaction(db, user=None):
    return SimpleNamespace(
        _state=Mock(),
        guild_id=1,
        guild=SimpleNamespace(id=1, owner_id=100, members=[]),
        user=user if user is not None else _member(),
        client=SimpleNamespace(db=db),
        response=SimpleNamespace(
            send_modal=AsyncMock(),
            send_message=AsyncMock(),
            is_done=Mock(return_value=False),
        ),
    )


def _profile(user_id=200, guild_id=1, name="original"):
    return UserProfile(
        guild_id=guild_id,
        user_id=user_id,
        name=name,
        twitter_id=None,
        birth_month=None,
        birth_day=None,
        start_year=None,
        start_month=None,
        start_day=None,
    )


async def _invoke(app_command, interaction, **options):
    namespace = app_commands.Namespace(interaction, {}, [])
    for name, value in options.items():
        setattr(namespace, name, value)
    await app_command._invoke_with_namespace(interaction, namespace)


def _fill_modal(modal):
    modal.name_input._value = " updated "
    modal.twitter_input._value = "@example"
    modal.birthday_input._value = "04/15"
    modal.start_input._value = "2020/04/15"


@pytest.mark.parametrize("command_name", ["profile", "profile_delete"])
@pytest.mark.parametrize("target_kind", ["omitted", "self", "other"])
@pytest.mark.parametrize(
    "mode,actor_id,role_ids,command_allowed",
    [
        (None, 200, (), True),
        (None, 100, (), True),
        ("owner", 200, (), False),
        ("owner", 100, (), True),
        ("everyone", 200, (), True),
        ("everyone", 100, (), True),
        ("role", 200, (20,), True),
        ("role", 200, (99,), False),
        ("role", 100, (20,), True),
        ("role", 100, (), False),
    ],
)
async def test_profile_command_permissions(
    db, monkeypatch, command_name, target_kind, mode, actor_id, role_ids,
    command_allowed,
):
    if mode is not None:
        await db.set_permission(1, "profile", mode, [10, 20] if mode == "role" else [])
    permission_before = await db.get_permission(1, "profile")
    interaction = _interaction(db, _member(actor_id, role_ids))
    target_id = 300 if target_kind == "other" else actor_id
    options = {} if target_kind == "omitted" else {"user": _member(target_id)}
    original = _profile(target_id)
    other_guild = _profile(target_id, guild_id=2, name="other guild")
    await db.upsert_profile(original)
    await db.upsert_profile(other_guild)
    monkeypatch.setattr(db, "upsert_profile", AsyncMock(wraps=db.upsert_profile))
    monkeypatch.setattr(db, "delete_profile", AsyncMock(wraps=db.delete_profile))
    cog = ProfileCog(interaction.client, db)
    command = getattr(cog, command_name)

    if not command_allowed or (target_kind == "other" and actor_id != 100):
        with pytest.raises(PermissionDenied):
            await _invoke(command, interaction, **options)
        interaction.response.send_modal.assert_not_awaited()
        interaction.response.send_message.assert_not_awaited()
        db.upsert_profile.assert_not_awaited()
        db.delete_profile.assert_not_awaited()
        assert await db.get_profile(1, target_id) == original
    elif command_name == "profile":
        await _invoke(command, interaction, **options)
        interaction.response.send_modal.assert_awaited_once()
        modal = interaction.response.send_modal.await_args.args[0]
        assert isinstance(modal, ProfileModal)
        assert modal.target_user_id == target_id
        assert modal.name_input.default == original.name
        _fill_modal(modal)
        await modal.on_submit(interaction)
        modal.stop()
        db.upsert_profile.assert_awaited_once()
        saved = await db.get_profile(1, target_id)
        assert saved.name == "updated"
        assert saved.twitter_id == "@example"
        assert (saved.birth_month, saved.birth_day) == (4, 15)
        assert (saved.start_year, saved.start_month, saved.start_day) == (2020, 4, 15)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
    else:
        await _invoke(command, interaction, **options)
        db.delete_profile.assert_awaited_once_with(1, target_id)
        assert await db.get_profile(1, target_id) is None
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
        if target_kind != "other":
            assert interaction.response.send_message.await_args.args[0] == (
                ":wastebasket: このサーバーのプロフィールを削除しました。"
            )

    assert await db.get_profile(2, target_id) == other_guild
    assert await db.get_permission(1, "profile") == permission_before


@pytest.mark.parametrize("explicit_self", [False, True])
async def test_default_self_registration_and_edit(db, explicit_self):
    interaction = _interaction(db)
    cog = ProfileCog(interaction.client, db)
    options = {"user": _member()} if explicit_self else {}
    for name in ("first", "edited"):
        await _invoke(cog.profile, interaction, **options)
        modal = interaction.response.send_modal.await_args.args[0]
        modal.name_input._value = name
        await modal.on_submit(interaction)
        modal.stop()
        assert await db.get_profile(1, 200) == _profile(name=name)
    assert await db.get_permission(1, "profile") is None


@pytest.mark.parametrize("command_name", ["profile", "profile_delete"])
@pytest.mark.parametrize("invalid_context", ["dm", "non_member"])
async def test_profile_commands_reject_invalid_context(db, command_name, invalid_context):
    interaction = _interaction(db)
    if invalid_context == "dm":
        interaction.guild = None
    else:
        interaction.user = Mock(spec=discord.User, id=200)
    cog = ProfileCog(interaction.client, db)
    with pytest.raises(PermissionDenied):
        await _invoke(getattr(cog, command_name), interaction)
    interaction.response.send_modal.assert_not_awaited()
    assert await db.list_profiles(1) == []


async def test_profile_rejects_bot_target(db):
    interaction = _interaction(db, _member(100))
    cog = ProfileCog(interaction.client, db)
    await _invoke(cog.profile, interaction, user=_member(300, bot=True))
    interaction.response.send_modal.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once_with(
        ":x: Bot のプロフィールは登録できません。", ephemeral=True
    )
    assert await db.get_profile(1, 300) is None


@pytest.mark.parametrize("command_name", ["show", "list_profiles"])
@pytest.mark.parametrize("actor_id", [100, 200])
async def test_read_commands_default_to_owner(db, command_name, actor_id):
    interaction = _interaction(db, _member(actor_id))
    cog = ProfileCog(interaction.client, db)
    command = getattr(cog, command_name)
    if actor_id == 100:
        await _invoke(command, interaction)
        interaction.response.send_message.assert_awaited_once()
    else:
        with pytest.raises(PermissionDenied):
            await _invoke(command, interaction)
        interaction.response.send_message.assert_not_awaited()


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    "change",
    ["mode", "allowed_roles", "member_roles", "ownership", "dm", "non_member"],
)
async def test_modal_rechecks_permissions_before_saving(db, monkeypatch, existing, change):
    actor_id = 100 if change == "ownership" else 200
    target_id = 300 if change == "ownership" else actor_id
    interaction = _interaction(db, _member(actor_id, (20,)))
    initial_mode = "role" if change in ("allowed_roles", "member_roles") else "everyone"
    await db.set_permission(1, "profile", initial_mode, [20])
    original = _profile(target_id) if existing else None
    if original is not None:
        await db.upsert_profile(original)
    cog = ProfileCog(interaction.client, db)
    await _invoke(cog.profile, interaction, user=_member(target_id))
    modal = interaction.response.send_modal.await_args.args[0]
    _fill_modal(modal)

    if change == "mode":
        await db.set_permission(1, "profile", "owner")
    elif change == "allowed_roles":
        await db.set_permission(1, "profile", "role", [99])
    elif change == "member_roles":
        interaction.user.roles = []
    elif change == "ownership":
        interaction.guild.owner_id = 999
    elif change == "dm":
        interaction.guild = None
    else:
        interaction.user = Mock(spec=discord.User, id=actor_id)

    monkeypatch.setattr(db, "upsert_profile", AsyncMock(wraps=db.upsert_profile))
    await modal.on_submit(interaction)
    modal.stop()
    db.upsert_profile.assert_not_awaited()
    assert await db.get_profile(1, target_id) == original
    interaction.response.send_message.assert_awaited_once()
    message = interaction.response.send_message.await_args
    assert message.kwargs["ephemeral"] is True
    assert message.args[0].startswith(":no_entry:")
    assert "予期しないエラー" not in message.args[0]


@pytest.mark.parametrize("mode", ["everyone", "role"])
async def test_modal_denies_non_owner_proxy_even_without_command(db, monkeypatch, mode):
    await db.set_permission(1, "profile", mode, [20])
    interaction = _interaction(db, _member(role_ids=(20,)))
    modal = ProfileModal(db, None, target_user_id=300)
    _fill_modal(modal)
    monkeypatch.setattr(db, "upsert_profile", AsyncMock(wraps=db.upsert_profile))
    await modal.on_submit(interaction)
    modal.stop()
    db.upsert_profile.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once_with(
        ":no_entry: 他のユーザーのプロフィールを登録・編集・削除できるのはサーバーオーナーのみです。",
        ephemeral=True,
    )


@pytest.mark.parametrize("target_user_id", [None, 200])
async def test_modal_default_self_target(db, target_user_id):
    interaction = _interaction(db)
    modal = ProfileModal(db, None, target_user_id=target_user_id)
    _fill_modal(modal)
    await modal.on_submit(interaction)
    modal.stop()
    assert (await db.get_profile(1, 200)).name == "updated"


@pytest.mark.parametrize(
    "field,value",
    [("twitter_input", "bad!"), ("birthday_input", "13/40"), ("start_input", "not-a-date")],
)
async def test_modal_validation_still_prevents_save(db, monkeypatch, field, value):
    interaction = _interaction(db)
    modal = ProfileModal(db, None)
    _fill_modal(modal)
    getattr(modal, field)._value = value
    monkeypatch.setattr(db, "upsert_profile", AsyncMock(wraps=db.upsert_profile))
    await modal.on_submit(interaction)
    modal.stop()
    db.upsert_profile.assert_not_awaited()
    message = interaction.response.send_message.await_args
    assert message.kwargs["ephemeral"] is True
    assert message.args[0].startswith(":warning: 入力エラー:")


@pytest.mark.parametrize("mode", [None, "owner", "everyone", "role"])
async def test_config_show_displays_effective_profile_default(db, mode):
    if mode is not None:
        await db.set_permission(1, "profile", mode, [10, 20] if mode == "role" else [])
    interaction = _interaction(db)
    cog = ConfigCog(interaction.client, db)
    await _invoke(cog.show_config, interaction)
    message = interaction.response.send_message.await_args
    assert message.kwargs["ephemeral"] is True
    embed = message.kwargs["embed"]
    permissions = next(field.value for field in embed.fields if field.name == "コマンド権限")
    profile_setting = (
        "**everyone** (既定)" if mode is None
        else "**role** (<@&10>, <@&20>)" if mode == "role"
        else f"**{mode}**"
    )
    assert f"`/profile` → {profile_setting}" in permissions
    assert "`/show` → **owner** (既定)" in permissions
    assert "`/list` → **owner** (既定)" in permissions
    assert "/profile_delete" in permissions
    assert "サーバーオーナー" in permissions
    permission = await db.get_permission(1, "profile")
    if mode is None:
        assert permission is None
    else:
        assert permission.mode == mode
        assert permission.role_ids == ([10, 20] if mode == "role" else [])


@pytest.mark.parametrize("mode", ["owner", "everyone", "role"])
async def test_config_profile_permission_explains_proxy_restriction(db, mode):
    interaction = _interaction(db)
    cog = ConfigCog(interaction.client, db)
    options = {"role1": Mock(spec=discord.Role, id=20)} if mode == "role" else {}
    await _invoke(
        cog.set_permission, interaction, command="profile", mode=mode, **options
    )
    permission = await db.get_permission(1, "profile")
    assert permission.mode == mode
    assert permission.role_ids == ([20] if mode == "role" else [])
    message = interaction.response.send_message.await_args
    assert message.kwargs["ephemeral"] is True
    assert "/profile_delete" in message.args[0]
    assert "他のユーザーの登録・編集・削除はサーバーオーナーのみ" in message.args[0]
