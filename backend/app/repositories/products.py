"""Product catalog queries for customers (only active, not deleted products)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import Select, and_, case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Category, Inventory, Product, ProductVariant


class ProductSort(StrEnum):
    NEWEST = "newest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    POPULAR = "popular"


@dataclass(frozen=True, slots=True)
class ProductFilters:
    category_id: uuid.UUID | None = None  # includes all sub-categories
    query: str | None = None  # name (fuzzy) or exact SKU
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    in_stock: bool = False
    discounted: bool = False
    featured: bool = False


@dataclass(frozen=True, slots=True)
class ProductCard:
    """One row of a product list: the product plus figures aggregated over variants."""

    product: Product
    min_price: Decimal  # lowest price a customer pays (discount applied)
    max_original_price: Decimal
    has_discount: bool
    available: int


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _variant_stats():  # type: ignore[no-untyped-def]
        effective = func.coalesce(ProductVariant.discount_price, ProductVariant.price)
        return (
            select(
                ProductVariant.product_id.label("product_id"),
                func.min(effective).label("min_price"),
                func.max(ProductVariant.price).label("max_original_price"),
                func.bool_or(ProductVariant.discount_price.is_not(None)).label("has_discount"),
                func.coalesce(
                    func.sum(func.greatest(Inventory.on_hand - Inventory.reserved, 0)), 0
                ).label("available"),
            )
            .outerjoin(Inventory, Inventory.variant_id == ProductVariant.id)
            .where(ProductVariant.is_active)
            .group_by(ProductVariant.product_id)
            .subquery("variant_stats")
        )

    async def category_tree_ids(self, root_id: uuid.UUID) -> list[uuid.UUID]:
        """The category and all its active descendants (recursive CTE)."""
        tree = (
            select(Category.id)
            .where(Category.id == root_id, Category.is_active)
            .cte("tree", recursive=True)
        )
        tree = tree.union_all(
            select(Category.id).where(Category.parent_id == tree.c.id, Category.is_active)
        )
        return list(await self.session.scalars(select(tree.c.id)))

    async def _filtered(self, filters: ProductFilters) -> tuple[Select, Any]:  # type: ignore[type-arg]
        stats = self._variant_stats()
        stmt = (
            select(
                Product,
                stats.c.min_price,
                stats.c.max_original_price,
                stats.c.has_discount,
                stats.c.available,
            )
            # Inner join: a product without any active variant cannot be sold, so hide it.
            .join(stats, stats.c.product_id == Product.id)
            .join(Category, Category.id == Product.category_id)
            .where(Product.is_active, Product.deleted_at.is_(None), Category.is_active)
        )
        if filters.category_id is not None:
            ids = await self.category_tree_ids(filters.category_id)
            stmt = stmt.where(Product.category_id.in_(ids or [filters.category_id]))
        if filters.query and (q := filters.query.strip()):
            sku_match = exists().where(
                ProductVariant.product_id == Product.id,
                func.upper(ProductVariant.sku) == q.upper(),
            )
            stmt = stmt.where(
                or_(
                    Product.name.ilike(f"%{_escape_like(q)}%", escape="\\"),
                    Product.name.op("%")(q),  # trigram similarity, uses the GIN index
                    sku_match,
                )
            )
        if filters.min_price is not None:
            stmt = stmt.where(stats.c.min_price >= filters.min_price)
        if filters.max_price is not None:
            stmt = stmt.where(stats.c.min_price <= filters.max_price)
        if filters.in_stock:
            stmt = stmt.where(stats.c.available > 0)
        if filters.discounted:
            stmt = stmt.where(stats.c.has_discount)
        if filters.featured:
            stmt = stmt.where(Product.is_featured)
        return stmt, stats

    async def list(
        self,
        filters: ProductFilters,
        *,
        sort: ProductSort = ProductSort.NEWEST,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[ProductCard], int]:
        stmt, stats = await self._filtered(filters)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        min_price = stats.c.min_price
        # In-stock products first, then the requested order; id as a stable tie-breaker.
        in_stock_first = case((stats.c.available > 0, 0), else_=1)
        order_by = {
            ProductSort.NEWEST: [Product.created_at.desc()],
            ProductSort.PRICE_ASC: [min_price.asc()],
            ProductSort.PRICE_DESC: [min_price.desc()],
            ProductSort.POPULAR: [Product.sold_count.desc(), Product.created_at.desc()],
        }[sort]
        rows = await self.session.execute(
            stmt.options(selectinload(Product.images))
            .order_by(in_stock_first, *order_by, Product.id)
            .offset(offset)
            .limit(limit)
        )
        cards = [
            ProductCard(
                product=row[0],
                min_price=row.min_price,
                max_original_price=row.max_original_price,
                has_discount=bool(row.has_discount),
                available=int(row.available),
            )
            for row in rows
        ]
        return cards, total

    async def get_visible(self, product_id: uuid.UUID) -> Product | None:
        """A product the customer may see, with active variants, stock and images."""
        product = await self.session.scalar(
            select(Product)
            .join(Category, Category.id == Product.category_id)
            .where(
                Product.id == product_id,
                Product.is_active,
                Product.deleted_at.is_(None),
                Category.is_active,
            )
            .options(
                selectinload(Product.images),
                selectinload(Product.variants.and_(ProductVariant.is_active)).selectinload(
                    ProductVariant.inventory
                ),
            )
        )
        if product is None or not product.variants:
            return None
        return product

    async def get_purchasable_variant(self, variant_id: uuid.UUID) -> ProductVariant | None:
        """A variant that can be put in a cart right now (ignores stock level)."""
        return await self.session.scalar(
            select(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .join(Category, Category.id == Product.category_id)
            .where(
                and_(
                    ProductVariant.id == variant_id,
                    ProductVariant.is_active,
                    Product.is_active,
                    Product.deleted_at.is_(None),
                    Category.is_active,
                )
            )
            .options(selectinload(ProductVariant.product), selectinload(ProductVariant.inventory))
        )
