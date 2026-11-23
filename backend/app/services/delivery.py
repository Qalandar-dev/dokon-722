"""Delivery fee calculation.

Rate lookup: a district-specific rate wins over the region-wide rate (district_id NULL).
Free delivery: if the order amount (after discount) reaches the rate's
``free_threshold`` — or, if the rate has none, the store-wide threshold — the fee is 0.
Prices are never hard-coded; they come from ``delivery_rates`` set by an admin.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.money import ZERO, money
from app.models import DeliveryMethod, DeliveryRate, District, Region
from app.models.enums import DeliveryMethodKind
from app.services.store_settings import StoreSettingsService


@dataclass(frozen=True, slots=True)
class DeliveryQuote:
    method_id: uuid.UUID
    method_code: str
    method_kind: DeliveryMethodKind
    method_name: str
    price: Decimal  # what the customer pays
    base_price: Decimal  # price before free-delivery rule
    free_applied: bool
    free_threshold: Decimal | None
    eta_min_days: int
    eta_max_days: int
    pickup_address: str | None


@dataclass(frozen=True, slots=True)
class Location:
    region_id: int
    region_name: str
    district_id: int
    district_name: str


class DeliveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def location(self, district_id: int) -> Location:
        row = (
            await self.session.execute(
                select(District, Region)
                .join(Region, Region.id == District.region_id)
                .where(District.id == district_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Tuman yoki shahar topilmadi.")
        district, region = row
        if not (district.is_active and region.is_active):
            raise BusinessRuleError(
                "Bu hududga hozircha yetkazib berilmaydi.", code="delivery_unavailable"
            )
        return Location(region.id, region.name, district.id, district.name)

    async def quotes(self, district_id: int, order_amount: Decimal) -> list[DeliveryQuote]:
        """All delivery options available for the district, cheapest first."""
        location = await self.location(district_id)
        rates = (
            await self.session.scalars(
                select(DeliveryRate)
                .join(DeliveryMethod, DeliveryMethod.id == DeliveryRate.method_id)
                .where(
                    DeliveryRate.is_active,
                    DeliveryMethod.is_active,
                    DeliveryRate.region_id == location.region_id,
                    or_(
                        DeliveryRate.district_id.is_(None),
                        DeliveryRate.district_id == location.district_id,
                    ),
                )
                .options(selectinload(DeliveryRate.method))
            )
        ).all()

        # Per method, prefer the district-specific rate.
        best: dict[uuid.UUID, DeliveryRate] = {}
        for rate in rates:
            current = best.get(rate.method_id)
            if current is None or (current.district_id is None and rate.district_id is not None):
                best[rate.method_id] = rate

        store_threshold = await StoreSettingsService(self.session).free_delivery_threshold()
        quotes = [self._quote(rate, order_amount, store_threshold) for rate in best.values()]
        return sorted(quotes, key=lambda q: (q.price, q.method_name))

    async def quote(
        self, method_id: uuid.UUID, district_id: int, order_amount: Decimal
    ) -> DeliveryQuote:
        for q in await self.quotes(district_id, order_amount):
            if q.method_id == method_id:
                return q
        raise BusinessRuleError(
            "Tanlangan yetkazib berish usuli bu hududda mavjud emas.",
            code="delivery_method_unavailable",
        )

    @staticmethod
    def _quote(
        rate: DeliveryRate, order_amount: Decimal, store_threshold: Decimal | None
    ) -> DeliveryQuote:
        threshold = rate.free_threshold if rate.free_threshold is not None else store_threshold
        free = threshold is not None and order_amount >= threshold
        return DeliveryQuote(
            method_id=rate.method.id,
            method_code=rate.method.code,
            method_kind=rate.method.kind,
            method_name=rate.method.name,
            price=ZERO if free else money(rate.price),
            base_price=money(rate.price),
            free_applied=free and rate.price > 0,
            free_threshold=threshold,
            eta_min_days=rate.eta_min_days,
            eta_max_days=rate.eta_max_days,
            pickup_address=rate.pickup_address,
        )
