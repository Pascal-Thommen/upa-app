"""Add category column to posts (redaktionelle Kategorie)

Revision ID: 004_add_post_category
Revises: 003_add_refresh_and_device_tokens
Create Date: 2026-10-21 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_add_post_category"
down_revision: str | None = "003_add_refresh_and_device_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table_name: str, column_name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table_name not in insp.get_table_names():
        return False
    return any(col["name"] == column_name for col in insp.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("posts", "category"):
        op.add_column("posts", sa.Column("category", sa.String(length=50), nullable=True))


def downgrade() -> None:
    if _column_exists("posts", "category"):
        op.drop_column("posts", "category")
