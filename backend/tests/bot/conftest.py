"""Bot test harness.

Real dispatcher, real handlers, real API (in-process, on the rolled-back test DB).
Only Telegram is fake: ``FakeTelegram`` records every Bot API call and returns
plausible results.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    AnswerCallbackQuery,
    SendMediaGroup,
    SendPhoto,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    Contact,
    InlineKeyboardMarkup,
    Message,
    PhotoSize,
    Update,
    User,
)

from app.bot.api_client import StoreApi
from app.bot.main import create_dispatcher
from app.core.config import Settings

_ids = itertools.count(1000)
BOT_USER = User(id=42, is_bot=True, first_name="Store bot", username="store_bot")


class FakeTelegram(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        return None

    async def stream_content(self, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def _message(self, method: Any) -> Message:
        photo = None
        if isinstance(method, SendPhoto):
            photo = [
                PhotoSize(file_id=f"tg-file-{next(_ids)}", file_unique_id="u", width=1, height=1)
            ]
        return Message(
            message_id=next(_ids),
            date=datetime.now(UTC),
            chat=Chat(id=getattr(method, "chat_id", 1) or 1, type="private"),
            from_user=BOT_USER,
            text=getattr(method, "text", None),
            caption=getattr(method, "caption", None),
            photo=photo,
        )

    # The `timeout` parameter is part of aiogram's BaseSession signature.
    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> Any:
        self.calls.append(method)
        if isinstance(method, SendMediaGroup):
            return [
                self._message(SendPhoto(chat_id=method.chat_id, photo="x")) for _ in method.media
            ]
        returning = method.__returning__
        if returning is Message:
            return self._message(method)
        return True


class Chatter:
    """Plays one Telegram user talking to the bot."""

    def __init__(self, bot: Bot, dp: Any, telegram: FakeTelegram, user_id: int) -> None:
        self.bot, self.dp, self.telegram = bot, dp, telegram
        self.user = User(
            id=user_id,
            is_bot=False,
            first_name="Aziza",
            last_name="Karimova",
            username="aziza_k",
            language_code="uz",
        )
        self.chat = Chat(id=user_id, type="private")
        self._seen = 0

    async def _feed(self, update: Update) -> list[TelegramMethod[Any]]:
        await self.dp.feed_update(self.bot, update)
        new = self.telegram.calls[self._seen :]
        self._seen = len(self.telegram.calls)
        return new

    async def say(self, text: str | None = None, *, contact: Contact | None = None) -> list[Any]:
        message = Message(
            message_id=next(_ids),
            date=datetime.now(UTC),
            chat=self.chat,
            from_user=self.user,
            text=text,
            contact=contact,
        )
        return await self._feed(Update(update_id=next(_ids), message=message))

    async def click(self, data: str, *, on_photo: bool = False) -> list[Any]:
        message = Message(
            message_id=next(_ids),
            date=datetime.now(UTC),
            chat=self.chat,
            from_user=BOT_USER,
            text=None if on_photo else "…",
            photo=[PhotoSize(file_id="p", file_unique_id="u", width=1, height=1)]
            if on_photo
            else None,
        )
        query = CallbackQuery(
            id=str(next(_ids)), from_user=self.user, chat_instance="ci", data=data, message=message
        )
        return await self._feed(Update(update_id=next(_ids), callback_query=query))

    def share_contact(self, phone: str, *, own: bool = True) -> Contact:
        return Contact(phone_number=phone, first_name="Aziza", user_id=self.user.id if own else 1)


def texts(calls: list[Any]) -> str:
    """All visible text of the given calls (messages, edits, captions, alerts)."""
    out = []
    for c in calls:
        for attr in ("text", "caption"):
            value = getattr(c, attr, None)
            if isinstance(value, str):
                out.append(value)
    return "\n".join(out)


def alerts(calls: list[Any]) -> list[str]:
    return [c.text for c in calls if isinstance(c, AnswerCallbackQuery) and c.text]


def buttons(calls: list[Any]) -> dict[str, str]:
    """Inline button text → callback data, from the last call that had an inline keyboard."""
    for c in reversed(calls):
        markup = getattr(c, "reply_markup", None)
        if isinstance(markup, InlineKeyboardMarkup):
            return {b.text: b.callback_data or "" for row in markup.inline_keyboard for b in row}
    return {}


def button(calls: list[Any], contains: str) -> str:
    found = [data for text, data in buttons(calls).items() if contains in text]
    assert found, f"no button containing {contains!r} in {list(buttons(calls))}"
    return found[0]


@pytest.fixture(scope="session")
def dispatcher(settings_session: Settings) -> Any:
    """One dispatcher for the whole run (aiogram routers attach to a single parent)."""
    placeholder = StoreApi(httpx.AsyncClient(), bot_secret="")
    return create_dispatcher(placeholder, MemoryStorage(), media_base_url=None, throttle_interval=0)


@pytest.fixture
async def chat(api: httpx.AsyncClient, settings: Settings, dispatcher: Any) -> Any:
    telegram = FakeTelegram()
    bot = Bot(
        token="42:TEST-TOKEN-NOT-REAL",
        session=telegram,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    middleware = dispatcher["api_middleware"]
    middleware.api = StoreApi(api, bot_secret=settings.bot_api_secret.get_secret_value())
    middleware._registered.clear()  # the database is fresh for every test
    dispatcher.fsm.storage.storage.clear()

    def new_user(user_id: int) -> Chatter:
        return Chatter(bot, dispatcher, telegram, user_id)

    return new_user
