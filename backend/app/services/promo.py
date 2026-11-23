"""Promo code rules.

Limits are enforced under a row lock (``SELECT … FOR UPDATE``) on the promo code when
an order redeems it, so two simultaneous orders cannot both take the last use.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.exceptions import PromoCodeError
from app.core.money import ZERO, format_som, money, round_som
from app.models import PromoCode, PromoCodeRedemption
from app.models.enums import DiscountType


def normalize_code(code: str) -> str:
    return code.strip().upper()


def calculate_discount(promo: PromoCode, subtotal: Decimal) -> Decimal:
    """Discount for a subtotal, never more than the subtotal or ``max_discount``."""
    if promo.discount_type is DiscountType.PERCENT:
        amount = round_som(subtotal * promo.value / Decimal(100))
    else:
        amount = money(promo.value)
    if promo.max_discount is not None:
        amount = min(amount, promo.max_discount)
    return money(min(amount, subtotal))


class PromoService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find(self, code: str, *, lock: bool = False) -> PromoCode:
        stmt = select(PromoCode).where(PromoCode.code == normalize_code(code))
        if lock:
            stmt = stmt.with_for_update()
        promo = await self.session.scalar(stmt)
        if promo is None:
            raise PromoCodeError("Bunday promokod topilmadi.", code="promo_not_found")
        return promo

    async def user_redemptions(self, promo_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(PromoCodeRedemption)
                .where(
                    PromoCodeRedemption.promo_code_id == promo_id,
                    PromoCodeRedemption.user_id == user_id,
                )
            )
            or 0
        )

    async def evaluate(
        self,
        promo: PromoCode,
        *,
        user_id: uuid.UUID,
        subtotal: Decimal,
        now: datetime | None = None,
    ) -> Decimal:
        """Return the discount, or raise ``PromoCodeError`` explaining why it can't be used."""
        now = now or utcnow()
        if not promo.is_active:
            raise PromoCodeError("Bu promokod faol emas.", code="promo_inactive")
        if promo.starts_at > now:
            raise PromoCodeError("Bu promokod hali kuchga kirmagan.", code="promo_not_started")
        if promo.ends_at is not None and promo.ends_at <= now:
            raise PromoCodeError("Bu promokodning muddati tugagan.", code="promo_expired")
        if subtotal < promo.min_order_amount:
            raise PromoCodeError(
                f"Bu promokod {format_som(promo.min_order_amount)} dan ortiq buyurtmalar uchun.",
                code="promo_min_order",
                details={"min_order_amount": str(promo.min_order_amount)},
            )
        if promo.usage_limit is not None and promo.used_count >= promo.usage_limit:
            raise PromoCodeError("Bu promokoddan foydalanish soni tugagan.", code="promo_exhausted")
        if promo.per_user_limit is not None:
            used = await self.user_redemptions(promo.id, user_id)
            if used >= promo.per_user_limit:
                raise PromoCodeError(
                    "Siz bu promokoddan allaqachon foydalangansiz.", code="promo_user_limit"
                )
        discount = calculate_discount(promo, subtotal)
        if discount <= ZERO:
            raise PromoCodeError("Bu promokod chegirma bermaydi.", code="promo_no_discount")
        return discount

    async def redeem(
        self,
        promo_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        order_id: uuid.UUID,
        subtotal: Decimal,
        now: datetime | None = None,
    ) -> Decimal:
        """Lock the promo row, re-check every rule, record the use. Caller commits."""
        promo = await self.session.scalar(
            select(PromoCode).where(PromoCode.id == promo_id).with_for_update()
        )
        if promo is None:
            raise PromoCodeError("Bunday promokod topilmadi.", code="promo_not_found")
        discount = await self.evaluate(promo, user_id=user_id, subtotal=subtotal, now=now)
        self.session.add(
            PromoCodeRedemption(
                promo_code_id=promo.id,
                user_id=user_id,
                order_id=order_id,
                discount_amount=discount,
            )
        )
        promo.used_count += 1
        return discount

    async def release(self, order_id: uuid.UUID) -> None:
        """Give the use back when an order is cancelled before it was paid/delivered."""
        promo_id = await self.session.scalar(
            delete(PromoCodeRedemption)
            .where(PromoCodeRedemption.order_id == order_id)
            .returning(PromoCodeRedemption.promo_code_id)
        )
        if promo_id is not None:
            await self.session.execute(
                update(PromoCode)
                .where(PromoCode.id == promo_id, PromoCode.used_count > 0)
                .values(used_count=PromoCode.used_count - 1)
            )
