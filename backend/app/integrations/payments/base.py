"""Provider-independent payment interface.

Each provider adapter only knows how to build its checkout link and how to read/answer
its own callbacks. Every business decision (amount check, order ownership, idempotency,
marking the order paid) is taken by ``PaymentService`` so all providers behave the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.exceptions import AppError
from app.models import Order, Payment
from app.models.enums import PaymentProvider


@dataclass(frozen=True, slots=True)
class CheckoutLink:
    url: str


class ProviderNotConfiguredError(AppError):
    status_code = 503
    code = "payment_provider_not_configured"
    message = (
        "Bu to‘lov tizimi hozircha ulanmagan. "
        "Iltimos, boshqa usulni tanlang yoki keyinroq urinib ko‘ring."
    )


class PaymentProviderAdapter(Protocol):
    provider: PaymentProvider
    #: True for the mock provider: no real money ever moves.
    is_simulated: bool

    def checkout_link(self, payment: Payment, order: Order) -> CheckoutLink: ...
