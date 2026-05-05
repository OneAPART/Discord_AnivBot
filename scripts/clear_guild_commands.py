"""特定ギルドに登録されたスラッシュコマンドを全削除するワンショットスクリプト。

二重表示 (グローバル登録 + ギルド登録) で、ギルド側を消したい場合のクリーンアップ用。
ギルド登録の削除は **即時** に Discord に反映されます。

使い方:
    # .env の TEST_GUILD_ID を対象にする
    .\\venv\\Scripts\\python.exe scripts\\clear_guild_commands.py --yes

    # 任意のギルド ID を直接指定する
    .\\venv\\Scripts\\python.exe scripts\\clear_guild_commands.py --yes --guild 1234567890123456789

確認のため `--yes` を付けないと実際には実行しません。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--yes", action="store_true", help="実際に削除を実行する")
    p.add_argument(
        "--guild",
        type=int,
        default=None,
        help="対象ギルド ID。省略時は .env の TEST_GUILD_ID を使用",
    )
    return p.parse_args()


async def _run(guild_id: int) -> None:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN が未設定です。")

    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        try:
            guild = discord.Object(id=guild_id)
            bot.tree.clear_commands(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(
                f"OK: ギルド {guild_id} の登録コマンドをクリアしました "
                f"(現在 {len(synced)} 件)"
            )
            print("ギルド登録の削除は即時反映されます。")
        finally:
            await bot.close()

    await bot.start(token)


def main() -> None:
    args = _parse_args()
    guild_id = args.guild or (
        int(os.getenv("TEST_GUILD_ID")) if os.getenv("TEST_GUILD_ID") else None
    )
    if guild_id is None:
        # .env がまだ読まれていないため明示ロード
        load_dotenv()
        env_id = os.getenv("TEST_GUILD_ID")
        if env_id:
            guild_id = int(env_id)
    if guild_id is None:
        print(
            "対象ギルド ID が指定されていません。"
            "--guild <id> を渡すか .env の TEST_GUILD_ID を設定してください。"
        )
        sys.exit(1)

    if not args.yes:
        print(
            f"このスクリプトはギルド {guild_id} の登録スラッシュコマンドを全削除します。"
        )
        print("実行する場合は --yes を付けて再実行してください。")
        return

    asyncio.run(_run(guild_id))


if __name__ == "__main__":
    main()
