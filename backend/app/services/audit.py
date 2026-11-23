from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_ctx
from app.models import AuditLog


def record_audit(
    session: AsyncSession,
    *,
    admin_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: object | None = None,
    changes: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Add an audit entry to the current transaction (written with the change itself)."""
    session.add(
        AuditLog(
            admin_user_id=admin_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            changes=changes,
            ip_address=ip_address,
            request_id=request_id_ctx.get(),
        )
    )


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """{"field": {"from": x, "to": y}} for changed fields, JSON-safe."""
    return {
        k: {"from": _json(before.get(k)), "to": _json(after.get(k))}
        for k in after
        if before.get(k) != after.get(k)
    }


def _json(value: object) -> object:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)
