"""Allowed status transitions. Pure functions: no database access.

Order status (commercial lifecycle):
    pending → confirmed → processing → shipped → out_for_delivery → delivered → refunded
    pending | confirmed | processing → cancelled → refunded (only if money was taken)

Payment status:
    pending → processing → paid → refunded
    pending | processing → failed → (retry) processing | paid
    pending | processing | failed → cancelled

Delivery status:
    awaiting_dispatch → preparing → shipped → out_for_delivery → delivered
    shipped | out_for_delivery → delivery_failed → out_for_delivery (retry) | returned

A returned parcel cancels the order and puts the goods back in stock; a paid order then
needs a refund. Staff cannot cancel a shipped order directly.
"""

from __future__ import annotations

from app.core.exceptions import InvalidTransitionError
from app.models.enums import DeliveryStatus, OrderStatus, PaymentMethod, PaymentStatus

O, P, D = OrderStatus, PaymentStatus, DeliveryStatus  # noqa: E741 - short aliases for tables

ORDER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    O.PENDING: frozenset({O.CONFIRMED, O.CANCELLED}),
    O.CONFIRMED: frozenset({O.PROCESSING, O.SHIPPED, O.CANCELLED}),
    O.PROCESSING: frozenset({O.SHIPPED, O.CANCELLED}),
    # → cancelled only when the parcel comes back (delivery status "returned").
    O.SHIPPED: frozenset({O.OUT_FOR_DELIVERY, O.DELIVERED, O.CANCELLED}),
    O.OUT_FOR_DELIVERY: frozenset({O.DELIVERED, O.CANCELLED}),
    O.DELIVERED: frozenset({O.REFUNDED}),
    O.CANCELLED: frozenset({O.REFUNDED}),
    O.REFUNDED: frozenset(),
}

PAYMENT_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    P.PENDING: frozenset({P.PROCESSING, P.PAID, P.FAILED, P.CANCELLED}),
    P.PROCESSING: frozenset({P.PAID, P.FAILED, P.CANCELLED}),
    P.FAILED: frozenset({P.PROCESSING, P.PAID, P.CANCELLED}),
    P.PAID: frozenset({P.REFUNDED}),
    P.CANCELLED: frozenset(),
    P.REFUNDED: frozenset(),
}

DELIVERY_TRANSITIONS: dict[DeliveryStatus, frozenset[DeliveryStatus]] = {
    D.AWAITING_DISPATCH: frozenset({D.PREPARING, D.SHIPPED}),
    D.PREPARING: frozenset({D.SHIPPED}),
    D.SHIPPED: frozenset({D.OUT_FOR_DELIVERY, D.DELIVERED, D.DELIVERY_FAILED}),
    D.OUT_FOR_DELIVERY: frozenset({D.DELIVERED, D.DELIVERY_FAILED}),
    D.DELIVERY_FAILED: frozenset({D.OUT_FOR_DELIVERY, D.RETURNED}),
    D.DELIVERED: frozenset(),
    D.RETURNED: frozenset(),
}

# Delivery progress drives the order status.
DELIVERY_TO_ORDER: dict[DeliveryStatus, OrderStatus] = {
    D.SHIPPED: O.SHIPPED,
    D.OUT_FOR_DELIVERY: O.OUT_FOR_DELIVERY,
    D.DELIVERED: O.DELIVERED,
}
ORDER_TO_DELIVERY: dict[OrderStatus, DeliveryStatus] = {
    O.PROCESSING: D.PREPARING,
    **{v: k for k, v in DELIVERY_TO_ORDER.items()},
}

CUSTOMER_CANCELLABLE = frozenset({O.PENDING, O.CONFIRMED})
STAFF_CANCELLABLE = frozenset({O.PENDING, O.CONFIRMED, O.PROCESSING})

ORDER_STATUS_LABELS: dict[OrderStatus, str] = {
    O.PENDING: "Yangi",
    O.CONFIRMED: "Tasdiqlangan",
    O.PROCESSING: "Tayyorlanmoqda",
    O.SHIPPED: "Joʻnatilgan",
    O.OUT_FOR_DELIVERY: "Yetkazilmoqda",
    O.DELIVERED: "Yetkazildi",
    O.CANCELLED: "Bekor qilingan",
    O.REFUNDED: "Pul qaytarilgan",
}
PAYMENT_STATUS_LABELS: dict[PaymentStatus, str] = {
    P.PENDING: "Toʻlov kutilmoqda",
    P.PROCESSING: "Toʻlov jarayonda",
    P.PAID: "Toʻlangan",
    P.FAILED: "Toʻlov amalga oshmadi",
    P.CANCELLED: "Toʻlov bekor qilingan",
    P.REFUNDED: "Pul qaytarilgan",
}
DELIVERY_STATUS_LABELS: dict[DeliveryStatus, str] = {
    D.AWAITING_DISPATCH: "Joʻnatish kutilmoqda",
    D.PREPARING: "Tayyorlanmoqda",
    D.SHIPPED: "Joʻnatildi",
    D.OUT_FOR_DELIVERY: "Kuryerda",
    D.DELIVERED: "Yetkazildi",
    D.DELIVERY_FAILED: "Yetkazib boʻlmadi",
    D.RETURNED: "Qaytarildi",
}


def ensure_order_transition(current: OrderStatus, target: OrderStatus) -> None:
    if target not in ORDER_TRANSITIONS[current]:
        raise InvalidTransitionError(
            f"Buyurtmani «{ORDER_STATUS_LABELS[current]}» holatidan "
            f"«{ORDER_STATUS_LABELS[target]}» holatiga oʻtkazib boʻlmaydi.",
            details={"from": current.value, "to": target.value},
        )


def ensure_payment_transition(current: PaymentStatus, target: PaymentStatus) -> None:
    if target not in PAYMENT_TRANSITIONS[current]:
        raise InvalidTransitionError(
            f"Toʻlovni «{PAYMENT_STATUS_LABELS[current]}» holatidan "
            f"«{PAYMENT_STATUS_LABELS[target]}» holatiga oʻtkazib boʻlmaydi.",
            details={"from": current.value, "to": target.value},
        )


def ensure_delivery_transition(current: DeliveryStatus, target: DeliveryStatus) -> None:
    if target not in DELIVERY_TRANSITIONS[current]:
        raise InvalidTransitionError(
            f"Yetkazib berishni «{DELIVERY_STATUS_LABELS[current]}» holatidan "
            f"«{DELIVERY_STATUS_LABELS[target]}» holatiga oʻtkazib boʻlmaydi.",
            details={"from": current.value, "to": target.value},
        )


def requires_payment_before_confirm(method: PaymentMethod) -> bool:
    """Online orders are confirmed only after the money arrives; cash orders right away."""
    return method is not PaymentMethod.CASH_ON_DELIVERY
