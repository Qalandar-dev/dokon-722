"""Bot middlewares: API client injection + auto-registration, and throttling."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from app.bot import texts as t
from app.bot.api_client import StoreApi

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

REGISTRATION_TTL_SECONDS = 3600


def _clock() -> float:
    """Seconds since an arbitrary point (boot). Separate function so tests can control it."""
    return time.monotonic()


class ApiMiddleware(BaseMiddleware):
    """Puts ``api`` into handler data and makes sure the user exists in the store.

    Registration is refreshed at most once an hour per user (keeps names/usernames current
    without calling the API on every click).
    """

    def __init__(self, api: StoreApi, *, media_base_url: str | None) -> None:
        self.api = api
        self.media_base_url = media_base_url
        self._registered: dict[int, float] = {}

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        data["api"] = self.api
        data["media_base_url"] = self.media_base_url
        user: User | None = data.get("event_from_user")
        if user is not None and not user.is_bot:
            now = _clock()
            # Note: monotonic() starts near 0 at boot, so "never registered" must be None,
            # not 0 — otherwise nobody is registered during the first hour after a restart.
            last = self._registered.get(user.id)
            if last is None or now - last > REGISTRATION_TTL_SECONDS:
                result = await self.api.register(
                    user.id, user.first_name, user.last_name, user.username, user.language_code
                )
                data["registration"] = result
                self._registered[user.id] = now
        return await handler(event, data)

    def forget(self, user_id: int) -> None:
        self._registered.pop(user_id, None)


class ThrottlingMiddleware(BaseMiddleware):
    """Drops updates arriving faster than ``interval`` seconds from the same user.

    Protects the API from button mashing; per process (one bot instance).
    """

    def __init__(self, interval: float = 0.4) -> None:
        self.interval = interval
        self._last: dict[int, float] = {}

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None or self.interval <= 0:
            return await handler(event, data)
        now = _clock()
        last = self._last.get(user.id)
        if last is not None and now - last < self.interval:
            if isinstance(event, CallbackQuery):
                await event.answer(t.TOO_FAST)
            return None
        self._last[user.id] = now
        if len(self._last) > 50_000:  # bound memory
            self._last.clear()
        return await handler(event, data)


async def reply(event: Message | CallbackQuery, text: str, **kwargs: Any) -> None:
    """Answer a message or a callback's message with new text."""
    target = event.message if isinstance(event, CallbackQuery) else event
    if target is not None:
        await target.answer(text, **kwargs)  # type: ignore[union-attr]
