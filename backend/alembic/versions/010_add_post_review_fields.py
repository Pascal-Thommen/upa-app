"""Campos de revision editorial (reviewed_by_id y reviewed_at) en posts

Revision ID: 010_add_post_review_fields
Revises: 009_normalize_upload_media_urls
Create Date: 2026-11-04 20:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "010_add_post_review_fields"
down_revision: str | None = "009_normalize_upload_media_urls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists("posts"):
        return

    with op.batch_alter_table("posts") as batch_op:
        if not _column_exists("posts", "reviewed_by_id"):
            batch_op.add_column(sa.Column("reviewed_by_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_posts_reviewed_by_id_users",
                "users",
                ["reviewed_by_id"],
                ["id"],
            )
        if not _column_exists("posts", "reviewed_at"):
            batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))

    if not _index_exists("posts", "ix_posts_reviewed_by_id"):
        op.create_index("ix_posts_reviewed_by_id", "posts", ["reviewed_by_id"], unique=False)

    if _column_exists("posts", "is_edited") and _column_exists("posts", "author_id"):
        bind.execute(
            sa.text(
                "UPDATE posts "
                "SET reviewed_by_id = author_id, reviewed_at = COALESCE(updated_at, created_at) "
                "WHERE is_edited = TRUE AND reviewed_by_id IS NULL AND author_id IS NOT NULL"
            )
        )


def downgrade() -> None:
    if not _table_exists("posts"):
        return

    if _index_exists("posts", "ix_posts_reviewed_by_id"):
        op.drop_index("ix_posts_reviewed_by_id", table_name="posts")

    cols_to_drop = [c for c in ("reviewed_at", "reviewed_by_id") if _column_exists("posts", c)]
    if cols_to_drop:
        with op.batch_alter_table("posts") as batch_op:
            for col in cols_to_drop:
                batch_op.drop_column(col)
