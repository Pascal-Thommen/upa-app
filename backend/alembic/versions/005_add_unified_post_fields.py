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
    if not _table_exists("audience_groups"):
        op.create_table(
            "audience_groups",
            sa.Column("id", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "badge_class",
                sa.String(length=100),
                server_default="bg-slate-100 text-slate-800 border-slate-200",
                nullable=False,
            ),
            sa.Column("google_group", sa.String(length=255), nullable=True),
            sa.Column("google_groups", sa.JSON(), nullable=True),
            sa.Column("emails", sa.JSON(), nullable=False),
            sa.Column("is_system", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    elif not _column_exists("audience_groups", "google_groups"):
        op.add_column("audience_groups", sa.Column("google_groups", sa.JSON(), nullable=True))

    if not _table_exists("user_roles"):
        op.create_table(
            "user_roles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=50), server_default="editor", nullable=False),
            sa.Column("permissions", sa.JSON(), nullable=False),
            sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_user_roles_id"), "user_roles", ["id"], unique=False)
        op.create_index(op.f("ix_user_roles_email"), "user_roles", ["email"], unique=True)

    if not _column_exists("users", "google_groups"):
        op.add_column("users", sa.Column("google_groups", sa.JSON(), server_default="[]", nullable=False))

    for col_name, col_def in (
        ("published_at", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)),
        ("reminders", sa.Column("reminders", sa.JSON(), nullable=True)),
        ("notify_groups", sa.Column("notify_groups", sa.JSON(), nullable=True)),
        ("event_notify_groups", sa.Column("event_notify_groups", sa.JSON(), nullable=True)),
        ("detail_text", sa.Column("detail_text", sa.Text(), nullable=True)),
        ("link_url", sa.Column("link_url", sa.Text(), nullable=True)),
        ("link_label", sa.Column("link_label", sa.String(length=100), nullable=True)),
        ("is_edited", sa.Column("is_edited", sa.Boolean(), nullable=False, server_default=sa.false())),
    ):
        if not _column_exists("posts", col_name):
            op.add_column("posts", col_def)

    op.execute("UPDATE posts SET is_edited = TRUE WHERE post_type <> 'INSTAGRAM'")

    if not _column_exists("admin_audit_logs", "target_key"):
        op.add_column("admin_audit_logs", sa.Column("target_key", sa.String(length=255), nullable=True))
    if not _index_exists("admin_audit_logs", "ix_admin_audit_logs_target_key"):
        op.create_index("ix_admin_audit_logs_target_key", "admin_audit_logs", ["target_key"])


def downgrade() -> None:
    if _index_exists("admin_audit_logs", "ix_admin_audit_logs_target_key"):
        op.drop_index("ix_admin_audit_logs_target_key", table_name="admin_audit_logs")
    if _column_exists("admin_audit_logs", "target_key"):
        op.drop_column("admin_audit_logs", "target_key")
    if _table_exists("user_roles"):
        if _index_exists("user_roles", "ix_user_roles_email"):
            op.drop_index(op.f("ix_user_roles_email"), table_name="user_roles")
        if _index_exists("user_roles", "ix_user_roles_id"):
            op.drop_index(op.f("ix_user_roles_id"), table_name="user_roles")
        op.drop_table("user_roles")
    if _table_exists("audience_groups"):
        op.drop_table("audience_groups")
    if _column_exists("users", "google_groups"):
        op.drop_column("users", "google_groups")
    for col_name in (
        "is_edited",
        "link_label",
        "link_url",
        "detail_text",
        "event_notify_groups",
        "notify_groups",
        "reminders",
        "published_at",
    ):
        if _column_exists("posts", col_name):
            op.drop_column("posts", col_name)
