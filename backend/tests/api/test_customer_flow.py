"""The customer journey through the bot-facing API, end to end."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PromoCode
from app.models.enums import DiscountType
from tests.factories import BEKTEMIR_DISTRICT_ID, make_shop

API = "/api/v1"
Headers = Callable[[int], dict[str, str]]


async def register(api: httpx.AsyncClient, headers: Headers, telegram_id: int) -> httpx.Response:
    return await api.post(
        f"{API}/customers/register",
        json={"telegram_id": telegram_id, "first_name": "Sardor", "username": "sardor_uz"},
        headers={"X-Bot-Secret": headers(telegram_id)["X-Bot-Secret"]},
    )


async def test_bot_secret_is_required(api: httpx.AsyncClient, bot_headers: Headers) -> None:
    r = await api.get(f"{API}/cart", headers={"X-Telegram-User-Id": "1"})
    assert r.status_code == 401
    bad = {**bot_headers(1), "X-Bot-Secret": "wrong"}
    assert (await api.get(f"{API}/cart", headers=bad)).status_code == 401
    r = await api.post(f"{API}/customers/register", json={"telegram_id": 1, "first_name": "A"})
    assert r.status_code == 401


async def test_unregistered_customer(api: httpx.AsyncClient, bot_headers: Headers) -> None:
    r = await api.get(f"{API}/profile", headers=bot_headers(999_000_111))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "customer_not_registered"


async def test_register_is_idempotent_and_phone_verification(
    api: httpx.AsyncClient, bot_headers: Headers
) -> None:
    tid = 700_000_001
    first = await register(api, bot_headers, tid)
    assert first.status_code == 201
    assert first.json()["created"] is True
    again = await register(api, bot_headers, tid)
    assert again.status_code == 200
    assert again.json()["profile"]["id"] == first.json()["profile"]["id"]

    # A forwarded contact of someone else is stored but not verified.
    r = await api.post(
        f"{API}/customers/phone",
        json={"phone": "+998 90 111 22 33", "contact_user_id": 12345},
        headers=bot_headers(tid),
    )
    assert r.json()["phone"] == "+998901112233"
    assert r.json()["phone_verified"] is False

    r = await api.post(
        f"{API}/customers/phone",
        json={"phone": "998901112233", "contact_user_id": tid},
        headers=bot_headers(tid),
    )
    assert r.json()["phone_verified"] is True


async def test_full_purchase_journey(
    api: httpx.AsyncClient, bot_headers: Headers, db: AsyncSession
) -> None:
    shop = await make_shop(db, price="150000", stock=5, delivery_price="20000")
    db.add(PromoCode(code="SALOM10", discount_type=DiscountType.PERCENT, value=Decimal(10)))
    await db.commit()
    tid = 700_000_002
    await register(api, bot_headers, tid)
    h = bot_headers(tid)

    # Browse
    product_id = str(shop.variant.product_id)
    listing = await api.get(f"{API}/products", params={"in_stock": True, "sort": "price_asc"})
    assert listing.status_code == 200
    assert product_id in [p["id"] for p in listing.json()["items"]]
    detail = (await api.get(f"{API}/products/{product_id}")).json()
    variant = detail["variants"][0]
    assert variant["available"] == 5
    assert variant["price"] == "150000.00"

    # Cart + promo
    cart = (
        await api.post(
            f"{API}/cart/items", json={"variant_id": variant["id"], "quantity": 2}, headers=h
        )
    ).json()
    assert cart["subtotal"] == "300000.00"
    bad = await api.post(
        f"{API}/cart/items", json={"variant_id": variant["id"], "quantity": 9}, headers=h
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "insufficient_stock"
    cart = (await api.post(f"{API}/cart/promo", json={"code": "salom10"}, headers=h)).json()
    assert cart["discount"] == "30000.00"

    # Delivery options for the chosen district
    quotes = (
        await api.get(
            f"{API}/delivery/quotes", params={"district_id": BEKTEMIR_DISTRICT_ID, "amount": 270000}
        )
    ).json()
    courier = next(q for q in quotes if q["method_code"] == "courier")

    preview = await api.post(
        f"{API}/checkout/preview",
        json={"district_id": BEKTEMIR_DISTRICT_ID, "delivery_method_id": courier["method_id"]},
        headers=h,
    )
    assert preview.json()["total"] == "290000.00"  # 300 000 - 30 000 + 20 000

    order_body = {
        "recipient_name": "Sardor Aliyev",
        "recipient_phone": "+998901112233",
        "district_id": BEKTEMIR_DISTRICT_ID,
        "address_line": "Amir Temur ko‘chasi 15",
        "delivery_method_id": courier["method_id"],
        "payment_method": "payme",
    }
    key = uuid.uuid4().hex
    missing_key = await api.post(f"{API}/orders", json=order_body, headers=h)
    assert missing_key.status_code == 422
    created = await api.post(
        f"{API}/orders", json=order_body, headers={**h, "Idempotency-Key": key}
    )
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["total"] == "290000.00"
    assert order["labels"]["status"] == "Yangi"
    assert order["can_cancel"] is True
    assert "internal_note" not in order

    # Double tap → same order
    repeat = await api.post(f"{API}/orders", json=order_body, headers={**h, "Idempotency-Key": key})
    assert repeat.json()["id"] == order["id"]

    history = (await api.get(f"{API}/orders", headers=h)).json()
    assert [o["id"] for o in history["items"]] == [order["id"]]

    # Another customer cannot see it
    other = 700_000_003
    await register(api, bot_headers, other)
    assert (
        await api.get(f"{API}/orders/{order['id']}", headers=bot_headers(other))
    ).status_code == 404

    cancelled = await api.post(f"{API}/orders/{order['id']}/cancel", json={}, headers=h)
    assert cancelled.json()["status"] == "cancelled"
    detail = (await api.get(f"{API}/products/{product_id}")).json()
    assert detail["variants"][0]["available"] == 5  # stock released


async def test_addresses(api: httpx.AsyncClient, bot_headers: Headers) -> None:
    tid = 700_000_004
    await register(api, bot_headers, tid)
    h = bot_headers(tid)
    body = {
        "district_id": BEKTEMIR_DISTRICT_ID,
        "recipient_name": "Malika",
        "recipient_phone": "93 555 44 33",
        "address_line": "Bunyodkor 1",
    }
    first = (await api.post(f"{API}/addresses", json=body, headers=h)).json()
    assert first["is_default"] is True
    assert first["recipient_phone"] == "+998935554433"
    second = (
        await api.post(f"{API}/addresses", json={**body, "is_default": True}, headers=h)
    ).json()
    listed = (await api.get(f"{API}/addresses", headers=h)).json()
    assert [a["id"] for a in listed if a["is_default"]] == [second["id"]]
    assert (await api.delete(f"{API}/addresses/{second['id']}", headers=h)).status_code == 204
    listed = (await api.get(f"{API}/addresses", headers=h)).json()
    assert listed[0]["is_default"] is True
    bad = await api.post(f"{API}/addresses", json={**body, "extra": 1}, headers=h)
    assert bad.status_code == 422  # unknown fields rejected


async def test_blocked_customer(
    api: httpx.AsyncClient, bot_headers: Headers, db: AsyncSession
) -> None:
    tid = 700_000_005
    r = await register(api, bot_headers, tid)
    from app.models import User

    user = await db.get(User, uuid.UUID(r.json()["profile"]["id"]))
    assert user is not None
    user.is_blocked = True
    await db.commit()
    r = await api.get(f"{API}/cart", headers=bot_headers(tid))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "customer_blocked"


async def test_public_reference_endpoints(api: httpx.AsyncClient) -> None:
    regions = (await api.get(f"{API}/regions")).json()
    assert len(regions) == 14
    districts = (await api.get(f"{API}/regions/{regions[0]['id']}/districts")).json()
    assert districts
    assert (await api.get(f"{API}/regions/9999/districts")).status_code == 404
    store = (await api.get(f"{API}/store")).json()
    assert store["currency_display"] == "so‘m"
    assert isinstance(await api.get(f"{API}/categories"), httpx.Response)
