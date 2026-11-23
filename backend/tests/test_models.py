"""Database-level guarantees: constraints, seed data and snapshot behaviour.

These run against the schema built by the real Alembic migrations.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import (
    Category,
    DeliveryMethod,
    DeliveryRate,
    District,
    Inventory,
    OrderItem,
    Payment,
    PaymentTransaction,
    Product,
    ProductVariant,
    PromoCode,
    Region,
    Role,
)
from app.models.enums import DiscountType, DistrictKind, PaymentProvider, PaymentStatus
from tests.factories import make_category, make_order, make_user, make_variant, order_item_for


async def assert_rejected(db: AsyncSession, constraint: str, *objects: object) -> None:
    """Adding ``objects`` must fail with the named constraint; the session stays usable."""
    with pytest.raises(IntegrityError) as exc:  # noqa: PT012 - savepoint must wrap the flush
        async with db.begin_nested():
            db.add_all(objects)
            await db.flush()
    assert constraint in str(exc.value)


# --- Seed data -------------------------------------------------------------------


async def test_regions_and_districts_seeded(db: AsyncSession) -> None:
    assert await db.scalar(select(func.count()).select_from(Region)) == 14
    assert await db.scalar(select(func.count()).select_from(District)) == 206
    tashkent = await db.scalar(select(Region).where(Region.code == "UZ-TK"))
    assert tashkent is not None
    assert tashkent.name == "Toshkent shahri"
    names = set(await db.scalars(select(District.name).where(District.region_id == tashkent.id)))
    assert {"Chilonzor tumani", "Yunusobod tumani", "Mirzo Ulugʻbek tumani"} <= names


async def test_admin_can_add_district_after_seed(db: AsyncSession) -> None:
    """The serial sequence was moved past the seeded ids, so new rows get free ids."""
    district = District(
        region_id=1, code="UZ-TK-99", name="Yangi tuman", kind=DistrictKind.DISTRICT
    )
    db.add(district)
    await db.flush()
    assert district.id > 206


async def test_roles_seeded_with_expected_permissions(db: AsyncSession) -> None:
    roles = {r.name: set(r.permissions) for r in await db.scalars(select(Role))}
    assert set(roles) == {"super_admin", "manager", "operator"}
    assert "staff.manage" in roles["super_admin"]
    assert "staff.manage" not in roles["manager"]
    assert "orders.refund" not in roles["operator"]
    assert roles["operator"] < roles["manager"] < roles["super_admin"]


async def test_delivery_methods_seeded_without_prices(db: AsyncSession) -> None:
    codes = set(await db.scalars(select(DeliveryMethod.code)))
    assert {"courier", "pickup"} <= codes
    assert await db.scalar(select(func.count()).select_from(DeliveryRate)) == 0


# --- Catalog ---------------------------------------------------------------------


async def test_discount_price_must_be_below_price(db: AsyncSession) -> None:
    category = await make_category(db)
    product = Product(category_id=category.id, name="Futbolka", slug=f"f-{uuid.uuid4().hex}")
    db.add(product)
    await db.flush()
    bad = ProductVariant(
        product_id=product.id,
        sku="BAD-1",
        price=Decimal("100000"),
        discount_price=Decimal("100000"),
    )
    await assert_rejected(db, "ck_product_variants_discount_below_price", bad)


async def test_only_one_default_variant_per_product(db: AsyncSession) -> None:
    first = await make_variant(db, is_default=True)
    second = ProductVariant(
        product_id=first.product_id, sku=f"S-{uuid.uuid4().hex}", price=Decimal(1), is_default=True
    )
    await assert_rejected(db, "uq_product_variants_product_default", second)


async def test_sku_is_unique(db: AsyncSession) -> None:
    variant = await make_variant(db)
    dup = ProductVariant(product_id=variant.product_id, sku=variant.sku, price=Decimal(1))
    await assert_rejected(db, "uq_product_variants_sku", dup)


async def test_category_with_products_cannot_be_deleted(db: AsyncSession) -> None:
    variant = await make_variant(db)
    product = await db.get(Product, variant.product_id)
    assert product is not None
    with pytest.raises(IntegrityError, match="fk_products_category_id_categories"):
        async with db.begin_nested():
            await db.execute(delete(Category).where(Category.id == product.category_id))


# --- Inventory -------------------------------------------------------------------


async def test_reserved_cannot_exceed_on_hand(db: AsyncSession) -> None:
    variant = await make_variant(db, stock=2)
    with pytest.raises(IntegrityError, match="ck_inventory_reserved_within_on_hand"):
        async with db.begin_nested():
            await db.execute(
                update(Inventory).where(Inventory.variant_id == variant.id).values(reserved=3)
            )


async def test_concurrent_reservations_cannot_oversell(engine: AsyncEngine) -> None:
    """Two customers try to buy the last unit at the same moment: exactly one wins.

    Uses the conditional UPDATE that the inventory service will use, in two real
    concurrent transactions (committed data, cleaned up afterwards).
    """
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        variant = await make_variant(setup, stock=1)
        await setup.commit()
        product_id, variant_id = variant.product_id, variant.id
        category_id = (await setup.get(Product, product_id)).category_id  # type: ignore[union-attr]

    reserve = text(
        "UPDATE inventory SET reserved = reserved + :q "
        "WHERE variant_id = :v AND on_hand - reserved >= :q"
    )
    both_ready = asyncio.Barrier(2)

    async def attempt() -> int:
        async with engine.connect() as conn, conn.begin():
            await both_ready.wait()
            result = await conn.execute(reserve, {"q": 1, "v": variant_id})
            await asyncio.sleep(0.2)  # hold the row lock so the other transaction waits
            return result.rowcount

    try:
        results = await asyncio.gather(attempt(), attempt())
        assert sorted(results) == [0, 1]
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT on_hand, reserved FROM inventory WHERE variant_id = :v"),
                    {"v": variant_id},
                )
            ).one()
        assert (row.on_hand, row.reserved) == (1, 1)
    finally:
        async with engine.begin() as conn:
            await conn.execute(delete(Product).where(Product.id == product_id))
            await conn.execute(delete(Category).where(Category.id == category_id))


# --- Orders ----------------------------------------------------------------------


async def test_order_number_is_generated(db: AsyncSession) -> None:
    order = await make_order(db)
    await db.refresh(order)
    assert order.number.startswith("OS-")
    assert len(order.number) == 9


async def test_order_total_must_be_consistent(db: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_orders_total_consistent"):
        async with db.begin_nested():
            await make_order(db, subtotal="100000", delivery_fee="20000", total="100000")


async def test_duplicate_checkout_key_rejected(db: AsyncSession) -> None:
    user = await make_user(db)
    await make_order(db, user=user, idempotency_key="checkout-abc")
    with pytest.raises(IntegrityError, match="uq_orders_user_id_idempotency_key"):
        async with db.begin_nested():
            await make_order(db, user=user, idempotency_key="checkout-abc")


async def test_order_item_line_total_must_match(db: AsyncSession) -> None:
    order = await make_order(db)
    variant = await make_variant(db, price="50000")
    item = order_item_for(order, variant, quantity=2)
    item.line_total = Decimal("99999")
    await assert_rejected(db, "ck_order_items_line_total_consistent", item)


async def test_order_item_snapshot_survives_product_deletion(db: AsyncSession) -> None:
    order = await make_order(db)
    variant = await make_variant(db, price="75000")
    item = order_item_for(order, variant, quantity=2)
    item.product_name = "Qishki kurtka"
    db.add(item)
    await db.flush()

    await db.execute(delete(Product).where(Product.id == variant.product_id))
    await db.flush()

    saved = await db.get(OrderItem, item.id, populate_existing=True)
    assert saved is not None
    assert saved.variant_id is None
    assert saved.product_id is None
    assert saved.product_name == "Qishki kurtka"
    assert saved.line_total == Decimal("150000.00")


# --- Payments --------------------------------------------------------------------


async def test_order_can_be_paid_only_once(db: AsyncSession) -> None:
    order = await make_order(db)
    db.add(
        Payment(
            order_id=order.id,
            provider=PaymentProvider.CLICK,
            amount=order.total,
            status=PaymentStatus.PAID,
        )
    )
    await db.flush()
    second = Payment(
        order_id=order.id,
        provider=PaymentProvider.PAYME,
        amount=order.total,
        status=PaymentStatus.PAID,
    )
    await assert_rejected(db, "uq_payments_order_paid", second)


async def test_duplicate_provider_transaction_rejected(db: AsyncSession) -> None:
    order = await make_order(db)
    payment = Payment(order_id=order.id, provider=PaymentProvider.PAYME, amount=order.total)
    db.add(payment)
    await db.flush()

    def txn() -> PaymentTransaction:
        return PaymentTransaction(
            payment_id=payment.id,
            provider=PaymentProvider.PAYME,
            external_id="ext-123",
            provider_state="1",
            amount=order.total,
        )

    db.add(txn())
    await db.flush()
    await assert_rejected(db, "uq_payment_transactions_provider_external_id", txn())


# --- Delivery & promo ------------------------------------------------------------


async def test_one_region_wide_rate_per_method(db: AsyncSession) -> None:
    method = await db.scalar(select(DeliveryMethod).where(DeliveryMethod.code == "courier"))
    assert method is not None
    db.add(DeliveryRate(method_id=method.id, region_id=1, price=Decimal("20000")))
    await db.flush()
    duplicate = DeliveryRate(method_id=method.id, region_id=1, price=Decimal("30000"))
    await assert_rejected(db, "uq_delivery_rates_method_id_region_id_district_id", duplicate)


async def test_district_rate_can_override_region_rate(db: AsyncSession) -> None:
    method = await db.scalar(select(DeliveryMethod).where(DeliveryMethod.code == "courier"))
    assert method is not None
    db.add_all(
        [
            DeliveryRate(method_id=method.id, region_id=1, price=Decimal("20000")),
            DeliveryRate(method_id=method.id, region_id=1, district_id=1, price=Decimal("0")),
        ]
    )
    await db.flush()


@pytest.mark.parametrize(
    ("code", "dtype", "value", "constraint"),
    [
        ("yoz25", DiscountType.PERCENT, "25", "ck_promo_codes_code_uppercase"),
        ("YOZ150", DiscountType.PERCENT, "150", "ck_promo_codes_percent_at_most_100"),
        ("YOZ0", DiscountType.FIXED, "0", "ck_promo_codes_value_positive"),
    ],
)
async def test_invalid_promo_codes_rejected(
    db: AsyncSession, code: str, dtype: DiscountType, value: str, constraint: str
) -> None:
    await assert_rejected(
        db, constraint, PromoCode(code=code, discount_type=dtype, value=Decimal(value))
    )
