# Payments (Phase 9)

## Status

| Part | State |
|---|---|
| Provider-independent architecture (`PaymentService`, adapter interface) | ✅ done, tested |
| Simulated provider (`PAYMENT_MODE=mock`) with a checkout page | ✅ done, tested |
| Bot "To‘lash" button, admin view of payment attempts | ✅ done |
| **Click adapter** | ⛔ not implemented — needs the official docs + merchant credentials |
| **Payme adapter** | ⛔ not implemented — needs the official docs + merchant credentials |
| Refund through the provider | ⛔ depends on the adapters; staff can record a refund manually |

The official documentation sites (`docs.click.uz`, `developer.help.paycom.uz`) were not
reachable from the development environment. As required, **no endpoint, callback format,
signature or error code was written from memory.** In `sandbox`/`live` mode, Click and
Payme answer clearly that they are not connected yet (HTTP 503,
`payment_provider_not_configured`), the bot tells the customer, and no payment is created.

## How it works

```
Bot "To‘lash" ──► POST /api/v1/payments {order_id}
                    PaymentService.start: owner? unpaid online order still holding stock?
                    reuse the open payment or create one; adapter builds the checkout URL
Customer pays on the provider's page
Provider ──► callback endpoint ──► adapter parses + verifies signature
                    PaymentService.record_success(payment, provider, external_id, amount)
                      row lock on the payment
                      same (provider, external_id) seen before → return stored result
                      amount == payment.amount == order.total, else reject
                      payment paid + PaymentTransaction (payload stored redacted)
                      OrderService.confirm_payment → order paid, reservation → sale
```

Guarantees (all tested):
- an order is marked paid **only** by `record_success`, never by a redirect or the bot;
- a repeated callback with the same transaction id changes nothing and still answers OK;
- wrong amount or wrong provider is rejected and the order stays unpaid;
- an order can be paid at most once (also enforced by a unique index);
- only the order's owner can start a payment; cash orders and cancelled/expired orders cannot be paid;
- a cancelled payment can be retried while the reservation lasts;
- no card data is ever received or stored.

## Mock mode (`PAYMENT_MODE=mock`, the default)

`POST /payments` returns a link to `/api/v1/payments/mock/{id}/checkout?token=…`: a small
page marked **"SINOV REJIMI — haqiqiy to‘lov emas"** with "To‘lash (sinov)" and
"Bekor qilish". The token is an HMAC of the payment id, so only the holder of the link can
complete it. Completing goes through the same `record_success` path as a real provider.
Such payments are stored with `provider=mock`, `is_simulated=true`, and shown with a
"SINOV" badge in the admin panel and "(SINOV)" on the bot button. The mock routes do not
exist in `sandbox`/`live` mode.

## What is needed to connect Click and Payme

1. **Documentation access** — allow `docs.click.uz` and `developer.help.paycom.uz` in the
   development environment's network settings, or provide the pages (Click: SHOP API
   Prepare/Complete, payment button/link; Payme: Merchant API methods, error codes,
   checkout initialisation, test environment).
2. **Sandbox credentials** — Click: `service_id`, `merchant_id`, `merchant_user_id`,
   `secret_key`; Payme: merchant id and test key.
3. **A public HTTPS address** for the callbacks, registered in each merchant cabinet:
   `https://<domain>/api/v1/payments/webhook/click` and `…/webhook/payme`.

With these, each adapter is one module (`backend/app/integrations/payments/click.py`,
`payme.py`): build the checkout link, parse and verify the callback, answer in the
provider's format, and call `record_success` / `record_failure`. The service, database,
bot and admin panel need no changes.
