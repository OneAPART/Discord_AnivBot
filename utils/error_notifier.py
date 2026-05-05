"""エラー通知 (HTTP Webhook) ユーティリティ。

`.env` に `ERROR_WEBHOOK_URL` が設定されていれば、
未捕捉エラー発生時にその URL へ JSON を POST する。

スキーマ: README.md の「エラー通知 Webhook」を参照。
"""
from __future__ import annotations

import asyncio
import logging
import os
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp


log = logging.getLogger(__name__)

_BOT_NAME = "AnniversaryBot"
_TIMEOUT_SEC = 5
_MAX_TRACEBACK_CHARS = 6000  # ペイロード肥大化防止


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def build_payload(
    *,
    level: str,
    message: str,
    exception: Optional[BaseException] = None,
    logger_name: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "bot": _BOT_NAME,
        "env": os.getenv("ENV_NAME", "unknown"),
        "level": level,
        "timestamp": _now_iso(),
        "logger": logger_name or "",
        "message": message,
    }
    if exception is not None:
        tb = "".join(
            traceback.format_exception(type(exception), exception, exception.__traceback__)
        )
        if len(tb) > _MAX_TRACEBACK_CHARS:
            tb = tb[: _MAX_TRACEBACK_CHARS] + "\n... (truncated)"
        payload["exception"] = {
            "type": type(exception).__name__,
            "message": str(exception),
            "traceback": tb,
        }
    else:
        payload["exception"] = None

    payload["context"] = context or {}
    return payload


class ErrorNotifier:
    """非ブロッキングで HTTP POST する通知クライアント。

    使い方:
        notifier = ErrorNotifier(os.getenv("ERROR_WEBHOOK_URL"))
        await notifier.start()
        notifier.notify(level="ERROR", message="...", exception=e, context={...})
        await notifier.close()
    """

    def __init__(self, url: Optional[str]):
        self.url = url.strip() if url else None
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    async def start(self) -> None:
        if not self.enabled:
            return
        timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SEC)
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def notify(
        self,
        *,
        level: str,
        message: str,
        exception: Optional[BaseException] = None,
        logger_name: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """送信は fire-and-forget。失敗してもアプリ動作には影響させない。"""
        if not self.enabled or self._session is None:
            return
        payload = build_payload(
            level=level,
            message=message,
            exception=exception,
            logger_name=logger_name,
            context=context,
        )
        try:
            asyncio.create_task(self._post(payload))
        except RuntimeError:
            # event loop 不在時 (テスト等)
            log.debug("event loop not running; skip error notify")

    async def _post(self, payload: dict[str, Any]) -> None:
        assert self._session is not None
        assert self.url is not None
        try:
            async with self._session.post(self.url, json=payload) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    log.warning(
                        "Error webhook returned %s: %s", resp.status, body[:500]
                    )
        except Exception as e:  # noqa: BLE001 - 通知失敗で本体が落ちないように
            log.warning("Error webhook POST failed: %s", e)
