from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models import Category, Product
from app.repositories.products import ProductCard, ProductFilters, ProductRepository, ProductSort

MAX_PAGE_SIZE = 50


@dataclass(slots=True)
class Page[T]:
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.page_size))

    @property
    def has_next(self) -> bool:
        return self.page < self.pages


@dataclass(slots=True)
class CategoryNode:
    id: uuid.UUID
    name: str
    slug: str
    image_path: str | None
    children: list[CategoryNode] = field(default_factory=list)


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.products = ProductRepository(session)

    async def list_products(
        self,
        filters: ProductFilters | None = None,
        *,
        sort: ProductSort = ProductSort.NEWEST,
        page: int = 1,
        page_size: int = 20,
    ) -> Page[ProductCard]:
        filters = filters or ProductFilters()
        if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
            raise BusinessRuleError("Sahifa parametrlari noto‘g‘ri.", code="invalid_pagination")
        if (
            filters.min_price is not None
            and filters.max_price is not None
            and filters.min_price > filters.max_price
        ):
            raise BusinessRuleError(
                "Eng kam narx eng yuqori narxdan katta bo‘lishi mumkin emas.",
                code="invalid_price_range",
            )
        items, total = await self.products.list(
            filters, sort=sort, offset=(page - 1) * page_size, limit=page_size
        )
        return Page(items=items, total=total, page=page, page_size=page_size)

    async def get_product(self, product_id: uuid.UUID) -> Product:
        product = await self.products.get_visible(product_id)
        if product is None:
            raise NotFoundError("Mahsulot topilmadi yoki sotuvda emas.")
        return product

    async def category_tree(self) -> list[CategoryNode]:
        """Active categories as a tree. A child of an inactive parent is hidden too."""
        rows = (
            await self.session.scalars(
                select(Category)
                .where(Category.is_active)
                .order_by(Category.sort_order, Category.name)
            )
        ).all()
        nodes = {c.id: CategoryNode(c.id, c.name, c.slug, c.image_path) for c in rows}
        roots: list[CategoryNode] = []
        for c in rows:
            if c.parent_id is None:
                roots.append(nodes[c.id])
            elif c.parent_id in nodes:
                nodes[c.parent_id].children.append(nodes[c.id])
        return roots

    async def get_category(self, category_id: uuid.UUID) -> Category:
        category = await self.session.get(Category, category_id)
        if category is None or not category.is_active:
            raise NotFoundError("Kategoriya topilmadi.")
        return category

    async def popular(self, limit: int = 10) -> list[ProductCard]:
        items, _ = await self.products.list(
            ProductFilters(in_stock=True), sort=ProductSort.POPULAR, limit=limit
        )
        return items

    async def discounted(self, page: int = 1, page_size: int = 20) -> Page[ProductCard]:
        return await self.list_products(
            ProductFilters(discounted=True, in_stock=True), page=page, page_size=page_size
        )

    async def product_exists(self, product_id: uuid.UUID) -> bool:
        return await self.session.get(Product, product_id) is not None
