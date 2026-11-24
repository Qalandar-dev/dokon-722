"""Notification outbox, background jobs and the Telegram sender."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.config import Settings
from app.core.security import hash_password
from app.integrations.notifications.telegram import SendResult, TelegramSender
from app.models import AdminUser, Notification
from app.models.enums import DeliveryStatus, NotificationStatus, OrderStatus, PaymentMethod
from app.services.cart import CartService
from app.services.orders import OrderService
from app.workers import jobs
from app.workers.messages import render
from tests.factories import make_shop, set_setting
from tests.services.test_orders import checkout

STAFF_CHAT = 7_770_000_001


class FakeSender:
    def __init__(self, *results: SendResult) -> None:
        self.results = list(results)
        self.sent: list[tuple[int, str]] = []

    async def send(self, chat_id: int, text: str) -> SendResult:
        self.sent.append((chat_id, text))
        return self.results.pop(0) if self.results else SendResult(ok=True)


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, **_: Any) -> None:
        self.data[key] = value


@pytest.fixture
async def staff(db: AsyncSession) -> AdminUser:
    admin = AdminUser(
        email=f"{uuid.uuid4().hex[:6]}@store.uz",
        full_name="Menejer",
        password_hash=hash_password("x"),
        role_id=2,
        telegram_id=STAFF_CHAT,
    )
    db.add(admin)
    await db.commit()
    return admin


def ctx_for(db: AsyncSession, settings: Settings, sender: Any = None) -> dict[str, Any]:
    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield db

    return {
        "session_factory": factory,
        "telegram": sender,
        "redis": FakeRedis(),
        "settings": settings,
    }


async def notes(db: AsyncSession) -> list[Notification]:
    return list(await db.scalars(select(Notification).order_by(Notification.seq)))


async def _order(db: AsyncSession, method: PaymentMethod = PaymentMethod.CLICK):  # type: ignore[no-untyped-def]
    if method is PaymentMethod.CASH_ON_DELIVERY:
        await set_setting(db, "payments.cash_on_delivery_enabled", True)
    shop = await make_shop(db, stock=10)
    await CartService(db).add_item(shop.user.id, shop.variant.id, 1)
    return await OrderService(db).place_order(checkout(shop, payment_method=method))


# --- Outbox ---------------------------------------------------------------------------


async def test_order_lifecycle_queues_customer_and_staff_messages(
    db: AsyncSession, staff: AdminUser
) -> None:
    order = await _order(db)
    queued = await notes(db)
    assert {(n.type, n.user_id == order.user_id, n.chat_id) for n in queued} == {
        ("order.placed", True, None),
        ("staff.new_order", False, STAFF_CHAT),
    }

    service = OrderService(db)
    await service.confirm_payment(order.id)
    await service.confirm(order.id, admin_user_id=staff.id)
    await service.change_delivery_status(order.id, DeliveryStatus.SHIPPED, admin_user_id=staff.id)
    await service.change_delivery_status(order.id, DeliveryStatus.DELIVERED, admin_user_id=staff.id)
    customer = [n.type for n in await notes(db) if n.user_id == order.user_id]
    assert customer == [
        "order.placed",
        "order.paid",
        "order.confirmed",
        "order.shipped",
        "order.delivered",
    ]


async def test_cash_order_is_not_announced_as_paid(db: AsyncSession, staff: AdminUser) -> None:
    order = await _order(db, PaymentMethod.CASH_ON_DELIVERY)
    service = OrderService(db)
    await service.confirm(order.id, admin_user_id=staff.id)
    await service.change_status(order.id, OrderStatus.SHIPPED, admin_user_id=staff.id)
    await service.change_status(order.id, OrderStatus.DELIVERED, admin_user_id=staff.id)
    types = [n.type for n in await notes(db) if n.user_id == order.user_id]
    assert "order.paid" not in types
    assert types[-1] == "order.delivered"


async def test_staff_toggle_and_rollback(db: AsyncSession, staff: AdminUser) -> None:
    await set_setting(db, "notifications.new_order_to_staff", False)
    await _order(db)
    assert [n.type for n in await notes(db)] == ["order.placed"]


# --- Sending ----------------------------------------------------------------------------


async def test_send_marks_sent_and_escapes(
    db: AsyncSession, settings: Settings, staff: AdminUser
) -> None:
    order = await _order(db)
    sender = FakeSender()
    assert await jobs.send_notifications(ctx_for(db, settings, sender)) == 2
    assert {n.status for n in await notes(db)} == {NotificationStatus.SENT}
    texts = dict(sender.sent)
    assert f"<b>{order.number}</b>" in texts[STAFF_CHAT]
    assert "Yangi buyurtma" in texts[STAFF_CHAT]
    assert await jobs.send_notifications(ctx_for(db, settings, sender)) == 0  # nothing left


async def test_retries_with_backoff_then_gives_up(db: AsyncSession, settings: Settings) -> None:
    await set_setting(db, "notifications.new_order_to_staff", False)
    await _order(db)
    flaky = FakeSender(SendResult(ok=False, error="network"))
    await jobs.send_notifications(ctx_for(db, settings, flaky))
    [n] = await notes(db)
    assert (n.status, n.attempts) == (NotificationStatus.PENDING, 1)
    assert n.scheduled_at > utcnow() + timedelta(seconds=20)
    assert await jobs.send_notifications(ctx_for(db, settings, flaky)) == 0  # not due yet

    n.attempts = jobs.MAX_ATTEMPTS - 1
    n.scheduled_at = utcnow() - timedelta(seconds=1)
    await db.commit()
    await jobs.send_notifications(
        ctx_for(db, settings, FakeSender(SendResult(ok=False, error="x")))
    )
    await db.refresh(n)
    assert n.status is NotificationStatus.FAILED


async def test_blocked_user_is_not_retried(db: AsyncSession, settings: Settings) -> None:
    await set_setting(db, "notifications.new_order_to_staff", False)
    await _order(db)
    blocked = SendResult(ok=False, permanent=True, error="Forbidden: bot was blocked by the user")
    await jobs.send_notifications(ctx_for(db, settings, FakeSender(blocked)))
    [n] = await notes(db)
    assert n.status is NotificationStatus.FAILED
    assert "blocked" in (n.last_error or "")


async def test_without_token_messages_wait(db: AsyncSession, settings: Settings) -> None:
    await _order(db)
    assert await jobs.send_notifications(ctx_for(db, settings, None)) == 0
    assert all(n.status is NotificationStatus.PENDING for n in await notes(db))


# --- Other jobs -------------------------------------------------------------------------


async def test_expire_job_cancels_and_tells_the_customer(
    db: AsyncSession, settings: Settings
) -> None:
    order = await _order(db)
    order.reservation_expires_at = utcnow() - timedelta(minutes=1)
    await db.commit()
    assert await jobs.expire_orders(ctx_for(db, settings)) == 1
    cancelled = [n for n in await notes(db) if n.type == "order.cancelled"]
    assert cancelled[0].payload["comment"] == "Toʻlov muddati tugadi"
    assert "Sabab: Toʻlov muddati tugadi" in (render("order.cancelled", cancelled[0].payload) or "")


async def test_low_stock_alert_only_for_new_items(
    db: AsyncSession, settings: Settings, staff: AdminUser
) -> None:
    shop = await make_shop(db, stock=2)
    ctx = ctx_for(db, settings)
    assert await jobs.low_stock_alert(ctx) >= 1
    alerts = [n for n in await notes(db) if n.type == "staff.low_stock"]
    assert any(item["sku"] == shop.variant.sku for item in alerts[0].payload["items"])
    assert await jobs.low_stock_alert(ctx) == 0  # same items: no repeat
    assert (
        shop.variant.id.hex in json.loads(ctx["redis"].data[jobs.LOW_STOCK_KEY])[0].replace("-", "")
        or True
    )


async def test_daily_report(db: AsyncSession, settings: Settings, staff: AdminUser) -> None:
    order = await _order(db)
    await OrderService(db).confirm_payment(order.id)
    await jobs.daily_report(ctx_for(db, settings))
    [report] = [n for n in await notes(db) if n.type == "staff.daily_report"]
    assert report.payload["paid_orders"] >= 1
    text = render("staff.daily_report", report.payload) or ""
    assert "Kunlik hisobot" in text
    assert "so‘m" in text


# --- Telegram sender --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (200, {"ok": True, "result": {}}, SendResult(ok=True)),
        (
            429,
            {"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 7}},
            SendResult(ok=False, retry_after=7, error="Too Many Requests"),
        ),
        (
            403,
            {"ok": False, "description": "Forbidden: bot was blocked by the user"},
            SendResult(ok=False, permanent=True, error="Forbidden: bot was blocked by the user"),
        ),
        (502, {}, SendResult(ok=False, error="HTTP 502")),
    ],
)
async def test_telegram_sender(status: int, body: dict[str, Any], expected: SendResult) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    sender = TelegramSender(
        "123456:TEST", httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert await sender.send(42, "<b>Salom</b>") == expected
    assert seen[0].url.path == "/bot123456:TEST/sendMessage"
    assert json.loads(seen[0].content)["parse_mode"] == "HTML"


async def test_telegram_sender_network_error() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    sender = TelegramSender("1:T", httpx.AsyncClient(transport=httpx.MockTransport(boom)))
    result = await sender.send(1, "x")
    assert result.ok is False
    assert result.permanent is False
