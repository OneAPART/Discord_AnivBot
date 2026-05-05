"""通知 Embed の thumbnail に使うアバター URL を解決する。

X(Twitter) のアバターは https://unavatar.io/x/<handle> 経由で取得する。
unavatar.io 側で公開キャッシュ + フォールバックを持つため、API キー不要・取得失敗時は
プレースホルダ画像が返る。
"""
from __future__ import annotations

from typing import Optional

import discord


def twitter_avatar_url(handle: Optional[str]) -> Optional[str]:
    if not handle:
        return None
    h = handle.lstrip("@")
    return f"https://unavatar.io/x/{h}"


def discord_avatar_url(member: Optional[discord.abc.User]) -> Optional[str]:
    if member is None:
        return None
    try:
        return member.display_avatar.url
    except Exception:  # noqa: BLE001 - 念のため
        return None


def resolve_avatar_url(
    *,
    source: str,
    twitter_id: Optional[str],
    member: Optional[discord.abc.User],
) -> Optional[str]:
    """設定された優先順位に従ってアバター URL を返す。

    source='twitter': X 優先、未登録なら Discord
    source='discord': Discord 優先、取得不能なら X
    """
    twitter = twitter_avatar_url(twitter_id)
    discord_av = discord_avatar_url(member)

    if source == "discord":
        return discord_av or twitter
    # 既定 / 'twitter'
    return twitter or discord_av
