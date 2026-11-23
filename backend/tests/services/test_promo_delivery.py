import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.exceptions import BusinessRuleError, NotFoundError, PromoCodeError
from app.models import DeliveryMethod, DeliveryRate, District, PromoCode
from app.models.enums import DiscountType
from app.services.delivery import DeliveryService
from app.services.promo import PromoService, calculate_discount
from tests.factories import (
    BEKTEMIR_DISTRICT_ID,
    TASHKENT_REGION_ID,
    courier_method,
    make_order,
    make_user,
    set_setting,
)


def promo(**kw: object) -> PromoCode:
    defaults: dict[str, object] = {
        "code": "YOZ",
        "discount_type": DiscountType.PERCENT,
        "value": Decimal("10"),
        "min_order_amount": Decimal("0"),
        "used_count": 0,
        "is_active": True,
        "starts_at": utcnow() - timedelta(days=1),
    }
    return PromoCode(**{**defaults, **kw})


# --- calculate_discount (pure) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("kw", "subtotal", "expected"),
    [
        ({"value": Decimal("10")}, "250000", "25000.00"),
        ({"value": Decimal("15")}, "99999", "15000.00"),  # rounded to whole so'm
        ({"value": Decimal("50"), "max_discount": Decimal("30000")}, "100000", "30000.00"),
        ({"discount_type": DiscountType.FIXED, "value": Decimal("20000")}, "150000", "20000.00"),
        ({"discount_type": DiscountType.FIXED, "value": Decimal("20000")}, "15000", "15000.00"),
    ],
)
def test_calculate_discount(kw: dict[str, object], subtotal: str, expected: str) -> None:
    assert calculate_discount(promo(**kw), Decimal(subtotal)) == Decimal(expected)


# --- PromoService ----------------------------------------------------------------------


async def _save(db: AsyncSession, **kw: object) -> PromoCode:
    p = promo(**kw)
    db.add(p)
    await db.flush()
    return p


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"is_active": False}, "promo_inactive"),
        ({"starts_at": utcnow() + timedelta(days=1)}, "promo_not_started"),
        ({"ends_at": utcnow() - timedelta(minutes=1)}, "promo_expired"),
        ({"min_order_amount": Decimal("500000")}, "promo_min_order"),
        ({"usage_limit": 5, "used_count": 5}, "promo_exhausted"),
    ],
)
async def test_promo_rules(db: AsyncSession, kw: dict[str, object], code: str) -> None:
    if "ends_at" in kw:
        kw["starts_at"] = utcnow() - timedelta(days=2)
    p = await _save(db, **kw)
    user = await make_user(db)
    with pytest.raises(PromoCodeError) as exc:
        await PromoService(db).evaluate(p, user_id=user.id, subtotal=Decimal("100000"))
    assert exc.value.code == code


async def test_promo_lookup_is_case_insensitive(db: AsyncSession) -> None:
    await _save(db, code="BAHOR20")
    assert (await PromoService(db).find("  bahor20 ")).code == "BAHOR20"
    with pytest.raises(PromoCodeError, match="topilmadi"):
        await PromoService(db).find("YOQ")


async def test_per_user_limit_and_release(db: AsyncSession) -> None:
    p = await _save(db, per_user_limit=1, usage_limit=10)
    user = await make_user(db)
    order = await make_order(db, user=user)
    service = PromoService(db)

    await service.redeem(p.id, user_id=user.id, order_id=order.id, subtotal=Decimal("100000"))
    assert p.used_count == 1
    with pytest.raises(PromoCodeError) as exc:
        await service.evaluate(p, user_id=user.id, subtotal=Decimal("100000"))
    assert exc.value.code == "promo_user_limit"

    # Another customer can still use it.
    other = await make_user(db)
    assert await service.evaluate(p, user_id=other.id, subtotal=Decimal("100000")) == Decimal(
        "10000.00"
    )

    # Cancelling the order gives the use back.
    await service.release(order.id)
    await db.refresh(p)
    assert p.used_count == 0
    assert await service.evaluate(p, user_id=user.id, subtotal=Decimal("100000"))


# --- DeliveryService -------------------------------------------------------------------


async def _rate(db: AsyncSession, method: DeliveryMethod, **kw: object) -> DeliveryRate:
    rate = DeliveryRate(method_id=method.id, region_id=TASHKENT_REGION_ID, **kw)
    db.add(rate)
    await db.flush()
    return rate


async def test_no_rates_means_no_delivery(db: AsyncSession) -> None:
    assert await DeliveryService(db).quotes(BEKTEMIR_DISTRICT_ID, Decimal("100000")) == []


async def test_district_rate_overrides_region_rate(db: AsyncSession) -> None:
    courier = await courier_method(db)
    await _rate(db, courier, price=Decimal("30000"))
    await _rate(db, courier, district_id=BEKTEMIR_DISTRICT_ID, price=Decimal("15000"))
    service = DeliveryService(db)

    [bektemir] = await service.quotes(BEKTEMIR_DISTRICT_ID, Decimal("100000"))
    assert bektemir.price == Decimal("15000.00")
    [chilonzor] = await service.quotes(2, Decimal("100000"))
    assert chilonzor.price == Decimal("30000.00")


async def test_free_delivery_thresholds(db: AsyncSession) -> None:
    courier = await courier_method(db)
    await _rate(db, courier, price=Decimal("25000"), free_threshold=Decimal("500000"))
    service = DeliveryService(db)

    below = await service.quote(courier.id, BEKTEMIR_DISTRICT_ID, Decimal("499999"))
    assert (below.price, below.free_applied) == (Decimal("25000.00"), False)
    at = await service.quote(courier.id, BEKTEMIR_DISTRICT_ID, Decimal("500000"))
    assert (at.price, at.free_applied) == (Decimal("0.00"), True)


async def test_store_wide_free_threshold_used_when_rate_has_none(db: AsyncSession) -> None:
    courier = await courier_method(db)
    await _rate(db, courier, price=Decimal("25000"))
    await set_setting(db, "delivery.free_threshold", 300000)
    quote = await DeliveryService(db).quote(courier.id, BEKTEMIR_DISTRICT_ID, Decimal("300000"))
    assert quote.price == Decimal("0.00")


async def test_inactive_district_and_unknown_method(db: AsyncSession) -> None:
    courier = await courier_method(db)
    await _rate(db, courier, price=Decimal("25000"))
    await db.execute(update(District).where(District.id == 2).values(is_active=False))
    service = DeliveryService(db)
    with pytest.raises(BusinessRuleError) as exc:
        await service.quotes(2, Decimal("1"))
    assert exc.value.code == "delivery_unavailable"
    with pytest.raises(NotFoundError):
        await service.quotes(999_999, Decimal("1"))
    with pytest.raises(BusinessRuleError) as exc:
        await service.quote(uuid.uuid4(), BEKTEMIR_DISTRICT_ID, Decimal("1"))
    assert exc.value.code == "delivery_method_unavailable"
