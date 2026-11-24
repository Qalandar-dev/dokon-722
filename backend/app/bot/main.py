"""Telegram bot entrypoint: ``python -m app.bot.main``.

The bot is a client of the store API (``API_INTERNAL_URL``): it holds no business
rules. Conversation state (FSM) is kept in Redis so a restart does not lose a
customer's checkout in progress.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage, DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from app.bot.api_client import StoreApi
from app.bot.handlers import build_router
from app.bot.middlewares import ApiMiddleware, ThrottlingMiddleware
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger("app.bot")

COMMANDS = [
    BotCommand(command="start", description="Boshlash"),
    BotCommand(command="menu", description="Bosh menyu"),
    BotCommand(command="help", description="Aloqa"),
    BotCommand(command="cancel", description="Joriy amalni bekor qilish"),
]


def create_dispatcher(
    api: StoreApi,
    storage: BaseStorage,
    *,
    media_base_url: str | None,
    throttle_interval: float = 0.4,
) -> Dispatcher:
    dp = Dispatcher(storage=storage)
    throttling = ThrottlingMiddleware(throttle_interval)
    api_middleware = ApiMiddleware(api, media_base_url=media_base_url)
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(throttling)
        observer.outer_middleware(api_middleware)
    dp.include_router(build_router())
    dp["api_middleware"] = api_middleware  # lets tests swap the API client
    return dp


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)

    if settings.bot_token is None:
        logger.critical("BOT_TOKEN is not set; the bot cannot start.")
        sys.exit(2)

    storage = RedisStorage.from_url(
        str(settings.redis_url),
        key_builder=DefaultKeyBuilder(prefix="fsm", with_destiny=True),
        state_ttl=60 * 60 * 24,  # abandoned checkouts expire after a day
        data_ttl=60 * 60 * 24,
    )
    api = StoreApi.create(settings.api_internal_url, settings.bot_api_secret.get_secret_value())
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher(
        api, storage, media_base_url=settings.bot_media_base_url or settings.api_internal_url
    )
    try:
        await bot.set_my_commands(COMMANDS)
        logger.info("Bot polling started")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await api.close()
        await bot.session.close()
        await storage.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
