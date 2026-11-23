"""Small helpers that insert valid rows for tests. Each returns the flushed object."""

from __future__ import annotations

import itertools
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Category,
    Inventory,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    User,
)
from app.models.enums import PaymentMethod

_seq = itertools.count(1)


def _n() -> int:
    return next(_seq)


async def make_user(db: AsyncSession, **kw: object) -> User:
    n = _n()
    user = User(telegram_id=10_000_000 + n, first_name=f"Mijoz {n}", **kw)
    db.add(user)
    await db.flush()
    return user


async def make_category(db: AsyncSession, **kw: object) -> Category:
    n = _n()
    cat = Category(name=f"Kategoriya {n}", slug=f"kategoriya-{n}-{uuid.uuid4().hex[:6]}", **kw)
    db.add(cat)
    await db.flush()
    return cat


async def make_variant(
    db: AsyncSession,
    *,
    price: str = "100000",
    stock: int = 10,
    product: Product | None = None,
    **kw: object,
) -> ProductVariant:
    n = _n()
    if product is None:
        category = await make_category(db)
        product = Product(
            category_id=category.id,
            name=f"Mahsulot {n}",
            slug=f"mahsulot-{n}-{uuid.uuid4().hex[:6]}",
        )
        db.add(product)
        await db.flush()
    variant = ProductVariant(
        product_id=product.id, sku=f"SKU-{n}-{uuid.uuid4().hex[:6]}", price=Decimal(price), **kw
    )
    db.add(variant)
    await db.flush()
    db.add(Inventory(variant_id=variant.id, on_hand=stock))
    await db.flush()
    return variant


async def make_order(
    db: AsyncSession,
    *,
    user: User | None = None,
    subtotal: str = "200000",
    discount: str = "0",
    delivery_fee: str = "25000",
    total: str | None = None,
    idempotency_key: str | None = None,
) -> Order:
    user = user or await make_user(db)
    sub, disc, fee = Decimal(subtotal), Decimal(discount), Decimal(delivery_fee)
    order = Order(
        user_id=user.id,
        payment_method=PaymentMethod.CLICK,
        subtotal=sub,
        discount_total=disc,
        delivery_fee=fee,
        total=Decimal(total) if total is not None else sub - disc + fee,
        recipient_name="Aziz Karimov",
        recipient_phone="+998901234567",
        region_id=1,
        district_id=1,
        region_name="Toshkent shahri",
        district_name="Bektemir tumani",
        address_line="Mustaqillik ko‘chasi, 1-uy",
        delivery_method_name="Kuryer orqali yetkazib berish",
        idempotency_key=idempotency_key or uuid.uuid4().hex,
    )
    db.add(order)
    await db.flush()
    return order


def order_item_for(order: Order, variant: ProductVariant, quantity: int = 1) -> OrderItem:
    return OrderItem(
        order_id=order.id,
        product_id=variant.product_id,
        variant_id=variant.id,
        product_name="Mahsulot",
        sku=variant.sku,
        original_unit_price=variant.price,
        unit_price=variant.price,
        quantity=quantity,
        line_total=variant.price * quantity,
    )
