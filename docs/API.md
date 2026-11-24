# HTTP API (Phase 5)

Base path `/api/v1`. Interactive docs: `/api/v1/docs` (OpenAPI JSON at
`/api/v1/openapi.json`); both are disabled when `ENVIRONMENT=production`.

## Conventions

- **Errors** always have one shape; `message` is Uzbek and safe to show to users:
  ```json
  {"error": {"code": "insufficient_stock", "message": "«Ko‘ylak» dan faqat 2 dona qoldi.",
             "details": {"available": 2}, "request_id": "…"}}
  ```
  Status codes: 401 not authenticated, 403 no permission, 404 not found, 409 conflict
  (duplicate SKU, category not empty), 422 validation or business rule, 429 rate limit.
- **Money** is a string with two decimals (`"1250000.00"`, UZS). Never parse it as a float.
- **Lists** return `{items, total, page, page_size, pages}`; query `page`, `page_size`.
- **Request bodies** reject unknown fields and trim strings.
- **Every response** carries `X-Request-ID` (also in logs and audit entries).

## Who can call what

| Area | Authentication |
|---|---|
| Public catalog, regions, delivery quotes, store info | none |
| Customer endpoints (used by the Telegram bot) | `X-Bot-Secret: <BOT_API_SECRET>` + `X-Telegram-User-Id: <id>` |
| Admin | `Authorization: Bearer <access token>` + a permission per endpoint |
| Payment callbacks (Phase 9) | provider-specific signature |

The bot secret is only for the internal Docker network; Nginx never needs to expose
customer endpoints to browsers.

### Admin sessions

1. `POST /admin/auth/login` `{email, password}` → `{access_token, expires_at, admin}` and an
   `os_refresh` cookie (`HttpOnly`, `SameSite=Strict`, `Path=/api/v1/admin/auth`, `Secure` in production).
2. Send `Authorization: Bearer <access_token>` (valid `ACCESS_TOKEN_TTL_MINUTES`, default 15).
3. When it expires: `POST /admin/auth/refresh` (cookie sent automatically) → new access token **and a new
   cookie**. Each refresh token works once; replaying an old one ends every session of that login.
4. `POST /admin/auth/logout` ends the session.

Login is limited to `RATE_LIMIT_LOGIN_PER_MINUTE` attempts per minute per IP and per email
(Redis), on top of the Nginx limit. Unknown email and wrong password give the same answer.
Deactivating an admin, changing their role or password ends their sessions; access is
re-checked on every request.

## Endpoints

### Public
| | |
|---|---|
| `GET /products` | `category_id` (includes sub-categories), `q` (name or SKU), `min_price`, `max_price`, `in_stock`, `discounted`, `featured`, `sort` = `newest`·`price_asc`·`price_desc`·`popular` |
| `GET /products/{id}` | details, images, active variants with available stock |
| `GET /categories` | active category tree |
| `GET /categories/{id}/products` | |
| `GET /regions`, `GET /regions/{id}/districts` | active only |
| `GET /delivery/quotes?district_id=&amount=` | available methods with price and ETA |
| `GET /store` | store name, phone, support Telegram, currency label |

### Customer (bot)
`POST /customers/register` (bot secret only) · `POST /customers/phone` · `GET /profile` ·
`GET|POST /addresses` · `PATCH|DELETE /addresses/{id}` ·
`GET|DELETE /cart` · `POST /cart/items` · `PATCH|DELETE /cart/items/{id}` · `POST|DELETE /cart/promo` ·
`POST /checkout/preview` · `POST /orders` (**`Idempotency-Key` header required**) · `GET /orders` ·
`GET /orders/{id}` · `POST /orders/{id}/cancel`

### Admin (permission in brackets)
- Auth: `POST /admin/auth/login|refresh|logout`, `GET /admin/auth/me`
- Dashboard: `GET /admin/dashboard` [dashboard.view]
- Products [products.view / products.manage]: `GET|POST /admin/products`, `GET|PATCH|DELETE /admin/products/{id}`,
  `POST /admin/products/{id}/variants`, `PATCH /admin/variants/{id}`,
  `POST /admin/products/{id}/images` (multipart `file`), `PATCH|DELETE /admin/product-images/{id}`
- Categories [categories.manage]: `GET|POST /admin/categories`, `PATCH|DELETE /admin/categories/{id}`, `POST /admin/categories/{id}/image`
- Inventory [inventory.view / inventory.manage]: `GET /admin/inventory`, `GET /admin/inventory/low-stock`,
  `POST /admin/inventory/{variant_id}/adjust`, `GET /admin/inventory/{variant_id}/movements`
- Orders [orders.view / orders.manage / orders.refund]: `GET /admin/orders`, `GET /admin/orders/{id}`,
  `POST …/confirm`, `POST …/status`, `POST …/delivery-status`, `POST …/cancel`, `POST …/refund`, `PATCH …/note`
- Customers [customers.view / customers.manage]: `GET /admin/customers`, `GET|PATCH /admin/customers/{id}`
- Promo codes [promo.manage]: `GET|POST /admin/promo-codes`, `GET|PATCH|DELETE /admin/promo-codes/{id}`
- Delivery [delivery.manage]: `GET /admin/regions`, `PATCH /admin/regions/{id}`, `GET|POST /admin/regions/{id}/districts`,
  `PATCH /admin/districts/{id}`, `GET|POST /admin/delivery-methods`, `PATCH /admin/delivery-methods/{id}`,
  `GET|POST /admin/delivery-rates`, `PATCH|DELETE /admin/delivery-rates/{id}`
- Staff [staff.manage]: `GET /admin/roles`, `GET|POST /admin/staff`, `PATCH /admin/staff/{id}`;
  audit log [audit.view]: `GET /admin/audit-logs`
- Settings [settings.manage]: `GET|PATCH /admin/settings`
- Reports [reports.view], `?date_from=&date_to=&format=json|csv`: `/admin/reports/sales` (`group_by=day|week|month`),
  `/categories`, `/products`, `/customers`, `/payment-methods`, `/order-statuses`

## Uploads

Images only (JPG, PNG, WEBP), detected from file content, not from the name or
`Content-Type`; at most `MAX_UPLOAD_SIZE_MB`; up to 10 per product. Files are stored
under a random name by the storage backend (local volume now; S3-compatible later) and
served from `/media/…` by Nginx.

## Payments

`POST /payments` `{order_id}` (bot) → `{payment, checkout_url}`; `GET /payments/{id}`.
`POST /payments/webhook/click|payme` answer 503 until the adapters exist. See `docs/PAYMENTS.md`.
