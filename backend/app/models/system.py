from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import NotificationStatus


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Outbound message queue/log (Telegram). The worker sends pending rows."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "user_id IS NOT NULL OR admin_user_id IS NOT NULL OR chat_id IS NOT NULL",
            name="has_recipient",
        ),
        Index(
            "ix_notifications_pending",
            "scheduled_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    # Send order: several notifications written in one transaction share created_at.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE")
    )
    # Direct Telegram chat id, e.g. a staff group.
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[NotificationStatus] = mapped_column(
        str_enum(NotificationStatus, "notification_status"),
        default=NotificationStatus.PENDING,
        server_default="pending",
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(server_default=func.now())
    sent_at: Mapped[datetime | None]


class AuditLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Who did what to which record. Append-only."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(64))  # e.g. "product.update"
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    changes: Mapped[dict[str, Any] | None]
    ip_address: Mapped[str | None] = mapped_column(String(45))
    request_id: Mapped[str | None] = mapped_column(String(64))


class StoreSetting(TimestampMixin, Base):
    """Key/value store settings editable from the admin panel (values are JSON)."""

    __tablename__ = "store_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]]
    description: Mapped[str | None] = mapped_column(String(255))
    updated_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
