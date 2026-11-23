"""Public catalog, delivery and cart/checkout schemas (shared by bot and admin)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.integrations.storage.base import Storage
from app.models import District, Product, ProductImage, ProductVariant, Region
from app.models.enums import DeliveryMethodKind, DistrictKind
from app.repositories.products import ProductCard
from app.schemas.common import InputSchema, Money, Schema
from app.services.cart import CartSummary
from app.services.catalog import CategoryNode
from app.services.delivery import DeliveryQuote


class ImageOut(BaseModel):
    id: uuid.UUID
    url: str
    alt_text: str | None
    is_main: bool
    sort_order: int

    @classmethod
    def build(cls, image: ProductImage, storage: Storage) -> ImageOut:
        return cls(
            id=image.id,
            url=storage.url(image.path),
            alt_text=image.alt_text,
            is_main=image.is_main,
            sort_order=image.sort_order,
        )


def main_image_url(product: Product, storage: Storage) -> str | None:
    images = sorted(product.images, key=lambda i: (not i.is_main, i.sort_order))
    return storage.url(images[0].path) if images else None


class ProductCardOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    brand: str | None
    category_id: uuid.UUID
    min_price: Money
    max_original_price: Money
    has_discount: bool
    in_stock: bool
    image_url: str | None

    @classmethod
    def build(cls, card: ProductCard, storage: Storage) -> ProductCardOut:
        p = card.product
        return cls(
            id=p.id,
            name=p.name,
            slug=p.slug,
            brand=p.brand,
            category_id=p.category_id,
            min_price=card.min_price,
            max_original_price=card.max_original_price,
            has_discount=card.has_discount,
            in_stock=card.available > 0,
            image_url=main_image_url(p, storage),
        )


class VariantOut(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    attributes: dict[str, str]
    price: Money
    discount_price: Money | None
    effective_price: Money
    available: int
    is_default: bool

    @classmethod
    def build(cls, v: ProductVariant) -> VariantOut:
        return cls(
            id=v.id,
            sku=v.sku,
            name=v.name,
            attributes={str(k): str(val) for k, val in v.attributes.items()},
            price=v.price,
            discount_price=v.discount_price,
            effective_price=v.effective_price,
            available=max(v.inventory.available, 0) if v.inventory else 0,
            is_default=v.is_default,
        )


class ProductDetailOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    brand: str | None
    category_id: uuid.UUID
    images: list[ImageOut]
    variants: list[VariantOut]

    @classmethod
    def build(cls, p: Product, storage: Storage) -> ProductDetailOut:
        return cls(
            id=p.id,
            name=p.name,
            slug=p.slug,
            description=p.description,
            brand=p.brand,
            category_id=p.category_id,
            images=[ImageOut.build(i, storage) for i in p.images],
            variants=[VariantOut.build(v) for v in p.variants],
        )


class CategoryNodeOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    image_url: str | None
    children: list[CategoryNodeOut]

    @classmethod
    def build(cls, node: CategoryNode, storage: Storage) -> CategoryNodeOut:
        return cls(
            id=node.id,
            name=node.name,
            slug=node.slug,
            image_url=storage.url(node.image_path) if node.image_path else None,
            children=[cls.build(c, storage) for c in node.children],
        )


class RegionOut(Schema):
    id: int
    code: str
    name: str


class DistrictOut(Schema):
    id: int
    region_id: int
    name: str
    kind: DistrictKind


class DeliveryQuoteOut(BaseModel):
    method_id: uuid.UUID
    method_code: str
    method_kind: DeliveryMethodKind
    method_name: str
    price: Money
    base_price: Money
    free_applied: bool
    free_threshold: Money | None
    eta_min_days: int
    eta_max_days: int
    pickup_address: str | None

    @classmethod
    def build(cls, q: DeliveryQuote) -> DeliveryQuoteOut:
        return cls(**{f: getattr(q, f) for f in cls.model_fields})


class StoreInfoOut(BaseModel):
    name: str
    phone: str | None
    address: str | None
    support_telegram: str | None
    currency_display: str


# --- Cart -----------------------------------------------------------------------------


class CartLineOut(BaseModel):
    item_id: uuid.UUID
    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    variant_name: str
    sku: str
    attributes: dict[str, str]
    original_unit_price: Money
    unit_price: Money
    quantity: int
    line_total: Money
    available: int
    is_purchasable: bool


class CartOut(BaseModel):
    lines: list[CartLineOut]
    subtotal: Money
    discount: Money
    total: Money
    promo_code: str | None
    promo_error: str | None
    total_quantity: int
    has_problems: bool

    @classmethod
    def build(cls, s: CartSummary) -> CartOut:
        return cls(
            lines=[
                CartLineOut(
                    **{f: getattr(ln, f) for f in CartLineOut.model_fields if f != "attributes"},
                    attributes={str(k): str(v) for k, v in ln.attributes.items()},
                )
                for ln in s.lines
            ],
            subtotal=s.subtotal,
            discount=s.discount,
            total=s.total,
            promo_code=s.promo_code,
            promo_error=s.promo_error,
            total_quantity=s.total_quantity,
            has_problems=s.has_problems,
        )


class AddCartItemIn(InputSchema):
    variant_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=999)


class UpdateCartItemIn(InputSchema):
    quantity: int = Field(ge=0, le=999)


class PromoCodeIn(InputSchema):
    code: str = Field(min_length=1, max_length=32)


def region_out(r: Region) -> RegionOut:
    return RegionOut.model_validate(r)


def district_out(d: District) -> DistrictOut:
    return DistrictOut.model_validate(d)
