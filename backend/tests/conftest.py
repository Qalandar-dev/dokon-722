"""Test configuration.

Tests use a separate database (``TEST_DATABASE_URL``, default ``online_store_test``)
and a separate Redis DB index so they can never touch development data.
WARNING: the test run drops and recreates the public schema of TEST_DATABASE_URL.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://store:store@localhost:5432/online_store_test"
)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
os.environ["LOG_JSON"] = "false"

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.core.redis import close_redis
from app.database.session import dispose_engine
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as c,
    ):
        yield c
    await close_redis()
    await dispose_engine()


# --- Database ------------------------------------------------------------------


def _alembic_config():  # type: ignore[no-untyped-def]
    from pathlib import Path

    from alembic.config import Config

    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


async def _reset_schema(url: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


@pytest.fixture(scope="session")
def migrated_db() -> str:
    """Build the test schema with the real migrations (not create_all), once per run."""
    import asyncio

    from alembic import command

    url = os.environ["DATABASE_URL"]
    asyncio.run(_reset_schema(url))
    command.upgrade(_alembic_config(), "head")
    return url


@pytest.fixture
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_db, poolclass=NullPool)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session whose work is always rolled back, even if the test commits.

    Each ``session.commit()`` inside the test only releases a SAVEPOINT.
    """
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()
