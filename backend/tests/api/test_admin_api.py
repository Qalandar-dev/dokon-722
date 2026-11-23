"""Admin panel API: catalog, uploads, inventory, delivery, promo, orders, staff, settings,
dashboard and reports."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Order
from app.services.cart import CartService
from app.services.orders import OrderService
from tests.api.conftest import AdminFactory
from tests.factories import BEKTEMIR_DISTRICT_ID, make_category, make_shop
from tests.services.test_orders import checkout

A = "/api/v1/admin"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def _create_product(
    api: httpx.AsyncClient, headers: dict[str, str], category_id: str, **extra: Any
) -> dict[str, Any]:
    body = {
        "name": "Erkaklar ko‘ylagi «Klassik»",
        "category_id": category_id,
        "variants": [
            {
                "sku": f"kl-m-{uuid.uuid4().hex[:6]}",
                "name": "M",
                "attributes": {"o‘lcham": "M"},
                "price": "180000",
                "initial_stock": 7,
            },
            {
                "sku": f"kl-l-{uuid.uuid4().hex[:6]}",
                "name": "L",
                "attributes": {"o‘lcham": "L"},
                "price": "180000",
                "discount_price": "150000",
                "is_default": True,
            },
        ],
        **extra,
    }
    r = await api.post(f"{A}/products", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def test_product_lifecycle(
    api: httpx.AsyncClient, make_admin: AdminFactory, db: AsyncSession
) -> None:
    h = await make_admin("manager")
    category = await make_category(db)
    await db.commit()
    product = await _create_product(api, h, str(category.id))

    assert product["slug"].startswith("erkaklar-koylagi-klassik")
    m, l_ = product["variants"]
    assert m["sku"].startswith("KL-M-")  # SKUs normalised to upper case
    assert (m["on_hand"], m["available"]) == (7, 7)
    assert l_["is_default"] is True
    assert m["is_default"] is False

    dup = await api.post(
        f"{A}/products/{product['id']}/variants",
        json={"sku": m["sku"].lower(), "price": "1"},
        headers=h,
    )
    assert dup.status_code == 409

    upd = await api.patch(f"{A}/variants/{m['id']}", json={"discount_price": "200000"}, headers=h)
    assert upd.status_code == 422  # discount must be below price
    upd = await api.patch(f"{A}/variants/{m['id']}", json={"price": "175000"}, headers=h)
    assert upd.json()["price"] == "175000.00"

    renamed = await api.patch(
        f"{A}/products/{product['id']}", json={"name": "Yangi nom", "is_featured": True}, headers=h
    )
    assert renamed.json()["name"] == "Yangi nom"
    assert renamed.json()["slug"] == product["slug"]  # URLs stay stable

    assert (await api.delete(f"{A}/products/{product['id']}", headers=h)).status_code == 204
    assert (await api.get(f"{A}/products/{product['id']}", headers=h)).status_code == 404
    assert (await api.get(f"/api/v1/products/{product['id']}")).status_code == 404

    actions = set(await db.scalars(select(AuditLog.action)))
    assert {"product.create", "variant.update", "product.update", "product.delete"} <= actions


async def test_image_upload_validation(
    api: httpx.AsyncClient, make_admin: AdminFactory, db: AsyncSession, settings: Any
) -> None:
    h = await make_admin("manager")
    category = await make_category(db)
    await db.commit()
    product = await _create_product(api, h, str(category.id))
    url = f"{A}/products/{product['id']}/images"

    ok = await api.post(url, files={"file": ("rasm.png", PNG, "image/png")}, headers=h)
    assert ok.status_code == 201, ok.text
    assert ok.json()["is_main"] is True
    assert ok.json()["url"].startswith("/media/products/")
    assert ok.json()["url"].endswith(".png")

    # Content decides, not the name or declared type.
    fake = await api.post(
        url, files={"file": ("rasm.png", b"<?php system($_GET['c']); ?>", "image/png")}, headers=h
    )
    assert fake.status_code == 422
    assert fake.json()["error"]["code"] == "unsupported_file_type"

    big = PNG + b"\x00" * settings.max_upload_size_bytes
    too_big = await api.post(url, files={"file": ("big.png", big, "image/png")}, headers=h)
    assert too_big.json()["error"]["code"] == "file_too_large"

    second = await api.post(url, files={"file": ("2.png", PNG, "image/png")}, headers=h)
    await api.patch(f"{A}/product-images/{second.json()['id']}", json={"is_main": True}, headers=h)
    images = (await api.get(f"{A}/products/{product['id']}", headers=h)).json()["images"]
    assert [i["id"] for i in images if i["is_main"]] == [second.json()["id"]]
    assert (
        await api.delete(f"{A}/product-images/{second.json()['id']}", headers=h)
    ).status_code == 204
    images = (await api.get(f"{A}/products/{product['id']}", headers=h)).json()["images"]
    assert images[0]["is_main"] is True  # the remaining image became main


async def test_categories(
    api: httpx.AsyncClient, make_admin: AdminFactory, db: AsyncSession
) -> None:
    h = await make_admin("manager")
    root = (await api.post(f"{A}/categories", json={"name": "Elektronika"}, headers=h)).json()
    child = (
        await api.post(
            f"{A}/categories", json={"name": "Telefonlar", "parent_id": root["id"]}, headers=h
        )
    ).json()
    cycle = await api.patch(
        f"{A}/categories/{root['id']}", json={"parent_id": child["id"]}, headers=h
    )
    assert cycle.json()["error"]["code"] == "category_cycle"

    await _create_product(api, h, child["id"])
    blocked = await api.delete(f"{A}/categories/{child['id']}", headers=h)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "category_not_empty"
    assert (await api.delete(f"{A}/categories/{root['id']}", headers=h)).json()["error"][
        "code"
    ] == "category_has_children"

    listed = {c["id"]: c for c in (await api.get(f"{A}/categories", headers=h)).json()}
    assert listed[child["id"]]["products_count"] == 1

    empty = (await api.post(f"{A}/categories", json={"name": "Bo‘sh"}, headers=h)).json()
    assert (await api.delete(f"{A}/categories/{empty['id']}", headers=h)).status_code == 204


async def test_inventory_adjust_and_history(
    api: httpx.AsyncClient, make_admin: AdminFactory, db: AsyncSession
) -> None:
    h = await make_admin("manager")
    category = await make_category(db)
    await db.commit()
    variant_id = (await _create_product(api, h, str(category.id)))["variants"][0]["id"]

    r = await api.post(
        f"{A}/inventory/{variant_id}/adjust", json={"delta": -10, "reason": "Xato"}, headers=h
    )
    assert r.status_code == 422  # cannot go below zero
    r = await api.post(
        f"{A}/inventory/{variant_id}/adjust",
        json={"delta": 5, "reason": "Yangi partiya"},
        headers=h,
    )
    assert r.json() == {"variant_id": variant_id, "on_hand": 12, "reserved": 0, "available": 12}
    history = (await api.get(f"{A}/inventory/{variant_id}/movements", headers=h)).json()
    assert [m["reason"] for m in history["items"]] == ["Yangi partiya", "Boshlang‘ich qoldiq"]

    low = (await api.get(f"{A}/inventory", params={"low_only": True}, headers=h)).json()
    assert all(row["is_low"] for row in low["items"])


async def test_delivery_configuration_drives_quotes(
    api: httpx.AsyncClient, make_admin: AdminFactory
) -> None:
    h = await make_admin("manager")
    method = (
        await api.post(
            f"{A}/delivery-methods",
            json={"code": "express", "kind": "courier", "name": "Tezkor kuryer"},
            headers=h,
        )
    ).json()
    rate = await api.post(
        f"{A}/delivery-rates",
        json={
            "method_id": method["id"],
            "region_id": 1,
            "price": "35000",
            "free_threshold": "1000000",
            "eta_min_days": 0,
            "eta_max_days": 1,
        },
        headers=h,
    )
    assert rate.status_code == 201, rate.text
    dup = await api.post(
        f"{A}/delivery-rates",
        json={"method_id": method["id"], "region_id": 1, "price": "1"},
        headers=h,
    )
    assert dup.status_code == 409
    mismatch = await api.post(
        f"{A}/delivery-rates",
        json={
            "method_id": method["id"],
            "region_id": 2,
            "district_id": BEKTEMIR_DISTRICT_ID,
            "price": "1",
        },
        headers=h,
    )
    assert mismatch.json()["error"]["code"] == "district_mismatch"

    quotes = (
        await api.get(
            "/api/v1/delivery/quotes",
            params={"district_id": BEKTEMIR_DISTRICT_ID, "amount": 500000},
        )
    ).json()
    express = next(q for q in quotes if q["method_code"] == "express")
    assert express["price"] == "35000.00"

    await api.patch(f"{A}/delivery-rates/{rate.json()['id']}", json={"price": "30000"}, headers=h)
    await api.patch(f"{A}/regions/1", json={"is_active": False}, headers=h)
    r = await api.get(
        "/api/v1/delivery/quotes", params={"district_id": BEKTEMIR_DISTRICT_ID, "amount": 1}
    )
    assert r.json()["error"]["code"] == "delivery_unavailable"
    assert len((await api.get("/api/v1/regions")).json()) == 13


async def test_promo_codes(api: httpx.AsyncClient, make_admin: AdminFactory) -> None:
    h = await make_admin("manager")
    r = await api.post(
        f"{A}/promo-codes",
        json={
            "code": "yangi-yil",
            "discount_type": "percent",
            "value": "15",
            "max_discount": "50000",
        },
        headers=h,
    )
    assert r.status_code == 201
    promo = r.json()
    assert promo["code"] == "YANGI-YIL"
    bad = await api.post(
        f"{A}/promo-codes",
        json={"code": "X1", "discount_type": "percent", "value": "120"},
        headers=h,
    )
    assert bad.status_code == 422
    dup = await api.post(
        f"{A}/promo-codes",
        json={"code": "Yangi-Yil", "discount_type": "fixed", "value": "1"},
        headers=h,
    )
    assert dup.status_code == 409
    r = await api.delete(f"{A}/promo-codes/{promo['id']}", headers=h)
    assert r.json() == {"deleted": True, "deactivated": False}


async def test_admin_order_workflow(
    api: httpx.AsyncClient, make_admin: AdminFactory, db: AsyncSession
) -> None:
    h = await make_admin("operator")
    shop = await make_shop(db, price="100000", stock=4)
    await CartService(db).add_item(shop.user.id, shop.variant.id, 1)
    service = OrderService(db)
    order = await service.place_order(checkout(shop))
    url = f"{A}/orders/{order.id}"

    found = (await api.get(f"{A}/orders", params={"q": order.number}, headers=h)).json()
    assert [o["id"] for o in found["items"]] == [str(order.id)]
    by_phone = (await api.get(f"{A}/orders", params={"q": "1234567"}, headers=h)).json()
    assert str(order.id) in [o["id"] for o in by_phone["items"]]

    early = await api.post(f"{url}/confirm", headers=h)
    assert early.json()["error"]["code"] == "payment_required"
    await service.confirm_payment(order.id)  # Phase 9: done by the verified payment callback

    assert (await api.post(f"{url}/confirm", headers=h)).json()["status"] == "confirmed"
    shipped = await api.post(
        f"{url}/delivery-status", json={"delivery_status": "shipped"}, headers=h
    )
    assert shipped.json()["status"] == "shipped"
    wrong = await api.post(f"{url}/status", json={"status": "pending"}, headers=h)
    assert wrong.json()["error"]["code"] == "invalid_status_transition"
    note = await api.patch(f"{url}/note", json={"internal_note": "Mijoz kechqurun uyda"}, headers=h)
    assert note.json()["internal_note"] == "Mijoz kechqurun uyda"
    assert [x["to_value"] for x in note.json()["history"]][-1] == "shipped"

    # Operators cannot refund.
    assert (await api.post(f"{url}/refund", json={"reason": "x"}, headers=h)).status_code == 403


async def test_customers_admin(
    api: httpx.AsyncClient, make_admin: AdminFactory, db: AsyncSession
) -> None:
    h = await make_admin("manager")
    shop = await make_shop(db)
    listing = (await api.get(f"{A}/customers", params={"sort": "orders"}, headers=h)).json()
    assert str(shop.user.id) in [c["id"] for c in listing["items"]]
    r = await api.patch(f"{A}/customers/{shop.user.id}", json={"is_blocked": True}, headers=h)
    assert r.json()["is_blocked"] is True


async def test_staff_management_guards(api: httpx.AsyncClient, make_admin: AdminFactory) -> None:
    h = await make_admin("super_admin")
    created = await api.post(
        f"{A}/staff",
        json={
            "email": "Operator@Store.uz",
            "full_name": "Operator",
            "password": "uzun-parol-12345",
            "role": "operator",
        },
        headers=h,
    )
    assert created.status_code == 201
    assert created.json()["email"] == "operator@store.uz"
    weak = await api.post(
        f"{A}/staff",
        json={"email": "w@store.uz", "full_name": "W", "password": "123", "role": "operator"},
        headers=h,
    )
    assert weak.status_code == 422

    me = (await api.get("/api/v1/admin/auth/me", headers=h)).json()
    self_off = await api.patch(f"{A}/staff/{me['id']}", json={"is_active": False}, headers=h)
    assert self_off.json()["error"]["code"] == "self_deactivate"

    promoted = await api.patch(
        f"{A}/staff/{created.json()['id']}", json={"role": "manager"}, headers=h
    )
    assert promoted.json()["role"] == "manager"
    logs = (
        await api.get(f"{A}/audit-logs", params={"entity_type": "admin_user"}, headers=h)
    ).json()
    assert {log["action"] for log in logs["items"]} >= {"staff.create", "staff.update"}


async def test_settings_validation(api: httpx.AsyncClient, make_admin: AdminFactory) -> None:
    h = await make_admin("super_admin")
    ok = await api.patch(
        f"{A}/settings",
        json={
            "store.name": "Mening do‘konim",
            "delivery.free_threshold": 400000,
            "store.support_telegram": "@dokon_yordam",
        },
        headers=h,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["store.support_telegram"] == "dokon_yordam"
    assert (await api.get("/api/v1/store")).json()["name"] == "Mening do‘konim"

    bad = await api.patch(
        f"{A}/settings",
        json={"delivery.free_threshold": -5, "payments.click_enabled": "yes"},
        headers=h,
    )
    assert bad.status_code == 422
    assert set(bad.json()["error"]["details"]) == {
        "delivery.free_threshold",
        "payments.click_enabled",
    }
    unknown = await api.patch(f"{A}/settings", json={"debug": True}, headers=h)
    assert unknown.json()["error"]["code"] == "unknown_setting"


async def test_dashboard_and_reports_use_real_data(
    api: httpx.AsyncClient, make_admin: AdminFactory, db: AsyncSession
) -> None:
    h = await make_admin("manager")
    before = (await api.get(f"{A}/dashboard", headers=h)).json()

    shop = await make_shop(db, price="250000", stock=5, delivery_price="25000")
    await CartService(db).add_item(shop.user.id, shop.variant.id, 2)
    service = OrderService(db)
    order = await service.place_order(checkout(shop))
    await service.confirm_payment(order.id)

    after = (await api.get(f"{A}/dashboard", headers=h)).json()
    gained = float(after["revenue_today"]["revenue"]) - float(before["revenue_today"]["revenue"])
    assert gained == 525000.0  # 2 × 250 000 + 25 000 delivery
    assert after["orders_total"] == before["orders_total"] + 1
    assert len(after["sales_chart"]) == 30
    assert any(p["product_id"] == str(shop.variant.product_id) for p in after["best_sellers"])

    csv = await api.get(f"{A}/reports/products", params={"format": "csv"}, headers=h)
    assert csv.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv.headers["content-disposition"]
    assert csv.text.startswith("﻿product_id,product_name,units,revenue")
    for report in ("sales", "categories", "customers", "payment-methods", "order-statuses"):
        r = await api.get(f"{A}/reports/{report}", headers=h)
        assert r.status_code == 200, report
    weekly = (await api.get(f"{A}/reports/sales", params={"group_by": "week"}, headers=h)).json()
    assert weekly["rows"]
    assert await db.scalar(select(func.count()).select_from(Order)) >= 1
