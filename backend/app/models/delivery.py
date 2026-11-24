from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import DeliveryMethodKind, DistrictKind


class Region(TimestampMixin, Base):
    """Top-level division: 12 viloyats, the Republic of Karakalpakstan, Tashkent city.

    Seeded by migration; ids are stable so they can be referenced from data.
    """

    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    # ISO 3166-2 code, e.g. UZ-TK
    code: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    districts: Mapped[list[District]] = relationship(
        back_populates="region", order_by="District.sort_order"
    )


class District(TimestampMixin, Base):
    """District (tuman) or city (shahar) inside a region."""

    __tablename__ = "districts"
    __table_args__ = (UniqueConstraint("region_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("regions.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[DistrictKind] = mapped_column(str_enum(DistrictKind, "district_kind"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    region: Mapped[Region] = relationship(back_populates="districts")


class DeliveryMethod(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "delivery_methods"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    kind: Mapped[DeliveryMethodKind] = mapped_column(
        str_enum(DeliveryMethodKind, "delivery_method_kind")
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    rates: Mapped[list[DeliveryRate]] = relationship(
        back_populates="method", cascade="all, delete-orphan", passive_deletes=True
    )


class DeliveryRate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Price and ETA of a delivery method for a region, optionally for one district.

    Lookup order: district-specific rate, then the region-wide rate (district_id NULL).
    """

    __tablename__ = "delivery_rates"
    __table_args__ = (
        # NULLS NOT DISTINCT: only one region-wide rate (district_id NULL) per method+region.
        UniqueConstraint(
            "method_id", "region_id", "district_id", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint(
            "free_threshold IS NULL OR free_threshold > 0", name="free_threshold_positive"
        ),
        CheckConstraint(
            "eta_min_days >= 0 AND eta_max_days >= eta_min_days", name="eta_range_valid"
        ),
    )

    method_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("delivery_methods.id", ondelete="CASCADE"), index=True
    )
    region_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("regions.id", ondelete="CASCADE"), index=True
    )
    district_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("districts.id", ondelete="CASCADE")
    )
    price: Mapped[Decimal]
    # Order amount from which delivery is free; NULL = use store-wide setting.
    free_threshold: Mapped[Decimal | None]
    eta_min_days: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    eta_max_days: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")
    pickup_address: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    method: Mapped[DeliveryMethod] = relationship(back_populates="rates")
    region: Mapped[Region] = relationship()
    district: Mapped[District | None] = relationship()
