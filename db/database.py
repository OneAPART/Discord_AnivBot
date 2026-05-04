"""SQLite (aiosqlite) を用いた非同期データアクセス層。

すべてのプロフィールはサーバー (guild) 単位で管理する。
複合主キー: (guild_id, user_id)
"""
from __future__ import annotations

import aiosqlite
from dataclasses import dataclass
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    guild_id     INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    name         TEXT    NOT NULL,
    twitter_id   TEXT,
    birth_month  INTEGER,
    birth_day    INTEGER,
    start_year   INTEGER,
    start_month  INTEGER,
    start_day    INTEGER,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS server_settings (
    guild_id      INTEGER PRIMARY KEY,
    channel_id    INTEGER NOT NULL,
    notify_absent INTEGER NOT NULL DEFAULT 0,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS command_permissions (
    guild_id     INTEGER NOT NULL,
    command_name TEXT    NOT NULL,
    mode         TEXT    NOT NULL,
    role_ids     TEXT,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, command_name)
);

CREATE INDEX IF NOT EXISTS idx_birth      ON user_profiles(guild_id, birth_month, birth_day);
CREATE INDEX IF NOT EXISTS idx_start_date ON user_profiles(guild_id, start_month, start_day);
"""


@dataclass
class UserProfile:
    guild_id: int
    user_id: int
    name: str
    twitter_id: Optional[str]
    birth_month: Optional[int]
    birth_day: Optional[int]
    start_year: Optional[int]
    start_month: Optional[int]
    start_day: Optional[int]


@dataclass
class CommandPermission:
    guild_id: int
    command_name: str
    mode: str
    role_ids: list[int]


def _row_to_profile(r) -> UserProfile:
    return UserProfile(
        guild_id=r["guild_id"],
        user_id=r["user_id"],
        name=r["name"],
        twitter_id=r["twitter_id"],
        birth_month=r["birth_month"],
        birth_day=r["birth_day"],
        start_year=r["start_year"],
        start_month=r["start_month"],
        start_day=r["start_day"],
    )


class Database:
    def __init__(self, path: str):
        self.path = path

    # ---------- 初期化 ----------
    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await self._migrate_legacy_user_profiles(db)
            await db.executescript(SCHEMA)
            await self._migrate_columns(db)
            await db.commit()

    async def _migrate_legacy_user_profiles(self, db: aiosqlite.Connection) -> None:
        """旧スキーマ (guild_id 列を持たない) を _legacy_user_profiles に退避する。

        旧データはサーバーが特定できないため自動移行はせず、退避のみ行う。
        ユーザーは各サーバーで /profile を再登録する。必要なら手動 SQL で移行可能。
        """
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'"
        ) as cur:
            exists = await cur.fetchone()
        if not exists:
            return
        async with db.execute("PRAGMA table_info(user_profiles)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        if "guild_id" in cols:
            return  # 既に新スキーマ
        # 旧スキーマ -> リネーム退避
        await db.execute(
            "ALTER TABLE user_profiles RENAME TO _legacy_user_profiles"
        )

    async def _migrate_columns(self, db: aiosqlite.Connection) -> None:
        """server_settings に notify_absent が無い場合に追加する。"""
        async with db.execute("PRAGMA table_info(server_settings)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        if "notify_absent" not in cols:
            await db.execute(
                "ALTER TABLE server_settings ADD COLUMN notify_absent INTEGER NOT NULL DEFAULT 0"
            )

    # ---------- user_profiles ----------
    async def upsert_profile(self, profile: UserProfile) -> None:
        sql = """
        INSERT INTO user_profiles
            (guild_id, user_id, name, twitter_id, birth_month, birth_day,
             start_year, start_month, start_day, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            name        = excluded.name,
            twitter_id  = excluded.twitter_id,
            birth_month = excluded.birth_month,
            birth_day   = excluded.birth_day,
            start_year  = excluded.start_year,
            start_month = excluded.start_month,
            start_day   = excluded.start_day,
            updated_at  = CURRENT_TIMESTAMP;
        """
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                sql,
                (
                    profile.guild_id,
                    profile.user_id,
                    profile.name,
                    profile.twitter_id,
                    profile.birth_month,
                    profile.birth_day,
                    profile.start_year,
                    profile.start_month,
                    profile.start_day,
                ),
            )
            await db.commit()

    async def get_profile(
        self, guild_id: int, user_id: int
    ) -> Optional[UserProfile]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM user_profiles WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ) as cur:
                row = await cur.fetchone()
        return _row_to_profile(row) if row else None

    async def delete_profile(self, guild_id: int, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "DELETE FROM user_profiles WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def find_birthdays(
        self, guild_id: int, month: int, day: int
    ) -> list[UserProfile]:
        return await self._find_by_md(guild_id, "birth_month", "birth_day", month, day)

    async def find_anniversaries(
        self, guild_id: int, month: int, day: int
    ) -> list[UserProfile]:
        return await self._find_by_md(guild_id, "start_month", "start_day", month, day)

    async def _find_by_md(
        self, guild_id: int, m_col: str, d_col: str, month: int, day: int
    ) -> list[UserProfile]:
        sql = (
            f"SELECT * FROM user_profiles "
            f"WHERE guild_id = ? AND {m_col} = ? AND {d_col} = ?"
        )
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, (guild_id, month, day)) as cur:
                rows = await cur.fetchall()
        return [_row_to_profile(r) for r in rows]

    async def list_profiles(
        self, guild_id: int, user_ids: list[int] | None = None
    ) -> list[UserProfile]:
        """指定サーバーのプロフィール一覧。user_ids 指定時はそれに含まれるもののみ。"""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            if user_ids is None:
                async with db.execute(
                    "SELECT * FROM user_profiles WHERE guild_id = ?",
                    (guild_id,),
                ) as cur:
                    rows = await cur.fetchall()
            else:
                if not user_ids:
                    return []
                placeholders = ",".join("?" for _ in user_ids)
                async with db.execute(
                    f"SELECT * FROM user_profiles "
                    f"WHERE guild_id = ? AND user_id IN ({placeholders})",
                    (guild_id, *user_ids),
                ) as cur:
                    rows = await cur.fetchall()
        return [_row_to_profile(r) for r in rows]

    # ---------- server_settings ----------
    async def set_channel(self, guild_id: int, channel_id: int) -> None:
        sql = """
        INSERT INTO server_settings (guild_id, channel_id, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(guild_id) DO UPDATE SET
            channel_id = excluded.channel_id,
            updated_at = CURRENT_TIMESTAMP;
        """
        async with aiosqlite.connect(self.path) as db:
            await db.execute(sql, (guild_id, channel_id))
            await db.commit()

    async def get_channel(self, guild_id: int) -> Optional[int]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT channel_id FROM server_settings WHERE guild_id = ?",
                (guild_id,),
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else None

    async def set_notify_absent(self, guild_id: int, value: bool) -> None:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE server_settings SET notify_absent = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?",
                (1 if value else 0, guild_id),
            )
            if cur.rowcount == 0:
                raise LookupError(
                    "channel 未設定です。先に /config channel でチャンネルを設定してください。"
                )
            await db.commit()

    async def get_notify_absent(self, guild_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT notify_absent FROM server_settings WHERE guild_id = ?",
                (guild_id,),
            ) as cur:
                row = await cur.fetchone()
        return bool(row[0]) if row else False

    async def all_channels(self) -> list[tuple[int, int, bool]]:
        """全 (guild_id, channel_id, notify_absent) を返す。"""
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT guild_id, channel_id, notify_absent FROM server_settings"
            ) as cur:
                return [(r[0], r[1], bool(r[2])) for r in await cur.fetchall()]

    # ---------- command_permissions ----------
    async def set_permission(
        self,
        guild_id: int,
        command_name: str,
        mode: str,
        role_ids: list[int] | None = None,
    ) -> None:
        if mode not in ("owner", "everyone", "role"):
            raise ValueError(f"unknown mode: {mode}")
        csv = ",".join(str(r) for r in (role_ids or []))
        sql = """
        INSERT INTO command_permissions
            (guild_id, command_name, mode, role_ids, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(guild_id, command_name) DO UPDATE SET
            mode       = excluded.mode,
            role_ids   = excluded.role_ids,
            updated_at = CURRENT_TIMESTAMP;
        """
        async with aiosqlite.connect(self.path) as db:
            await db.execute(sql, (guild_id, command_name, mode, csv))
            await db.commit()

    async def get_permission(
        self, guild_id: int, command_name: str
    ) -> Optional[CommandPermission]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM command_permissions WHERE guild_id = ? AND command_name = ?",
                (guild_id, command_name),
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        ids = [int(s) for s in (row["role_ids"] or "").split(",") if s]
        return CommandPermission(
            guild_id=row["guild_id"],
            command_name=row["command_name"],
            mode=row["mode"],
            role_ids=ids,
        )

    async def list_permissions(self, guild_id: int) -> list[CommandPermission]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM command_permissions WHERE guild_id = ?",
                (guild_id,),
            ) as cur:
                rows = await cur.fetchall()
        return [
            CommandPermission(
                guild_id=r["guild_id"],
                command_name=r["command_name"],
                mode=r["mode"],
                role_ids=[int(s) for s in (r["role_ids"] or "").split(",") if s],
            )
            for r in rows
        ]
