"""seed reference data: regions, districts, roles, store settings, delivery methods

Revision ID: 7642bc13bed8
Revises: 95807fc3202d
Create Date: 2026-11-23 18:14:13.509485

"""
from typing import Sequence, Union

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.database.seed.uzbekistan_v1 import district_rows, region_rows


# revision identifiers, used by Alembic.
revision: str = '7642bc13bed8'
down_revision: Union[str, Sequence[str], None] = '95807fc3202d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Permission codes are copied here on purpose: a migration must not change when
# application code changes later.
_ALL_PERMISSIONS = [
    "dashboard.view",
    "reports.view",
    "products.view",
    "products.manage",
    "categories.manage",
    "inventory.view",
    "inventory.manage",
    "orders.view",
    "orders.manage",
    "orders.refund",
    "customers.view",
    "customers.manage",
    "promo.manage",
    "delivery.manage",
    "staff.manage",
    "settings.manage",
    "audit.view",
]
_MANAGER_EXCLUDED = {"staff.manage", "settings.manage", "audit.view"}
_OPERATOR = [
    "orders.view",
    "orders.manage",
    "products.view",
    "inventory.view",
    "customers.view",
]

_ROLES = [
    {"id": 1, "name": "super_admin", "title": "Bosh administrator", "permissions": _ALL_PERMISSIONS},
    {
        "id": 2,
        "name": "manager",
        "title": "Menejer",
        "permissions": [p for p in _ALL_PERMISSIONS if p not in _MANAGER_EXCLUDED],
    },
    {"id": 3, "name": "operator", "title": "Operator", "permissions": _OPERATOR},
]

# Values are wrapped as {"value": ...} so every setting is a JSON object.
_SETTINGS = [
    ("store.name", {"value": "Online Store"}, "Do‘kon nomi"),
    ("store.phone", {"value": None}, "Aloqa telefoni"),
    ("store.address", {"value": None}, "Do‘kon manzili"),
    ("store.support_telegram", {"value": None}, "Qo‘llab-quvvatlash Telegram username"),
    ("store.currency_display", {"value": "so‘m"}, "Narx yonidagi valyuta belgisi"),
    ("delivery.free_threshold", {"value": None}, "Bepul yetkazib berish chegarasi (so‘m)"),
    ("inventory.low_stock_threshold", {"value": 5}, "Kam qoldiq ogohlantirish chegarasi"),
    ("payments.click_enabled", {"value": True}, "Click orqali to‘lov yoqilgan"),
    ("payments.payme_enabled", {"value": True}, "Payme orqali to‘lov yoqilgan"),
    ("payments.cash_on_delivery_enabled", {"value": False}, "Yetkazib berishda naqd to‘lov"),
    ("notifications.new_order_to_staff", {"value": True}, "Yangi buyurtma haqida xodimlarga xabar"),
    ("notifications.low_stock_to_staff", {"value": True}, "Kam qoldiq haqida xodimlarga xabar"),
]

_DELIVERY_METHODS = [
    # Prices are NOT seeded: an admin sets rates per region in the panel. Until then
    # the method is unavailable everywhere.
    {
        "id": uuid.UUID("5d6f6c1e-0000-4000-8000-000000000001"),
        "code": "courier",
        "kind": "courier",
        "name": "Kuryer orqali yetkazib berish",
        "sort_order": 1,
        "is_active": True,
    },
    {
        "id": uuid.UUID("5d6f6c1e-0000-4000-8000-000000000002"),
        "code": "pickup",
        "kind": "pickup",
        "name": "Do‘kondan olib ketish",
        "sort_order": 2,
        "is_active": False,
    },
]


def _sync_sequence(table: str) -> None:
    """Explicit ids were inserted; move the serial sequence past them."""
    op.execute(
        sa.text(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"(SELECT COALESCE(MAX(id), 1) FROM {table}))"
        )
    )


def upgrade() -> None:
    regions = sa.table(
        "regions",
        sa.column("id", sa.SmallInteger),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    districts = sa.table(
        "districts",
        sa.column("id", sa.Integer),
        sa.column("region_id", sa.SmallInteger),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("kind", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    roles = sa.table(
        "roles",
        sa.column("id", sa.SmallInteger),
        sa.column("name", sa.String),
        sa.column("title", sa.String),
        sa.column("permissions", ARRAY(sa.String)),
    )
    settings = sa.table(
        "store_settings",
        sa.column("key", sa.String),
        sa.column("value", JSONB),
        sa.column("description", sa.String),
    )
    methods = sa.table(
        "delivery_methods",
        sa.column("id", sa.UUID),
        sa.column("code", sa.String),
        sa.column("kind", sa.String),
        sa.column("name", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )

    op.bulk_insert(regions, region_rows())
    op.bulk_insert(districts, district_rows())
    op.bulk_insert(roles, _ROLES)
    op.bulk_insert(
        settings, [{"key": k, "value": v, "description": d} for k, v, d in _SETTINGS]
    )
    op.bulk_insert(methods, _DELIVERY_METHODS)
    for table in ("regions", "districts", "roles"):
        _sync_sequence(table)


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM delivery_methods WHERE code IN ('courier', 'pickup')")
    )
    op.execute(sa.text("DELETE FROM store_settings"))
    op.execute(sa.text("DELETE FROM roles WHERE id IN (1, 2, 3)"))
    op.execute(sa.text("DELETE FROM districts"))
    op.execute(sa.text("DELETE FROM regions"))
