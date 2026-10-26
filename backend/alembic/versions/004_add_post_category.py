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


def upgrade() -> None:
    op.add_column("posts", sa.Column("category", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "category")
