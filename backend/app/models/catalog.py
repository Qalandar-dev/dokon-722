from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.inventory import Inventory


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Nested product category. A category with products or children cannot be deleted
    (FK RESTRICT); deactivate it or move its contents first."""

    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
    )

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    parent: Mapped[Category | None] = relationship(
        remote_side="Category.id", back_populates="children"
    )
    children: Mapped[list[Category]] = relationship(back_populates="parent")
    products: Mapped[list[Product]] = relationship(back_populates="category")


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A sellable item. Prices and stock live on its variants; every product has at
    least one variant (a simple product has exactly one default variant)."""

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_category_active", "category_id", "is_active"),
        # Fuzzy search by name (pg_trgm, created in the initial migration).
        Index(
            "ix_products_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(220), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    is_featured: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Denormalised counter for "popular products"; updated when an order is paid.
    sold_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Soft delete: orders keep referencing deleted products.
    deleted_at: Mapped[datetime | None]

    category: Mapped[Category] = relationship(back_populates="products")
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProductImage.sort_order",
    )
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProductVariant.sort_order",
    )


class ProductImage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_images"
    __table_args__ = (
        Index(
            "uq_product_images_product_main",
            "product_id",
            unique=True,
            postgresql_where=text("is_main"),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    # Storage key (relative path / object key), never a full URL.
    path: Mapped[str] = mapped_column(String(255))
    alt_text: Mapped[str | None] = mapped_column(String(200))
    # Telegram file_id cache so the bot does not re-upload the same image.
    telegram_file_id: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_main: Mapped[bool] = mapped_column(default=False, server_default=false())

    product: Mapped[Product] = relationship(back_populates="images")


class ProductVariant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A concrete purchasable option of a product, e.g. size M, colour black."""

    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint(
            "discount_price IS NULL OR (discount_price >= 0 AND discount_price < price)",
            name="discount_below_price",
        ),
        Index(
            "uq_product_variants_product_default",
            "product_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    # Display name, e.g. "M / Qora". Empty for the default variant of a simple product.
    name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    # e.g. {"o‘lcham": "M", "rang": "Qora"}
    attributes: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )
    price: Mapped[Decimal]
    discount_price: Mapped[Decimal | None]
    barcode: Mapped[str | None] = mapped_column(String(64))
    # Fiscal codes (IKPU / MXIK and package code) for receipts, if the business needs them.
    ikpu_code: Mapped[str | None] = mapped_column(String(32))
    package_code: Mapped[str | None] = mapped_column(String(32))
    weight_grams: Mapped[int | None] = mapped_column(Integer)
    is_default: Mapped[bool] = mapped_column(default=False, server_default=false())
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    product: Mapped[Product] = relationship(back_populates="variants")
    inventory: Mapped[Inventory | None] = relationship(
        back_populates="variant", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def effective_price(self) -> Decimal:
        return self.discount_price if self.discount_price is not None else self.price


class Review(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    rating: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    is_published: Mapped[bool] = mapped_column(default=False, server_default=false())
