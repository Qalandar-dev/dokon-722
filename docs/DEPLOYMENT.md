# Production deployment

Everything below was rehearsed end to end on Docker (production images, hardened
containers, migrations, admin creation, browser smoke test, backup → damage → restore).

## 1. Server

- Linux VPS, 2 vCPU / 4 GB RAM / 40 GB SSD is enough to start (Uzbekistan-hosted or nearby
  for latency). Docker Engine 24+ with the Compose plugin.
- A domain, e.g. `shop.example.uz`, pointing (A record) to the server.
- Firewall: allow 22 (SSH, keys only), 80 and 443. Nothing else.

## 2. TLS in front of Nginx

The stack's Nginx listens on `HTTP_PORT` (plain HTTP). Terminate HTTPS before it and pass
`X-Forwarded-Proto` (HSTS and secure cookies rely on it). Simplest: Caddy on the host,
which obtains Let's Encrypt certificates automatically:

```
# /etc/caddy/Caddyfile
shop.example.uz {
    reverse_proxy 127.0.0.1:8080
}
```

and set `HTTP_PORT=8080` (bind it to localhost only if you prefer, by changing the port
mapping in `docker-compose.prod.yml` to `127.0.0.1:${HTTP_PORT}:8080`).

## 3. Configuration

```bash
git clone https://github.com/Qalandar-dev/dokon-722.git && cd dokon-722
cp .env.example .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # run 3×
```

Set at least: `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `BOT_API_SECRET` (the three random
values), `PUBLIC_BASE_URL=https://shop.example.uz`, `CORS_ORIGINS=https://shop.example.uz`,
`TRUSTED_HOSTS=shop.example.uz`, `BOT_TOKEN`, `TELEGRAM_ADMIN_IDS`. The backend refuses
to start in production if any of these is unsafe; the error says which.

## 4. Start

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps        # all healthy
```

`migrate` applies the database migrations and exits (status `Exited (0)`); the other
services start after it.

## 5. First admin and store setup

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m app.scripts.create_admin --email owner@example.uz --name "Ism Familiya"
```

Then in the admin panel (`https://shop.example.uz`):
1. **Sozlamalar** — store name, phone, support Telegram username, free-delivery threshold,
   payment methods (keep only those that work: see `docs/PAYMENTS.md`).
2. **Yetkazib berish → Tariflar** — a rate per region (and per district where it differs).
   Without a rate, customers in that region cannot check out.
3. **Kategoriyalar**, **Mahsulotlar** (with stock), images.
4. **Xodimlar** — staff accounts; link their Telegram id to receive alerts.
5. Open the bot, `/start`, place a test order, confirm it in the panel.

## 6. Backups

```bash
scripts/backup.sh /var/backups/dokon          # db.dump + media.tar.gz, keeps 14 days
```

Daily via cron (as the deploy user, from the project directory):

```
30 2 * * * cd /opt/dokon-722 && scripts/backup.sh /var/backups/dokon >> /var/log/dokon-backup.log 2>&1
```

Copy backups off the server (object storage, another machine). Restore (replaces all data):

```bash
scripts/restore.sh /var/backups/dokon/20261124T020000Z
```

## 7. Updates

```bash
git pull
scripts/backup.sh /var/backups/dokon
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Migrations run automatically. Roll back by checking out the previous version and, if a
migration must be undone, `docker compose … run --rm migrate alembic downgrade -1`.

## 8. Operations

| Check | How |
|---|---|
| Health | `curl https://shop.example.uz/api/v1/health/ready` → `{"status":"ok",…}` |
| Logs (JSON, secrets redacted) | `docker compose … logs -f api worker bot` |
| Worker alive | `worker` container healthy; `redis-cli get worker:heartbeat` |
| Failed Telegram messages | `select type, last_error from notifications where status='failed'` |
| Staff activity | Admin panel → Amallar jurnali |

## 9. Before going live

- [ ] Rotate the Telegram bot token with @BotFather (`/revoke`) — the current one was shared in chat.
- [ ] Click/Payme connected (`docs/PAYMENTS.md`) or online payments switched off in settings
      and cash on delivery enabled; never go live with `PAYMENT_MODE=mock`.
- [ ] Verify the region/district list against the official classifier.
- [ ] Backups scheduled and one restore tested on a copy.
