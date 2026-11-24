from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.catalog import ProductVariant
from app.models.enums import InventoryMovementType


class Inventory(Base):
    """Stock for one variant.

    ``available = on_hand - reserved``. Reservations are taken with a conditional
    UPDATE (``WHERE on_hand - reserved >= :qty``), and the CHECK constraints below make
    overselling impossible even if application code has a bug.
    """

    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint("on_hand >= 0", name="on_hand_non_negative"),
        CheckConstraint("reserved >= 0", name="reserved_non_negative"),
        CheckConstraint("reserved <= on_hand", name="reserved_within_on_hand"),
        CheckConstraint(
            "low_stock_threshold IS NULL OR low_stock_threshold >= 0", name="threshold_non_negative"
        ),
    )

    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_variants.id", ondelete="CASCADE"), primary_key=True
    )
    on_hand: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reserved: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # NULL = use the store-wide default from settings.
    low_stock_threshold: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    variant: Mapped[ProductVariant] = relationship(back_populates="inventory")

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


class InventoryMovement(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only stock ledger. Each row records a change to on_hand and/or reserved."""

    __tablename__ = "inventory_movements"
    __table_args__ = (
        Index("ix_inventory_movements_variant_seq", "variant_id", "seq"),
        CheckConstraint("on_hand_delta <> 0 OR reserved_delta <> 0", name="changes_something"),
    )

    # Insertion order. created_at is the transaction start time, so rows written in one
    # transaction share it; seq keeps the ledger in the exact order of the changes.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_variants.id", ondelete="CASCADE")
    )
    type: Mapped[InventoryMovementType] = mapped_column(
        str_enum(InventoryMovementType, "inventory_movement_type")
    )
    on_hand_delta: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reserved_delta: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    on_hand_after: Mapped[int] = mapped_column(Integer)
    reserved_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(255))
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), index=True
    )
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
