"""コマンド権限チェック共通モジュール。

サーバー（ギルド）ごとに、コマンド単位で次の3モードを選択できる。

- ``owner``    : サーバーオーナーのみ実行可
- ``everyone`` : 全員実行可（既定）
- ``role``     : 指定ロールを保持しているメンバーのみ実行可

DM での実行は常に拒否する。
"""
from __future__ import annotations

import discord
from discord import app_commands

from db.database import Database


class PermissionDenied(app_commands.CheckFailure):
    """権限不足。グローバル on_app_command_error で文言を出すために使用。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


async def is_allowed(
    db: Database,
    interaction: discord.Interaction,
    command_name: str,
) -> bool:
    """設定に基づいて実行可否を判定する。"""
    if interaction.guild is None or not isinstance(
        interaction.user, discord.Member
    ):
        raise PermissionDenied("このコマンドはサーバー内で実行してください。")

    perm = await db.get_permission(interaction.guild.id, command_name)
    mode = perm.mode if perm else "everyone"

    if mode == "everyone":
        return True

    if mode == "owner":
        if interaction.user.id == interaction.guild.owner_id:
            return True
        raise PermissionDenied("このコマンドはサーバーオーナーのみ実行できます。")

    if mode == "role":
        allowed_ids = set(perm.role_ids) if perm else set()
        if not allowed_ids:
            raise PermissionDenied(
                "ロール制限モードですが、許可ロールが設定されていません。管理者に設定を依頼してください。"
            )
        member_role_ids = {r.id for r in interaction.user.roles}
        if member_role_ids & allowed_ids:
            return True
        raise PermissionDenied("このコマンドを実行できるロールを持っていません。")

    raise PermissionDenied(f"未知の権限モードです: {mode}")


def require(command_name: str):
    """app_commands 用のチェックデコレータを生成する。"""

    async def predicate(interaction: discord.Interaction) -> bool:
        db: Database = interaction.client.db  # type: ignore[attr-defined]
        return await is_allowed(db, interaction, command_name)

    return app_commands.check(predicate)
