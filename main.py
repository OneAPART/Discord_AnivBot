"""AnniversaryBot エントリポイント。"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from db.database import Database
from utils.error_notifier import ErrorNotifier
from utils.permissions import PermissionDenied

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("anniversarybot")

TOKEN = os.getenv("DISCORD_TOKEN")
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")
DB_PATH = os.getenv("DB_PATH", "anniversary.db")

# エラー通知先 (Power Automate トリガー)。
# .env の ERROR_WEBHOOK_URL があればそちらを優先、未設定ならハードコードの URL を使用する。
_DEFAULT_ERROR_WEBHOOK_URL = (
    "https://2226eed15edeee65b4b052511edb35.b5.environment.api.powerplatform.com:443"
    "/powerautomate/automations/direct/workflows/413fd917d9d4432b866c972b9e6baba4"
    "/triggers/manual/paths/invoke"
    "?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0"
    "&sig=FRa0StTGJztvKMYl4SJ5JhmD-ByqUUptwe13r3OfNjY"
)
ERROR_WEBHOOK_URL = os.getenv("ERROR_WEBHOOK_URL") or _DEFAULT_ERROR_WEBHOOK_URL

INITIAL_COGS = (
    "cogs.profile_cog",
    "cogs.config_cog",
    "cogs.anniversary_cog",
    "cogs.admin_cog",
)


class _NotifyingLogHandler(logging.Handler):
    """ERROR 以上のログを ErrorNotifier 経由で外部 Webhook へ転送する。"""

    def __init__(self, notifier: ErrorNotifier):
        super().__init__(level=logging.ERROR)
        self.notifier = notifier

    def emit(self, record: logging.LogRecord) -> None:
        if not self.notifier.enabled:
            return
        # 通知ハンドラ自体のログ (utils.error_notifier) でループしないようにガード
        if record.name.startswith("utils.error_notifier"):
            return
        exc = record.exc_info[1] if record.exc_info else None
        try:
            self.notifier.notify(
                level=record.levelname,
                message=record.getMessage(),
                exception=exc,
                logger_name=record.name,
                context={"module": record.module, "func": record.funcName},
            )
        except Exception:  # noqa: BLE001
            pass


class AnniversaryBot(commands.Bot):
    def __init__(self, db: Database, notifier: ErrorNotifier):
        intents = discord.Intents.default()
        intents.members = True  # ギルドメンバー判定で使用
        super().__init__(command_prefix="!", intents=intents)
        self.db = db
        self.notifier = notifier

    async def setup_hook(self) -> None:
        for ext in INITIAL_COGS:
            await self.load_extension(ext)
            log.info("Loaded extension: %s", ext)

        # グローバル app_command エラーハンドラ
        self.tree.on_error = self._on_app_command_error  # type: ignore[assignment]

        if TEST_GUILD_ID:
            guild = discord.Object(id=int(TEST_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d commands to test guild %s", len(synced), TEST_GUILD_ID)
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global commands", len(synced))

    async def on_ready(self) -> None:
        log.info("Logged in as %s (id=%s)", self.user, self.user.id if self.user else "?")

    async def _on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, PermissionDenied):
            msg = f":no_entry: {error.message}"
        elif isinstance(error, app_commands.CheckFailure):
            msg = ":no_entry: このコマンドを実行する権限がありません。"
        elif isinstance(error, app_commands.TransformerError):
            # 引数の自動変換失敗 (例: チャンネル選択を手入力された等)。
            # ユーザー操作ミスのため Webhook 通知はせず、案内のみ返す。
            log.info(
                "TransformerError on /%s: value=%r option_type=%s",
                interaction.command.qualified_name if interaction.command else "?",
                getattr(error, "value", None),
                getattr(error, "type", None),
            )
            value = getattr(error, "value", None)
            msg = (
                f":warning: 引数 `{value}` を正しく解釈できませんでした。\n"
                "サジェスト一覧から候補を **クリックして選択** してください "
                "（チャンネル指定の場合は `#チャンネル名` を選ぶか、`#` を入力すると候補が出ます）。"
            )
        else:
            log.exception("Unhandled app command error: %s", error)
            # 外部 Webhook へ通知（コンテキスト付き）
            self.notifier.notify(
                level="ERROR",
                message=f"Unhandled app command error: {type(error).__name__}",
                exception=error,
                logger_name="anniversarybot",
                context={
                    "guild_id": interaction.guild.id if interaction.guild else None,
                    "channel_id": interaction.channel.id if interaction.channel else None,
                    "user_id": interaction.user.id,
                    "command": interaction.command.qualified_name
                    if interaction.command
                    else None,
                },
            )
            msg = f":x: コマンド実行中にエラーが発生しました: `{type(error).__name__}`"

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.InteractionResponded:
            pass


async def main() -> None:
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN が未設定です。.env を作成してください。")

    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = Database(DB_PATH)
    await db.init()
    log.info("DB initialized: %s", DB_PATH)

    notifier = ErrorNotifier(ERROR_WEBHOOK_URL)
    await notifier.start()
    if notifier.enabled:
        logging.getLogger().addHandler(_NotifyingLogHandler(notifier))
        log.info("Error webhook enabled")
    else:
        log.info("Error webhook disabled (ERROR_WEBHOOK_URL unset)")

    bot = AnniversaryBot(db, notifier)
    try:
        async with bot:
            await bot.start(TOKEN)
    finally:
        await notifier.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
