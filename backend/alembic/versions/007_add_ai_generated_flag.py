"""Indicador de eventos extraidos por IA multimodal (is_ai_generated)

Revision ID: 007_add_ai_generated_flag
Revises: 006_add_app_settings
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_add_ai_generated_flag"
down_revision: str | None = "006_add_app_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "posts" in inspector.get_table_names():
        cols = {col["name"] for col in inspector.get_columns("posts")}
        if "is_ai_generated" not in cols:
            op.add_column(
                "posts",
                sa.Column("is_ai_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "posts" in inspector.get_table_names():
        cols = {col["name"] for col in inspector.get_columns("posts")}
        if "is_ai_generated" in cols:
            op.drop_column("posts", "is_ai_generated")
