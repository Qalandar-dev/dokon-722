"""API test fixtures: the real app, wired to the rolled-back test session."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.redis import close_redis, get_redis
from app.core.security import hash_password
from app.database.session import get_session
from app.integrations.storage.factory import get_storage
from app.integrations.storage.local import LocalStorage
from app.main import create_app
from app.models import AdminUser

PASSWORD = "Juda-kuchli-parol-2026"
ROLE_IDS = {"super_admin": 1, "manager": 2, "operator": 3}

AdminFactory = Callable[..., Awaitable[dict[str, str]]]


@pytest.fixture
async def api(
    db: AsyncSession, settings: Settings, tmp_path: Path
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    storage = LocalStorage(settings.model_copy(update={"media_root": str(tmp_path)}))

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_storage] = lambda: storage
    await get_redis().flushdb()  # rate-limit counters (test Redis DB only)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    await close_redis()


@pytest.fixture
def bot_headers(settings: Settings) -> Callable[[int], dict[str, str]]:
    def build(telegram_id: int) -> dict[str, str]:
        return {
            "X-Bot-Secret": settings.bot_api_secret.get_secret_value(),
            "X-Telegram-User-Id": str(telegram_id),
        }

    return build


@pytest.fixture
def make_admin(db: AsyncSession, api: httpx.AsyncClient) -> AdminFactory:
    """Create an admin with the given role, log in, return Authorization headers."""

    async def build(role: str = "super_admin", **kw: object) -> dict[str, str]:
        email = f"{role}-{uuid.uuid4().hex[:8]}@store.uz"
        db.add(
            AdminUser(
                email=email,
                full_name=role,
                password_hash=hash_password(PASSWORD),
                role_id=ROLE_IDS[role],
                **kw,
            )
        )
        await db.commit()
        r = await api.post("/api/v1/admin/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}", "X-Admin-Email": email}

    return build
