"""Outbound Telegram notifications, written to the ``notifications`` table (outbox).

They are added in the same transaction as the change they describe, so a notification is
never lost and never sent for a change that was rolled back. The worker sends them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import AdminUser, Notification, Order
from app.models.enums import DeliveryStatus, OrderStatus, PaymentMethod, PaymentStatus, StatusField
from app.services.store_settings import StoreSettingsService

# (field, new value) → customer notification type
_CUSTOMER_EVENTS: dict[tuple[StatusField, str], str] = {
    (StatusField.STATUS, OrderStatus.CONFIRMED.value): "order.confirmed",
    (StatusField.STATUS, OrderStatus.SHIPPED.value): "order.shipped",
    (StatusField.STATUS, OrderStatus.OUT_FOR_DELIVERY.value): "order.out_for_delivery",
    (StatusField.STATUS, OrderStatus.DELIVERED.value): "order.delivered",
    (StatusField.STATUS, OrderStatus.CANCELLED.value): "order.cancelled",
    (StatusField.STATUS, OrderStatus.REFUNDED.value): "order.refunded",
    (StatusField.PAYMENT_STATUS, PaymentStatus.PAID.value): "order.paid",
    (StatusField.DELIVERY_STATUS, DeliveryStatus.DELIVERY_FAILED.value): "order.delivery_failed",
}


def order_payload(order: Order, comment: str | None = None) -> dict[str, Any]:
    return {
        "order_id": str(order.id),
        "number": order.number,
        "total": str(order.total),
        "payment_method": order.payment_method.value,
        "delivery_method": order.delivery_method_name,
        "comment": comment,
    }


def customer_event(
    order: Order, field: StatusField, from_value: str | None, to_value: str
) -> str | None:
    if field is StatusField.STATUS and from_value is None and to_value == OrderStatus.PENDING.value:
        return "order.placed"
    event = _CUSTOMER_EVENTS.get((field, to_value))
    # Cash is collected on delivery; "delivered" already tells the customer.
    if event == "order.paid" and order.payment_method is PaymentMethod.CASH_ON_DELIVERY:
        return None
    return event


def enqueue_customer(
    session: AsyncSession, order: Order, event: str, comment: str | None = None
) -> None:
    session.add(
        Notification(user_id=order.user_id, type=event, payload=order_payload(order, comment))
    )


async def staff_chat_ids(session: AsyncSession, settings: Settings) -> list[int]:
    """TELEGRAM_ADMIN_IDS plus active staff who linked their Telegram account."""
    linked = await session.scalars(
        select(AdminUser.telegram_id).where(AdminUser.is_active, AdminUser.telegram_id.is_not(None))
    )
    return sorted({*settings.telegram_admin_ids, *(t for t in linked if t)})


async def enqueue_staff(
    session: AsyncSession,
    settings: Settings,
    event: str,
    payload: dict[str, Any],
    *,
    setting_key: str | None = None,
) -> int:
    """One notification per staff chat; skipped when the store setting turns it off."""
    if setting_key and not await StoreSettingsService(session).get(setting_key, True):
        return 0
    chats = await staff_chat_ids(session, settings)
    for chat_id in chats:
        session.add(Notification(chat_id=chat_id, type=event, payload=payload))
    return len(chats)
