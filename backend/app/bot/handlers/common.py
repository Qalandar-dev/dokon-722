from __future__ import annotations

import contextlib
import logging
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from app.bot import keyboards as kb
from app.bot import texts as t
from app.bot.api_client import ApiError, StoreApi

logger = logging.getLogger(__name__)


async def show_main_menu(message: Message, text: str = t.MAIN_MENU) -> None:
    await message.answer(text, reply_markup=kb.main_menu())


async def edit_or_send(
    callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None
) -> None:
    """Replace the callback's message text; photo messages can't become text, so a new
    message is sent in that case."""
    message = callback.message
    if isinstance(message, Message) and message.text is not None:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc):
                return
            logger.info("Edit failed, sending new message: %s", exc)
    if isinstance(message, Message):
        await message.answer(text, reply_markup=markup)


async def photo_source(api: StoreApi, image: dict[str, Any], media_base_url: str | None) -> Any:
    """Telegram file id if the image was uploaded before, otherwise the file bytes."""
    if image.get("telegram_file_id"):
        return image["telegram_file_id"]
    data = await api.download(image["url"], media_base_url)
    return BufferedInputFile(data, filename=image["url"].rsplit("/", 1)[-1])


async def remember_file_id(
    api: StoreApi, image: dict[str, Any], sent: Message | list[Message]
) -> None:
    if image.get("telegram_file_id"):
        return
    message = sent[0] if isinstance(sent, list) else sent
    if message.photo:
        with contextlib.suppress(ApiError):
            await api.save_image_file_id(image["id"], message.photo[-1].file_id)


async def send_album(
    message: Message, api: StoreApi, images: list[dict[str, Any]], media_base_url: str | None
) -> None:
    media = [
        InputMediaPhoto(media=await photo_source(api, img, media_base_url)) for img in images[:10]
    ]
    sent = await message.answer_media_group(media)
    for img, msg in zip(images[:10], sent, strict=False):
        await remember_file_id(api, img, msg)
