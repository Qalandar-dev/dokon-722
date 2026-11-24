"""Middleware behaviour right after a server boot (monotonic clock near zero)."""

from __future__ import annotations

from typing import Any

import pytest
from aiogram.types import User

from app.bot import middlewares as mw


class FakeApi:
    def __init__(self) -> None:
        self.registered: list[int] = []

    async def register(self, telegram_id: int, *args: Any) -> dict[str, Any]:
        self.registered.append(telegram_id)
        return {}


USER = User(id=7, is_bot=False, first_name="A")


async def _handler(event: Any, data: dict[str, Any]) -> str:
    return "handled"


async def test_registers_user_even_just_after_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mw, "_clock", lambda: 5.0)  # 5 s after boot
    api = FakeApi()
    middleware = mw.ApiMiddleware(api, media_base_url=None)  # type: ignore[arg-type]
    await middleware(_handler, object(), {"event_from_user": USER})  # type: ignore[arg-type]
    await middleware(_handler, object(), {"event_from_user": USER})  # type: ignore[arg-type]
    assert api.registered == [7]  # once, then cached


async def test_throttling_lets_first_update_through_after_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = iter([0.1, 0.2, 1.0])
    monkeypatch.setattr(mw, "_clock", lambda: next(clock))
    middleware = mw.ThrottlingMiddleware(0.4)
    data = {"event_from_user": USER}
    assert await middleware(_handler, object(), data) == "handled"  # type: ignore[arg-type]
    assert await middleware(_handler, object(), data) is None  # too fast
    assert await middleware(_handler, object(), data) == "handled"  # type: ignore[arg-type]
