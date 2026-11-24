# Telegram bot (Phase 6)

Customer interface, built with Aiogram 3 (`backend/app/bot/`). The bot is a **client of
the store API**: it holds no prices, stock or order rules. Everything it shows comes from
the API, and every action goes through it, with `X-Bot-Secret` and the customer's
Telegram id.

## What a customer can do

| Menu | Flow |
|---|---|
| `/start` | Registers the customer (name, username, language from Telegram), asks to share the phone with Telegram's contact button. Only a shared **own** contact marks the phone verified; a typed number is not accepted here. |
| 🛍 Katalog | All products, 8 per page; sort (new, cheaper, dearer, popular); filters: in stock, discounted, price range (`100000-500000`). |
| 📂 Kategoriyalar | Category tree → sub-categories → products. |
| 🔎 Qidiruv | Name (fuzzy) or exact SKU. |
| Product card | Photo, price (discount shown struck through), availability, description; variant buttons (size/colour) with price and stock; "Savatga qo‘shish"; "Barcha rasmlar" album. |
| 🛒 Savat | Lines with ➖ ➕ 🗑, warnings for items that ran out, promo code, totals; "Rasmiylashtirish". |
| Checkout | Name → phone (contact button or typed, validated) → saved address or region → district → delivery method with price and ETA (from admin-configured rates) → address → landmark (optional) → payment method (only those enabled in settings) → **summary from the API's checkout preview** → confirm. |
| 📦 Buyurtmalarim | Paginated history; order card with status, payment and delivery status in Uzbek; cancel (with confirmation) while allowed. |
| 👤 Profil | Name, phone (✅ when verified), saved addresses (delete). |
| ☎️ Aloqa | Store phone, support Telegram, address from settings. |

## Safety properties

- **No duplicate orders:** the summary step creates one idempotency key; tapping "Tasdiqlash" again
  (or Telegram retrying) returns the same order, and buttons of a finished checkout are rejected.
- **Totals are the API's:** the summary is the API's checkout preview, the same calculation that creates the order.
- **HTML-safe:** product names, addresses and other data are escaped before being shown.
- **Errors:** API business errors are shown with the API's Uzbek message; connection problems and
  unexpected errors get a friendly message and are logged; stale buttons get "eskirgan".
- **Throttling:** updates faster than 0.4 s per user are dropped (protects the API from button mashing).
- **State:** conversation state lives in Redis (24 h TTL), so a restart does not lose a checkout in progress.
- **Photos:** downloaded once over the internal network (`BOT_MEDIA_BASE_URL`), uploaded to Telegram,
  then reused by Telegram `file_id` (saved through the API).

## Payments

Click and Payme are connected in Phase 9. Until then an online order is created and its
items are held for `ORDER_RESERVATION_TTL_MINUTES`; the bot says so plainly and does not
pretend a payment happened. Cash on delivery appears only if enabled in settings.

## Running

```bash
# Docker (BOT_TOKEN in .env)
docker compose up -d bot
# Local
cd backend && BOT_TOKEN=... API_INTERNAL_URL=http://localhost:8000 uv run python -m app.bot.main
```

The bot uses long polling. It needs outbound HTTPS to `api.telegram.org`.

## Tests

`backend/tests/bot/` drives the real dispatcher and handlers against the real API and test
database; only Telegram is replaced (`FakeTelegram` records every Bot API call). Covered:
registration and phone verification, catalog sort/filter/search, HTML escaping, photo
`file_id` reuse, cart controls, the full checkout with double-tap protection and saved
address reuse, order cancel, profile, error messages, stale buttons.
