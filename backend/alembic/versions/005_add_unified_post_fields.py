"""Campos del modelo unificado de publicaciones, grupos de Google y auditoria

Revision ID: 005_add_unified_post_fields
Revises: 004_add_post_category
Create Date: 2026-10-26 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_add_unified_post_fields"
down_revision: str | None = "004_add_post_category"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("posts", sa.Column("reminders", sa.JSON(), nullable=True))
    op.add_column("posts", sa.Column("notify_groups", sa.JSON(), nullable=True))
    op.add_column("posts", sa.Column("event_notify_groups", sa.JSON(), nullable=True))
    op.add_column("posts", sa.Column("detail_text", sa.Text(), nullable=True))
    op.add_column("posts", sa.Column("link_url", sa.Text(), nullable=True))
    op.add_column("posts", sa.Column("link_label", sa.String(length=100), nullable=True))
    op.add_column(
        "posts",
        sa.Column("is_edited", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE posts SET is_edited = TRUE WHERE post_type <> 'INSTAGRAM'")
    op.add_column("audience_groups", sa.Column("google_groups", sa.JSON(), nullable=True))
    op.add_column("admin_audit_logs", sa.Column("target_key", sa.String(length=255), nullable=True))
    op.create_index("ix_admin_audit_logs_target_key", "admin_audit_logs", ["target_key"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_logs_target_key", table_name="admin_audit_logs")
    op.drop_column("admin_audit_logs", "target_key")
    op.drop_column("audience_groups", "google_groups")
    op.drop_column("posts", "is_edited")
    op.drop_column("posts", "link_label")
    op.drop_column("posts", "link_url")
    op.drop_column("posts", "detail_text")
    op.drop_column("posts", "event_notify_groups")
    op.drop_column("posts", "notify_groups")
    op.drop_column("posts", "reminders")
    op.drop_column("posts", "published_at")
