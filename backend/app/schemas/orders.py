from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models import Address, Order, User
from app.models.enums import (
    ActorType,
    DeliveryStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    StatusField,
)
from app.schemas.catalog import CartOut, DeliveryQuoteOut
from app.schemas.common import InputSchema, Money, Schema
from app.services import order_status as rules
from app.services.orders import CheckoutPreview

# --- Customer identity (bot) ---------------------------------------------------------


class RegisterIn(InputSchema):
    telegram_id: int = Field(gt=0)
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    username: str | None = Field(default=None, max_length=64)
    language_code: str | None = Field(default=None, max_length=16)


class PhoneIn(InputSchema):
    phone: str = Field(min_length=5, max_length=32)
    # Telegram's contact.user_id; the phone is verified only when it equals the sender.
    contact_user_id: int | None = None


class ProfileOut(Schema):
    id: uuid.UUID
    telegram_id: int
    first_name: str
    last_name: str | None
    username: str | None
    phone: str | None
    phone_verified: bool
    language: str
    created_at: datetime


class RegisterOut(BaseModel):
    profile: ProfileOut
    created: bool


class AddressIn(InputSchema):
    district_id: int
    recipient_name: str = Field(min_length=1, max_length=128)
    recipient_phone: str = Field(min_length=5, max_length=32)
    address_line: str = Field(min_length=1, max_length=255)
    landmark: str | None = Field(default=None, max_length=255)
    instructions: str | None = Field(default=None, max_length=1000)
    is_default: bool = False


class AddressOut(Schema):
    id: uuid.UUID
    district_id: int
    recipient_name: str
    recipient_phone: str
    address_line: str
    landmark: str | None
    instructions: str | None
    is_default: bool


def address_out(a: Address) -> AddressOut:
    return AddressOut.model_validate(a)


def profile_out(u: User) -> ProfileOut:
    return ProfileOut.model_validate(u)


# --- Checkout ----------------------------------------------------------------------------


class CheckoutPreviewIn(InputSchema):
    district_id: int
    delivery_method_id: uuid.UUID


class CheckoutPreviewOut(BaseModel):
    cart: CartOut
    region_name: str
    district_name: str
    delivery: DeliveryQuoteOut
    subtotal: Money
    discount: Money
    delivery_fee: Money
    total: Money

    @classmethod
    def build(cls, p: CheckoutPreview) -> CheckoutPreviewOut:
        return cls(
            cart=CartOut.build(p.cart),
            region_name=p.location.region_name,
            district_name=p.location.district_name,
            delivery=DeliveryQuoteOut.build(p.delivery),
            subtotal=p.subtotal,
            discount=p.discount,
            delivery_fee=p.delivery_fee,
            total=p.total,
        )


class OrderCreateIn(InputSchema):
    recipient_name: str = Field(min_length=1, max_length=128)
    recipient_phone: str = Field(min_length=5, max_length=32)
    district_id: int
    address_line: str = Field(min_length=1, max_length=255)
    landmark: str | None = Field(default=None, max_length=255)
    delivery_instructions: str | None = Field(default=None, max_length=1000)
    delivery_method_id: uuid.UUID
    payment_method: PaymentMethod
    customer_note: str | None = Field(default=None, max_length=1000)


class CancelIn(InputSchema):
    reason: str | None = Field(default=None, max_length=255)


# --- Order views -------------------------------------------------------------------------


class OrderItemOut(Schema):
    id: uuid.UUID
    product_id: uuid.UUID | None
    variant_id: uuid.UUID | None
    product_name: str
    variant_name: str
    sku: str
    attributes: dict[str, str]
    original_unit_price: Money
    unit_price: Money
    quantity: int
    line_total: Money


class StatusLabels(BaseModel):
    status: str
    payment_status: str
    delivery_status: str


def _labels(o: Order) -> StatusLabels:
    return StatusLabels(
        status=rules.ORDER_STATUS_LABELS[o.status],
        payment_status=rules.PAYMENT_STATUS_LABELS[o.payment_status],
        delivery_status=rules.DELIVERY_STATUS_LABELS[o.delivery_status],
    )


class OrderSummaryOut(BaseModel):
    id: uuid.UUID
    number: str
    status: OrderStatus
    payment_status: PaymentStatus
    delivery_status: DeliveryStatus
    payment_method: PaymentMethod
    labels: StatusLabels
    total: Money
    items_count: int
    created_at: datetime

    @classmethod
    def build(cls, o: Order) -> OrderSummaryOut:
        return cls(
            id=o.id,
            number=o.number,
            status=o.status,
            payment_status=o.payment_status,
            delivery_status=o.delivery_status,
            payment_method=o.payment_method,
            labels=_labels(o),
            total=o.total,
            items_count=sum(i.quantity for i in o.items),
            created_at=o.created_at,
        )


class OrderOut(OrderSummaryOut):
    """Customer view of an order (no internal notes)."""

    subtotal: Money
    discount_total: Money
    delivery_fee: Money
    promo_code: str | None
    recipient_name: str
    recipient_phone: str
    region_name: str
    district_name: str
    address_line: str
    landmark: str | None
    delivery_instructions: str | None
    delivery_method_name: str
    delivery_eta_min_days: int | None
    delivery_eta_max_days: int | None
    pickup_address: str | None
    customer_note: str | None
    cancel_reason: str | None
    can_cancel: bool
    reservation_expires_at: datetime | None
    paid_at: datetime | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
    items: list[OrderItemOut]

    @classmethod
    def build(cls, o: Order) -> OrderOut:  # type: ignore[override]
        base = OrderSummaryOut.build(o).model_dump()
        extra = {
            f: getattr(o, f)
            for f in cls.model_fields
            if f not in base and f not in {"items", "can_cancel"}
        }
        return cls(
            **base,
            **extra,
            can_cancel=o.status in rules.CUSTOMER_CANCELLABLE
            and o.payment_status is not PaymentStatus.PAID,
            items=[OrderItemOut.model_validate(i) for i in o.items],
        )


class HistoryOut(Schema):
    field: StatusField
    from_value: str | None
    to_value: str
    actor_type: ActorType
    admin_user_id: uuid.UUID | None
    comment: str | None
    created_at: datetime


class AdminOrderOut(OrderOut):
    user_id: uuid.UUID
    region_id: int
    district_id: int
    stock_state: str
    internal_note: str | None
    idempotency_key: str
    confirmed_at: datetime | None
    history: list[HistoryOut]

    @classmethod
    def build(cls, o: Order) -> AdminOrderOut:  # type: ignore[override]
        base = OrderOut.build(o).model_dump()
        return cls(
            **base,
            user_id=o.user_id,
            region_id=o.region_id,
            district_id=o.district_id,
            stock_state=o.stock_state.value,
            internal_note=o.internal_note,
            idempotency_key=o.idempotency_key,
            confirmed_at=o.confirmed_at,
            history=[HistoryOut.model_validate(h) for h in o.history],
        )


class AdminOrderListItemOut(OrderSummaryOut):
    user_id: uuid.UUID
    recipient_name: str
    recipient_phone: str
    region_name: str
    district_name: str

    @classmethod
    def build(cls, o: Order) -> AdminOrderListItemOut:  # type: ignore[override]
        return cls(
            **OrderSummaryOut.build(o).model_dump(),
            user_id=o.user_id,
            recipient_name=o.recipient_name,
            recipient_phone=o.recipient_phone,
            region_name=o.region_name,
            district_name=o.district_name,
        )


class StatusChangeIn(InputSchema):
    status: OrderStatus
    comment: str | None = Field(default=None, max_length=255)


class DeliveryStatusChangeIn(InputSchema):
    delivery_status: DeliveryStatus
    comment: str | None = Field(default=None, max_length=255)


class RefundIn(InputSchema):
    reason: str = Field(min_length=1, max_length=255)
    restock: bool = False


class InternalNoteIn(InputSchema):
    internal_note: str | None = Field(default=None, max_length=4000)
