# Business services (Phase 4)

All business rules live in `backend/app/services/`. The API (Phase 5), the bot (via the
API) and the worker call these; nothing else changes orders, stock or prices.
Each public method is one database transaction: all of its effects commit together or
not at all. Errors are `AppError` subclasses with an Uzbek message and a stable `code`.

| Service | Responsibility |
|---|---|
| `CatalogService` | Product list with category (incl. sub-categories), name/SKU search (trigram), price range, in-stock, discounted, featured filters; sort by newest / price / popularity; in-stock items first; category tree; product details. Only active, non-deleted products in active categories are visible. |
| `CartService` | Add / change / remove items with stock checks; live prices (never stored in the cart); promo code apply/remove; summary flags lines that became unavailable instead of failing. |
| `PromoService` | Percent / fixed discounts, max discount, minimum order, validity period, total and per-customer limits. Redemption locks the promo row, so the last use cannot be taken twice. Cancelling an order gives the use back. |
| `DeliveryService` | Quotes per district: district rate overrides region rate; free delivery from the rate's threshold or the store-wide one. No hard-coded prices. |
| `InventoryService` | Reserve / release / sell / return / manual adjust. Every write is a conditional `UPDATE`; every change writes an `inventory_movements` row. Low-stock report. |
| `OrderService` | Checkout preview and order placement, payment confirmation, confirm, status and delivery-status changes, cancellation, refund recording, internal notes, expiry of unpaid orders. |
| `order_status` | Pure transition tables and Uzbek labels for order, payment and delivery statuses. |
| `StoreSettingsService` | Typed access to admin-editable settings. |

## Checkout guarantees (all covered by tests)

- **No overselling:** two customers buying the last unit at the same moment → exactly one order (`test_two_customers_last_unit`).
- **No duplicate orders:** the same `Idempotency-Key` returns the first order, also when both requests arrive at the same time (`test_concurrent_duplicate_submission`).
- **All or nothing:** if any item is short, no order, no reservation, and the cart is kept.
- **What the customer saw is what is stored:** names, SKUs, prices, address, delivery method and fee are copied into the order.

## Stock policy

| Event | Stock | `orders.stock_state` |
|---|---|---|
| Order placed | reserved | `reserved` |
| Online payment confirmed, or cash order confirmed by staff | deducted (sale) | `sold` |
| Cancelled / payment window expired before sale | reservation released | `released` |
| Cancelled after sale (not shipped yet) | returned to stock | `returned` |
| Refund after delivery, goods back on the shelf | returned to stock (staff choice) | `returned` |
| Parcel returned undelivered (delivery status `returned`) | returned to stock; order cancelled; unpaid payment cancelled, paid stays `paid` for a refund | `returned` |

Unpaid Click/Payme orders hold stock for `ORDER_RESERVATION_TTL_MINUTES` (default 30);
`OrderService.expire_unpaid` cancels them (wired to the worker in Phase 10).

## Status rules

See the docstring of `app/services/order_status.py`. Highlights:
- online orders are confirmed only after payment; cash orders can be confirmed immediately;
- customers can cancel while the order is new or confirmed and unpaid; paid orders go through staff;
- shipped orders cannot be cancelled by staff; if the parcel comes back (`delivery_failed → returned`) the order is cancelled automatically and the goods return to stock;
- delivery-status progress (shipped, out for delivery, delivered) moves the order status with it;
- a cash order becomes paid when it is delivered.

## Not in this phase

- `record_refund` changes statuses only. Returning money through Click/Payme is Phase 9.
- `confirm_payment` must be called only after server-side provider verification (Phase 9).
