"""fix admin email unique index

The original index was built on lower('email') — the constant string, not the
column — so it allowed only one admin account in total. Rebuild it on lower(email).

Revision ID: a8fc36f3032a
Revises: 25aeb6aefb6f
Create Date: 2026-11-23 18:45:33.015132

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8fc36f3032a'
down_revision: Union[str, Sequence[str], None] = '25aeb6aefb6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_admin_users_email_lower", table_name="admin_users")
    op.create_index(
        "uq_admin_users_email_lower", "admin_users", [sa.text("lower(email)")], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_admin_users_email_lower", table_name="admin_users")
    op.create_index(
        "uq_admin_users_email_lower", "admin_users", [sa.text("lower('email')")], unique=True
    )
