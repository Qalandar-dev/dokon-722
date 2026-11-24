from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A customer, identified by their Telegram account."""

    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    # E.164, e.g. +998901234567
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    # True only when the number came from Telegram contact sharing of the user's own contact.
    phone_verified: Mapped[bool] = mapped_column(default=False, server_default=false())
    language: Mapped[str] = mapped_column(String(8), default="uz", server_default="uz")
    is_blocked: Mapped[bool] = mapped_column(default=False, server_default=false())
    last_seen_at: Mapped[datetime | None]

    addresses: Mapped[list[Address]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Address(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = (
        # At most one default address per user.
        Index(
            "uq_addresses_user_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    district_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("districts.id", ondelete="RESTRICT"), index=True
    )
    recipient_name: Mapped[str] = mapped_column(String(128))
    recipient_phone: Mapped[str] = mapped_column(String(20))
    address_line: Mapped[str] = mapped_column(String(255))
    landmark: Mapped[str | None] = mapped_column(String(255))  # mo‘ljal
    instructions: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(default=False, server_default=false())

    user: Mapped[User] = relationship(back_populates="addresses")
