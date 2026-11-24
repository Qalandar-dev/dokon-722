"""Background worker (arq on Redis): ``arq app.workers.main.WorkerSettings``.

Schedule (UTC):
- every 10 s   send queued Telegram notifications
- every minute cancel unpaid online orders whose reservation expired
- hourly :07   low-stock alert to staff (only newly low items)
- 15:00 daily  sales report to staff (20:00 Tashkent)
- every minute heartbeat (container health check)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.session import dispose_engine, get_sessionmaker
from app.integrations.notifications.telegram import TelegramSender
from app.workers import jobs

logger = logging.getLogger("app.worker")

HEARTBEAT_KEY = "worker:heartbeat"


async def heartbeat(ctx: dict[str, Any]) -> str:
    now = datetime.now(UTC).isoformat()
    await ctx["redis"].set(HEARTBEAT_KEY, now, ex=180)
    return now


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    ctx["settings"] = settings
    ctx["session_factory"] = get_sessionmaker()
    ctx["telegram"] = (
        TelegramSender(settings.bot_token.get_secret_value()) if settings.bot_token else None
    )
    if ctx["telegram"] is None:
        logger.warning("BOT_TOKEN is not set: notifications are queued but not sent")
    await heartbeat(ctx)
    logger.info("Worker started")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    if ctx.get("telegram") is not None:
        await ctx["telegram"].close()
    await dispose_engine()
    logger.info("Worker stopped")


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
    functions: ClassVar[list[Any]] = []
    cron_jobs: ClassVar[list[Any]] = [
        cron(jobs.send_notifications, second={0, 10, 20, 30, 40, 50}, run_at_startup=True),
        cron(jobs.expire_orders, second=5),
        cron(jobs.low_stock_alert, minute=7, second=30),
        cron(jobs.daily_report, hour=15, minute=0, second=0),
        cron(heartbeat, second=0),
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = 10
    job_timeout = 120
    health_check_interval = 30
