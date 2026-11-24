"""Catalog management for staff: products, variants, images, categories."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.money import money
from app.core.text import slugify
from app.integrations.storage.base import Storage
from app.models import (
    Category,
    Inventory,
    Product,
    ProductImage,
    ProductVariant,
)
from app.services.audit import diff, record_audit
from app.services.catalog import Page
from app.services.inventory import InventoryService
from app.services.store_settings import StoreSettingsService
from app.services.uploads import image_key, validate_image

MAX_IMAGES_PER_PRODUCT = 10


@dataclass(slots=True)
class VariantInput:
    sku: str
    price: Decimal
    name: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    discount_price: Decimal | None = None
    barcode: str | None = None
    ikpu_code: str | None = None
    package_code: str | None = None
    weight_grams: int | None = None
    is_default: bool = False
    is_active: bool = True
    sort_order: int = 0
    initial_stock: int = 0
    low_stock_threshold: int | None = None


@dataclass(slots=True)
class ProductInput:
    name: str
    category_id: uuid.UUID
    description: str | None = None
    brand: str | None = None
    is_active: bool = True
    is_featured: bool = False


def _variant_fields(v: VariantInput) -> dict[str, Any]:
    sku = v.sku.strip().upper()
    if not sku:
        raise BusinessRuleError("SKU kiritilishi shart.", code="sku_required")
    if v.discount_price is not None and v.discount_price >= v.price:
        raise BusinessRuleError(
            "Chegirma narxi asosiy narxdan kichik bo‘lishi kerak.", code="invalid_discount_price"
        )
    if v.price < 0:
        raise BusinessRuleError("Narx manfiy bo‘lishi mumkin emas.", code="invalid_price")
    return {
        "sku": sku,
        "name": v.name.strip()[:120],
        "attributes": {str(k).strip(): str(val).strip() for k, val in v.attributes.items()},
        "price": money(v.price),
        "discount_price": money(v.discount_price) if v.discount_price is not None else None,
        "barcode": (v.barcode or "").strip() or None,
        "ikpu_code": (v.ikpu_code or "").strip() or None,
        "package_code": (v.package_code or "").strip() or None,
        "weight_grams": v.weight_grams,
        "is_active": v.is_active,
        "sort_order": v.sort_order,
    }


def _product_snapshot(p: Product) -> dict[str, Any]:
    return {
        k: getattr(p, k)
        for k in ("name", "category_id", "description", "brand", "is_active", "is_featured")
    }


class AdminCatalogService:
    def __init__(self, session: AsyncSession, storage: Storage | None = None) -> None:
        self.session = session
        self.storage = storage

    # --- Helpers -------------------------------------------------------------------

    async def _unique_slug(self, model: type[Product] | type[Category], name: str) -> str:
        base = slugify(name)
        slug, n = base, 1
        while await self.session.scalar(select(model.id).where(model.slug == slug)) is not None:
            n += 1
            slug = f"{base}-{n}"
        return slug

    async def _sku_taken(self, sku: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = select(ProductVariant.id).where(func.upper(ProductVariant.sku) == sku.upper())
        if exclude_id is not None:
            stmt = stmt.where(ProductVariant.id != exclude_id)
        return await self.session.scalar(stmt) is not None

    async def _category(self, category_id: uuid.UUID) -> Category:
        category = await self.session.get(Category, category_id)
        if category is None:
            raise NotFoundError("Kategoriya topilmadi.")
        return category

    async def get_product(self, product_id: uuid.UUID) -> Product:
        product = await self.session.scalar(
            select(Product)
            .where(Product.id == product_id, Product.deleted_at.is_(None))
            .options(
                selectinload(Product.images),
                selectinload(Product.variants).selectinload(ProductVariant.inventory),
                selectinload(Product.category),
            )
            .execution_options(populate_existing=True)
        )
        if product is None:
            raise NotFoundError("Mahsulot topilmadi.")
        return product

    # --- Products ------------------------------------------------------------------

    async def list_products(
        self,
        *,
        query: str | None = None,
        category_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        low_stock: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> Page[Product]:
        stmt = select(Product).where(Product.deleted_at.is_(None))
        if query and (q := query.strip()):
            sku_match = select(ProductVariant.product_id).where(ProductVariant.sku.ilike(f"%{q}%"))
            stmt = stmt.where(or_(Product.name.ilike(f"%{q}%"), Product.id.in_(sku_match)))
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)
        if low_stock:
            default = await StoreSettingsService(self.session).low_stock_threshold()
            threshold = func.coalesce(Inventory.low_stock_threshold, default)
            low = (
                select(ProductVariant.product_id)
                .join(Inventory, Inventory.variant_id == ProductVariant.id)
                .where(
                    ProductVariant.is_active, Inventory.on_hand - Inventory.reserved <= threshold
                )
            )
            stmt = stmt.where(Product.id.in_(low))
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        products = await self.session.scalars(
            stmt.options(
                selectinload(Product.images),
                selectinload(Product.variants).selectinload(ProductVariant.inventory),
                selectinload(Product.category),
            )
            .order_by(Product.created_at.desc(), Product.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return Page(items=list(products), total=total, page=page, page_size=page_size)

    async def create_product(
        self, data: ProductInput, variants: list[VariantInput], *, admin_user_id: uuid.UUID
    ) -> Product:
        if not variants:
            raise BusinessRuleError("Kamida bitta variant kerak.", code="variant_required")
        name = " ".join(data.name.split())[:200]
        if not name:
            raise BusinessRuleError("Mahsulot nomini kiriting.", code="name_required")
        await self._category(data.category_id)
        skus = [v.sku.strip().upper() for v in variants]
        if len(set(skus)) != len(skus):
            raise ConflictError("Variantlarda bir xil SKU bor.", code="duplicate_sku")
        for sku in skus:
            if await self._sku_taken(sku):
                raise ConflictError(f"«{sku}» SKU allaqachon mavjud.", code="duplicate_sku")

        product = Product(
            name=name,
            slug=await self._unique_slug(Product, name),
            category_id=data.category_id,
            description=(data.description or "").strip() or None,
            brand=(data.brand or "").strip()[:100] or None,
            is_active=data.is_active,
            is_featured=data.is_featured,
        )
        self.session.add(product)
        await self.session.flush()

        default_index = next((i for i, v in enumerate(variants) if v.is_default), 0)
        inventory = InventoryService(self.session)
        for i, v in enumerate(variants):
            variant = ProductVariant(
                product_id=product.id, is_default=i == default_index, **_variant_fields(v)
            )
            self.session.add(variant)
            await self.session.flush()
            self.session.add(
                Inventory(variant_id=variant.id, low_stock_threshold=v.low_stock_threshold)
            )
            await self.session.flush()
            if v.initial_stock < 0:
                raise BusinessRuleError(
                    "Boshlang‘ich qoldiq manfiy bo‘lmasin.", code="invalid_quantity"
                )
            if v.initial_stock > 0:
                await inventory.adjust(
                    variant.id,
                    delta=v.initial_stock,
                    reason="Boshlang‘ich qoldiq",
                    admin_user_id=admin_user_id,
                    commit=False,
                )
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="product.create",
            entity_type="product",
            entity_id=product.id,
            changes={"name": name, "variants": skus},
        )
        await self.session.commit()
        return await self.get_product(product.id)

    async def update_product(
        self, product_id: uuid.UUID, changes: dict[str, Any], *, admin_user_id: uuid.UUID
    ) -> Product:
        product = await self.get_product(product_id)
        before = _product_snapshot(product)
        if "category_id" in changes:
            await self._category(changes["category_id"])
        if "name" in changes:
            name = " ".join(str(changes["name"]).split())[:200]
            if not name:
                raise BusinessRuleError("Mahsulot nomini kiriting.", code="name_required")
            changes["name"] = name
        for key in ("name", "category_id", "description", "brand", "is_active", "is_featured"):
            if key in changes:
                setattr(product, key, changes[key])
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="product.update",
            entity_type="product",
            entity_id=product.id,
            changes=diff(before, _product_snapshot(product)),
        )
        await self.session.commit()
        return await self.get_product(product_id)

    async def delete_product(self, product_id: uuid.UUID, *, admin_user_id: uuid.UUID) -> None:
        """Soft delete: hidden everywhere, but past orders keep their references."""
        product = await self.get_product(product_id)
        product.deleted_at = utcnow()
        product.is_active = False
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="product.delete",
            entity_type="product",
            entity_id=product.id,
            changes={"name": product.name},
        )
        await self.session.commit()

    # --- Variants ------------------------------------------------------------------

    async def add_variant(
        self, product_id: uuid.UUID, data: VariantInput, *, admin_user_id: uuid.UUID
    ) -> ProductVariant:
        product = await self.get_product(product_id)
        fields_ = _variant_fields(data)
        if await self._sku_taken(fields_["sku"]):
            raise ConflictError(f"«{fields_['sku']}» SKU allaqachon mavjud.", code="duplicate_sku")
        if data.is_default:
            for v in product.variants:
                v.is_default = False
            await self.session.flush()
        variant = ProductVariant(product_id=product.id, is_default=data.is_default, **fields_)
        self.session.add(variant)
        await self.session.flush()
        self.session.add(
            Inventory(variant_id=variant.id, low_stock_threshold=data.low_stock_threshold)
        )
        await self.session.flush()
        if data.initial_stock < 0:
            raise BusinessRuleError(
                "Boshlang‘ich qoldiq manfiy bo‘lmasin.", code="invalid_quantity"
            )
        if data.initial_stock:
            await InventoryService(self.session).adjust(
                variant.id,
                delta=data.initial_stock,
                reason="Boshlang‘ich qoldiq",
                admin_user_id=admin_user_id,
                commit=False,
            )
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="variant.create",
            entity_type="product_variant",
            entity_id=variant.id,
            changes={"sku": variant.sku, "price": str(variant.price)},
        )
        await self.session.commit()
        return variant

    async def update_variant(
        self, variant_id: uuid.UUID, changes: dict[str, Any], *, admin_user_id: uuid.UUID
    ) -> ProductVariant:
        variant = await self.session.get(ProductVariant, variant_id, populate_existing=True)
        if variant is None:
            raise NotFoundError("Variant topilmadi.")
        keys = (
            "sku",
            "name",
            "attributes",
            "price",
            "discount_price",
            "barcode",
            "ikpu_code",
            "package_code",
            "weight_grams",
            "is_active",
            "sort_order",
        )
        before = {k: getattr(variant, k) for k in keys}
        merged = VariantInput(**{**before, **{k: v for k, v in changes.items() if k in keys}})
        fields_ = _variant_fields(merged)
        if fields_["sku"] != variant.sku and await self._sku_taken(fields_["sku"], variant.id):
            raise ConflictError(f"«{fields_['sku']}» SKU allaqachon mavjud.", code="duplicate_sku")
        for k, v in fields_.items():
            setattr(variant, k, v)
        if changes.get("is_default"):
            siblings = await self.session.scalars(
                select(ProductVariant).where(
                    ProductVariant.product_id == variant.product_id, ProductVariant.id != variant.id
                )
            )
            for s in siblings:
                s.is_default = False
            await self.session.flush()
            variant.is_default = True
        if "low_stock_threshold" in changes:
            inv = await self.session.get(Inventory, variant.id)
            if inv is not None:
                inv.low_stock_threshold = changes["low_stock_threshold"]
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="variant.update",
            entity_type="product_variant",
            entity_id=variant.id,
            changes=diff(before, {k: getattr(variant, k) for k in keys}),
        )
        await self.session.commit()
        await self.session.refresh(variant)
        return variant

    # --- Images --------------------------------------------------------------------

    async def add_image(
        self,
        product_id: uuid.UUID,
        data: bytes,
        *,
        alt_text: str | None,
        admin_user_id: uuid.UUID,
    ) -> ProductImage:
        if self.storage is None:  # pragma: no cover - wired by the API
            raise RuntimeError("Storage is not configured")
        product = await self.get_product(product_id)
        if len(product.images) >= MAX_IMAGES_PER_PRODUCT:
            raise BusinessRuleError(
                f"Bitta mahsulotga {MAX_IMAGES_PER_PRODUCT} tadan ortiq rasm qo‘shib bo‘lmaydi.",
                code="too_many_images",
            )
        image_type = validate_image(data, max_bytes=get_settings().max_upload_size_bytes)
        key = image_key("products", product.id, image_type)
        await self.storage.save(key, data, image_type.content_type)
        image = ProductImage(
            product_id=product.id,
            path=key,
            alt_text=(alt_text or "").strip()[:200] or None,
            sort_order=len(product.images),
            is_main=not product.images,
        )
        self.session.add(image)
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="product.image_add",
            entity_type="product",
            entity_id=product.id,
            changes={"path": key},
        )
        try:
            await self.session.commit()
        except Exception:
            await self.storage.delete(key)  # don't leave orphan files
            raise
        return image

    async def update_image(
        self,
        image_id: uuid.UUID,
        *,
        is_main: bool | None,
        sort_order: int | None,
        alt_text: str | None,
        admin_user_id: uuid.UUID,
    ) -> ProductImage:
        image = await self.session.get(ProductImage, image_id)
        if image is None:
            raise NotFoundError("Rasm topilmadi.")
        if is_main:
            siblings = await self.session.scalars(
                select(ProductImage).where(ProductImage.product_id == image.product_id)
            )
            for s in siblings:
                s.is_main = False
            await self.session.flush()
            image.is_main = True
        if sort_order is not None:
            image.sort_order = sort_order
        if alt_text is not None:
            image.alt_text = alt_text.strip()[:200] or None
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="product.image_update",
            entity_type="product_image",
            entity_id=image.id,
        )
        await self.session.commit()
        return image

    async def delete_image(self, image_id: uuid.UUID, *, admin_user_id: uuid.UUID) -> None:
        image = await self.session.get(ProductImage, image_id)
        if image is None:
            raise NotFoundError("Rasm topilmadi.")
        product_id, key, was_main = image.product_id, image.path, image.is_main
        await self.session.delete(image)
        await self.session.flush()
        if was_main:
            nxt = await self.session.scalar(
                select(ProductImage)
                .where(ProductImage.product_id == product_id)
                .order_by(ProductImage.sort_order)
                .limit(1)
            )
            if nxt is not None:
                nxt.is_main = True
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="product.image_delete",
            entity_type="product",
            entity_id=product_id,
            changes={"path": key},
        )
        await self.session.commit()
        if self.storage is not None:
            await self.storage.delete(key)

    # --- Categories ----------------------------------------------------------------

    async def list_categories(self) -> list[tuple[Category, int]]:
        """All categories (active or not) with their number of non-deleted products."""
        counts = (
            select(Product.category_id, func.count().label("n"))
            .where(Product.deleted_at.is_(None))
            .group_by(Product.category_id)
            .subquery()
        )
        rows = await self.session.execute(
            select(Category, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.category_id == Category.id)
            .order_by(Category.sort_order, Category.name)
        )
        return [(c, int(n)) for c, n in rows]

    async def _check_parent(
        self, category_id: uuid.UUID | None, parent_id: uuid.UUID | None
    ) -> None:
        if parent_id is None:
            return
        await self._category(parent_id)
        # Walk up from the new parent: reaching the category itself would create a cycle.
        current: uuid.UUID | None = parent_id
        while current is not None:
            if current == category_id:
                raise BusinessRuleError(
                    "Kategoriyani o‘zining ichiga joylashtirib bo‘lmaydi.", code="category_cycle"
                )
            current = await self.session.scalar(
                select(Category.parent_id).where(Category.id == current)
            )

    async def create_category(
        self,
        *,
        name: str,
        parent_id: uuid.UUID | None,
        description: str | None,
        sort_order: int,
        is_active: bool,
        admin_user_id: uuid.UUID,
    ) -> Category:
        name = " ".join(name.split())[:128]
        if not name:
            raise BusinessRuleError("Kategoriya nomini kiriting.", code="name_required")
        await self._check_parent(None, parent_id)
        category = Category(
            name=name,
            slug=await self._unique_slug(Category, name),
            parent_id=parent_id,
            description=(description or "").strip() or None,
            sort_order=sort_order,
            is_active=is_active,
        )
        self.session.add(category)
        await self.session.flush()
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="category.create",
            entity_type="category",
            entity_id=category.id,
            changes={"name": name},
        )
        await self.session.commit()
        return category

    async def update_category(
        self, category_id: uuid.UUID, changes: dict[str, Any], *, admin_user_id: uuid.UUID
    ) -> Category:
        category = await self._category(category_id)
        keys = ("name", "parent_id", "description", "sort_order", "is_active")
        before = {k: getattr(category, k) for k in keys}
        if "parent_id" in changes:
            await self._check_parent(category.id, changes["parent_id"])
        if "name" in changes:
            changes["name"] = " ".join(str(changes["name"]).split())[:128]
            if not changes["name"]:
                raise BusinessRuleError("Kategoriya nomini kiriting.", code="name_required")
        for k in keys:
            if k in changes:
                setattr(category, k, changes[k])
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="category.update",
            entity_type="category",
            entity_id=category.id,
            changes=diff(before, {k: getattr(category, k) for k in keys}),
        )
        await self.session.commit()
        return category

    async def delete_category(self, category_id: uuid.UUID, *, admin_user_id: uuid.UUID) -> None:
        category = await self._category(category_id)
        products = await self.session.scalar(
            select(func.count()).where(Product.category_id == category.id)
        )
        if products:
            raise ConflictError(
                f"Bu kategoriyada {products} ta mahsulot bor. Avval ularni boshqa kategoriyaga "
                "o‘tkazing yoki kategoriyani faolsizlantiring.",
                code="category_not_empty",
                details={"products": products},
            )
        children = await self.session.scalar(
            select(func.count()).where(Category.parent_id == category.id)
        )
        if children:
            raise ConflictError(
                "Bu kategoriyaning ichki kategoriyalari bor. "
                "Avval ularni o‘chiring yoki ko‘chiring.",
                code="category_has_children",
            )
        await self.session.delete(category)
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="category.delete",
            entity_type="category",
            entity_id=category_id,
            changes={"name": category.name},
        )
        await self.session.commit()
        if category.image_path and self.storage is not None:
            await self.storage.delete(category.image_path)

    async def set_category_image(
        self, category_id: uuid.UUID, data: bytes, *, admin_user_id: uuid.UUID
    ) -> Category:
        if self.storage is None:  # pragma: no cover
            raise RuntimeError("Storage is not configured")
        category = await self._category(category_id)
        image_type = validate_image(data, max_bytes=get_settings().max_upload_size_bytes)
        key = image_key("categories", category.id, image_type)
        await self.storage.save(key, data, image_type.content_type)
        old = category.image_path
        category.image_path = key
        record_audit(
            self.session,
            admin_user_id=admin_user_id,
            action="category.image",
            entity_type="category",
            entity_id=category.id,
        )
        await self.session.commit()
        if old:
            await self.storage.delete(old)
        return category
