"""グローバル登録のスラッシュコマンドを全削除するワンショットスクリプト。

二重表示 (グローバル登録 + ギルド登録) になってしまった場合のクリーンアップ用。
実行後、Discord 各クライアントへの反映に最大 1 時間ほどかかる場合があります。

使い方:
    .\\venv\\Scripts\\python.exe scripts\\clear_global_commands.py

確認のため `--yes` を付けないと実際には実行しません。
    .\\venv\\Scripts\\python.exe scripts\\clear_global_commands.py --yes
"""
from __future__ import annotations

import asyncio
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv


async def _run() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN が未設定です。")

    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        try:
            bot.tree.clear_commands(guild=None)  # グローバル
            synced = await bot.tree.sync()
            print(f"OK: グローバル登録をクリアしました (現在 {len(synced)} 件)")
            print("反映に最大 1 時間ほどかかる場合があります。")
        finally:
            await bot.close()

    await bot.start(token)


def main() -> None:
    if "--yes" not in sys.argv:
        print("このスクリプトはグローバル登録のスラッシュコマンドを全削除します。")
        print("実行する場合は --yes を付けて再実行してください。")
        return
    asyncio.run(_run())


if __name__ == "__main__":
    main()
