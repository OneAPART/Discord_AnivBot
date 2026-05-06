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
# ページャーの有効期限。Discord の Interaction トークン有効期間に合わせ 15 分。
VIEW_TIMEOUT_SEC = 15 * 60


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db

    # ----------------------------------------------------------
    # /profile
    # ----------------------------------------------------------
    @app_commands.command(name="profile", description="プロフィールを登録 / 編集します (サーバーごと)。")
    @app_commands.describe(user="代理登録する対象ユーザー (省略時は自分)")
    @app_commands.guild_only()
    @require("profile")
    async def profile(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ):
        assert interaction.guild is not None
        target = user or interaction.user
        if target.bot:
            await interaction.response.send_message(
                ":x: Bot のプロフィールは登録できません。", ephemeral=True
            )
            return
        existing = await self.db.get_profile(interaction.guild.id, target.id)
        await interaction.response.send_modal(
            ProfileModal(
                self.db,
                existing,
                target_user_id=target.id,
                target_display=target.display_name,
            )
        )

    @app_commands.command(
        name="profile_delete",
        description="このサーバーからプロフィールを削除します。",
    )
    @app_commands.describe(user="削除対象ユーザー (省略時は自分)")
    @app_commands.guild_only()
    @require("profile")
    async def profile_delete(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ):
        assert interaction.guild is not None
        target = user or interaction.user
        deleted = await self.db.delete_profile(interaction.guild.id, target.id)
        if deleted:
            if user is None:
                msg = ":wastebasket: このサーバーのプロフィールを削除しました。"
            else:
                msg = f":wastebasket: <@{target.id}> のプロフィールを削除しました。"
        else:
            msg = ":information_source: 該当するプロフィールはありませんでした。"
        await interaction.response.send_message(msg, ephemeral=True)

    # ----------------------------------------------------------
    # /show
    # ----------------------------------------------------------
    @app_commands.command(name="show", description="プロフィールを表示します。")
    @app_commands.describe(
        user="表示するユーザー (省略時は自分)",
        public="他の人にも見えるように表示する (既定: 自分のみ)",
    )
    @app_commands.guild_only()
    @require("show")
    async def show(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
        public: bool = False,
    ):
        assert interaction.guild is not None
        target = user or interaction.user
        profile = await self.db.get_profile(interaction.guild.id, target.id)
        if profile is None:
            await interaction.response.send_message(
                f"{target.display_name} さんはこのサーバーでまだプロフィール未登録です。",
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

        kwargs: dict = {"embed": embed, "ephemeral": not public}
        if profile.twitter_id:
            kwargs["view"] = TwitterLinkView(profile.twitter_id)
        await interaction.response.send_message(**kwargs)

    # ----------------------------------------------------------
    # /list
    # ----------------------------------------------------------
    @app_commands.command(
        name="list",
        description="このサーバーに登録されているプロフィール一覧を表示します。",
    )
    @app_commands.describe(
        sort="並び順",
        public="他の人にも見えるように表示する (既定: 自分のみ)",
    )
    @app_commands.guild_only()
    @require("list")
    async def list_profiles(
        self,
        interaction: discord.Interaction,
        sort: Literal["name", "birthday", "anniversary"] = "name",
        public: bool = False,
    ):
        guild = interaction.guild
        assert guild is not None

        member_ids = [m.id for m in guild.members if not m.bot]
        profiles = await self.db.list_profiles(guild.id, user_ids=member_ids)

        if not profiles:
            await interaction.response.send_message(
                "このサーバーに登録済みのプロフィールはまだありません。",
                ephemeral=True,
            )
            return

        profiles.sort(key=_sort_key(sort))
        # public=True のときは誰でもページ送りできるよう requester_id=None
        view = ProfileListView(
            guild,
            profiles,
            sort,
            requester_id=None if public else interaction.user.id,
        )
        await interaction.response.send_message(
            embed=view.build_embed(), view=view, ephemeral=not public
        )
        # on_timeout でボタンを無効化するため元メッセージを保持
        try:
            view.message = await interaction.original_response()
        except discord.HTTPException:
            view.message = None


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
        requester_id: int | None,
    ):
        super().__init__(timeout=VIEW_TIMEOUT_SEC)
        self.guild = guild
        self.profiles = profiles
        self.sort = sort
        # None の場合は誰でも操作可 (公開モード)
        self.requester_id = requester_id
        # 初期メッセージへの参照。on_timeout でボタンを無効化するため保持。
        self.message: discord.Message | discord.InteractionMessage | None = None
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
        # requester_id が None なら誰でも操作可 (public モード)
        if self.requester_id is None:
            return True
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "このページ操作は実行者のみ行えます。", ephemeral=True
            )
            return False
        return True

    async def _safe_edit(self, interaction: discord.Interaction) -> None:
        """defer で 15 分の応答猟予を確保したうえでメッセージを更新する。

        - ボタンクリックの Interaction トークンは Discord 仕様で 15 分有効。
        - 3 秒以内に `response.defer()` しておけば、その後は 15 分間 followup / edit 可能。
        - 15 分を超過してクリックされた場合は Discord が 10062 (Unknown interaction)
          を返すため、ユーザーへ「再実行してください」と伝える。
        """
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()  # 15 分の猟予を確保
            await interaction.edit_original_response(
                embed=self.build_embed(), view=self
            )
        except discord.NotFound:
            # Unknown interaction (10062) — 15 分を超えてクリックされた / メッセージが削除された
            await self._notify_expired(interaction)
        except discord.HTTPException:
            # その他一過性エラーもページャーではサイレント化
            pass

    async def _notify_expired(self, interaction: discord.Interaction) -> None:
        """ボタンの猟予期限を超えた際のユーザー向け案内。送信失敗は黙視。"""
        # ボタンを全て無効化して表示だけ更新を試みる (失敗してもよい)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            await interaction.followup.send(
                ":hourglass: このページ操作は有効期限 (15分) を超えたため受け付けられませんでした。\n"
                "お手数ですが **コマンドを再実行** してください。",
                ephemeral=True,
            )
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        """15 分経過した View のボタンを無効化する。"""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
            finally:
                # 参照を解放してメモリリークを防止
                self.message = None

    @discord.ui.button(label="◀ 前へ", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ):
        if not await self._guard(interaction):
            return
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await self._safe_edit(interaction)

    @discord.ui.button(label="次へ ▶", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ):
        if not await self._guard(interaction):
            return
        self.page = min(self.max_page, self.page + 1)
        self._update_buttons()
        await self._safe_edit(interaction)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        # NotFound (Unknown interaction) は Webhook 通知しない (ノイズ)
        if isinstance(error, discord.NotFound):
            return
        # それ以外は既定のハンドラ (logger へ)
        await super().on_error(interaction, error, item)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot, bot.db))  # type: ignore[attr-defined]
