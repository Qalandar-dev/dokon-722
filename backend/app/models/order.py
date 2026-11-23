from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import (
    ActorType,
    DeliveryStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    StatusField,
    StockState,
)

if TYPE_CHECKING:
    from app.models.payment import Payment


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A placed order.

    Everything a customer saw at checkout (recipient, address, delivery method, prices)
    is copied here, so editing products, rates or regions never changes past orders.
    ``status``, ``payment_status`` and ``delivery_status`` are independent fields.
    """

    __tablename__ = "orders"
    __table_args__ = (
        # A retried checkout with the same key returns the existing order.
        UniqueConstraint("user_id", "idempotency_key"),
        CheckConstraint("subtotal >= 0", name="subtotal_non_negative"),
        CheckConstraint(
            "discount_total >= 0 AND discount_total <= subtotal", name="discount_within_subtotal"
        ),
        CheckConstraint("delivery_fee >= 0", name="delivery_fee_non_negative"),
        CheckConstraint(
            "total = subtotal - discount_total + delivery_fee", name="total_consistent"
        ),
        Index("ix_orders_user_created", "user_id", "created_at"),
        Index("ix_orders_status_created", "status", "created_at"),
        Index("ix_orders_payment_status", "payment_status"),
        # The expiry job scans only unpaid orders that hold a reservation.
        Index(
            "ix_orders_reservation_expires",
            "reservation_expires_at",
            postgresql_where=text("reservation_expires_at IS NOT NULL"),
        ),
    )

    # Filled by the database from order_number_seq (created in the initial migration).
    number: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text("'OS-' || lpad(nextval('order_number_seq')::text, 6, '0')"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    status: Mapped[OrderStatus] = mapped_column(
        str_enum(OrderStatus, "order_status"), default=OrderStatus.PENDING, server_default="pending"
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        str_enum(PaymentStatus, "order_payment_status"),
        default=PaymentStatus.PENDING,
        server_default="pending",
    )
    delivery_status: Mapped[DeliveryStatus] = mapped_column(
        str_enum(DeliveryStatus, "order_delivery_status"),
        default=DeliveryStatus.AWAITING_DISPATCH,
        server_default="awaiting_dispatch",
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        str_enum(PaymentMethod, "order_payment_method")
    )

    # Amounts (UZS)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", server_default="UZS")
    subtotal: Mapped[Decimal]
    discount_total: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    delivery_fee: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    total: Mapped[Decimal]

    # Recipient and address snapshot
    recipient_name: Mapped[str] = mapped_column(String(128))
    recipient_phone: Mapped[str] = mapped_column(String(20))
    region_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("regions.id", ondelete="RESTRICT"), index=True
    )
    district_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("districts.id", ondelete="RESTRICT")
    )
    region_name: Mapped[str] = mapped_column(String(100))
    district_name: Mapped[str] = mapped_column(String(100))
    address_line: Mapped[str] = mapped_column(String(255))
    landmark: Mapped[str | None] = mapped_column(String(255))
    delivery_instructions: Mapped[str | None] = mapped_column(Text)

    # Delivery method snapshot
    delivery_method_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("delivery_methods.id", ondelete="SET NULL")
    )
    delivery_method_name: Mapped[str] = mapped_column(String(100))
    delivery_eta_min_days: Mapped[int | None] = mapped_column(SmallInteger)
    delivery_eta_max_days: Mapped[int | None] = mapped_column(SmallInteger)
    pickup_address: Mapped[str | None] = mapped_column(String(255))

    # Promo snapshot
    promo_code_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("promo_codes.id", ondelete="SET NULL")
    )
    promo_code: Mapped[str | None] = mapped_column(String(32))

    stock_state: Mapped[StockState] = mapped_column(
        str_enum(StockState, "order_stock_state"),
        default=StockState.RESERVED,
        server_default="reserved",
    )
    idempotency_key: Mapped[str] = mapped_column(String(64))
    # Set while stock is reserved for an unpaid online payment; cleared when paid/released.
    reservation_expires_at: Mapped[datetime | None]

    customer_note: Mapped[str | None] = mapped_column(Text)
    internal_note: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(String(255))

    confirmed_at: Mapped[datetime | None]
    paid_at: Mapped[datetime | None]
    shipped_at: Mapped[datetime | None]
    delivered_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", passive_deletes=True
    )
    history: Mapped[list[OrderStatusHistory]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OrderStatusHistory.created_at",
    )
    payments: Mapped[list[Payment]] = relationship(back_populates="order")


class OrderItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Snapshot of one purchased variant. References are nullable so history survives
    product deletion."""

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("unit_price <= original_unit_price", name="unit_price_within_original"),
        CheckConstraint("line_total = unit_price * quantity", name="line_total_consistent"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"), index=True
    )
    product_name: Mapped[str] = mapped_column(String(200))
    variant_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    sku: Mapped[str] = mapped_column(String(64))
    attributes: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )
    ikpu_code: Mapped[str | None] = mapped_column(String(32))
    original_unit_price: Mapped[Decimal]
    unit_price: Mapped[Decimal]
    quantity: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[Decimal]

    order: Mapped[Order] = relationship(back_populates="items")


class OrderStatusHistory(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "order_status_history"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[StatusField] = mapped_column(str_enum(StatusField, "status_field"))
    from_value: Mapped[str | None] = mapped_column(String(32))
    to_value: Mapped[str] = mapped_column(String(32))
    actor_type: Mapped[ActorType] = mapped_column(str_enum(ActorType, "actor_type"))
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    comment: Mapped[str | None] = mapped_column(String(255))

    order: Mapped[Order] = relationship(back_populates="history")
