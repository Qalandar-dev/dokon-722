"""Payment rules shared by every provider.

- Only the order's owner can start a payment, only for an unpaid online order.
- An order has at most one open payment per provider; starting again reuses it.
- A provider success is applied only after checking the amount against our own records,
  inside a row lock, and is recorded once per provider transaction id: a repeated
  callback returns the stored result instead of applying it twice.
- The order becomes paid only through ``record_success`` (never from a redirect).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import utcnow
from app.core.config import Settings
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.logging import redact
from app.integrations.payments.base import ProviderNotConfiguredError
from app.integrations.payments.registry import provider_for
from app.models import Order, Payment, PaymentTransaction
from app.models.enums import OrderStatus, PaymentMethod, PaymentProvider, PaymentStatus, StockState
from app.services.orders import Actor, OrderService

ONLINE = frozenset({PaymentMethod.CLICK, PaymentMethod.PAYME})
OPEN = frozenset({PaymentStatus.PENDING, PaymentStatus.PROCESSING})


@dataclass(frozen=True, slots=True)
class StartedPayment:
    payment: Payment
    checkout_url: str


def _safe_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Store provider payloads without secrets (signatures, tokens, card data)."""
    if payload is None:
        return None
    return {k: redact(str(v)) for k, v in payload.items()}


class PaymentService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def get(self, payment_id: uuid.UUID, *, lock: bool = False) -> Payment:
        stmt = (
            select(Payment)
            .where(Payment.id == payment_id)
            .options(selectinload(Payment.transactions))
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update(of=Payment)
        payment = await self.session.scalar(stmt)
        if payment is None:
            raise NotFoundError("To‘lov topilmadi.")
        return payment

    async def get_for_user(self, payment_id: uuid.UUID, user_id: uuid.UUID) -> Payment:
        payment = await self.get(payment_id)
        order = await self.session.get(Order, payment.order_id)
        if order is None or order.user_id != user_id:
            raise NotFoundError("To‘lov topilmadi.")
        return payment

    async def for_order(self, order_id: uuid.UUID) -> list[Payment]:
        return list(
            await self.session.scalars(
                select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at)
            )
        )

    async def start(self, order_id: uuid.UUID, *, user_id: uuid.UUID) -> StartedPayment:
        order = await self.session.scalar(
            select(Order).where(Order.id == order_id).with_for_update()
        )
        if order is None or order.user_id != user_id:
            raise NotFoundError("Buyurtma topilmadi.")
        if order.payment_method not in ONLINE:
            raise BusinessRuleError(
                "Bu buyurtma yetkazib berilganda naqd to‘lanadi.", code="not_online_payment"
            )
        if order.payment_status is PaymentStatus.PAID:
            raise ConflictError("Buyurtma allaqachon to‘langan.", code="already_paid")
        if order.status is not OrderStatus.PENDING or order.stock_state is not StockState.RESERVED:
            raise BusinessRuleError(
                "Bu buyurtmani endi to‘lab bo‘lmaydi. Yangi buyurtma bering.",
                code="order_not_payable",
            )
        adapter = provider_for(order.payment_method, self.settings)
        existing = await self.session.scalar(
            select(Payment).where(
                Payment.order_id == order.id,
                Payment.provider == adapter.provider,
                Payment.status.in_(OPEN),
            )
        )
        payment = existing or Payment(
            order_id=order.id,
            provider=adapter.provider,
            amount=order.total,
            is_simulated=adapter.is_simulated,
        )
        if existing is None:
            self.session.add(payment)
            await self.session.flush()
        try:
            link = adapter.checkout_link(payment, order)
        except ProviderNotConfiguredError:
            await self.session.rollback()  # leave no half-created payment behind
            raise
        await self.session.commit()
        return StartedPayment(payment=payment, checkout_url=link.url)

    async def record_success(
        self,
        payment_id: uuid.UUID,
        *,
        provider: PaymentProvider,
        external_id: str,
        amount: Decimal,
        payload: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> Payment:
        """Apply a provider-confirmed payment. Safe to call again with the same
        ``external_id`` (returns the already-paid payment)."""
        now = now or utcnow()
        payment = await self.get(payment_id, lock=True)
        if payment.provider is not provider:
            raise BusinessRuleError("To‘lov tizimi mos emas.", code="provider_mismatch")
        known = await self.session.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.provider == provider,
                PaymentTransaction.external_id == external_id,
            )
        )
        if known is not None:
            if known.payment_id != payment.id:
                raise ConflictError(
                    "Tranzaksiya boshqa to‘lovga tegishli.", code="transaction_mismatch"
                )
            # Duplicate callback: nothing to change. Commit only to release the row lock
            # (a rollback would expire objects the caller is still holding).
            await self.session.commit()
            return await self.get(payment_id)
        order = await self.session.get(Order, payment.order_id)
        if order is None:  # pragma: no cover - FK guarantees it
            raise NotFoundError("Buyurtma topilmadi.")
        if amount != payment.amount or amount != order.total:
            raise BusinessRuleError(
                "To‘lov summasi buyurtma summasiga mos emas.",
                code="amount_mismatch",
                details={"expected": str(order.total), "received": str(amount)},
            )
        if payment.status not in OPEN:
            raise ConflictError("Bu to‘lov yopilgan.", code="payment_closed")

        self.session.add(
            PaymentTransaction(
                payment_id=payment.id,
                provider=provider,
                external_id=external_id,
                provider_state="performed",
                amount=amount,
                performed_at=now,
                request_payload=_safe_payload(payload),
            )
        )
        payment.status = PaymentStatus.PAID
        payment.paid_at = now
        # Marks the order paid and turns the reservation into a sale; commits everything.
        await OrderService(self.session).confirm_payment(order.id, actor=Actor.provider(), now=now)
        return await self.get(payment_id)

    async def record_failure(
        self,
        payment_id: uuid.UUID,
        *,
        provider: PaymentProvider,
        reason: str,
        cancelled: bool = False,
        payload: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> Payment:
        """The customer cancelled or the provider declined. The order stays unpaid and can
        be paid again until its reservation expires."""
        now = now or utcnow()
        payment = await self.get(payment_id, lock=True)
        if payment.provider is not provider:
            raise BusinessRuleError("To‘lov tizimi mos emas.", code="provider_mismatch")
        if payment.status in OPEN:
            payment.status = PaymentStatus.CANCELLED if cancelled else PaymentStatus.FAILED
            payment.failure_reason = reason[:255]
            if cancelled:
                payment.cancelled_at = now
        await self.session.commit()
        return await self.get(payment_id)
