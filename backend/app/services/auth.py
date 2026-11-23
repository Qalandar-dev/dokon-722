"""Admin authentication.

- Access token: short-lived JWT (``ACCESS_TOKEN_TTL_MINUTES``), sent as ``Bearer``.
- Refresh token: random opaque value in an HttpOnly cookie; only its SHA-256 is stored
  (``admin_sessions``). Every refresh **rotates** it. Presenting an already-rotated token
  means it was copied, so the whole session family is revoked (reuse detection).
- Deactivating an admin or changing their password revokes all of their sessions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    TokenType,
    create_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.models import AdminSession, AdminUser

# Verifying against this when the email is unknown keeps response times equal,
# so attackers cannot discover which emails exist.
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")

INVALID_CREDENTIALS = "Email yoki parol noto‘g‘ri."


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    admin: AdminUser


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def _admin_by_email(self, email: str) -> AdminUser | None:
        return await self.session.scalar(
            select(AdminUser).where(func.lower(AdminUser.email) == email.strip().lower())
        )

    async def login(
        self, email: str, password: str, *, user_agent: str | None, ip: str | None
    ) -> TokenPair:
        admin = await self._admin_by_email(email)
        valid = verify_password(password, admin.password_hash if admin else _DUMMY_HASH)
        if admin is None or not valid:
            raise AuthenticationError(INVALID_CREDENTIALS, code="invalid_credentials")
        if not admin.is_active:
            raise AuthenticationError("Hisobingiz o‘chirilgan.", code="account_disabled")
        if password_needs_rehash(admin.password_hash):
            admin.password_hash = hash_password(password)
        admin.last_login_at = utcnow()
        pair = await self._issue(admin, family_id=uuid.uuid4(), user_agent=user_agent, ip=ip)
        await self.session.commit()
        return pair

    async def refresh(
        self, refresh_token: str, *, user_agent: str | None, ip: str | None
    ) -> TokenPair:
        now = utcnow()
        record = await self.session.scalar(
            select(AdminSession)
            .where(AdminSession.token_hash == hash_token(refresh_token))
            .with_for_update()
        )
        if record is None:
            raise AuthenticationError("Sessiya topilmadi. Qayta kiring.", code="invalid_refresh")
        if record.rotated_at is not None or record.revoked_at is not None:
            # A used or revoked token came back: assume theft, end every session of this login.
            await self._revoke_family(record.family_id, now)
            await self.session.commit()
            raise AuthenticationError(
                "Sessiya bekor qilingan. Qayta kiring.", code="refresh_reused"
            )
        if record.expires_at <= now:
            raise AuthenticationError(
                "Sessiya muddati tugagan. Qayta kiring.", code="refresh_expired"
            )
        admin = await self.session.get(AdminUser, record.admin_user_id)
        if admin is None or not admin.is_active:
            await self._revoke_family(record.family_id, now)
            await self.session.commit()
            raise AuthenticationError("Hisobingiz o‘chirilgan.", code="account_disabled")

        record.rotated_at = now
        pair = await self._issue(admin, family_id=record.family_id, user_agent=user_agent, ip=ip)
        await self.session.commit()
        return pair

    async def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        record = await self.session.scalar(
            select(AdminSession).where(AdminSession.token_hash == hash_token(refresh_token))
        )
        if record is not None:
            await self._revoke_family(record.family_id, utcnow())
            await self.session.commit()

    async def _revoke_family(self, family_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(
            update(AdminSession)
            .where(AdminSession.family_id == family_id, AdminSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def _issue(
        self,
        admin: AdminUser,
        *,
        family_id: uuid.UUID,
        user_agent: str | None,
        ip: str | None,
    ) -> TokenPair:
        access, _, access_exp = create_token(
            self.settings,
            subject=str(admin.id),
            token_type=TokenType.ACCESS,
            extra_claims={"role": admin.role.name},
        )
        refresh = generate_opaque_token(48)
        refresh_exp = utcnow() + timedelta(days=self.settings.refresh_token_ttl_days)
        self.session.add(
            AdminSession(
                admin_user_id=admin.id,
                family_id=family_id,
                token_hash=hash_token(refresh),
                expires_at=refresh_exp,
                user_agent=(user_agent or "")[:512] or None,
                ip_address=ip,
            )
        )
        return TokenPair(access, access_exp, refresh, refresh_exp, admin)


async def revoke_all_sessions(session: AsyncSession, admin_user_id: uuid.UUID) -> None:
    """End every session of an admin (deactivation, role or password change). Caller commits."""
    await session.execute(
        update(AdminSession)
        .where(AdminSession.admin_user_id == admin_user_id, AdminSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
