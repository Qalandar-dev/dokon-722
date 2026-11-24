from __future__ import annotations

from app.core.config import PaymentMode, Settings
from app.integrations.payments.base import PaymentProviderAdapter
from app.integrations.payments.click import ClickPaymentProvider
from app.integrations.payments.mock import MockPaymentProvider
from app.integrations.payments.payme import PaymePaymentProvider
from app.models.enums import PaymentMethod


def provider_for(method: PaymentMethod, settings: Settings) -> PaymentProviderAdapter:
    """In mock mode every online method uses the simulated provider."""
    if settings.payment_mode is PaymentMode.MOCK:
        return MockPaymentProvider(settings)
    if method is PaymentMethod.CLICK:
        return ClickPaymentProvider()
    if method is PaymentMethod.PAYME:
        return PaymePaymentProvider()
    raise ValueError(f"{method} is not an online payment method")
