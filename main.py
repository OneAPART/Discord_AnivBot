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

INITIAL_COGS = (
    "cogs.profile_cog",
    "cogs.config_cog",
    "cogs.anniversary_cog",
    "cogs.admin_cog",
)


class AnniversaryBot(commands.Bot):
    def __init__(self, db: Database):
        intents = discord.Intents.default()
        intents.members = True  # ギルドメンバー判定で使用
        super().__init__(command_prefix="!", intents=intents)
        self.db = db

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
        else:
            log.exception("Unhandled app command error: %s", error)
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

    bot = AnniversaryBot(db)
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
