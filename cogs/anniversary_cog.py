"""毎日 JST 00:00 に誕生日 / 活動記念日を通知する Cog。"""
from __future__ import annotations

import logging
from datetime import datetime, time, timezone, timedelta

import discord
from discord.ext import commands, tasks

from db.database import Database, UserProfile
from ui.modals import TwitterLinkView
from utils.avatar import resolve_avatar_url
from utils.validators import twitter_url

JST = timezone(timedelta(hours=9))
NOTIFY_TIME = time(hour=0, minute=0, tzinfo=JST)

log = logging.getLogger(__name__)


class AnniversaryCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        self.daily_notify.start()

    def cog_unload(self) -> None:
        self.daily_notify.cancel()

    # --------------------------------------------------------------
    # Daily task
    # --------------------------------------------------------------
    @tasks.loop(time=NOTIFY_TIME)
    async def daily_notify(self) -> None:
        today = datetime.now(JST).date()
        await self.run_for_date(today)

    async def run_for_date(self, target_date) -> dict:
        """指定日付について通知ロジックを実行する。テスト・手動再実行用。

        サーバーごとに DB を引き、対象がいるサーバーのみ通知する。

        Returns:
            集計結果 {'birthdays': int, 'anniversaries': int, 'channels': int}
        """
        log.info("Notify run for: %s", target_date.isoformat())
        try:
            channels = await self.db.all_channels()
        except Exception:
            log.exception("DB 取得に失敗しました")
            return {"birthdays": 0, "anniversaries": 0, "channels": 0}

        total_b = 0
        total_a = 0
        notified_channels = 0

        for guild_id, channel_id, notify_absent, avatar_source in channels:
            try:
                birthdays = await self.db.find_birthdays(
                    guild_id, target_date.month, target_date.day
                )
                anniversaries = await self.db.find_anniversaries(
                    guild_id, target_date.month, target_date.day
                )
            except Exception:
                log.exception("DB 検索失敗 guild=%s", guild_id)
                continue

            if not birthdays and not anniversaries:
                continue

            total_b += len(birthdays)
            total_a += len(anniversaries)
            notified_channels += 1
            await self._send_to_channel(
                guild_id,
                channel_id,
                target_date.year,
                birthdays,
                anniversaries,
                notify_absent=notify_absent,
                avatar_source=avatar_source,
            )

        return {
            "birthdays": total_b,
            "anniversaries": total_a,
            "channels": notified_channels,
        }

    @daily_notify.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()

    @daily_notify.error
    async def _on_error(self, error: Exception) -> None:
        log.exception("daily_notify でエラー: %s", error)

    # --------------------------------------------------------------
    # Senders
    # --------------------------------------------------------------
    async def _send_to_channel(
        self,
        guild_id: int,
        channel_id: int,
        current_year: int,
        birthdays: list[UserProfile],
        anniversaries: list[UserProfile],
        notify_absent: bool = False,
        avatar_source: str = "twitter",
    ) -> None:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden):
                log.warning("guild=%s channel=%s が取得不可", guild_id, channel_id)
                return
            except Exception:
                log.exception("channel 取得失敗 guild=%s", guild_id)
                return

        if not isinstance(channel, discord.abc.Messageable):
            return

        guild = self.bot.get_guild(guild_id)
        guild_member_ids: set[int] | None = (
            {m.id for m in guild.members} if guild else None
        )

        # ギルド未取得 (キャッシュミス / Intent不足等) の場合、notify_absent=True でなければ安全側で送信しない。
        if guild_member_ids is None and not notify_absent:
            log.warning(
                "guild=%s のメンバー一覧が取得できず、notify_absent=False のため送信をスキップしました",
                guild_id,
            )
            return

        def _allowed(uid: int) -> bool:
            if notify_absent:
                return True
            if guild_member_ids is None:
                return False
            return uid in guild_member_ids

        for p in birthdays:
            if not _allowed(p.user_id):
                log.info(
                    "不在ユーザーのためスキップ (birthday) guild=%s user=%s",
                    guild_id, p.user_id,
                )
                continue
            member = guild.get_member(p.user_id) if guild else None
            await self._safe_send(
                channel, *self._birthday_payload(p, member, avatar_source)
            )

        for p in anniversaries:
            if not _allowed(p.user_id):
                log.info(
                    "不在ユーザーのためスキップ (anniversary) guild=%s user=%s",
                    guild_id, p.user_id,
                )
                continue
            member = guild.get_member(p.user_id) if guild else None
            await self._safe_send(
                channel,
                *self._anniversary_payload(p, current_year, member, avatar_source),
            )

    async def _safe_send(
        self,
        channel: discord.abc.Messageable,
        content: str,
        embed: discord.Embed,
        view: discord.ui.View | None,
    ) -> None:
        try:
            await channel.send(content=content, embed=embed, view=view)
        except discord.Forbidden:
            log.warning("送信権限なし channel=%s", getattr(channel, "id", "?"))
        except Exception:
            log.exception("通知送信失敗")

    # --------------------------------------------------------------
    # Payload builders
    # --------------------------------------------------------------
    def _birthday_payload(
        self,
        p: UserProfile,
        member: discord.abc.User | None = None,
        avatar_source: str = "twitter",
    ) -> tuple[str, discord.Embed, discord.ui.View | None]:
        embed = discord.Embed(
            title="🎂 Happy Birthday! 🎂",
            description=f"**{p.name}** さん、お誕生日おめでとうございます！🎉",
            color=discord.Color.magenta(),
        )
        avatar = resolve_avatar_url(
            source=avatar_source, twitter_id=p.twitter_id, member=member
        )
        if avatar:
            embed.set_thumbnail(url=avatar)
        if p.twitter_id:
            embed.add_field(
                name="Twitter",
                value=f"[{p.twitter_id}]({twitter_url(p.twitter_id)})",
            )
        view = TwitterLinkView(p.twitter_id) if p.twitter_id else None
        return (f"<@{p.user_id}>", embed, view)

    def _anniversary_payload(
        self,
        p: UserProfile,
        current_year: int,
        member: discord.abc.User | None = None,
        avatar_source: str = "twitter",
    ) -> tuple[str, discord.Embed, discord.ui.View | None]:
        years = current_year - (p.start_year or current_year)
        embed = discord.Embed(
            title="🎉 活動記念日 🎉",
            description=(
                f"**{p.name}** さん、活動 **{years}周年** おめでとうございます！🥳\n"
                f"({p.start_year}年{p.start_month}月{p.start_day}日 〜)"
            ),
            color=discord.Color.gold(),
        )
        avatar = resolve_avatar_url(
            source=avatar_source, twitter_id=p.twitter_id, member=member
        )
        if avatar:
            embed.set_thumbnail(url=avatar)
        if p.twitter_id:
            embed.add_field(
                name="Twitter",
                value=f"[{p.twitter_id}]({twitter_url(p.twitter_id)})",
            )
        view = TwitterLinkView(p.twitter_id) if p.twitter_id else None
        return (f"<@{p.user_id}>", embed, view)


async def setup(bot: commands.Bot):
    await bot.add_cog(AnniversaryCog(bot, bot.db))  # type: ignore[attr-defined]
