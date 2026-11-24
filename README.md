# Online Store — Uzbekistan

Universal e-commerce platform for the Uzbek market: a Telegram bot for customers,
a web admin panel for staff, a FastAPI backend, PostgreSQL, Redis, Click and Payme
payments, and nationwide delivery. Uzbek (Latin) interface, UZS, Asia/Tashkent.

> **Status: Phases 1–8 complete, payments architecture done (Click/Payme adapters need the official docs — see [`docs/PAYMENTS.md`](docs/PAYMENTS.md))** (architecture, configuration, Docker, database,
> business services, HTTP API, Telegram bot and admin panel — see [`docs/ADMIN_PANEL.md`](docs/ADMIN_PANEL.md), [`docs/DATABASE.md`](docs/DATABASE.md),
> [`docs/SERVICES.md`](docs/SERVICES.md), [`docs/API.md`](docs/API.md) and [`docs/BOT.md`](docs/BOT.md)). Catalog, cart, orders, payments, bot flows and admin screens are built in
> later phases; see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full plan.
> Nothing in this repository processes real payments yet.

## Contents

- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Project structure](#project-structure)
- [Quick start (Docker)](#quick-start-docker)
- [Local development without Docker](#local-development-without-docker)
- [Database and migrations](#database-and-migrations)
- [Tests and quality checks](#tests-and-quality-checks)
- [Environment variables](#environment-variables)
- [Production deployment](#production-deployment)
- [Click, Payme, delivery, admin accounts](#click-payme-delivery-admin-accounts)

## Architecture

Modular monolith. One backend image runs four processes (`api`, `bot`, `worker`,
`migrate`); the admin panel is a separate Next.js app. Nginx is the only public
entrypoint: `/api` and `/media` go to FastAPI, everything else to Next.js. All
business rules live in the backend service layer, and the bot and panel are API clients.
Details, ERD, API design and state machines: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Technology stack

| Layer | Choice (pinned) |
|---|---|
| API | Python 3.12, FastAPI 0.165, Pydantic 2.14, pydantic-settings, Uvicorn |
| Data | PostgreSQL 17, SQLAlchemy 2.0 (async) + asyncpg, Alembic |
| Bot | Aiogram 3.34, Redis FSM storage |
| Jobs | arq 0.28 on Redis 7.4 |
| Auth | Argon2id (argon2-cffi), JWT (PyJWT) with refresh-token rotation |
| Admin UI | Next.js 16, React 19, TypeScript (strict), Tailwind CSS 4, shadcn/ui pattern + Radix, TanStack Query, React Hook Form, Zod |
| Quality | pytest + pytest-asyncio + HTTPX, Ruff, ESLint, Vitest + Testing Library |
| Ops | Docker, Docker Compose, Nginx |

Python versions are locked in `backend/uv.lock`, JS versions in `frontend/package-lock.json`;
direct dependencies are pinned exactly.

## Project structure

```
dokon-722/
├── backend/            FastAPI app, bot, worker, migrations, tests (one image)
│   └── app/{core,database,models,schemas,repositories,services,api,bot,integrations,workers}
├── frontend/           Next.js admin panel
├── docker/nginx/       reverse proxy config
├── docs/               architecture and design docs
├── scripts/            operational scripts (added in later phases)
├── docker-compose.yml            base stack
├── docker-compose.override.yml   development overrides (auto-loaded)
├── docker-compose.prod.yml       production overrides
└── .env.example
```

## Quick start (Docker)

Requirements: Docker 24+ with Compose v2.

```bash
git clone https://github.com/Qalandar-dev/dokon-722.git
cd dokon-722
cp .env.example .env            # then edit secrets (see below)
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost | Admin panel through Nginx (`HTTP_PORT`, default 80) |
| http://localhost:8000/api/v1/docs | OpenAPI docs (development only) |
| http://localhost/api/v1/health/ready | Readiness: database and Redis |

Development mode hot-reloads `backend/app` and `frontend/src`, and publishes
PostgreSQL (5432), Redis (6379) and the API (8000) on **127.0.0.1 only**.

**Telegram bot:** set `BOT_TOKEN` (from @BotFather) in `.env` and run
`docker compose up -d bot`. Without a token the bot logs a clear error and stops.

## Local development without Docker

```bash
# Backend (needs PostgreSQL and Redis running locally)
cd backend
uv sync                                    # creates .venv from uv.lock
export DATABASE_URL=postgresql+asyncpg://store:store@localhost:5432/online_store
uv run alembic upgrade head
uv run uvicorn app.main:app --reload       # API on :8000
uv run python -m app.bot.main              # bot (needs BOT_TOKEN)
uv run arq app.workers.main.WorkerSettings # worker

# Frontend
cd frontend
npm ci
API_PROXY_TARGET=http://localhost:8000 npm run dev   # :3000, proxies /api to FastAPI
```

## Database and migrations

Migrations live in `backend/app/database/migrations/`. The database URL always comes
from `DATABASE_URL`, never from `alembic.ini`.

```bash
uv run alembic revision --autogenerate -m "describe change"   # create
uv run alembic upgrade head                                    # apply
uv run alembic downgrade -1                                    # roll back one
```

In Docker the one-shot `migrate` service runs `alembic upgrade head` on every start;
`api`, `bot` and `worker` start only after it succeeds. Always review autogenerated
migrations before committing them.

## Tests and quality checks

Backend tests use a **separate database** (`online_store_test`) and Redis DB 15.
The test run **drops and rebuilds that database's schema** with the real migrations,
so never point `TEST_DATABASE_URL` at a database holding real data.

```bash
cd backend
createdb online_store_test          # once
uv run ruff format --check . && uv run ruff check .
uv run pytest
# or point at other instances:
TEST_DATABASE_URL=postgresql+asyncpg://u:p@host/db TEST_REDIS_URL=redis://host:6379/15 uv run pytest

cd frontend
npm run lint && npm run typecheck && npm test && npm run build

# Browser smoke test of the admin panel against a running stack (creates test data;
# never against production)
ADMIN_EMAIL=... ADMIN_PASSWORD=... node frontend/e2e/admin-smoke.cjs /tmp/shots
```

## Environment variables

`.env.example` documents each variable inline. Summary:

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` / `test` / `production`. Production enables strict validation and disables API docs. |
| `DEBUG` | `false` | Must be false in production. |
| `PROJECT_NAME`, `TIMEZONE` | `Online Store`, `Asia/Tashkent` | Display name / business timezone. |
| `LOG_LEVEL`, `LOG_JSON` | `INFO`, `true` | Logging. Secrets, tokens, signatures and card-like numbers are redacted. |
| `HTTP_PORT` | `80` | Host port for Nginx. |
| `PUBLIC_BASE_URL` | `http://localhost` | Public site URL (payment return URLs, media links). |
| `CORS_ORIGINS` | localhost | Comma-separated allowed origins; no `*` in production. |
| `TRUSTED_HOSTS` | `*` | Accepted `Host` headers; set your domains in production. |
| `API_WORKERS` | `2` | Uvicorn workers in production. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | — | Database credentials (required by Compose). |
| `DATABASE_URL` | built by Compose | Only needed outside Docker. |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | `10` / `10` | Connection pool per process. |
| `REDIS_URL` | built by Compose | Only needed outside Docker. |
| `JWT_SECRET_KEY` | — | Admin JWT signing key, 32+ random chars. |
| `ACCESS_TOKEN_TTL_MINUTES` / `REFRESH_TOKEN_TTL_DAYS` | `15` / `14` | Admin session lifetimes. |
| `RATE_LIMIT_LOGIN_PER_MINUTE` | `10` | Login attempts per IP. |
| `BOT_TOKEN` | empty | Telegram bot token. |
| `BOT_MEDIA_BASE_URL` | Nginx in Docker | Internal URL the bot downloads product photos from. |
| `BOT_API_SECRET` | — | Secret the bot sends to customer API endpoints, 32+ chars. |
| `TELEGRAM_ADMIN_IDS` | empty | Telegram IDs that receive staff alerts. |
| `STORAGE_BACKEND`, `MAX_UPLOAD_SIZE_MB` | `local`, `5` | Upload storage and size limit. |
| `ORDER_RESERVATION_TTL_MINUTES` | `30` | Stock hold for unpaid online orders. |
| `PAYMENT_MODE` | `mock` | `mock` (simulated, flagged) / `sandbox` / `live`. |
| `CLICK_SERVICE_ID`, `CLICK_MERCHANT_ID`, `CLICK_MERCHANT_USER_ID`, `CLICK_SECRET_KEY` | empty | Click merchant credentials. |
| `PAYME_MERCHANT_ID`, `PAYME_SECRET_KEY`, `PAYME_CHECKOUT_URL` | empty | Payme merchant credentials. |

Generate secrets with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Never commit `.env`.

## Production deployment

1. On a server with Docker, clone the repository and `cd dokon-722`.
2. `cp .env.example .env`, then set strong `POSTGRES_PASSWORD`, `JWT_SECRET_KEY` and `BOT_API_SECRET`,
   your domains in `CORS_ORIGINS` / `TRUSTED_HOSTS` / `PUBLIC_BASE_URL`, and `BOT_TOKEN`.
3. Start the stack:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
   This forces `ENVIRONMENT=production`; the backend **refuses to start** with default
   or weak secrets, `DEBUG=true`, wildcard CORS, or live payments without credentials.
4. **TLS:** terminate HTTPS in front of Nginx (a host-level Caddy/Nginx with Let's Encrypt,
   or a load balancer) and forward to `HTTP_PORT`. Payment callbacks require HTTPS.
5. Only Nginx publishes a port. PostgreSQL and Redis are reachable only on the
   internal Docker network. All app containers run as a non-root user (uid 10001).
6. Back up the `postgres_data` and `media` volumes (a full backup/restore runbook comes in Phase 12).

## Admin account setup

Create the first super-admin (the password is asked interactively, or read from
`ADMIN_PASSWORD`; never pass it as an argument):

```bash
# Docker
docker compose exec api python -m app.scripts.create_admin --email owner@example.uz --name "Ism Familiya"
# Local
cd backend && uv run python -m app.scripts.create_admin --email owner@example.uz --name "Ism Familiya"
```

Further staff accounts are created by a super-admin in the admin panel (or `POST /api/v1/admin/staff`).
Roles: `super_admin` (everything), `manager` (no staff, settings, audit log), `operator`
(orders, read-only catalog, inventory and customers). The full matrix is in `docs/API.md`.

## Click, Payme, delivery

These sections are completed in their phases:

- **Delivery configuration:** Phase 8 (regions and districts are seeded in Phase 3).
- **Click / Payme setup:** see [`docs/PAYMENTS.md`](docs/PAYMENTS.md). Until the adapters are written from the
  official documentation, keep `PAYMENT_MODE=mock` (simulated, clearly labelled) or offer cash on delivery.
