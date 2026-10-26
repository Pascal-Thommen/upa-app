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


def upgrade() -> None:
    op.add_column("users", sa.Column("classroom_token", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "classroom_token")
