from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.api.deps import AdminContext, SessionDep, SettingsDep, StorageDep, require
from app.core.exceptions import BusinessRuleError
from app.core.permissions import Permission
from app.schemas.admin import (
    AdminCategoryOut,
    AdminProductOut,
    AdminVariantOut,
    CategoryIn,
    CategoryUpdateIn,
    ImageUpdateIn,
    LowStockOut,
    MovementOut,
    ProductCreateIn,
    ProductUpdateIn,
    StockAdjustIn,
    StockLevelOut,
    StockRowOut,
    VariantIn,
    VariantUpdateIn,
    movement_out,
)
from app.schemas.catalog import ImageOut
from app.schemas.common import Page
from app.services.admin_catalog import AdminCatalogService, ProductInput, VariantInput
from app.services.catalog import Page as ServicePage
from app.services.inventory import InventoryService, movements, stock_list

router = APIRouter(prefix="/admin", tags=["admin: catalog"])

ViewProducts = Annotated[AdminContext, Depends(require(Permission.PRODUCTS_VIEW))]
ManageProducts = Annotated[AdminContext, Depends(require(Permission.PRODUCTS_MANAGE))]
ManageCategories = Annotated[AdminContext, Depends(require(Permission.CATEGORIES_MANAGE))]
ViewInventory = Annotated[AdminContext, Depends(require(Permission.INVENTORY_VIEW))]
ManageInventory = Annotated[AdminContext, Depends(require(Permission.INVENTORY_MANAGE))]


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    # Read at most one byte over the limit so a huge upload is not held in memory.
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise BusinessRuleError(
            f"Fayl hajmi {max_bytes // (1024 * 1024)} MB dan oshmasligi kerak.",
            code="file_too_large",
        )
    return data


# --- Products ----------------------------------------------------------------------------


@router.get("/products", response_model=Page[AdminProductOut])
async def list_products(
    _: ViewProducts,
    session: SessionDep,
    storage: StorageDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    low_stock: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AdminProductOut]:
    result = await AdminCatalogService(session).list_products(
        query=q,
        category_id=category_id,
        is_active=is_active,
        low_stock=low_stock,
        page=page,
        page_size=page_size,
    )
    return Page.build(result, lambda p: AdminProductOut.build(p, storage))


@router.post("/products", response_model=AdminProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreateIn, ctx: ManageProducts, session: SessionDep, storage: StorageDep
) -> AdminProductOut:
    data = body.model_dump(exclude={"variants"})
    product = await AdminCatalogService(session, storage).create_product(
        ProductInput(**data),
        [VariantInput(**v.model_dump()) for v in body.variants],
        admin_user_id=ctx.id,
    )
    return AdminProductOut.build(product, storage)


@router.get("/products/{product_id}", response_model=AdminProductOut)
async def get_product(
    product_id: uuid.UUID, _: ViewProducts, session: SessionDep, storage: StorageDep
) -> AdminProductOut:
    return AdminProductOut.build(
        await AdminCatalogService(session).get_product(product_id), storage
    )


@router.patch("/products/{product_id}", response_model=AdminProductOut)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdateIn,
    ctx: ManageProducts,
    session: SessionDep,
    storage: StorageDep,
) -> AdminProductOut:
    product = await AdminCatalogService(session, storage).update_product(
        product_id, body.model_dump(exclude_unset=True), admin_user_id=ctx.id
    )
    return AdminProductOut.build(product, storage)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: uuid.UUID, ctx: ManageProducts, session: SessionDep) -> None:
    await AdminCatalogService(session).delete_product(product_id, admin_user_id=ctx.id)


@router.post(
    "/products/{product_id}/variants",
    response_model=AdminVariantOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_variant(
    product_id: uuid.UUID, body: VariantIn, ctx: ManageProducts, session: SessionDep
) -> AdminVariantOut:
    service = AdminCatalogService(session)
    variant = await service.add_variant(
        product_id, VariantInput(**body.model_dump()), admin_user_id=ctx.id
    )
    product = await service.get_product(product_id)
    return AdminVariantOut.build(next(v for v in product.variants if v.id == variant.id))


@router.patch("/variants/{variant_id}", response_model=AdminVariantOut)
async def update_variant(
    variant_id: uuid.UUID, body: VariantUpdateIn, ctx: ManageProducts, session: SessionDep
) -> AdminVariantOut:
    service = AdminCatalogService(session)
    variant = await service.update_variant(
        variant_id, body.model_dump(exclude_unset=True), admin_user_id=ctx.id
    )
    product = await service.get_product(variant.product_id)
    return AdminVariantOut.build(next(v for v in product.variants if v.id == variant.id))


@router.post(
    "/products/{product_id}/images",
    response_model=ImageOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    product_id: uuid.UUID,
    ctx: ManageProducts,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="JPG, PNG or WEBP")],
    alt_text: Annotated[str | None, Form(max_length=200)] = None,
) -> ImageOut:
    data = await _read_upload(file, settings.max_upload_size_bytes)
    image = await AdminCatalogService(session, storage).add_image(
        product_id, data, alt_text=alt_text, admin_user_id=ctx.id
    )
    return ImageOut.build(image, storage)


@router.patch("/product-images/{image_id}", response_model=ImageOut)
async def update_image(
    image_id: uuid.UUID,
    body: ImageUpdateIn,
    ctx: ManageProducts,
    session: SessionDep,
    storage: StorageDep,
) -> ImageOut:
    image = await AdminCatalogService(session, storage).update_image(
        image_id, admin_user_id=ctx.id, **body.model_dump()
    )
    return ImageOut.build(image, storage)


@router.delete("/product-images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    image_id: uuid.UUID, ctx: ManageProducts, session: SessionDep, storage: StorageDep
) -> None:
    await AdminCatalogService(session, storage).delete_image(image_id, admin_user_id=ctx.id)


# --- Categories --------------------------------------------------------------------------


@router.get("/categories", response_model=list[AdminCategoryOut])
async def list_categories(
    _: ViewProducts, session: SessionDep, storage: StorageDep
) -> list[AdminCategoryOut]:
    rows = await AdminCatalogService(session).list_categories()
    return [AdminCategoryOut.build(c, n, storage) for c, n in rows]


@router.post("/categories", response_model=AdminCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryIn, ctx: ManageCategories, session: SessionDep, storage: StorageDep
) -> AdminCategoryOut:
    category = await AdminCatalogService(session).create_category(
        admin_user_id=ctx.id, **body.model_dump()
    )
    return AdminCategoryOut.build(category, 0, storage)


async def _category_out(
    session: SessionDep, storage: StorageDep, category_id: uuid.UUID
) -> AdminCategoryOut:
    rows = await AdminCatalogService(session).list_categories()
    category, count = next((c, n) for c, n in rows if c.id == category_id)
    return AdminCategoryOut.build(category, count, storage)


@router.patch("/categories/{category_id}", response_model=AdminCategoryOut)
async def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdateIn,
    ctx: ManageCategories,
    session: SessionDep,
    storage: StorageDep,
) -> AdminCategoryOut:
    await AdminCatalogService(session).update_category(
        category_id, body.model_dump(exclude_unset=True), admin_user_id=ctx.id
    )
    return await _category_out(session, storage, category_id)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID, ctx: ManageCategories, session: SessionDep, storage: StorageDep
) -> None:
    await AdminCatalogService(session, storage).delete_category(category_id, admin_user_id=ctx.id)


@router.post("/categories/{category_id}/image", response_model=AdminCategoryOut)
async def upload_category_image(
    category_id: uuid.UUID,
    ctx: ManageCategories,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="JPG, PNG or WEBP")],
) -> AdminCategoryOut:
    data = await _read_upload(file, settings.max_upload_size_bytes)
    await AdminCatalogService(session, storage).set_category_image(
        category_id, data, admin_user_id=ctx.id
    )
    return await _category_out(session, storage, category_id)


# --- Inventory ---------------------------------------------------------------------------


@router.get("/inventory", response_model=Page[StockRowOut], tags=["admin: inventory"])
async def inventory(
    _: ViewInventory,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    low_only: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[StockRowOut]:
    rows, total = await stock_list(
        session, query=q, low_only=low_only, page=page, page_size=page_size
    )
    return Page.build(ServicePage(rows, total, page, page_size), StockRowOut.build)


@router.get("/inventory/low-stock", response_model=list[LowStockOut], tags=["admin: inventory"])
async def low_stock(_: ViewInventory, session: SessionDep) -> list[LowStockOut]:
    return [LowStockOut.build(i) for i in await InventoryService(session).low_stock()]


@router.post(
    "/inventory/{variant_id}/adjust", response_model=StockLevelOut, tags=["admin: inventory"]
)
async def adjust_stock(
    variant_id: uuid.UUID, body: StockAdjustIn, ctx: ManageInventory, session: SessionDep
) -> StockLevelOut:
    level = await InventoryService(session).adjust(
        variant_id, delta=body.delta, reason=body.reason, admin_user_id=ctx.id
    )
    return StockLevelOut(
        variant_id=variant_id,
        on_hand=level.on_hand,
        reserved=level.reserved,
        available=level.available,
    )


@router.get(
    "/inventory/{variant_id}/movements",
    response_model=Page[MovementOut],
    tags=["admin: inventory"],
)
async def stock_movements(
    variant_id: uuid.UUID,
    _: ViewInventory,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[MovementOut]:
    items, total = await movements(session, variant_id, page=page, page_size=page_size)
    return Page.build(ServicePage(items, total, page, page_size), movement_out)
