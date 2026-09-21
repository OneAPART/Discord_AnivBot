"""コマンド権限チェック共通モジュール。

サーバー（ギルド）ごとに、コマンド単位で次の3モードを選択できる。

- ``owner``    : サーバーオーナーのみ実行可
- ``everyone`` : 全員実行可
- ``role``     : 指定ロールを保持しているメンバーのみ実行可

未設定時は ``profile`` のみ ``everyone``、それ以外は ``owner``。
``profile_delete`` は ``profile`` の設定を共有する。他人のプロフィールの
登録・編集・削除には、コマンド権限に加えてサーバーオーナーであることが必要。
DM およびサーバーメンバー以外の実行は常に拒否する。
"""
from __future__ import annotations

import discord
from discord import app_commands

from db.database import Database


class PermissionDenied(app_commands.CheckFailure):
    """権限不足。コマンドと Modal の応答で案内するために使用。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def default_permission_mode(command_name: str) -> str:
    """明示設定がない場合の権限モード。未知のコマンドはオーナー限定。"""
    return "everyone" if command_name == "profile" else "owner"


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
    mode = perm.mode if perm else default_permission_mode(command_name)

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


def check_profile_target(
    interaction: discord.Interaction, target_user_id: int
) -> None:
    """コマンド権限とは別に、他人のプロフィール操作をオーナーに制限する。"""
    if interaction.guild is None:
        raise PermissionDenied("このコマンドはサーバー内で実行してください。")
    if (
        target_user_id != interaction.user.id
        and interaction.user.id != interaction.guild.owner_id
    ):
        raise PermissionDenied(
            "他のユーザーのプロフィールを登録・編集・削除できるのはサーバーオーナーのみです。"
        )


def require(command_name: str):
    """app_commands 用のチェックデコレータを生成する。"""

    async def predicate(interaction: discord.Interaction) -> bool:
        db: Database = interaction.client.db  # type: ignore[attr-defined]
        return await is_allowed(db, interaction, command_name)

    return app_commands.check(predicate)
