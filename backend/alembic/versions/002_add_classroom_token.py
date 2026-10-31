"""Add classroom_token to users table

Revision ID: 002_add_classroom_token
Revises: 001_initial_schema
Create Date: 2026-10-20 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_add_classroom_token"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table_name: str, column_name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table_name not in insp.get_table_names():
        return False
    return any(col["name"] == column_name for col in insp.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("users", "classroom_token"):
        op.add_column("users", sa.Column("classroom_token", sa.Text(), nullable=True))


def downgrade() -> None:
    if _column_exists("users", "classroom_token"):
        op.drop_column("users", "classroom_token")
