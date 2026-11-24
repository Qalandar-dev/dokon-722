"""Payme (https://developer.help.paycom.uz/) — NOT IMPLEMENTED YET.

Payme's Merchant API methods, authentication, transaction states, error codes and the
checkout URL format must come from Payme's official documentation, which was not
reachable from the development environment. Nothing here is guessed: selecting Payme in
sandbox/live mode fails clearly until this adapter is written from the docs.

To finish: implement ``checkout_link`` and the Merchant API endpoint handler, verifying
the request with PAYME_SECRET_KEY, and call ``PaymentService.record_success`` /
``record_failure``.
"""

from __future__ import annotations

from app.integrations.payments.base import CheckoutLink, ProviderNotConfiguredError
from app.models import Order, Payment
from app.models.enums import PaymentProvider


class PaymePaymentProvider:
    provider = PaymentProvider.PAYME
    is_simulated = False

    def checkout_link(self, payment: Payment, order: Order) -> CheckoutLink:
        raise ProviderNotConfiguredError()
