# Admin panel (Phase 7)

Next.js 16 (App Router) + React 19 + TypeScript (strict) + Tailwind 4, shadcn/ui-style
components on Radix, TanStack Query, React Hook Form + Zod, Recharts. Uzbek (Latin) UI.
Every screen works against the real API; there is no mock data.

## Pages

| Page | What staff can do | Permission |
|---|---|---|
| `/login` | Sign in (rate-limited, generic error on wrong credentials) | — |
| `/` | Revenue today / this week / this month / total, order and customer counters, 30-day revenue chart, best sellers, low stock, system status | `dashboard.view` |
| `/orders`, `/orders/[id]` | Search (number, name, phone), filter by status, payment status and dates; detail with items, totals, delivery address, payment info, history; confirm, move status, change delivery status, cancel (with reason), record refund (restock option), internal note | `orders.view` / `orders.manage` / `orders.refund` |
| `/products`, `/products/new`, `/products/[id]` | Search, filter (category, active, low stock); create with several variants and initial stock; edit details; add/edit/deactivate variants; upload images (JPG/PNG/WEBP ≤ 5 MB), choose main image, delete; soft-delete product | `products.view` / `products.manage` |
| `/categories` | Tree view with product counts; create/edit (parent, order, active), image, delete (refused while products or sub-categories exist) | `categories.manage` |
| `/inventory` | Stock, reserved, available with low-stock colouring; adjust (+/−) with a required reason; movement history per variant | `inventory.view` / `inventory.manage` |
| `/customers`, `/customers/[id]` | Search, sort by spending or orders; profile with totals and order history; block / unblock | `customers.view` / `customers.manage` |
| `/promo-codes` | Percent or fixed, max discount, minimum order, period, total and per-customer limits; delete (used codes are deactivated instead) | `promo.manage` |
| `/delivery` | **Rates** per region or district (price, free-from threshold, ETA, pickup address); **methods**; **regions/districts** (enable/disable, add) | `delivery.manage` |
| `/reports` | Sales (day/week/month), categories, top products, top customers, payment methods, order statuses; CSV export (Excel-friendly) | `reports.view` |
| `/staff` | Create staff, change role, reset password, deactivate (sessions end immediately) | `staff.manage` |
| `/audit-log` | Every important change, filterable by staff member | `audit.view` |
| `/settings` | Store name and contacts, free-delivery threshold, low-stock threshold, enabled payment methods, staff notifications | `settings.manage` |

The menu shows only what the signed-in role may use; the API enforces the same permissions.

## Session handling

The access token is kept in memory only. On page load the panel exchanges the HttpOnly
refresh cookie for a new access token; on any 401 it refreshes once (parallel requests
share that single refresh) and retries. If the refresh fails, the panel returns to `/login`.

## Development

```bash
cd frontend
npm ci
API_PROXY_TARGET=http://localhost:8000 npm run dev    # http://localhost:3000
npm run lint && npm run typecheck && npm test && npm run build
```

## Tests

- Vitest + Testing Library (19): API client refresh/retry/single-flight/session expiry,
  login validation and errors, route guard redirect, permission-filtered navigation,
  variant form rules, formatting, system status.
- Browser end-to-end (Playwright, run against the real API during development, 14 steps):
  redirect when anonymous, wrong password, login, reload keeps session, create category,
  create product (with validation errors first), image upload, stock adjust incl. the
  "below reserved" rule and history, delivery rate, promo code, settings, all report/list
  pages, mobile drawer navigation, logout. No console errors.
