"""Payments: provider-independent rules, the simulated provider, and the not-yet-connected
Click/Payme adapters."""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PaymentMode, Settings
from app.core.exceptions import BusinessRuleError
from app.database.session import get_session
from app.main import create_app
from app.models import Inventory, Payment, PaymentTransaction
from app.models.enums import PaymentMethod, PaymentProvider, PaymentStatus
from app.services.cart import CartService
from app.services.orders import OrderService
from app.services.payments import PaymentService
from tests.conftest import AdminFactory
from tests.factories import make_shop, make_user, set_setting
from tests.services.test_orders import checkout

Headers = Callable[[int], dict[str, str]]


@dataclass(frozen=True)
class Placed:
    """Plain values: ORM objects expire whenever a request rolls back the shared session."""

    order_id: uuid.UUID
    telegram_id: int
    variant_id: uuid.UUID
    total: Decimal
    expires_at: datetime


async def _online_order(db: AsyncSession, *, method: PaymentMethod = PaymentMethod.CLICK) -> Placed:
    shop = await make_shop(db, price="150000", stock=5)
    await CartService(db).add_item(shop.user.id, shop.variant.id, 2)
    order = await OrderService(db).place_order(checkout(shop, payment_method=method))
    return Placed(
        order_id=order.id,
        telegram_id=shop.user.telegram_id,
        variant_id=shop.variant.id,
        total=order.total,
        expires_at=order.reservation_expires_at or datetime.now(UTC),
    )


def _token(url: str) -> str:
    match = re.search(r"token=([0-9a-f]{64})", url)
    assert match, url
    return match.group(1)


async def _start(api: httpx.AsyncClient, bot_headers: Headers, placed: Placed) -> httpx.Response:
    return await api.post(
        "/api/v1/payments",
        json={"order_id": str(placed.order_id)},
        headers=bot_headers(placed.telegram_id),
    )


async def test_simulated_payment_marks_order_paid_once(
    api: httpx.AsyncClient, bot_headers: Headers, db: AsyncSession
) -> None:
    placed = await _online_order(db)
    r = await _start(api, bot_headers, placed)
    assert r.status_code == 200, r.text
    started = r.json()
    assert started["payment"]["provider"] == "mock"
    assert started["payment"]["is_simulated"] is True
    assert started["payment"]["amount"] == "325000.00"  # 2 × 150 000 + 25 000
    url = started["checkout_url"]
    assert "/api/v1/payments/mock/" in url

    # Starting again reuses the open payment.
    again = (await _start(api, bot_headers, placed)).json()
    assert again["payment"]["id"] == started["payment"]["id"]

    path = url.split("http://localhost:8000", 1)[-1].split("?")[0]
    page = await api.get(path, params={"token": _token(url)})
    assert page.status_code == 200
    assert "SINOV REJIMI" in page.text
    assert "325 000 so‘m" in page.text

    complete = path.replace("/checkout", "/complete")
    done = await api.post(complete, data={"token": _token(url), "result": "paid"})
    assert "qabul qilindi" in done.text
    duplicate = await api.post(complete, data={"token": _token(url), "result": "paid"})
    assert duplicate.status_code == 200  # a repeated callback is harmless

    paid = await OrderService(db).get(placed.order_id)
    assert paid.payment_status is PaymentStatus.PAID
    inv = await db.get(Inventory, placed.variant_id, populate_existing=True)
    assert inv is not None
    assert (inv.on_hand, inv.reserved) == (3, 0)  # sold once, not twice
    assert await db.scalar(select(func.count()).select_from(PaymentTransaction)) == 1

    status = await api.get(
        f"/api/v1/payments/{started['payment']['id']}", headers=bot_headers(placed.telegram_id)
    )
    assert status.json()["status"] == "paid"
    assert (await _start(api, bot_headers, placed)).json()["error"]["code"] == "already_paid"


async def test_checkout_link_requires_its_token(
    api: httpx.AsyncClient, bot_headers: Headers, db: AsyncSession
) -> None:
    placed = await _online_order(db)
    url = (await _start(api, bot_headers, placed)).json()["checkout_url"]
    path = url.split("http://localhost:8000", 1)[-1].split("?")[0]
    assert (await api.get(path, params={"token": "0" * 64})).status_code == 403
    forged = await api.post(
        path.replace("/checkout", "/complete"), data={"token": "0" * 64, "result": "paid"}
    )
    assert forged.status_code == 403
    assert (await OrderService(db).get(placed.order_id)).payment_status is PaymentStatus.PENDING


async def test_cancelled_payment_can_be_retried(
    api: httpx.AsyncClient, bot_headers: Headers, db: AsyncSession
) -> None:
    placed = await _online_order(db)
    first = (await _start(api, bot_headers, placed)).json()
    path = first["checkout_url"].split("http://localhost:8000", 1)[-1].split("?")[0]
    await api.post(
        path.replace("/checkout", "/complete"),
        data={"token": _token(first["checkout_url"]), "result": "cancelled"},
    )
    assert (await OrderService(db).get(placed.order_id)).payment_status is PaymentStatus.PENDING
    second = (await _start(api, bot_headers, placed)).json()
    assert second["payment"]["id"] != first["payment"]["id"]
    statuses = {p.status for p in await PaymentService(db, Settings()).for_order(placed.order_id)}
    assert statuses == {PaymentStatus.CANCELLED, PaymentStatus.PENDING}


async def test_payment_ownership_and_eligibility(
    api: httpx.AsyncClient, bot_headers: Headers, db: AsyncSession
) -> None:
    placed = await _online_order(db)
    stranger = await make_user(db)
    stranger_tid = stranger.telegram_id
    await api.post(
        "/api/v1/customers/register",
        json={"telegram_id": stranger_tid, "first_name": "X"},
        headers={"X-Bot-Secret": bot_headers(1)["X-Bot-Secret"]},
    )
    assert (
        await _start(
            api,
            bot_headers,
            Placed(
                placed.order_id, stranger_tid, placed.variant_id, placed.total, placed.expires_at
            ),
        )
    ).status_code == 404

    await set_setting(db, "payments.cash_on_delivery_enabled", True)
    cash = await _online_order(db, method=PaymentMethod.CASH_ON_DELIVERY)
    r = await _start(api, bot_headers, cash)
    assert r.json()["error"]["code"] == "not_online_payment"

    await OrderService(db).expire_unpaid(now=placed.expires_at + timedelta(minutes=1))
    r = await _start(api, bot_headers, placed)
    assert r.json()["error"]["code"] == "order_not_payable"


async def test_amount_and_provider_are_verified(db: AsyncSession, settings: Settings) -> None:
    placed = await _online_order(db)
    order_id, total = placed.order_id, placed.total
    service = PaymentService(db, settings)
    payment = Payment(
        order_id=order_id, provider=PaymentProvider.MOCK, amount=total, is_simulated=True
    )
    db.add(payment)
    await db.commit()
    payment_id = payment.id

    with pytest.raises(BusinessRuleError) as exc:
        await service.record_success(
            payment_id, provider=PaymentProvider.MOCK, external_id="t-1", amount=Decimal("1")
        )
    assert exc.value.code == "amount_mismatch"
    await db.rollback()
    with pytest.raises(BusinessRuleError) as exc:
        await service.record_success(
            payment_id, provider=PaymentProvider.CLICK, external_id="t-1", amount=total
        )
    assert exc.value.code == "provider_mismatch"
    await db.rollback()
    assert (await OrderService(db).get(order_id)).payment_status is PaymentStatus.PENDING


async def test_provider_webhooks_are_not_connected_yet(api: httpx.AsyncClient) -> None:
    for provider in ("click", "payme"):
        r = await api.post(f"/api/v1/payments/webhook/{provider}", json={})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "payment_provider_not_configured"


@pytest.fixture
async def sandbox_api(db: AsyncSession, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    sandbox = settings.model_copy(update={"payment_mode": PaymentMode.SANDBOX})
    app = create_app(sandbox)

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db

    from app.core.config import get_settings

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings] = lambda: sandbox
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        yield client


async def test_sandbox_mode_does_not_pretend(
    sandbox_api: httpx.AsyncClient, bot_headers: Headers, db: AsyncSession
) -> None:
    """Outside mock mode Click/Payme refuse clearly and the simulated checkout is gone."""
    placed = await _online_order(db, method=PaymentMethod.PAYME)
    r = await sandbox_api.post(
        "/api/v1/payments",
        json={"order_id": str(placed.order_id)},
        headers=bot_headers(placed.telegram_id),
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "payment_provider_not_configured"
    assert await db.scalar(select(func.count()).where(Payment.order_id == placed.order_id)) == 0
    gone = await sandbox_api.get(
        f"/api/v1/payments/mock/{uuid.uuid4()}/checkout", params={"token": "x"}
    )
    assert gone.status_code == 404


async def test_admin_sees_simulated_payments(
    api: httpx.AsyncClient, bot_headers: Headers, db: AsyncSession, make_admin: AdminFactory
) -> None:
    placed = await _online_order(db)
    await _start(api, bot_headers, placed)
    h = await make_admin("operator")
    detail = (await api.get(f"/api/v1/admin/orders/{placed.order_id}", headers=h)).json()
    assert [(p["provider"], p["is_simulated"], p["status"]) for p in detail["payments"]] == [
        ("mock", True, "pending")
    ]
