"""プロフィール登録 Modal および Twitter リンクボタン View。"""
from __future__ import annotations

import discord

from db.database import Database, UserProfile
from utils.validators import normalize_twitter, parse_md, parse_ymd, twitter_url


class ProfileModal(discord.ui.Modal, title="プロフィール登録 / 更新"):
    def __init__(self, db: Database, existing: UserProfile | None):
        super().__init__(timeout=600)
        self.db = db

        self.name_input = discord.ui.TextInput(
            label="表示名",
            placeholder="例: たろう",
            max_length=64,
            default=existing.name if existing else None,
            required=True,
        )
        self.twitter_input = discord.ui.TextInput(
            label="Twitter ID (任意)",
            placeholder="例: @example_user",
            max_length=16,
            default=existing.twitter_id if existing else None,
            required=False,
        )
        self.birthday_input = discord.ui.TextInput(
            label="誕生日 (MM/DD)",
            placeholder="例: 04/15",
            max_length=5,
            default=(
                f"{existing.birth_month:02d}/{existing.birth_day:02d}"
                if existing and existing.birth_month and existing.birth_day
                else None
            ),
            required=True,
        )
        self.start_input = discord.ui.TextInput(
            label="活動開始日 (YYYY/MM/DD)",
            placeholder="例: 2018/04/15",
            max_length=10,
            default=(
                f"{existing.start_year:04d}/{existing.start_month:02d}/{existing.start_day:02d}"
                if existing
                and existing.start_year
                and existing.start_month
                and existing.start_day
                else None
            ),
            required=True,
        )

        self.add_item(self.name_input)
        self.add_item(self.twitter_input)
        self.add_item(self.birthday_input)
        self.add_item(self.start_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                ":x: サーバー内で実行してください。", ephemeral=True
            )
            return
        try:
            twitter = normalize_twitter(self.twitter_input.value)
            b_month, b_day = parse_md(self.birthday_input.value)
            s_year, s_month, s_day = parse_ymd(self.start_input.value)
        except ValueError as e:
            await interaction.response.send_message(
                f":warning: 入力エラー: {e}", ephemeral=True
            )
            return

        profile = UserProfile(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            name=self.name_input.value.strip(),
            twitter_id=twitter,
            birth_month=b_month,
            birth_day=b_day,
            start_year=s_year,
            start_month=s_month,
            start_day=s_day,
        )
        await self.db.upsert_profile(profile)
        await interaction.response.send_message(
            ":white_check_mark: このサーバー用にプロフィールを保存しました！", ephemeral=True
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f":x: 予期しないエラーが発生しました: {error}", ephemeral=True
            )


class TwitterLinkView(discord.ui.View):
    """Twitter ハンドルを開くリンクボタン付き View。"""

    def __init__(self, handle: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label=f"Twitter: {handle}",
                style=discord.ButtonStyle.link,
                url=twitter_url(handle),
                emoji="🐦",
            )
        )
