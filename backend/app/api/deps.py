"""FastAPI dependencies: database session, admin auth + permissions, bot auth."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AppError,
    AuthenticationError,
    PermissionDeniedError,
)
from app.core.permissions import Permission
from app.core.rate_limit import RateLimiter
from app.core.redis import get_redis
from app.core.security import TokenType, constant_time_equals, decode_token
from app.database.session import get_session
from app.integrations.storage.base import Storage
from app.integrations.storage.factory import get_storage
from app.models import AdminUser, User

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
StorageDep = Annotated[Storage, Depends(get_storage)]

_bearer = HTTPBearer(auto_error=False, description="Admin access token")


def get_rate_limiter() -> RateLimiter:
    return RateLimiter(get_redis())


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


def client_ip(request: Request) -> str | None:
    # Uvicorn's --proxy-headers already applied X-Forwarded-For from trusted proxies.
    return request.client.host if request.client else None


# --- Admin -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AdminContext:
    admin: AdminUser
    permissions: frozenset[str]

    @property
    def id(self) -> uuid.UUID:
        return self.admin.id


async def current_admin(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AdminContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()
    claims = decode_token(settings, credentials.credentials, expected_type=TokenType.ACCESS)
    try:
        admin_id = uuid.UUID(claims["sub"])
    except ValueError as exc:
        raise AuthenticationError("Token yaroqsiz.", code="invalid_token") from exc
    admin = await session.scalar(select(AdminUser).where(AdminUser.id == admin_id))
    # Re-checked on every request: deactivation takes effect immediately.
    if admin is None or not admin.is_active:
        raise AuthenticationError("Hisobingiz o‘chirilgan.", code="account_disabled")
    return AdminContext(admin=admin, permissions=frozenset(admin.role.permissions))


AdminDep = Annotated[AdminContext, Depends(current_admin)]


def require(*permissions: Permission):  # type: ignore[no-untyped-def]
    """Dependency factory: the admin must hold every listed permission."""

    async def checker(ctx: AdminDep) -> AdminContext:
        missing = [p.value for p in permissions if p.value not in ctx.permissions]
        if missing:
            raise PermissionDeniedError(details={"missing_permissions": missing})
        return ctx

    return checker


# --- Bot (customer endpoints) ------------------------------------------------------------


class CustomerNotRegisteredError(AppError):
    status_code = 404
    code = "customer_not_registered"
    message = "Avval /start buyrug‘i bilan ro‘yxatdan o‘ting."


async def bot_auth(
    settings: SettingsDep,
    x_bot_secret: Annotated[str | None, Header(description="Shared bot secret")] = None,
) -> None:
    """Customer endpoints are called only by our Telegram bot over the internal network."""
    expected = settings.bot_api_secret.get_secret_value()
    if not x_bot_secret or not constant_time_equals(x_bot_secret, expected):
        raise AuthenticationError(
            "Bot autentifikatsiyasi talab qilinadi.", code="invalid_bot_secret"
        )


async def current_customer(
    session: SessionDep,
    _: Annotated[None, Depends(bot_auth)],
    x_telegram_user_id: Annotated[int, Header(gt=0, description="Telegram user id")],
) -> User:
    user = await session.scalar(select(User).where(User.telegram_id == x_telegram_user_id))
    if user is None:
        raise CustomerNotRegisteredError()
    if user.is_blocked:
        raise PermissionDeniedError(
            "Hisobingiz bloklangan. Qo‘llab-quvvatlash bilan bog‘laning.", code="customer_blocked"
        )
    return user


CustomerDep = Annotated[User, Depends(current_customer)]
