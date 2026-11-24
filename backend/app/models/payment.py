from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import PaymentProvider, PaymentStatus
from app.models.order import Order


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One payment attempt for an order."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        # An order can be paid at most once, whatever the provider.
        Index(
            "uq_payments_order_paid",
            "order_id",
            unique=True,
            postgresql_where=text("status = 'paid'"),
        ),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[PaymentProvider] = mapped_column(str_enum(PaymentProvider, "payment_provider"))
    amount: Mapped[Decimal]
    status: Mapped[PaymentStatus] = mapped_column(
        str_enum(PaymentStatus, "payment_status"),
        default=PaymentStatus.PENDING,
        server_default="pending",
    )
    # True for PAYMENT_MODE=mock: never real money, always shown as a test payment.
    is_simulated: Mapped[bool] = mapped_column(default=False, server_default=false())
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    paid_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    refunded_at: Mapped[datetime | None]

    order: Mapped[Order] = relationship(back_populates="payments")
    transactions: Mapped[list[PaymentTransaction]] = relationship(
        back_populates="payment", order_by="PaymentTransaction.created_at"
    )


class PaymentTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A provider-side transaction (Click click_trans_id, Payme transaction id).

    The unique (provider, external_id) pair is what makes duplicate callbacks harmless.
    Provider-specific states and payloads are stored as received (secrets redacted).
    """

    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("provider", "external_id"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[PaymentProvider] = mapped_column(
        str_enum(PaymentProvider, "payment_transaction_provider")
    )
    external_id: Mapped[str] = mapped_column(String(128))
    provider_state: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal]
    provider_created_at: Mapped[datetime | None]
    performed_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None] = mapped_column(String(64))
    request_payload: Mapped[dict[str, Any] | None]
    response_payload: Mapped[dict[str, Any] | None]

    payment: Mapped[Payment] = relationship(back_populates="transactions")
