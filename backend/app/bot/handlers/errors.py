"""Turns failures into friendly Uzbek messages. API business errors already carry a
message meant for the customer; anything unexpected is logged with its traceback."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ErrorEvent

from app.bot import texts as t
from app.bot.api_client import ApiError

logger = logging.getLogger("app.bot.errors")

router = Router(name="errors")


async def _tell(event: ErrorEvent, text: str) -> None:
    update = event.update
    if update.callback_query is not None:
        try:
            await update.callback_query.answer(t.truncate(text, 200), show_alert=True)
        except TelegramBadRequest:  # callback already answered or too old
            if update.callback_query.message is not None:
                await update.callback_query.message.answer(text)
    elif update.message is not None:
        await update.message.answer(text)


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    exc = event.exception
    if isinstance(exc, ApiError):
        if exc.status >= 500 or exc.status == 0:
            logger.warning("API problem: %s %s", exc.status, exc.code)
        await _tell(event, exc.message)
        return True
    if isinstance(exc, TelegramBadRequest) and "message is not modified" in str(exc):
        return True
    logger.exception("Unhandled bot error", exc_info=exc)
    try:
        await _tell(event, t.ERROR_GENERIC)
    except Exception:  # never let error reporting crash the dispatcher
        logger.exception("Could not report error to the user")
    return True
