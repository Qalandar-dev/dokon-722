"""Minimal Telegram Bot API sender (sendMessage) for the worker.

The bot token is part of the URL, so httpx's own request logging is silenced and every
log record goes through the redaction filter (which masks bot tokens) anyway.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logging.getLogger("httpx").setLevel(logging.WARNING)

API = "https://api.telegram.org"


@dataclass(frozen=True, slots=True)
class SendResult:
    ok: bool
    #: Do not retry (user blocked the bot, chat does not exist, bad request).
    permanent: bool = False
    retry_after: int | None = None
    error: str | None = None


class TelegramSender:
    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        self._url = f"{API}/bot{token}/sendMessage"
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))

    async def close(self) -> None:
        await self._client.aclose()

    async def send(self, chat_id: int, text: str) -> SendResult:
        try:
            response = await self._client.post(
                self._url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
            )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"network: {exc.__class__.__name__}")
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code == 200 and data.get("ok"):
            return SendResult(ok=True)
        description = str(data.get("description") or f"HTTP {response.status_code}")[:500]
        if response.status_code == 429:
            retry = (data.get("parameters") or {}).get("retry_after")
            return SendResult(ok=False, retry_after=int(retry) if retry else 30, error=description)
        # 400 (chat not found / bad request) and 403 (blocked by the user) won't fix themselves.
        permanent = response.status_code in (400, 403)
        return SendResult(ok=False, permanent=permanent, error=description)
