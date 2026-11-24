"""Atomic stock operations.

Every write is a single conditional ``UPDATE … RETURNING``: the WHERE clause is the
business check, so two concurrent transactions can never both pass it. Callers own
the transaction; nothing here commits.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Inventory


@dataclass(frozen=True, slots=True)
class StockLevel:
    on_hand: int
    reserved: int

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


class InventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _apply(self, stmt: object) -> StockLevel | None:
        row = (await self.session.execute(stmt)).one_or_none()  # type: ignore[call-overload]
        return StockLevel(row.on_hand, row.reserved) if row is not None else None

    async def try_reserve(self, variant_id: uuid.UUID, qty: int) -> StockLevel | None:
        return await self._apply(
            update(Inventory)
            .where(Inventory.variant_id == variant_id)
            .where(Inventory.on_hand - Inventory.reserved >= qty)
            .values(reserved=Inventory.reserved + qty)
            .returning(Inventory.on_hand, Inventory.reserved)
        )

    async def try_release(self, variant_id: uuid.UUID, qty: int) -> StockLevel | None:
        return await self._apply(
            update(Inventory)
            .where(Inventory.variant_id == variant_id, Inventory.reserved >= qty)
            .values(reserved=Inventory.reserved - qty)
            .returning(Inventory.on_hand, Inventory.reserved)
        )

    async def try_commit_sale(self, variant_id: uuid.UUID, qty: int) -> StockLevel | None:
        """Turn a reservation into a sale: both on_hand and reserved go down."""
        return await self._apply(
            update(Inventory)
            .where(Inventory.variant_id == variant_id, Inventory.reserved >= qty)
            .values(on_hand=Inventory.on_hand - qty, reserved=Inventory.reserved - qty)
            .returning(Inventory.on_hand, Inventory.reserved)
        )

    async def add_on_hand(self, variant_id: uuid.UUID, qty: int) -> StockLevel | None:
        """Add (or, with a negative qty, remove) physical stock without touching
        reservations. Fails (None) if it would drop below what is reserved."""
        return await self._apply(
            update(Inventory)
            .where(Inventory.variant_id == variant_id)
            .where(Inventory.on_hand + qty >= Inventory.reserved)
            .values(on_hand=Inventory.on_hand + qty)
            .returning(Inventory.on_hand, Inventory.reserved)
        )

    async def get_level(self, variant_id: uuid.UUID) -> StockLevel | None:
        row = (
            await self.session.execute(
                select(Inventory.on_hand, Inventory.reserved).where(
                    Inventory.variant_id == variant_id
                )
            )
        ).one_or_none()
        return StockLevel(row.on_hand, row.reserved) if row is not None else None

    async def ensure_row(self, variant_id: uuid.UUID) -> None:
        await self.session.execute(
            text(
                "INSERT INTO inventory (variant_id) VALUES (:v) ON CONFLICT (variant_id) DO NOTHING"
            ),
            {"v": variant_id},
        )
