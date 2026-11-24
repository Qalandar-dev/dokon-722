# Background worker and notifications (Phase 10)

`arq app.workers.main.WorkerSettings` (the `worker` service in Docker), on Redis.

## Jobs (UTC)

| Schedule | Job | What it does |
|---|---|---|
| every 10 s | `send_notifications` | Sends queued Telegram messages; retries with backoff (30 s → 1 h), honours Telegram's `retry_after`, gives up after 6 attempts; a blocked bot / unknown chat is not retried |
| every minute | `expire_orders` | Cancels unpaid Click/Payme orders whose reservation (`ORDER_RESERVATION_TTL_MINUTES`) expired and releases the stock (`SKIP LOCKED`: safe with several workers, skips orders a payment is touching) |
| hourly :07 | `low_stock_alert` | Tells staff about variants that **became** low since the last check (no repeats) |
| 15:00 (20:00 Tashkent) | `daily_report` | Today's revenue, paid/new/cancelled orders and top products to staff |
| every minute | `heartbeat` | Container health check |

## Notifications

Written to the `notifications` table **in the same transaction** as the change they describe
(outbox), so a message is never lost and never sent for a change that was rolled back; the
worker sends them in order (`seq`).

| To | When |
|---|---|
| Customer | order received, payment received (online), confirmed, shipped, out for delivery, delivered, delivery failed, cancelled (with reason, incl. payment timeout), refunded |
| Staff | new order (setting `notifications.new_order_to_staff`), low stock (`notifications.low_stock_to_staff`), daily report |

Staff recipients: `TELEGRAM_ADMIN_IDS` plus active staff accounts with a Telegram id.
Without `BOT_TOKEN` nothing is sent; messages wait in the table and go out once a token is set.
Texts are Uzbek, HTML-escaped (`app/workers/messages.py`).
