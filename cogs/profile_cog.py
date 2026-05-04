"""/profile, /show, /list コマンド。"""
from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from db.database import Database, UserProfile
from ui.modals import ProfileModal, TwitterLinkView
from utils.permissions import require
from utils.validators import twitter_url


PAGE_SIZE = 10


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db

    # ----------------------------------------------------------
    # /profile
    # ----------------------------------------------------------
    @app_commands.command(name="profile", description="プロフィールを登録 / 編集します。")
    @app_commands.guild_only()
    @require("profile")
    async def profile(self, interaction: discord.Interaction):
        existing = await self.db.get_profile(interaction.user.id)
        await interaction.response.send_modal(ProfileModal(self.db, existing))

    # ----------------------------------------------------------
    # /show
    # ----------------------------------------------------------
    @app_commands.command(name="show", description="プロフィールを表示します。")
    @app_commands.describe(user="表示するユーザー (省略時は自分)")
    @app_commands.guild_only()
    @require("show")
    async def show(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ):
        target = user or interaction.user
        profile = await self.db.get_profile(target.id)
        if profile is None:
            await interaction.response.send_message(
                f"{target.display_name} さんはまだプロフィール未登録です。",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"{profile.name} さんのプロフィール",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        if profile.birth_month and profile.birth_day:
            embed.add_field(
                name="🎂 誕生日",
                value=f"{profile.birth_month}月{profile.birth_day}日",
                inline=True,
            )
        if profile.start_year and profile.start_month and profile.start_day:
            embed.add_field(
                name="🎉 活動開始",
                value=f"{profile.start_year}年{profile.start_month}月{profile.start_day}日",
                inline=True,
            )
        if profile.twitter_id:
            embed.add_field(
                name="🐦 Twitter",
                value=f"[{profile.twitter_id}]({twitter_url(profile.twitter_id)})",
                inline=False,
            )

        view = TwitterLinkView(profile.twitter_id) if profile.twitter_id else None
        await interaction.response.send_message(embed=embed, view=view)

    # ----------------------------------------------------------
    # /list
    # ----------------------------------------------------------
    @app_commands.command(
        name="list",
        description="このサーバーに登録されているプロフィール一覧を表示します。",
    )
    @app_commands.describe(sort="並び順")
    @app_commands.guild_only()
    @require("list")
    async def list_profiles(
        self,
        interaction: discord.Interaction,
        sort: Literal["name", "birthday", "anniversary"] = "name",
    ):
        guild = interaction.guild
        assert guild is not None

        member_ids = [m.id for m in guild.members if not m.bot]
        profiles = await self.db.list_profiles(user_ids=member_ids)

        if not profiles:
            await interaction.response.send_message(
                "このサーバーに登録済みのプロフィールはまだありません。",
                ephemeral=True,
            )
            return

        profiles.sort(key=_sort_key(sort))
        view = ProfileListView(guild, profiles, sort, requester_id=interaction.user.id)
        await interaction.response.send_message(embed=view.build_embed(), view=view)


# --------------------------------------------------------------
# Pagination View
# --------------------------------------------------------------
def _sort_key(sort: str):
    if sort == "birthday":
        return lambda p: (p.birth_month or 99, p.birth_day or 99, p.name)
    if sort == "anniversary":
        return lambda p: (
            p.start_year or 9999,
            p.start_month or 99,
            p.start_day or 99,
            p.name,
        )
    return lambda p: p.name.lower()


class ProfileListView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        profiles: list[UserProfile],
        sort: str,
        requester_id: int,
    ):
        super().__init__(timeout=180)
        self.guild = guild
        self.profiles = profiles
        self.sort = sort
        self.requester_id = requester_id
        self.page = 0
        self.max_page = max(0, (len(profiles) - 1) // PAGE_SIZE)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.max_page

    def build_embed(self) -> discord.Embed:
        start = self.page * PAGE_SIZE
        chunk = self.profiles[start : start + PAGE_SIZE]
        embed = discord.Embed(
            title=f"📋 登録プロフィール一覧 ({len(self.profiles)}件)",
            color=discord.Color.blurple(),
        )
        embed.set_footer(
            text=f"並び: {self.sort}  |  ページ {self.page + 1}/{self.max_page + 1}"
        )
        for p in chunk:
            member = self.guild.get_member(p.user_id)
            mention = member.mention if member else f"<@{p.user_id}>"
            lines = [mention]
            if p.birth_month and p.birth_day:
                lines.append(f"🎂 {p.birth_month}/{p.birth_day}")
            if p.start_year and p.start_month and p.start_day:
                lines.append(
                    f"🎉 {p.start_year}/{p.start_month}/{p.start_day}"
                )
            if p.twitter_id:
                lines.append(f"🐦 [{p.twitter_id}]({twitter_url(p.twitter_id)})")
            embed.add_field(
                name=p.name,
                value="  ".join(lines),
                inline=False,
            )
        return embed

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "このページ操作は実行者のみ行えます。", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="◀ 前へ", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ):
        if not await self._guard(interaction):
            return
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="次へ ▶", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ):
        if not await self._guard(interaction):
            return
        self.page = min(self.max_page, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot, bot.db))  # type: ignore[attr-defined]
