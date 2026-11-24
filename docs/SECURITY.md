# Security (Phase 11)

## Review checklist

| Area | Measure | Where / test |
|---|---|---|
| Secrets | Only from environment; `SecretStr`; never in repo (`.env` ignored); production refuses weak/default secrets, `DEBUG`, wildcard CORS, `TRUSTED_HOSTS=*`, non-HTTPS `PUBLIC_BASE_URL`, live payments without credentials; validation errors never echo values | `core/config.py`, `tests/test_config.py` |
| Logs | Redaction of auth headers, tokens, passwords, signatures, Telegram bot tokens, card-like numbers; httpx request logging silenced (bot token in URL) | `core/logging.py`, `tests/test_logging.py` |
| Admin passwords | Argon2id, min 10 characters, rehash on login when parameters change | `core/security.py`, `services/admin_config.py` |
| Admin login | Same answer for unknown email and wrong password (timing equalised), 10 attempts/min per IP and per email (Redis) + Nginx limit | `services/auth.py`, `test_auth_permissions.py` |
| Sessions | 15-min JWT access token (algorithm pinned, issuer checked) kept in memory by the panel; refresh token in `HttpOnly; SameSite=Strict; Secure` cookie scoped to `/api/v1/admin/auth`, stored hashed, rotated on every use, reuse revokes the family; deactivation/role/password change ends sessions; account re-checked on every request | `services/auth.py`, `api/deps.py` |
| CSRF | Cookie used only by refresh/logout: SameSite=Strict **and** Origin must be our host or an allowed origin | `api/v1/admin/auth.py`, `test_refresh_rejects_foreign_origin` |
| Authorization | Permission per admin endpoint, enforced server-side (matrix test); customers only see their own orders/payments/addresses (404 otherwise) | `api/deps.py`, `test_permission_matrix`, payment/order ownership tests |
| Bot ↔ API | Shared secret (constant-time compare) + Telegram user id; internal network only; phone "verified" only from the user's own contact share | `api/deps.py`, `test_customer_flow.py` |
| Input | Pydantic validation, unknown fields rejected, length limits; LIKE wildcards escaped in search; ORM only (no string SQL with user input) | `schemas/`, `repositories/products.py` |
| Uploads | Type from file content (JPG/PNG/WEBP only, no SVG), size limit enforced while reading, random names, path-traversal guard, served with `nosniff` and a restrictive CSP | `services/uploads.py`, `integrations/storage/local.py`, `test_image_upload_validation` |
| Output | Telegram HTML escaped; React escapes by default; no `dangerouslySetInnerHTML` | `bot/texts.py`, `tests/bot` |
| Payments | Only verified provider confirmation marks paid; amount and provider checked; idempotent per transaction id; mock checkout protected by an HMAC token, only in mock mode; no card data stored | `services/payments.py`, `test_payments.py` |
| Integrity | DB constraints: stock never negative/oversold, totals consistent, one paid payment per order, unique provider transactions | `docs/DATABASE.md`, `test_models.py` |
| Headers | API: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`; panel: CSP (`default-src 'self'`, `frame-ancestors 'none'`, no `eval` in production), Permissions-Policy; Nginx: HSTS when served over HTTPS, `server_tokens off` | `api/middleware.py`, `frontend/next.config.ts`, `docker/nginx/nginx.conf` |
| CORS / hosts | Explicit origins; `TrustedHostMiddleware` | `main.py` |
| Audit | Every staff change in `audit_logs` with actor, diff, IP-ready, request id | `services/audit.py`, admin tests |
| Containers | Non-root (uid 10001); production: read-only root FS, all capabilities dropped, `no-new-privileges`; only Nginx publishes a port; Postgres/Redis internal | `Dockerfile`s, `docker-compose.prod.yml` |
| Dependencies | Exact pins + lock files; `pip-audit` and `npm audit` in CI | `.github/workflows/ci.yml` |

## Findings fixed in this phase

- **Next.js 16.2.12 had published critical advisories** (RCE in the image optimizer,
  cache poisoning, SSRF, …). Upgraded to 16.4.6; the image optimizer is disabled because
  images are served by Nginx. `npm audit`: 0 vulnerabilities. `pip-audit`: none found.
- Nginx `location` blocks with their own `add_header` dropped the server-level security
  headers; they now repeat them.
- Production now also requires `TRUSTED_HOSTS` and an `https://` `PUBLIC_BASE_URL`.

Earlier phases fixed (see commit history): secrets echoed in config validation errors,
Bearer tokens not redacted, the single-admin email index, payment duplicate-callback
crash, bot registration skipped after boot.

## Operating securely

- Put TLS in front of Nginx and forward `X-Forwarded-Proto` (HSTS and secure cookies rely on it).
- Keep `.env` readable only by the deploy user (`chmod 600`).
- Rotate `JWT_SECRET_KEY` (logs everyone out) and `BOT_API_SECRET` if leaked; rotate the
  bot token with @BotFather `/revoke` — **the current bot token was posted in a chat and
  should be rotated before going live.**
- Back up the database and the `media` volume (see `docs/DEPLOYMENT.md`).
- Review `audit_logs` and failed notifications periodically.

## Out of scope / known limits

- No WAF or bot-detection beyond rate limits.
- Customer API is reachable through Nginx but useless without the bot secret; it could
  additionally be blocked at Nginx if the bot always uses the internal network.
- Click/Payme callback signature checks will be added with the adapters (`docs/PAYMENTS.md`).
