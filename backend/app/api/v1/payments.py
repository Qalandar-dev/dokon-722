"""Payment endpoints.

- ``POST /payments`` and ``GET /payments/{id}``: the bot, on behalf of a customer.
- ``/payments/mock/...``: the simulated checkout page, only when ``PAYMENT_MODE=mock``.
- ``/payments/webhook/click`` and ``/payments/webhook/payme``: provider callbacks. They
  answer 503 until the adapters are implemented from the official documentation.
"""

from __future__ import annotations

import html
import uuid
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.deps import CustomerDep, SessionDep, SettingsDep
from app.core.config import PaymentMode
from app.core.exceptions import AppError, NotFoundError, PermissionDeniedError, error_body
from app.integrations.payments.base import ProviderNotConfiguredError
from app.integrations.payments.mock import verify_checkout_token
from app.models import Order, Payment
from app.models.enums import PaymentProvider
from app.schemas.payments import PaymentOut, PaymentStartIn, PaymentStartOut
from app.services.payments import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("", response_model=PaymentStartOut)
async def start_payment(
    body: PaymentStartIn, user: CustomerDep, session: SessionDep, settings: SettingsDep
) -> PaymentStartOut:
    started = await PaymentService(session, settings).start(body.order_id, user_id=user.id)
    return PaymentStartOut(
        payment=PaymentOut.build(started.payment), checkout_url=started.checkout_url
    )


@router.get("/{payment_id}", response_model=PaymentOut)
async def get_payment(
    payment_id: uuid.UUID, user: CustomerDep, session: SessionDep, settings: SettingsDep
) -> PaymentOut:
    return PaymentOut.build(
        await PaymentService(session, settings).get_for_user(payment_id, user.id)
    )


# --- Provider callbacks (not connected yet) -------------------------------------------------


@router.post("/webhook/click", include_in_schema=True)
async def click_webhook(request: Request) -> JSONResponse:
    exc = ProviderNotConfiguredError()
    return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code)


@router.post("/webhook/payme", include_in_schema=True)
async def payme_webhook(request: Request) -> JSONResponse:
    exc = ProviderNotConfiguredError()
    return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code)


# --- Simulated checkout (PAYMENT_MODE=mock only) --------------------------------------------

_PAGE = """<!doctype html>
<html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Sinov to‘lovi</title>
<style>
body{{font-family:system-ui,sans-serif;background:#f5f5f5;margin:0;padding:24px;color:#171717}}
.card{{max-width:420px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;
border:1px solid #e5e5e5}}
.warn{{background:#fff7ed;border:1px solid #fdba74;border-radius:8px;
padding:12px;font-size:14px}}
.sum{{font-size:28px;font-weight:700;margin:16px 0}}
button{{width:100%;padding:12px;border-radius:8px;border:0;font-size:16px;
margin-top:8px;cursor:pointer}}
.pay{{background:#171717;color:#fff}} .cancel{{background:#e5e5e5}}
</style></head><body><div class="card">
<p class="warn"><b>SINOV REJIMI.</b> Bu haqiqiy to‘lov emas — hech qanday pul yechilmaydi.</p>
<p>Buyurtma <b>{number}</b></p><p class="sum">{amount}</p>
{body}
</div></body></html>"""


def _som(amount: object) -> str:
    return f"{int(float(str(amount))):,}".replace(",", " ") + " so‘m"


def _require_mock(settings: SettingsDep) -> None:
    if settings.payment_mode is not PaymentMode.MOCK:
        raise NotFoundError()


async def _mock_payment(
    payment_id: uuid.UUID, token: str, session: SessionDep, settings: SettingsDep
) -> tuple[PaymentService, Payment, Order]:
    _require_mock(settings)
    if not verify_checkout_token(settings, payment_id, token):
        raise PermissionDeniedError("Havola yaroqsiz.", code="invalid_checkout_token")
    service = PaymentService(session, settings)
    payment = await service.get(payment_id)
    order = await session.get(Order, payment.order_id)
    if order is None or payment.provider is not PaymentProvider.MOCK:
        raise NotFoundError()
    return service, payment, order


@router.get("/mock/{payment_id}/checkout", response_class=HTMLResponse, include_in_schema=False)
async def mock_checkout(
    payment_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    token: Annotated[str, Query(max_length=128)],
) -> HTMLResponse:
    _, payment, order = await _mock_payment(payment_id, token, session, settings)
    status = payment.status.value
    if status == "pending":
        form = (
            '<form method="post" action="complete">'
            f'<input type="hidden" name="token" value="{html.escape(token)}">'
            '<button class="pay" name="result" value="paid">To‘lash (sinov)</button>'
            '<button class="cancel" name="result" value="cancelled">Bekor qilish</button></form>'
        )
    else:
        form = f"<p>To‘lov holati: <b>{html.escape(status)}</b>. Telegram botga qayting.</p>"
    return HTMLResponse(
        _PAGE.format(number=html.escape(order.number), amount=_som(payment.amount), body=form),
        headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"},
    )


@router.post("/mock/{payment_id}/complete", response_class=HTMLResponse, include_in_schema=False)
async def mock_complete(
    payment_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    token: Annotated[str, Form(max_length=128)],
    result: Annotated[str, Form(pattern="^(paid|cancelled)$")],
) -> HTMLResponse:
    service, payment, order = await _mock_payment(payment_id, token, session, settings)
    try:
        if result == "paid":
            # Same path a real provider callback takes, with the amount we expect.
            payment = await service.record_success(
                payment_id,
                provider=PaymentProvider.MOCK,
                external_id=f"mock-{payment_id}",
                amount=payment.amount,
            )
            message = "✅ Sinov to‘lovi qabul qilindi. Telegram botga qayting."
        else:
            payment = await service.record_failure(
                payment_id,
                provider=PaymentProvider.MOCK,
                reason="Mijoz bekor qildi",
                cancelled=True,
            )
            message = "To‘lov bekor qilindi. Botdan qayta to‘lashingiz mumkin."
    except AppError as exc:
        message = exc.message
    return HTMLResponse(
        _PAGE.format(
            number=html.escape(order.number),
            amount=_som(payment.amount),
            body=f"<p>{html.escape(message)}</p>",
        ),
        headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"},
    )
