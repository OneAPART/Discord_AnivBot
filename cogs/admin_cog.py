"""動作確認用の管理者コマンド（テスト・運用補助）。

`/admin trigger` で任意日付の通知ロジックを即時実行できる。
サーバーオーナーのみ実行可。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.anniversary_cog import AnniversaryCog, JST
from db.database import Database

# UTC で扱うと混乱するので JST 基準
def _today_jst() -> date:
    return datetime.now(JST).date()


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db

    admin = app_commands.Group(
        name="admin",
        description="運用・動作確認コマンド",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    @admin.command(
        name="trigger",
        description="今日(または指定日)の通知ロジックを即時実行します（試験用）。",
    )
    @app_commands.describe(
        date_str="判定基準日 (YYYY-MM-DD)。省略時は今日(JST)。",
        dry_run="True にすると DB を読むだけで送信はしません。",
    )
    async def trigger(
        self,
        interaction: discord.Interaction,
        date_str: str | None = None,
        dry_run: bool = False,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "サーバー内で実行してください。", ephemeral=True
            )
            return
        if interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                ":no_entry: このコマンドはサーバーオーナーのみ実行できます。",
                ephemeral=True,
            )
            return

        # 日付パース
        if date_str:
            try:
                target = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                await interaction.response.send_message(
                    ":x: 日付形式が不正です。`YYYY-MM-DD` で指定してください。",
                    ephemeral=True,
                )
                return
        else:
            target = _today_jst()

        await interaction.response.defer(ephemeral=True)

        cog: AnniversaryCog | None = self.bot.get_cog("AnniversaryCog")  # type: ignore[assignment]
        if cog is None:
            await interaction.followup.send(":x: AnniversaryCog がロードされていません。", ephemeral=True)
            return

        if dry_run:
            assert interaction.guild is not None
            bdays = await self.db.find_birthdays(
                interaction.guild.id, target.month, target.day
            )
            anns = await self.db.find_anniversaries(
                interaction.guild.id, target.month, target.day
            )
            await interaction.followup.send(
                f"🧪 dry-run (このサーバーのみ): {target}\n"
                f"- 誕生日対象: {len(bdays)} 名 ({', '.join(p.name for p in bdays) or 'なし'})\n"
                f"- 記念日対象: {len(anns)} 名 ({', '.join(p.name for p in anns) or 'なし'})",
                ephemeral=True,
            )
            return

        result = await cog.run_for_date(target)
        await interaction.followup.send(
            f":white_check_mark: 実行完了 ({target})\n"
            f"- 誕生日: {result['birthdays']} 件\n"
            f"- 記念日: {result['anniversaries']} 件\n"
            f"- 配信先チャンネル: {result['channels']} 件",
            ephemeral=True,
        )

    @admin.command(name="next_run", description="次回 daily_notify の発火予定時刻を表示します。")
    async def next_run(self, interaction: discord.Interaction):
        cog: AnniversaryCog | None = self.bot.get_cog("AnniversaryCog")  # type: ignore[assignment]
        if cog is None:
            await interaction.response.send_message(":x: 未ロード", ephemeral=True)
            return
        nxt = cog.daily_notify.next_iteration
        now = datetime.now(timezone.utc)
        if nxt is None:
            await interaction.response.send_message("未スケジュール", ephemeral=True)
            return
        delta = nxt - now
        await interaction.response.send_message(
            f"次回発火: {nxt.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S JST')}\n"
            f"あと {delta}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot, bot.db))  # type: ignore[attr-defined]
