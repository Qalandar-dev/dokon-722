from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.clock import utcnow
from app.core.exceptions import (
    BusinessRuleError,
    InsufficientStockError,
    InvalidTransitionError,
    NotFoundError,
)
from app.models import (
    AuditLog,
    Category,
    DeliveryRate,
    Inventory,
    Order,
    Product,
    PromoCode,
    PromoCodeRedemption,
    User,
)
from app.models.enums import (
    ActorType,
    DeliveryStatus,
    DiscountType,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    StockState,
)
from app.services.cart import CartService
from app.services.orders import Actor, CheckoutRequest, OrderService
from tests.factories import BEKTEMIR_DISTRICT_ID, Shop, make_shop, make_user, set_setting


def checkout(shop: Shop, **kw: object) -> CheckoutRequest:
    defaults: dict[str, object] = {
        "user_id": shop.user.id,
        "idempotency_key": uuid.uuid4().hex,
        "recipient_name": "  Dilnoza   Rahimova ",
        "recipient_phone": "90 123 45 67",
        "district_id": BEKTEMIR_DISTRICT_ID,
        "address_line": "Yangi Sergeli ko‘chasi, 12-uy, 5-xonadon",
        "landmark": "Makro yonida",
        "delivery_method_id": shop.courier_id,
        "payment_method": PaymentMethod.CLICK,
    }
    return CheckoutRequest(**{**defaults, **kw})  # type: ignore[arg-type]


async def stock(db: AsyncSession, variant_id: uuid.UUID) -> tuple[int, int]:
    inv = await db.get(Inventory, variant_id, populate_existing=True)
    assert inv is not None
    return inv.on_hand, inv.reserved


@pytest.fixture
async def admin_id(db: AsyncSession) -> uuid.UUID:
    from app.core.security import hash_password
    from app.models import AdminUser

    admin = AdminUser(
        email=f"{uuid.uuid4().hex[:8]}@store.uz",
        full_name="Menejer",
        password_hash=hash_password("x"),
        role_id=2,
    )
    db.add(admin)
    await db.flush()
    return admin.id


# --- Checkout --------------------------------------------------------------------------


async def test_place_order_snapshots_everything(db: AsyncSession) -> None:
    shop = await make_shop(db, price="120000", stock=5, delivery_price="25000")
    await CartService(db).add_item(shop.user.id, shop.variant.id, 2)

    order = await OrderService(db).place_order(checkout(shop))

    assert order.number.startswith("OS-")
    assert (order.subtotal, order.delivery_fee, order.total) == (
        Decimal("240000.00"),
        Decimal("25000.00"),
        Decimal("265000.00"),
    )
    assert order.recipient_name == "Dilnoza Rahimova"
    assert order.recipient_phone == "+998901234567"
    assert (order.region_name, order.district_name) == ("Toshkent shahri", "Bektemir tumani")
    assert order.delivery_method_name == "Kuryer orqali yetkazib berish"
    assert (order.status, order.payment_status) == (OrderStatus.PENDING, PaymentStatus.PENDING)
    assert order.stock_state is StockState.RESERVED
    assert order.reservation_expires_at is not None  # online payment window
    [item] = order.items
    assert (item.quantity, item.unit_price, item.sku) == (2, Decimal("120000.00"), shop.variant.sku)
    assert await stock(db, shop.variant.id) == (5, 2)
    assert (await CartService(db).summary(shop.user.id)).is_empty
    assert [h.to_value for h in order.history] == ["pending"]


async def test_same_key_returns_same_order(db: AsyncSession) -> None:
    shop = await make_shop(db)
    await CartService(db).add_item(shop.user.id, shop.variant.id, 1)
    req = checkout(shop)
    service = OrderService(db)

    first = await service.place_order(req)
    second = await service.place_order(req)  # double tap / retry
    assert first.id == second.id
    assert await db.scalar(select(func.count()).where(Order.user_id == shop.user.id)) == 1


async def test_failed_checkout_changes_nothing(db: AsyncSession) -> None:
    shop = await make_shop(db, stock=3)
    cart = CartService(db)
    await cart.add_item(shop.user.id, shop.variant.id, 3)
    # Someone else bought two units after this customer filled the cart.
    other = await make_user(db)
    await cart.add_item(other.id, shop.variant.id, 2)
    await OrderService(db).place_order(checkout(shop, user_id=other.id))

    with pytest.raises(BusinessRuleError) as exc:
        await OrderService(db).place_order(checkout(shop))
    assert exc.value.code == "cart_has_unavailable_items"
    assert await db.scalar(select(func.count()).where(Order.user_id == shop.user.id)) == 0
    assert await stock(db, shop.variant.id) == (3, 2)
    assert not (await cart.summary(shop.user.id)).is_empty  # cart kept for the customer


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"recipient_phone": "12345"}, "invalid_phone"),
        ({"address_line": "   "}, "address_required"),
        ({"payment_method": PaymentMethod.CASH_ON_DELIVERY}, "payment_method_unavailable"),
        ({"idempotency_key": "x"}, "invalid_idempotency_key"),
    ],
)
async def test_checkout_validation(db: AsyncSession, kw: dict[str, object], code: str) -> None:
    shop = await make_shop(db)
    await CartService(db).add_item(shop.user.id, shop.variant.id, 1)
    with pytest.raises(BusinessRuleError) as exc:
        await OrderService(db).place_order(checkout(shop, **kw))
    assert exc.value.code == code


async def test_empty_cart_and_blocked_user(db: AsyncSession) -> None:
    shop = await make_shop(db)
    with pytest.raises(BusinessRuleError, match="Savat boʻsh"):
        await OrderService(db).place_order(checkout(shop))
    shop.user.is_blocked = True
    await db.flush()
    with pytest.raises(Exception, match="bloklangan"):
        await OrderService(db).place_order(checkout(shop))


async def test_promo_is_applied_and_redeemed(db: AsyncSession) -> None:
    shop = await make_shop(db, price="200000")
    db.add(PromoCode(code="QISH15", discount_type=DiscountType.PERCENT, value=Decimal(15)))
    await db.flush()
    cart = CartService(db)
    await cart.add_item(shop.user.id, shop.variant.id, 1)
    await cart.apply_promo(shop.user.id, "qish15")

    order = await OrderService(db).place_order(checkout(shop))
    assert order.discount_total == Decimal("30000.00")
    assert order.total == Decimal("195000.00")  # 200 000 - 30 000 + 25 000
    assert order.promo_code == "QISH15"
    assert await db.scalar(select(func.count()).where(PromoCodeRedemption.order_id == order.id))


# --- Payment, confirmation, fulfilment -------------------------------------------------


async def _placed(db: AsyncSession, *, method: PaymentMethod = PaymentMethod.CLICK) -> Order:
    if method is PaymentMethod.CASH_ON_DELIVERY:
        await set_setting(db, "payments.cash_on_delivery_enabled", True)
    shop = await make_shop(db, price="100000", stock=10)
    await CartService(db).add_item(shop.user.id, shop.variant.id, 2)
    return await OrderService(db).place_order(checkout(shop, payment_method=method))


async def test_payment_turns_reservation_into_sale(db: AsyncSession) -> None:
    order = await _placed(db)
    variant_id = order.items[0].variant_id
    assert variant_id is not None
    service = OrderService(db)

    paid = await service.confirm_payment(order.id)
    assert paid.payment_status is PaymentStatus.PAID
    assert paid.stock_state is StockState.SOLD
    assert paid.reservation_expires_at is None
    assert await stock(db, variant_id) == (8, 0)
    product = await db.get(Product, paid.items[0].product_id, populate_existing=True)
    assert product is not None
    assert product.sold_count == 2

    again = await service.confirm_payment(order.id)  # duplicate callback
    assert again.payment_status is PaymentStatus.PAID
    assert await stock(db, variant_id) == (8, 0)


async def test_online_order_must_be_paid_before_confirmation(
    db: AsyncSession, admin_id: uuid.UUID
) -> None:
    order = await _placed(db)
    service = OrderService(db)
    with pytest.raises(BusinessRuleError) as exc:
        await service.confirm(order.id, admin_user_id=admin_id)
    assert exc.value.code == "payment_required"
    await service.confirm_payment(order.id)
    confirmed = await service.confirm(order.id, admin_user_id=admin_id)
    assert confirmed.status is OrderStatus.CONFIRMED
    assert confirmed.confirmed_at is not None
    assert await db.scalar(
        select(func.count()).where(
            AuditLog.entity_id == str(order.id), AuditLog.action == "order.confirm"
        )
    )


async def test_cash_order_full_lifecycle(db: AsyncSession, admin_id: uuid.UUID) -> None:
    order = await _placed(db, method=PaymentMethod.CASH_ON_DELIVERY)
    assert order.reservation_expires_at is None  # no payment window for cash
    variant_id = order.items[0].variant_id
    assert variant_id is not None
    service = OrderService(db)

    order = await service.confirm(order.id, admin_user_id=admin_id)
    assert order.stock_state is StockState.SOLD
    assert await stock(db, variant_id) == (8, 0)

    order = await service.change_status(order.id, OrderStatus.PROCESSING, admin_user_id=admin_id)
    assert order.delivery_status is DeliveryStatus.PREPARING
    order = await service.change_delivery_status(
        order.id, DeliveryStatus.SHIPPED, admin_user_id=admin_id
    )
    assert order.status is OrderStatus.SHIPPED
    assert order.shipped_at is not None
    order = await service.change_delivery_status(
        order.id, DeliveryStatus.DELIVERED, admin_user_id=admin_id
    )
    assert order.status is OrderStatus.DELIVERED
    assert order.payment_status is PaymentStatus.PAID  # courier collected the cash
    fields = [(h.field.value, h.to_value) for h in order.history]
    assert ("delivery_status", "delivered") in fields
    assert ("payment_status", "paid") in fields


async def test_invalid_transition_is_rejected(db: AsyncSession, admin_id: uuid.UUID) -> None:
    order = await _placed(db)
    with pytest.raises(InvalidTransitionError):
        await OrderService(db).change_status(
            order.id, OrderStatus.DELIVERED, admin_user_id=admin_id
        )
    with pytest.raises(BusinessRuleError) as exc:
        await OrderService(db).change_delivery_status(
            order.id, DeliveryStatus.SHIPPED, admin_user_id=admin_id
        )
    assert exc.value.code == "order_not_in_fulfilment"


# --- Cancellation, refund, expiry ------------------------------------------------------


async def test_customer_cancels_unpaid_order(db: AsyncSession) -> None:
    order = await _placed(db)
    variant_id = order.items[0].variant_id
    assert variant_id is not None
    cancelled = await OrderService(db).cancel(order.id, actor=Actor.customer(order.user_id))
    assert cancelled.status is OrderStatus.CANCELLED
    assert cancelled.payment_status is PaymentStatus.CANCELLED
    assert cancelled.stock_state is StockState.RELEASED
    assert await stock(db, variant_id) == (10, 0)


async def test_customer_cannot_cancel_others_or_paid_orders(db: AsyncSession) -> None:
    order = await _placed(db)
    stranger = await make_user(db)
    service = OrderService(db)
    with pytest.raises(NotFoundError):
        await service.cancel(order.id, actor=Actor.customer(stranger.id))
    await service.confirm_payment(order.id)
    with pytest.raises(BusinessRuleError) as exc:
        await service.cancel(order.id, actor=Actor.customer(order.user_id))
    assert exc.value.code == "cancel_requires_support"


async def test_staff_cancel_after_payment_returns_stock(
    db: AsyncSession, admin_id: uuid.UUID
) -> None:
    order = await _placed(db)
    variant_id = order.items[0].variant_id
    assert variant_id is not None
    service = OrderService(db)
    await service.confirm_payment(order.id)
    cancelled = await service.cancel(order.id, actor=Actor.admin(admin_id), reason="Mijoz rad etdi")
    assert cancelled.stock_state is StockState.RETURNED
    assert cancelled.payment_status is PaymentStatus.PAID  # money still to be refunded
    assert await stock(db, variant_id) == (10, 0)

    refunded = await service.record_refund(
        order.id, admin_user_id=admin_id, restock=True, reason="Pul qaytarildi"
    )
    assert refunded.status is OrderStatus.REFUNDED
    assert refunded.payment_status is PaymentStatus.REFUNDED
    assert await stock(db, variant_id) == (10, 0)  # not returned twice


async def test_refund_after_delivery_with_restock(db: AsyncSession, admin_id: uuid.UUID) -> None:
    order = await _placed(db)
    variant_id = order.items[0].variant_id
    assert variant_id is not None
    service = OrderService(db)
    await service.confirm_payment(order.id)
    await service.confirm(order.id, admin_user_id=admin_id)
    await service.change_status(order.id, OrderStatus.SHIPPED, admin_user_id=admin_id)
    await service.change_status(order.id, OrderStatus.DELIVERED, admin_user_id=admin_id)
    with pytest.raises(BusinessRuleError):
        await service.cancel(order.id, actor=Actor.admin(admin_id))

    refunded = await service.record_refund(
        order.id, admin_user_id=admin_id, restock=True, reason="Nuqsonsiz qaytarildi"
    )
    assert refunded.stock_state is StockState.RETURNED
    assert await stock(db, variant_id) == (10, 0)


async def test_unpaid_orders_expire(db: AsyncSession) -> None:
    order = await _placed(db)
    variant_id = order.items[0].variant_id
    assert variant_id is not None
    service = OrderService(db)

    assert await service.expire_unpaid(now=utcnow()) == 0  # still inside the window
    later = utcnow() + timedelta(hours=2)
    assert await service.expire_unpaid(now=later) == 1
    expired = await service.get(order.id)
    assert expired.status is OrderStatus.CANCELLED
    assert expired.cancel_reason == "Toʻlov muddati tugadi"
    assert expired.history[-1].actor_type is ActorType.SYSTEM
    assert await stock(db, variant_id) == (10, 0)
    assert await service.expire_unpaid(now=later) == 0


async def test_paid_order_never_expires(db: AsyncSession) -> None:
    order = await _placed(db)
    service = OrderService(db)
    await service.confirm_payment(order.id)
    assert await service.expire_unpaid(now=utcnow() + timedelta(days=1)) == 0


# --- Concurrency (real parallel transactions on committed data) ------------------------


@pytest.fixture
async def last_unit(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    """A product with exactly one unit in stock, two customers with it in their cart."""
    async with AsyncSession(engine, expire_on_commit=False) as s:
        shop = await make_shop(s, stock=1)
        second = await make_user(s)
        for user_id in (shop.user.id, second.id):
            await CartService(s).add_item(user_id, shop.variant.id, 1)
        product = await s.get(Product, shop.variant.product_id)
        assert product is not None
        ids = {
            "users": [shop.user.id, second.id],
            "product": product.id,
            "category": product.category_id,
            "variant": shop.variant.id,
        }
    yield shop, ids
    async with engine.begin() as conn:
        await conn.execute(delete(Order).where(Order.user_id.in_(ids["users"])))
        await conn.execute(delete(User).where(User.id.in_(ids["users"])))
        await conn.execute(delete(Product).where(Product.id == ids["product"]))
        await conn.execute(delete(Category).where(Category.id == ids["category"]))
        await conn.execute(delete(DeliveryRate))


async def test_two_customers_last_unit(engine: AsyncEngine, last_unit) -> None:  # type: ignore[no-untyped-def]
    shop, ids = last_unit

    async def buy(user_id: uuid.UUID) -> str:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            try:
                await OrderService(s).place_order(checkout(shop, user_id=user_id))
                return "ok"
            except InsufficientStockError:
                return "sold_out"

    results = await asyncio.gather(*(buy(u) for u in ids["users"]))
    assert sorted(results) == ["ok", "sold_out"]
    async with AsyncSession(engine) as s:
        assert await stock(s, ids["variant"]) == (1, 1)
        assert await s.scalar(select(func.count()).where(Order.user_id.in_(ids["users"]))) == 1


async def test_concurrent_duplicate_submission(engine: AsyncEngine, last_unit) -> None:  # type: ignore[no-untyped-def]
    shop, ids = last_unit
    req = checkout(shop, user_id=ids["users"][0], idempotency_key="same-key-123")

    async def submit() -> uuid.UUID:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            return (await OrderService(s).place_order(req)).id

    first, second = await asyncio.gather(submit(), submit())
    assert first == second
    async with AsyncSession(engine) as s:
        assert await s.scalar(select(func.count()).where(Order.user_id == ids["users"][0])) == 1
        assert await stock(s, ids["variant"]) == (1, 1)
