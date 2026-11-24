"""The whole business story through the HTTP API, as the admin panel and the bot use it."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal

import httpx

from tests.conftest import AdminFactory

A = "/api/v1/admin"
C = "/api/v1"
Headers = Callable[[int], dict[str, str]]


async def _customer(
    api: httpx.AsyncClient, bot_headers: Headers, telegram_id: int
) -> dict[str, str]:
    h = bot_headers(telegram_id)
    r = await api.post(
        f"{C}/customers/register",
        json={"telegram_id": telegram_id, "first_name": "Mijoz"},
        headers={"X-Bot-Secret": h["X-Bot-Secret"]},
    )
    assert r.status_code in (200, 201)
    return h


async def _order(
    api: httpx.AsyncClient, h: dict[str, str], variant_id: str, qty: int, method_id: str
) -> httpx.Response:
    await api.delete(f"{C}/cart", headers=h)
    r = await api.post(
        f"{C}/cart/items", json={"variant_id": variant_id, "quantity": qty}, headers=h
    )
    if r.status_code != 200:
        return r
    return await api.post(
        f"{C}/orders",
        json={
            "recipient_name": "Javohir Toshmatov",
            "recipient_phone": "+998901112233",
            "district_id": 1,
            "address_line": "Navoiy ko‘chasi 10",
            "delivery_method_id": method_id,
            "payment_method": "cash_on_delivery",
        },
        headers={**h, "Idempotency-Key": uuid.uuid4().hex},
    )


async def test_admin_setup_customer_order_fulfilment(
    api: httpx.AsyncClient, bot_headers: Headers, make_admin: AdminFactory
) -> None:
    manager = await make_admin("manager")
    owner = await make_admin("super_admin")
    operator = await make_admin("operator")

    # 1. Store setup in the admin panel
    category = (
        await api.post(f"{A}/categories", json={"name": "Maishiy texnika"}, headers=manager)
    ).json()
    product = (
        await api.post(
            f"{A}/products",
            json={
                "name": "Changyutgich Artel",
                "category_id": category["id"],
                "variants": [
                    {"sku": f"ART-{uuid.uuid4().hex[:6]}", "price": "1200000", "initial_stock": 3}
                ],
            },
            headers=manager,
        )
    ).json()
    variant_id = product["variants"][0]["id"]
    methods = (await api.get(f"{A}/delivery-methods", headers=manager)).json()
    courier = next(m for m in methods if m["code"] == "courier")
    rate = await api.post(
        f"{A}/delivery-rates",
        json={
            "method_id": courier["id"],
            "region_id": 1,
            "price": "30000",
            "free_threshold": "2000000",
        },
        headers=manager,
    )
    assert rate.status_code == 201
    settings = await api.patch(
        f"{A}/settings", json={"payments.cash_on_delivery_enabled": True}, headers=owner
    )
    assert settings.json()["payments.cash_on_delivery_enabled"] is True
    assert "cash_on_delivery" in (await api.get(f"{C}/store")).json()["payment_methods"]

    # 2. A customer orders 2 through the bot API
    first = await _customer(api, bot_headers, 900_000_001)
    created = await _order(api, first, variant_id, 2, courier["id"])
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["total"] == "2400000.00"  # 2 × 1 200 000, delivery free from 2 000 000

    stock = (
        await api.get(
            f"{A}/inventory", params={"q": product["variants"][0]["sku"]}, headers=manager
        )
    ).json()
    assert (stock["items"][0]["on_hand"], stock["items"][0]["reserved"]) == (3, 2)

    # 3. Another customer cannot take the reserved units
    second = await _customer(api, bot_headers, 900_000_002)
    blocked = await _order(api, second, variant_id, 2, courier["id"])
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "insufficient_stock"

    # 4. Operator fulfils the order
    url = f"{A}/orders/{order['id']}"
    assert (await api.post(f"{url}/confirm", headers=operator)).json()["status"] == "confirmed"
    stock = (
        await api.get(
            f"{A}/inventory", params={"q": product["variants"][0]["sku"]}, headers=manager
        )
    ).json()
    assert (stock["items"][0]["on_hand"], stock["items"][0]["reserved"]) == (1, 0)
    for step in ("shipped", "out_for_delivery", "delivered"):
        r = await api.post(
            f"{url}/delivery-status", json={"delivery_status": step}, headers=operator
        )
        assert r.status_code == 200, r.text
    final = r.json()
    assert (final["status"], final["payment_status"]) == ("delivered", "paid")

    # 5. Customer sees it in Uzbek; revenue reaches the dashboard and reports
    seen = (await api.get(f"{C}/orders/{order['id']}", headers=first)).json()
    assert seen["labels"]["status"] == "Yetkazildi"
    assert seen["can_cancel"] is False
    dashboard = (await api.get(f"{A}/dashboard", headers=manager)).json()
    assert Decimal(dashboard["revenue_today"]["revenue"]) >= Decimal("2400000")
    report = (await api.get(f"{A}/reports/payment-methods", headers=manager)).json()
    assert any(row["payment_method"] == "cash_on_delivery" for row in report["rows"])

    # 6. Low stock follows the configured threshold (1 left)
    def low_ids(resp: httpx.Response) -> list[str]:
        return [p["id"] for p in resp.json()["items"]]

    assert product["id"] in low_ids(
        await api.get(f"{A}/products", params={"low_stock": True}, headers=manager)
    )
    await api.patch(f"{A}/settings", json={"inventory.low_stock_threshold": 0}, headers=owner)
    assert product["id"] not in low_ids(
        await api.get(f"{A}/products", params={"low_stock": True}, headers=manager)
    )

    # 7. Every staff action is in the audit log
    actions = {
        a["action"]
        for a in (
            await api.get(f"{A}/audit-logs", params={"page_size": 100}, headers=owner)
        ).json()["items"]
    }
    assert {
        "product.create",
        "delivery_rate.create",
        "settings.update",
        "order.confirm",
        "order.delivery_status",
    } <= actions
