"""Admin panel request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.integrations.storage.base import Storage
from app.models import (
    AdminUser,
    AuditLog,
    Category,
    DeliveryMethod,
    DeliveryRate,
    District,
    InventoryMovement,
    Product,
    ProductVariant,
    PromoCode,
    Region,
)
from app.models.enums import (
    AdminRoleName,
    DeliveryMethodKind,
    DiscountType,
    DistrictKind,
    InventoryMovementType,
)
from app.schemas.catalog import ImageOut, main_image_url
from app.schemas.common import InputSchema, Money, Schema
from app.services.customers import CustomerStats
from app.services.inventory import LowStockItem, StockRow
from app.services.reports import Dashboard, RevenueStat

# --- Auth ------------------------------------------------------------------------------


class LoginIn(InputSchema):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class AdminMeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    role_title: str
    permissions: list[str]

    @classmethod
    def build(cls, admin: AdminUser) -> AdminMeOut:
        return cls(
            id=admin.id,
            email=admin.email,
            full_name=admin.full_name,
            role=admin.role.name,
            role_title=admin.role.title,
            permissions=sorted(admin.role.permissions),
        )


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth scheme name, not a secret
    expires_at: datetime
    admin: AdminMeOut


# --- Catalog ---------------------------------------------------------------------------


class VariantIn(InputSchema):
    sku: str = Field(min_length=1, max_length=64)
    price: Money = Field(ge=0, max_digits=14, decimal_places=2)
    name: str = Field(default="", max_length=120)
    attributes: dict[str, str] = Field(default_factory=dict, max_length=10)
    discount_price: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    barcode: str | None = Field(default=None, max_length=64)
    ikpu_code: str | None = Field(default=None, max_length=32)
    package_code: str | None = Field(default=None, max_length=32)
    weight_grams: int | None = Field(default=None, ge=0)
    is_default: bool = False
    is_active: bool = True
    sort_order: int = 0
    initial_stock: int = Field(default=0, ge=0, le=1_000_000)
    low_stock_threshold: int | None = Field(default=None, ge=0)


class VariantUpdateIn(InputSchema):
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    price: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    name: str | None = Field(default=None, max_length=120)
    attributes: dict[str, str] | None = None
    discount_price: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    barcode: str | None = None
    ikpu_code: str | None = None
    package_code: str | None = None
    weight_grams: int | None = Field(default=None, ge=0)
    is_default: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    low_stock_threshold: int | None = Field(default=None, ge=0)


class ProductCreateIn(InputSchema):
    name: str = Field(min_length=1, max_length=200)
    category_id: uuid.UUID
    description: str | None = Field(default=None, max_length=10_000)
    brand: str | None = Field(default=None, max_length=100)
    is_active: bool = True
    is_featured: bool = False
    variants: list[VariantIn] = Field(min_length=1, max_length=100)


class ProductUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=10_000)
    brand: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    is_featured: bool | None = None


class AdminVariantOut(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    attributes: dict[str, str]
    price: Money
    discount_price: Money | None
    barcode: str | None
    ikpu_code: str | None
    package_code: str | None
    weight_grams: int | None
    is_default: bool
    is_active: bool
    sort_order: int
    on_hand: int
    reserved: int
    available: int
    low_stock_threshold: int | None

    @classmethod
    def build(cls, v: ProductVariant) -> AdminVariantOut:
        inv = v.inventory
        return cls(
            id=v.id,
            sku=v.sku,
            name=v.name,
            attributes={str(k): str(val) for k, val in v.attributes.items()},
            price=v.price,
            discount_price=v.discount_price,
            barcode=v.barcode,
            ikpu_code=v.ikpu_code,
            package_code=v.package_code,
            weight_grams=v.weight_grams,
            is_default=v.is_default,
            is_active=v.is_active,
            sort_order=v.sort_order,
            on_hand=inv.on_hand if inv else 0,
            reserved=inv.reserved if inv else 0,
            available=inv.available if inv else 0,
            low_stock_threshold=inv.low_stock_threshold if inv else None,
        )


class AdminProductOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    brand: str | None
    category_id: uuid.UUID
    category_name: str | None
    is_active: bool
    is_featured: bool
    sold_count: int
    image_url: str | None
    images: list[ImageOut]
    variants: list[AdminVariantOut]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(cls, p: Product, storage: Storage) -> AdminProductOut:
        return cls(
            id=p.id,
            name=p.name,
            slug=p.slug,
            description=p.description,
            brand=p.brand,
            category_id=p.category_id,
            category_name=p.category.name if p.category else None,
            is_active=p.is_active,
            is_featured=p.is_featured,
            sold_count=p.sold_count,
            image_url=main_image_url(p, storage),
            images=[ImageOut.build(i, storage) for i in p.images],
            variants=[AdminVariantOut.build(v) for v in p.variants],
            created_at=p.created_at,
            updated_at=p.updated_at,
        )


class ImageUpdateIn(InputSchema):
    is_main: bool | None = None
    sort_order: int | None = None
    alt_text: str | None = Field(default=None, max_length=200)


class CategoryIn(InputSchema):
    name: str = Field(min_length=1, max_length=128)
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = None
    is_active: bool | None = None


class AdminCategoryOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    slug: str
    description: str | None
    image_url: str | None
    sort_order: int
    is_active: bool
    products_count: int

    @classmethod
    def build(cls, c: Category, products_count: int, storage: Storage) -> AdminCategoryOut:
        return cls(
            id=c.id,
            parent_id=c.parent_id,
            name=c.name,
            slug=c.slug,
            description=c.description,
            image_url=storage.url(c.image_path) if c.image_path else None,
            sort_order=c.sort_order,
            is_active=c.is_active,
            products_count=products_count,
        )


# --- Inventory -------------------------------------------------------------------------


class StockRowOut(BaseModel):
    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    variant_name: str
    sku: str
    is_active: bool
    on_hand: int
    reserved: int
    available: int
    low_stock_threshold: int | None
    is_low: bool

    @classmethod
    def build(cls, r: StockRow) -> StockRowOut:
        return cls(**{f: getattr(r, f) for f in cls.model_fields})


class LowStockOut(BaseModel):
    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    variant_name: str
    sku: str
    on_hand: int
    reserved: int
    available: int
    threshold: int

    @classmethod
    def build(cls, r: LowStockItem) -> LowStockOut:
        return cls(**{f: getattr(r, f) for f in cls.model_fields})


class StockAdjustIn(InputSchema):
    delta: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=1, max_length=255)

    @field_validator("delta")
    @classmethod
    def _non_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("0 bo‘lishi mumkin emas")
        return v


class StockLevelOut(BaseModel):
    variant_id: uuid.UUID
    on_hand: int
    reserved: int
    available: int


class MovementOut(Schema):
    id: uuid.UUID
    type: InventoryMovementType
    on_hand_delta: int
    reserved_delta: int
    on_hand_after: int
    reserved_after: int
    reason: str | None
    order_id: uuid.UUID | None
    admin_user_id: uuid.UUID | None
    created_at: datetime


def movement_out(m: InventoryMovement) -> MovementOut:
    return MovementOut.model_validate(m)


# --- Customers -------------------------------------------------------------------------


class AdminCustomerOut(BaseModel):
    id: uuid.UUID
    telegram_id: int
    first_name: str
    last_name: str | None
    username: str | None
    phone: str | None
    phone_verified: bool
    is_blocked: bool
    orders_count: int
    total_spent: Money
    last_order_at: datetime | None
    created_at: datetime

    @classmethod
    def build(cls, s: CustomerStats) -> AdminCustomerOut:
        u = s.user
        return cls(
            id=u.id,
            telegram_id=u.telegram_id,
            first_name=u.first_name,
            last_name=u.last_name,
            username=u.username,
            phone=u.phone,
            phone_verified=u.phone_verified,
            is_blocked=u.is_blocked,
            orders_count=s.orders_count,
            total_spent=s.total_spent,
            last_order_at=s.last_order_at,
            created_at=u.created_at,
        )


class CustomerUpdateIn(InputSchema):
    is_blocked: bool


# --- Promo codes -----------------------------------------------------------------------


class PromoIn(InputSchema):
    code: str = Field(min_length=2, max_length=32)
    description: str | None = Field(default=None, max_length=2000)
    discount_type: DiscountType
    value: Money = Field(gt=0, max_digits=14, decimal_places=2)
    max_discount: Money | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    min_order_amount: Money = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    usage_limit: int | None = Field(default=None, gt=0)
    per_user_limit: int | None = Field(default=None, gt=0)
    is_active: bool = True


class PromoUpdateIn(InputSchema):
    code: str | None = Field(default=None, min_length=2, max_length=32)
    description: str | None = Field(default=None, max_length=2000)
    discount_type: DiscountType | None = None
    value: Money | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    max_discount: Money | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    min_order_amount: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    usage_limit: int | None = Field(default=None, gt=0)
    per_user_limit: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class PromoOut(Schema):
    id: uuid.UUID
    code: str
    description: str | None
    discount_type: DiscountType
    value: Money
    max_discount: Money | None
    min_order_amount: Money
    starts_at: datetime
    ends_at: datetime | None
    usage_limit: int | None
    per_user_limit: int | None
    used_count: int
    is_active: bool
    created_at: datetime


def promo_out(p: PromoCode) -> PromoOut:
    return PromoOut.model_validate(p)


# --- Delivery --------------------------------------------------------------------------


class AdminRegionOut(BaseModel):
    id: int
    code: str
    name: str
    sort_order: int
    is_active: bool
    districts_count: int

    @classmethod
    def build(cls, r: Region, districts_count: int) -> AdminRegionOut:
        return cls(
            id=r.id,
            code=r.code,
            name=r.name,
            sort_order=r.sort_order,
            is_active=r.is_active,
            districts_count=districts_count,
        )


class RegionUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = None
    is_active: bool | None = None


class AdminDistrictOut(Schema):
    id: int
    region_id: int
    code: str
    name: str
    kind: DistrictKind
    sort_order: int
    is_active: bool


def district_admin_out(d: District) -> AdminDistrictOut:
    return AdminDistrictOut.model_validate(d)


class DistrictIn(InputSchema):
    name: str = Field(min_length=1, max_length=100)
    kind: DistrictKind = DistrictKind.DISTRICT
    sort_order: int = 0


class DistrictUpdateIn(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: DistrictKind | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class DeliveryMethodIn(InputSchema):
    code: str = Field(min_length=2, max_length=32)
    kind: DeliveryMethodKind
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int = 0
    is_active: bool = True


class DeliveryMethodUpdateIn(InputSchema):
    kind: DeliveryMethodKind | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = None
    is_active: bool | None = None


class DeliveryMethodOut(Schema):
    id: uuid.UUID
    code: str
    kind: DeliveryMethodKind
    name: str
    description: str | None
    sort_order: int
    is_active: bool


def method_out(m: DeliveryMethod) -> DeliveryMethodOut:
    return DeliveryMethodOut.model_validate(m)


class DeliveryRateIn(InputSchema):
    method_id: uuid.UUID
    region_id: int
    district_id: int | None = None
    price: Money = Field(ge=0, max_digits=14, decimal_places=2)
    free_threshold: Money | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    eta_min_days: int = Field(default=1, ge=0, le=60)
    eta_max_days: int = Field(default=3, ge=0, le=60)
    pickup_address: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class DeliveryRateUpdateIn(InputSchema):
    price: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    free_threshold: Money | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    eta_min_days: int | None = Field(default=None, ge=0, le=60)
    eta_max_days: int | None = Field(default=None, ge=0, le=60)
    pickup_address: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class DeliveryRateOut(BaseModel):
    id: uuid.UUID
    method_id: uuid.UUID
    method_name: str
    region_id: int
    region_name: str
    district_id: int | None
    district_name: str | None
    price: Money
    free_threshold: Money | None
    eta_min_days: int
    eta_max_days: int
    pickup_address: str | None
    is_active: bool

    @classmethod
    def build(cls, r: DeliveryRate) -> DeliveryRateOut:
        return cls(
            id=r.id,
            method_id=r.method_id,
            method_name=r.method.name,
            region_id=r.region_id,
            region_name=r.region.name,
            district_id=r.district_id,
            district_name=r.district.name if r.district else None,
            price=r.price,
            free_threshold=r.free_threshold,
            eta_min_days=r.eta_min_days,
            eta_max_days=r.eta_max_days,
            pickup_address=r.pickup_address,
            is_active=r.is_active,
        )


# --- Staff -----------------------------------------------------------------------------


class StaffIn(InputSchema):
    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=10, max_length=256)
    role: AdminRoleName
    telegram_id: int | None = None


class StaffUpdateIn(InputSchema):
    full_name: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, min_length=10, max_length=256)
    role: AdminRoleName | None = None
    is_active: bool | None = None
    telegram_id: int | None = None


class StaffOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    role_title: str
    telegram_id: int | None
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime

    @classmethod
    def build(cls, a: AdminUser) -> StaffOut:
        return cls(
            id=a.id,
            email=a.email,
            full_name=a.full_name,
            role=a.role.name,
            role_title=a.role.title,
            telegram_id=a.telegram_id,
            is_active=a.is_active,
            last_login_at=a.last_login_at,
            created_at=a.created_at,
        )


class RoleOut(Schema):
    id: int
    name: str
    title: str
    permissions: list[str]


class AuditLogOut(Schema):
    id: uuid.UUID
    admin_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    changes: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime


def audit_out(a: AuditLog) -> AuditLogOut:
    return AuditLogOut.model_validate(a)


# --- Dashboard -------------------------------------------------------------------------


class RevenueStatOut(BaseModel):
    revenue: Money
    orders: int

    @classmethod
    def build(cls, s: RevenueStat) -> RevenueStatOut:
        return cls(revenue=s.revenue, orders=s.orders)


class DashboardOut(BaseModel):
    revenue_total: Money
    revenue_today: RevenueStatOut
    revenue_week: RevenueStatOut
    revenue_month: RevenueStatOut
    orders_total: int
    orders_pending: int
    orders_in_progress: int
    orders_completed: int
    orders_cancelled: int
    customers_total: int
    customers_new_month: int
    low_stock: list[LowStockOut]
    best_sellers: list[dict[str, Any]]
    sales_chart: list[dict[str, Any]]

    @classmethod
    def build(cls, d: Dashboard) -> DashboardOut:
        return cls(
            revenue_total=d.revenue_total,
            revenue_today=RevenueStatOut.build(d.revenue_today),
            revenue_week=RevenueStatOut.build(d.revenue_week),
            revenue_month=RevenueStatOut.build(d.revenue_month),
            orders_total=d.orders_total,
            orders_pending=d.orders_pending,
            orders_in_progress=d.orders_in_progress,
            orders_completed=d.orders_completed,
            orders_cancelled=d.orders_cancelled,
            customers_total=d.customers_total,
            customers_new_month=d.customers_new_month,
            low_stock=[LowStockOut.build(i) for i in d.low_stock],
            best_sellers=d.best_sellers,
            sales_chart=d.sales_chart,
        )
