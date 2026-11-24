"""Click (https://docs.click.uz/) — NOT IMPLEMENTED YET.

The checkout link format, the Prepare/Complete callback parameters, the signature
formula and the error codes must be taken from Click's official documentation, which
was not reachable from the development environment. Nothing here is guessed: selecting
Click in sandbox/live mode fails clearly until this adapter is written from the docs.

To finish: implement ``checkout_link`` and a callback handler that parses Click's
request, verifies its signature with CLICK_SECRET_KEY, and calls
``PaymentService.record_success`` / ``record_failure``.
"""

from __future__ import annotations

from app.integrations.payments.base import CheckoutLink, ProviderNotConfiguredError
from app.models import Order, Payment
from app.models.enums import PaymentProvider


class ClickPaymentProvider:
    provider = PaymentProvider.CLICK
    is_simulated = False

    def checkout_link(self, payment: Payment, order: Order) -> CheckoutLink:
        raise ProviderNotConfiguredError()
