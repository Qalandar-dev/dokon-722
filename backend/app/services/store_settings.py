"""Typed access to admin-editable store settings (``store_settings`` table)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import money
from app.models import StoreSetting
from app.models.enums import PaymentMethod

DEFAULT_LOW_STOCK_THRESHOLD = 5

_PAYMENT_METHOD_KEYS = {
    PaymentMethod.CLICK: "payments.click_enabled",
    PaymentMethod.PAYME: "payments.payme_enabled",
    PaymentMethod.CASH_ON_DELIVERY: "payments.cash_on_delivery_enabled",
}


class StoreSettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str, default: Any = None) -> Any:
        row = await self.session.scalar(select(StoreSetting).where(StoreSetting.key == key))
        if row is None:
            return default
        value = row.value.get("value", default)
        return default if value is None else value

    async def free_delivery_threshold(self) -> Decimal | None:
        value = await self.get("delivery.free_threshold")
        return money(str(value)) if value is not None else None

    async def low_stock_threshold(self) -> int:
        return int(await self.get("inventory.low_stock_threshold", DEFAULT_LOW_STOCK_THRESHOLD))

    async def payment_method_enabled(self, method: PaymentMethod) -> bool:
        # Cash on delivery is off unless explicitly enabled; online methods are on by default.
        default = method is not PaymentMethod.CASH_ON_DELIVERY
        return bool(await self.get(_PAYMENT_METHOD_KEYS[method], default))
