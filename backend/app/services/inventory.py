"""Stock rules: reservations, sales, returns and manual adjustments.

Policy (see docs/ARCHITECTURE.md §3):
- placing an order *reserves* stock;
- online payment confirmed / cash order confirmed → the reservation becomes a *sale*;
- cancellation before the sale *releases* the reservation;
- cancellation after the sale, or a refund with goods back on the shelf, *returns* stock.
Every change writes an ``InventoryMovement`` row in the same transaction.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, InsufficientStockError, NotFoundError
from app.models import Inventory, InventoryMovement, Product, ProductVariant
from app.models.enums import InventoryMovementType
from app.repositories.inventory import InventoryRepository, StockLevel
from app.services.audit import record_audit
from app.services.store_settings import StoreSettingsService


@dataclass(frozen=True, slots=True)
class StockLine:
    variant_id: uuid.UUID
    quantity: int


@dataclass(frozen=True, slots=True)
class LowStockItem:
    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    variant_name: str
    sku: str
    on_hand: int
    reserved: int
    threshold: int

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


def _merge(lines: Iterable[StockLine]) -> list[StockLine]:
    """Combine duplicates and sort by id, so concurrent transactions lock rows in the
    same order and cannot deadlock."""
    totals: dict[uuid.UUID, int] = defaultdict(int)
    for line in lines:
        if line.quantity <= 0:
            raise BusinessRuleError("Miqdor musbat bo‘lishi kerak.", code="invalid_quantity")
        totals[line.variant_id] += line.quantity
    return [StockLine(v, q) for v, q in sorted(totals.items(), key=lambda kv: kv[0].bytes)]


class InventoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = InventoryRepository(session)

    def _movement(
        self,
        variant_id: uuid.UUID,
        type_: InventoryMovementType,
        level: StockLevel,
        *,
        on_hand_delta: int = 0,
        reserved_delta: int = 0,
        order_id: uuid.UUID | None = None,
        admin_user_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> None:
        self.session.add(
            InventoryMovement(
                variant_id=variant_id,
                type=type_,
                on_hand_delta=on_hand_delta,
                reserved_delta=reserved_delta,
                on_hand_after=level.on_hand,
                reserved_after=level.reserved,
                order_id=order_id,
                admin_user_id=admin_user_id,
                reason=reason,
            )
        )

    async def _variant_label(self, variant_id: uuid.UUID) -> str:
        row = (
            await self.session.execute(
                select(Product.name, ProductVariant.name)
                .join(ProductVariant, ProductVariant.product_id == Product.id)
                .where(ProductVariant.id == variant_id)
            )
        ).one_or_none()
        if row is None:
            return "Mahsulot"
        return f"{row[0]} ({row[1]})" if row[1] else row[0]

    async def reserve(self, lines: Iterable[StockLine], *, order_id: uuid.UUID) -> None:
        """Reserve all lines or none (the caller's transaction is rolled back on error)."""
        for line in _merge(lines):
            level = await self.repo.try_reserve(line.variant_id, line.quantity)
            if level is None:
                current = await self.repo.get_level(line.variant_id)
                available = max(current.available, 0) if current else 0
                label = await self._variant_label(line.variant_id)
                message = (
                    f"«{label}» tugagan."
                    if available == 0
                    else f"«{label}» dan faqat {available} dona qoldi."
                )
                raise InsufficientStockError(
                    message,
                    details={
                        "variant_id": str(line.variant_id),
                        "requested": line.quantity,
                        "available": available,
                    },
                )
            self._movement(
                line.variant_id,
                InventoryMovementType.RESERVE,
                level,
                reserved_delta=line.quantity,
                order_id=order_id,
            )

    async def release(self, lines: Iterable[StockLine], *, order_id: uuid.UUID) -> None:
        for line in _merge(lines):
            level = await self.repo.try_release(line.variant_id, line.quantity)
            if level is None:
                raise BusinessRuleError(
                    "Zaxirani bekor qilib bo‘lmadi: ombor ma’lumotlari mos emas.",
                    code="inventory_inconsistent",
                    details={"variant_id": str(line.variant_id)},
                )
            self._movement(
                line.variant_id,
                InventoryMovementType.RELEASE,
                level,
                reserved_delta=-line.quantity,
                order_id=order_id,
            )

    async def commit_sale(self, lines: Iterable[StockLine], *, order_id: uuid.UUID) -> None:
        for line in _merge(lines):
            level = await self.repo.try_commit_sale(line.variant_id, line.quantity)
            if level is None:
                raise BusinessRuleError(
                    "Sotuvni rasmiylashtirib bo‘lmadi: zaxira topilmadi.",
                    code="inventory_inconsistent",
                    details={"variant_id": str(line.variant_id)},
                )
            self._movement(
                line.variant_id,
                InventoryMovementType.SALE,
                level,
                on_hand_delta=-line.quantity,
                reserved_delta=-line.quantity,
                order_id=order_id,
            )

    async def return_to_stock(
        self,
        lines: Iterable[StockLine],
        *,
        order_id: uuid.UUID,
        admin_user_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> None:
        for line in _merge(lines):
            await self.repo.ensure_row(line.variant_id)
            level = await self.repo.add_on_hand(line.variant_id, line.quantity)
            if level is None:  # pragma: no cover - adding stock cannot violate reserved
                raise BusinessRuleError("Omborga qaytarib bo‘lmadi.", code="inventory_inconsistent")
            self._movement(
                line.variant_id,
                InventoryMovementType.RETURN,
                level,
                on_hand_delta=line.quantity,
                order_id=order_id,
                admin_user_id=admin_user_id,
                reason=reason,
            )

    async def adjust(
        self,
        variant_id: uuid.UUID,
        *,
        delta: int,
        reason: str,
        admin_user_id: uuid.UUID | None,
    ) -> StockLevel:
        """Manual stock change by staff: positive = restock, negative = write-off/correction."""
        if delta == 0:
            raise BusinessRuleError(
                "O‘zgarish miqdori 0 bo‘lishi mumkin emas.", code="invalid_quantity"
            )
        if not reason.strip():
            raise BusinessRuleError("Sababni kiriting.", code="reason_required")
        if await self.session.get(ProductVariant, variant_id) is None:
            raise NotFoundError("Mahsulot varianti topilmadi.")
        await self.repo.ensure_row(variant_id)
        level = await self.repo.add_on_hand(variant_id, delta)
        if level is None:
            current = await self.repo.get_level(variant_id)
            raise BusinessRuleError(
                "Qoldiqni bunchalik kamaytirib bo‘lmaydi: bu mahsulot buyurtmalar uchun band.",
                code="below_reserved",
                details={
                    "on_hand": current.on_hand if current else 0,
                    "reserved": current.reserved if current else 0,
                },
            )
        self._movement(
            variant_id,
            InventoryMovementType.RESTOCK if delta > 0 else InventoryMovementType.ADJUSTMENT,
            level,
            on_hand_delta=delta,
            admin_user_id=admin_user_id,
            reason=reason.strip(),
        )
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="inventory.adjust",
            entity_type="product_variant",
            entity_id=variant_id,
            changes={"delta": delta, "reason": reason.strip(), "on_hand_after": level.on_hand},
        )
        await self.session.commit()
        return level

    async def low_stock(self, limit: int = 100) -> list[LowStockItem]:
        """Active variants whose available stock is at or below their threshold."""
        default = await StoreSettingsService(self.session).low_stock_threshold()
        threshold = func.coalesce(Inventory.low_stock_threshold, default)
        rows = await self.session.execute(
            select(
                ProductVariant.id,
                Product.id,
                Product.name,
                ProductVariant.name,
                ProductVariant.sku,
                Inventory.on_hand,
                Inventory.reserved,
                threshold.label("threshold"),
            )
            .join(Inventory, Inventory.variant_id == ProductVariant.id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                ProductVariant.is_active,
                Product.is_active,
                Product.deleted_at.is_(None),
                Inventory.on_hand - Inventory.reserved <= threshold,
            )
            .order_by(Inventory.on_hand - Inventory.reserved, Product.name)
            .limit(limit)
        )
        return [LowStockItem(*row) for row in rows]
