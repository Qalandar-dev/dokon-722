"""Background jobs. Each one is a function of the arq ``ctx`` dict:

- ``session_factory``: ``() -> async context manager yielding an AsyncSession``
- ``telegram``: ``TelegramSender`` or ``None`` (no BOT_TOKEN → nothing is sent, rows wait)
- ``redis``: the arq Redis connection
- ``settings``: application settings
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from app.core.clock import utcnow
from app.models import Notification, Order, User
from app.models.enums import NotificationStatus, OrderStatus
from app.services.inventory import InventoryService
from app.services.notifications import enqueue_staff
from app.services.orders import OrderService
from app.services.reports import DateRange, ReportService, store_tz
from app.workers.messages import render

logger = logging.getLogger("app.worker")

MAX_ATTEMPTS = 6
BATCH = 50
LOW_STOCK_KEY = "alerts:low_stock:last"


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * 2 ** max(attempts - 1, 0), 3600))


async def send_notifications(ctx: dict[str, Any]) -> int:
    """Send due notifications; retry with backoff; give up after MAX_ATTEMPTS."""
    sender = ctx.get("telegram")
    if sender is None:
        return 0
    sent = 0
    async with ctx["session_factory"]() as session:
        rows = (
            await session.execute(
                select(Notification, User.telegram_id)
                .outerjoin(User, User.id == Notification.user_id)
                .where(
                    Notification.status == NotificationStatus.PENDING,
                    Notification.scheduled_at <= utcnow(),
                )
                .order_by(Notification.scheduled_at, Notification.seq)
                .limit(BATCH)
                .with_for_update(of=Notification, skip_locked=True)
            )
        ).all()
        for notification, user_chat in rows:
            chat_id = notification.chat_id or user_chat
            text = render(notification.type, notification.payload)
            if chat_id is None or text is None:
                notification.status = NotificationStatus.FAILED
                notification.last_error = "no recipient" if chat_id is None else "unknown type"
                continue
            result = await sender.send(chat_id, text)
            notification.attempts += 1
            if result.ok:
                notification.status = NotificationStatus.SENT
                notification.sent_at = utcnow()
                sent += 1
            elif result.permanent or notification.attempts >= MAX_ATTEMPTS:
                notification.status = NotificationStatus.FAILED
                notification.last_error = result.error
            else:
                notification.last_error = result.error
                delay = (
                    timedelta(seconds=result.retry_after)
                    if result.retry_after
                    else _backoff(notification.attempts)
                )
                notification.scheduled_at = utcnow() + delay
        await session.commit()
    if sent:
        logger.info("Sent %s notifications", sent)
    return sent


async def expire_orders(ctx: dict[str, Any]) -> int:
    async with ctx["session_factory"]() as session:
        expired = await OrderService(session).expire_unpaid()
    if expired:
        logger.info("Expired %s unpaid orders", expired)
    return expired


async def low_stock_alert(ctx: dict[str, Any]) -> int:
    """Tell staff about variants that *became* low since the last check (no repeats)."""
    redis = ctx["redis"]
    async with ctx["session_factory"]() as session:
        items = await InventoryService(session).low_stock(limit=200)
        current = {str(i.variant_id) for i in items}
        raw = await redis.get(LOW_STOCK_KEY)
        previous = set(json.loads(raw)) if raw else set()
        fresh = [i for i in items if str(i.variant_id) not in previous]
        await redis.set(LOW_STOCK_KEY, json.dumps(sorted(current)))
        if not fresh:
            return 0
        payload = {
            "items": [
                {
                    "name": i.product_name + (f" ({i.variant_name})" if i.variant_name else ""),
                    "sku": i.sku,
                    "available": i.available,
                }
                for i in fresh[:20]
            ],
            "more": max(len(fresh) - 20, 0),
        }
        await enqueue_staff(
            session,
            ctx["settings"],
            "staff.low_stock",
            payload,
            setting_key="notifications.low_stock_to_staff",
        )
        await session.commit()
        return len(fresh)


async def daily_report(ctx: dict[str, Any]) -> None:
    today = utcnow().astimezone(store_tz()).date()
    period = DateRange(today, today)
    async with ctx["session_factory"]() as session:
        reports = ReportService(session)
        sales = await reports.sales(period, "day")
        top = await reports.top_products(period, limit=3)
        created = (Order.created_at >= period.start_utc, Order.created_at < period.end_utc)
        new_orders = await session.scalar(select(func.count()).where(*created)) or 0
        cancelled = (
            await session.scalar(
                select(func.count()).where(*created, Order.status == OrderStatus.CANCELLED)
            )
            or 0
        )
        day = sales[0] if sales else {"revenue": 0, "orders": 0}
        await enqueue_staff(
            session,
            ctx["settings"],
            "staff.daily_report",
            {
                "date": today.strftime("%d.%m.%Y"),
                "revenue": str(day["revenue"]),
                "paid_orders": day["orders"],
                "new_orders": new_orders,
                "cancelled": cancelled,
                "top": [{"product_name": p["product_name"], "units": p["units"]} for p in top],
            },
        )
        await session.commit()
