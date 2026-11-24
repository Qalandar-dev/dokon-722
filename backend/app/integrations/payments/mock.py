"""Simulated payment provider for development and demos (``PAYMENT_MODE=mock``).

The "checkout page" is served by our own API and its buttons go through exactly the same
``PaymentService`` path a real provider callback will use (amount check, idempotent
transaction record, order marked paid). Payments made here are stored with
``provider=mock`` and ``is_simulated=true`` and are labelled "SINOV" everywhere.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid

from app.core.config import Settings
from app.integrations.payments.base import CheckoutLink
from app.models import Order, Payment
from app.models.enums import PaymentProvider


def checkout_token(settings: Settings, payment_id: uuid.UUID) -> str:
    """Unguessable token so only the holder of the checkout link can complete it."""
    key = settings.jwt_secret_key.get_secret_value().encode()
    return hmac.new(key, f"mock-pay:{payment_id}".encode(), hashlib.sha256).hexdigest()


def verify_checkout_token(settings: Settings, payment_id: uuid.UUID, token: str) -> bool:
    return hmac.compare_digest(checkout_token(settings, payment_id), token)


class MockPaymentProvider:
    provider = PaymentProvider.MOCK
    is_simulated = True

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def checkout_link(self, payment: Payment, order: Order) -> CheckoutLink:
        base = self.settings.public_base_url.rstrip("/")
        token = checkout_token(self.settings, payment.id)
        return CheckoutLink(
            url=f"{base}{self.settings.api_v1_prefix}/payments/mock/{payment.id}/checkout?token={token}"
        )
