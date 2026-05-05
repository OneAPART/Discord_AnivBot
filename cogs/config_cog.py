"""/config グループ（サーバー設定）。

すべて `manage_guild` 権限を持つメンバーのみ実行可能。
"""
from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from db.database import Database

# 権限制御の対象となるコマンド一覧
MANAGED_COMMANDS = ("profile", "show", "list")


class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db

    config = app_commands.Group(
        name="config",
        description="サーバー設定",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    # ----------------------------------------------------------
    # /config channel
    # ----------------------------------------------------------
    @config.command(
        name="channel", description="お祝いメッセージを投稿するチャンネルを設定します。"
    )
    @app_commands.describe(channel="通知を投稿するテキストチャンネル")
    async def set_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内で実行してください。", ephemeral=True
            )
            return

        perms = channel.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.embed_links):
            await interaction.response.send_message(
                f":x: {channel.mention} に送信する権限がありません。"
                "`メッセージを送信` と `埋め込みリンク` 権限を付与してください。",
                ephemeral=True,
            )
            return

        await self.db.set_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            f":white_check_mark: 通知チャンネルを {channel.mention} に設定しました。",
            ephemeral=True,
        )

    # ----------------------------------------------------------
    # /config permission
    # ----------------------------------------------------------
    @config.command(
        name="permission",
        description="コマンドごとの実行権限を設定します。",
    )
    @app_commands.describe(
        command="対象コマンド",
        mode="権限モード (owner/everyone/role)",
        role1="role モード時に許可するロール (1)",
        role2="role モード時に許可するロール (2)",
        role3="role モード時に許可するロール (3)",
    )
    async def set_permission(
        self,
        interaction: discord.Interaction,
        command: Literal["profile", "show", "list"],
        mode: Literal["owner", "everyone", "role"],
        role1: discord.Role | None = None,
        role2: discord.Role | None = None,
        role3: discord.Role | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内で実行してください。", ephemeral=True
            )
            return

        role_ids: list[int] = [r.id for r in (role1, role2, role3) if r is not None]

        if mode == "role" and not role_ids:
            await interaction.response.send_message(
                ":x: `role` モードでは、許可するロールを少なくとも 1 つ指定してください。",
                ephemeral=True,
            )
            return

        await self.db.set_permission(interaction.guild.id, command, mode, role_ids)

        if mode == "owner":
            detail = "サーバーオーナーのみ実行可"
        elif mode == "everyone":
            detail = "全員実行可"
        else:
            roles = ", ".join(f"<@&{rid}>" for rid in role_ids)
            detail = f"次のロールが実行可: {roles}"

        await interaction.response.send_message(
            f":white_check_mark: `/{command}` の権限を **{mode}** に設定しました。\n{detail}",
            ephemeral=True,
        )

    # ----------------------------------------------------------
    # /config absent
    # ----------------------------------------------------------
    @config.command(
        name="absent",
        description="サーバーに不在のユーザーへの通知可否を切り替えます。",
    )
    @app_commands.describe(
        notify="True: 不在ユーザーにも通知する / False: サーバー在籍メンバーのみ通知 (既定)"
    )
    async def set_absent(
        self,
        interaction: discord.Interaction,
        notify: bool,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内で実行してください。", ephemeral=True
            )
            return
        try:
            await self.db.set_notify_absent(interaction.guild.id, notify)
        except LookupError as e:
            await interaction.response.send_message(f":x: {e}", ephemeral=True)
            return

        if notify:
            msg = ":white_check_mark: 不在ユーザーへの通知を **有効** にしました。"
        else:
            msg = ":white_check_mark: 不在ユーザーへの通知を **無効** にしました。サーバー在籍メンバーのみ通知されます。"
        await interaction.response.send_message(msg, ephemeral=True)

    # ----------------------------------------------------------
    # /config avatar
    # ----------------------------------------------------------
    @config.command(
        name="avatar",
        description="通知カード右側に表示するアバターの取得元を設定します。",
    )
    @app_commands.describe(
        source="twitter: X を優先 / discord: Discord アバターを優先"
    )
    async def set_avatar(
        self,
        interaction: discord.Interaction,
        source: Literal["twitter", "discord"],
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内で実行してください。", ephemeral=True
            )
            return
        try:
            await self.db.set_avatar_source(interaction.guild.id, source)
        except LookupError as e:
            await interaction.response.send_message(f":x: {e}", ephemeral=True)
            return
        label = "X (Twitter) を優先" if source == "twitter" else "Discord アバターを優先"
        await interaction.response.send_message(
            f":white_check_mark: アバター表示を **{label}** に設定しました。\n"
            f" (未登録 / 取得不能時はもう一方にフォールバックします)",
            ephemeral=True,
        )

    # ----------------------------------------------------------
    # /config show
    # ----------------------------------------------------------
    @config.command(
        name="show",
        description="現在のサーバー設定を表示します。",
    )
    async def show_config(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内で実行してください。", ephemeral=True
            )
            return

        channel_id = await self.db.get_channel(interaction.guild.id)
        notify_absent = await self.db.get_notify_absent(interaction.guild.id)
        avatar_source = await self.db.get_avatar_source(interaction.guild.id)
        perms = await self.db.list_permissions(interaction.guild.id)
        perm_map = {p.command_name: p for p in perms}

        embed = discord.Embed(
            title="⚙️ サーバー設定",
            color=discord.Color.greyple(),
        )
        embed.add_field(
            name="通知チャンネル",
            value=(f"<#{channel_id}>" if channel_id else "*未設定*"),
            inline=False,
        )
        embed.add_field(
            name="不在ユーザーへの通知",
            value=("有効 (全員に通知)" if notify_absent else "無効 (サーバー在籍者のみ)"),
            inline=False,
        )
        embed.add_field(
            name="アバター取得元",
            value=(
                "X (Twitter) を優先"
                if avatar_source == "twitter"
                else "Discord アバターを優先"
            ),
            inline=False,
        )

        lines: list[str] = []
        for cmd in MANAGED_COMMANDS:
            p = perm_map.get(cmd)
            if p is None:
                lines.append(f"`/{cmd}` → **owner** (既定)")
                continue
            if p.mode == "role":
                roles = (
                    ", ".join(f"<@&{rid}>" for rid in p.role_ids)
                    if p.role_ids
                    else "*未設定*"
                )
                lines.append(f"`/{cmd}` → **role** ({roles})")
            else:
                lines.append(f"`/{cmd}` → **{p.mode}**")
        embed.add_field(name="コマンド権限", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot, bot.db))  # type: ignore[attr-defined]
