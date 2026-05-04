"""共通ユーティリティ。"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional


_TWITTER_RE = re.compile(r"^@?([A-Za-z0-9_]{1,15})$")


def normalize_twitter(raw: Optional[str]) -> Optional[str]:
    """Twitter ハンドルを `@username` 形式に正規化。空入力は None。"""
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    m = _TWITTER_RE.match(raw)
    if not m:
        raise ValueError("Twitter ID は半角英数字とアンダースコア（最大15文字）で入力してください。")
    return f"@{m.group(1)}"


def twitter_url(handle: str) -> str:
    return f"https://x.com/{handle.lstrip('@')}"


def parse_md(text: str) -> tuple[int, int]:
    """`MM/DD` 等を (month, day) にパース。"""
    text = text.strip().replace("-", "/").replace(".", "/")
    parts = [p for p in text.split("/") if p]
    if len(parts) != 2:
        raise ValueError("月日は `MM/DD` 形式で入力してください（例: 04/15）。")
    month, day = int(parts[0]), int(parts[1])
    _validate_md(month, day)
    return month, day


def parse_ymd(text: str) -> tuple[int, int, int]:
    """`YYYY/MM/DD` を (year, month, day) にパース。"""
    text = text.strip().replace("-", "/").replace(".", "/")
    parts = [p for p in text.split("/") if p]
    if len(parts) != 3:
        raise ValueError("活動開始日は `YYYY/MM/DD` 形式で入力してください（例: 2018/04/15）。")
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    if year < 1900 or year > date.today().year:
        raise ValueError("活動開始年は 1900 〜 今年 の範囲で入力してください。")
    _validate_md(month, day)
    # 実在日のチェック (うるう年含む)
    try:
        date(year, month, day)
    except ValueError as e:
        raise ValueError(f"日付が不正です: {e}") from e
    return year, month, day


def _validate_md(month: int, day: int) -> None:
    if not (1 <= month <= 12):
        raise ValueError("月は 1〜12 で入力してください。")
    if not (1 <= day <= 31):
        raise ValueError("日は 1〜31 で入力してください。")
    # 月別の最大日数
    max_days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    if day > max_days:
        raise ValueError(f"{month}月は最大 {max_days} 日までです。")
