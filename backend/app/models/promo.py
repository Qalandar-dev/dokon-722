from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import DiscountType


class PromoCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "promo_codes"
    __table_args__ = (
        CheckConstraint("code = upper(code)", name="code_uppercase"),
        CheckConstraint("value > 0", name="value_positive"),
        CheckConstraint("discount_type <> 'percent' OR value <= 100", name="percent_at_most_100"),
        CheckConstraint("max_discount IS NULL OR max_discount > 0", name="max_discount_positive"),
        CheckConstraint("min_order_amount >= 0", name="min_order_non_negative"),
        CheckConstraint("usage_limit IS NULL OR usage_limit > 0", name="usage_limit_positive"),
        CheckConstraint(
            "per_user_limit IS NULL OR per_user_limit > 0", name="per_user_limit_positive"
        ),
        CheckConstraint(
            "usage_limit IS NULL OR used_count <= usage_limit", name="used_within_limit"
        ),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="valid_period"),
    )

    # Stored upper-case; lookups upper-case the input.
    code: Mapped[str] = mapped_column(String(32), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    discount_type: Mapped[DiscountType] = mapped_column(str_enum(DiscountType, "discount_type"))
    value: Mapped[Decimal]
    max_discount: Mapped[Decimal | None]
    min_order_amount: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default="0")
    starts_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ends_at: Mapped[datetime | None]
    usage_limit: Mapped[int | None] = mapped_column(Integer)
    per_user_limit: Mapped[int | None] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class PromoCodeRedemption(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One row per order that used a promo code. Counting these under a row lock on the
    promo code enforces the total and per-customer limits."""

    __tablename__ = "promo_code_redemptions"
    __table_args__ = (
        Index("ix_promo_code_redemptions_code_user", "promo_code_id", "user_id"),
        CheckConstraint("discount_amount > 0", name="discount_positive"),
    )

    promo_code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("promo_codes.id", ondelete="RESTRICT")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), unique=True
    )
    discount_amount: Mapped[Decimal]
