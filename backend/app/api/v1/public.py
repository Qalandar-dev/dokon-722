"""Public, read-only endpoints: catalog, regions, delivery quotes, store info."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import SessionDep, SettingsDep, StorageDep
from app.core.exceptions import NotFoundError
from app.models import Region
from app.models.enums import PaymentMethod
from app.repositories.products import ProductFilters, ProductSort
from app.schemas.catalog import (
    CategoryNodeOut,
    DeliveryQuoteOut,
    DistrictOut,
    ProductCardOut,
    ProductDetailOut,
    RegionOut,
    StoreInfoOut,
    district_out,
    region_out,
)
from app.schemas.common import Page
from app.services.admin_config import PUBLIC_SETTINGS, DeliveryAdminService, SettingsAdminService
from app.services.catalog import CatalogService
from app.services.delivery import DeliveryService
from app.services.store_settings import StoreSettingsService

router = APIRouter(tags=["catalog"])

PageQ = Annotated[int, Query(ge=1, le=10_000)]
PageSizeQ = Annotated[int, Query(ge=1, le=50)]


@router.get("/products", response_model=Page[ProductCardOut])
async def list_products(
    session: SessionDep,
    storage: StorageDep,
    category_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Name or SKU")] = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    in_stock: bool = False,
    discounted: bool = False,
    featured: bool = False,
    sort: ProductSort = ProductSort.NEWEST,
    page: PageQ = 1,
    page_size: PageSizeQ = 20,
) -> Page[ProductCardOut]:
    filters = ProductFilters(
        category_id=category_id,
        query=q,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        discounted=discounted,
        featured=featured,
    )
    result = await CatalogService(session).list_products(
        filters, sort=sort, page=page, page_size=page_size
    )
    return Page.build(result, lambda c: ProductCardOut.build(c, storage))


@router.get("/products/{product_id}", response_model=ProductDetailOut)
async def get_product(
    product_id: uuid.UUID, session: SessionDep, storage: StorageDep
) -> ProductDetailOut:
    return ProductDetailOut.build(await CatalogService(session).get_product(product_id), storage)


@router.get("/categories", response_model=list[CategoryNodeOut])
async def category_tree(session: SessionDep, storage: StorageDep) -> list[CategoryNodeOut]:
    return [
        CategoryNodeOut.build(n, storage) for n in await CatalogService(session).category_tree()
    ]


@router.get("/categories/{category_id}/products", response_model=Page[ProductCardOut])
async def category_products(
    category_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    sort: ProductSort = ProductSort.NEWEST,
    in_stock: bool = False,
    page: PageQ = 1,
    page_size: PageSizeQ = 20,
) -> Page[ProductCardOut]:
    service = CatalogService(session)
    await service.get_category(category_id)
    result = await service.list_products(
        ProductFilters(category_id=category_id, in_stock=in_stock),
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return Page.build(result, lambda c: ProductCardOut.build(c, storage))


@router.get("/regions", response_model=list[RegionOut], tags=["delivery"])
async def regions(session: SessionDep) -> list[RegionOut]:
    rows = await session.scalars(
        select(Region).where(Region.is_active).order_by(Region.sort_order, Region.name)
    )
    return [region_out(r) for r in rows]


@router.get("/regions/{region_id}/districts", response_model=list[DistrictOut], tags=["delivery"])
async def districts(region_id: int, session: SessionDep) -> list[DistrictOut]:
    region = await session.get(Region, region_id)
    if region is None or not region.is_active:
        raise NotFoundError("Hudud topilmadi.")
    items = await DeliveryAdminService(session).districts(region_id, include_inactive=False)
    return [district_out(d) for d in items]


@router.get("/delivery/quotes", response_model=list[DeliveryQuoteOut], tags=["delivery"])
async def delivery_quotes(
    session: SessionDep,
    district_id: int,
    amount: Annotated[Decimal, Query(ge=0, description="Order amount after discount")],
) -> list[DeliveryQuoteOut]:
    quotes = await DeliveryService(session).quotes(district_id, amount)
    return [DeliveryQuoteOut.build(q) for q in quotes]


@router.get("/store", response_model=StoreInfoOut, tags=["store"])
async def store_info(session: SessionDep, settings: SettingsDep) -> StoreInfoOut:
    values = await SettingsAdminService(session).values(PUBLIC_SETTINGS)
    store_settings = StoreSettingsService(session)
    return StoreInfoOut(
        name=values.get("store.name") or "Online Store",
        phone=values.get("store.phone"),
        address=values.get("store.address"),
        support_telegram=values.get("store.support_telegram"),
        currency_display=values.get("store.currency_display") or "so‘m",
        payment_methods=[
            m for m in PaymentMethod if await store_settings.payment_method_enabled(m)
        ],
        reservation_minutes=settings.order_reservation_ttl_minutes,
    )
