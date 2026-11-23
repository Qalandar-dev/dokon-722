from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, BigInteger, ForeignKey, Index, SmallInteger, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Role(TimestampMixin, Base):
    """Admin role. ``permissions`` is a list of permission codes (see services/permissions)."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(64))
    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default="{}"
    )

    admins: Mapped[list[AdminUser]] = relationship(back_populates="role")


class AdminUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        # Case-insensitive unique email without needing the citext extension.
        Index("uq_admin_users_email_lower", func.lower("email"), unique=True),
    )

    email: Mapped[str] = mapped_column(String(254))
    full_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), index=True)
    # Optional link to a Telegram account for staff alerts.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    last_login_at: Mapped[datetime | None]

    role: Mapped[Role] = relationship(back_populates="admins", lazy="joined")
    sessions: Mapped[list[AdminSession]] = relationship(
        back_populates="admin_user", cascade="all, delete-orphan", passive_deletes=True
    )


class AdminSession(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One refresh token. Tokens issued by rotation share a ``family_id``; reuse of a
    rotated token revokes the whole family (theft detection)."""

    __tablename__ = "admin_sessions"

    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    rotated_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(45))

    admin_user: Mapped[AdminUser] = relationship(back_populates="sessions")
