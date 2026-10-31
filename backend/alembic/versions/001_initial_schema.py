"""Initial schema with users, posts, registrations, views, audit logs

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-20 13:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table_name not in insp.get_table_names():
        return False
    return any(idx["name"] == index_name for idx in insp.get_indexes(table_name))


def upgrade() -> None:
    # Ampliar version_num en PostgreSQL para permitir identificadores descriptivos de mas de 32 caracteres
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(128) NOT NULL)"))
        op.execute(sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"))

    # 1. users
    if not _table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=50), server_default="user", nullable=False),
            sa.Column("groups", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("users", op.f("ix_users_email")):
        op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    if not _index_exists("users", op.f("ix_users_id")):
        op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)

    # 2. posts
    if not _table_exists("posts"):
        op.create_table(
            "posts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("caption", sa.Text(), nullable=True),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("post_type", sa.String(length=50), server_default="MANUAL", nullable=False),
            sa.Column("is_news", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("is_event", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("is_pinned", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("event_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("event_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("location", sa.String(length=255), nullable=True),
            sa.Column("target_groups", sa.JSON(), nullable=False),
            sa.Column("has_registration", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("send_push_notification", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("push_notification_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reminder_minutes_before", sa.Integer(), server_default="30", nullable=True),
            sa.Column("instagram_id", sa.String(length=100), nullable=True),
            sa.Column("media_type", sa.String(length=50), nullable=True),
            sa.Column("media_url", sa.Text(), nullable=True),
            sa.Column("permalink", sa.Text(), nullable=True),
            sa.Column("author_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["author_id"],
                ["users.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("posts", op.f("ix_posts_id")):
        op.create_index(op.f("ix_posts_id"), "posts", ["id"], unique=False)
    if not _index_exists("posts", op.f("ix_posts_instagram_id")):
        op.create_index(op.f("ix_posts_instagram_id"), "posts", ["instagram_id"], unique=True)

    # 3. event_registrations
    if not _table_exists("event_registrations"):
        op.create_table(
            "event_registrations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("post_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=50), server_default="attending", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("post_id", "user_id", name="uq_post_user_registration"),
        )
    if not _index_exists("event_registrations", op.f("ix_event_registrations_id")):
        op.create_index(op.f("ix_event_registrations_id"), "event_registrations", ["id"], unique=False)
    if not _index_exists("event_registrations", op.f("ix_event_registrations_post_id")):
        op.create_index(op.f("ix_event_registrations_post_id"), "event_registrations", ["post_id"], unique=False)
    if not _index_exists("event_registrations", op.f("ix_event_registrations_user_id")):
        op.create_index(op.f("ix_event_registrations_user_id"), "event_registrations", ["user_id"], unique=False)

    # 4. post_views
    if not _table_exists("post_views"):
        op.create_table(
            "post_views",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("post_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("viewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("post_id", "user_id", name="uq_post_user_view"),
        )
    if not _index_exists("post_views", op.f("ix_post_views_id")):
        op.create_index(op.f("ix_post_views_id"), "post_views", ["id"], unique=False)
    if not _index_exists("post_views", op.f("ix_post_views_post_id")):
        op.create_index(op.f("ix_post_views_post_id"), "post_views", ["post_id"], unique=False)
    if not _index_exists("post_views", op.f("ix_post_views_user_id")):
        op.create_index(op.f("ix_post_views_user_id"), "post_views", ["user_id"], unique=False)

    # 5. admin_audit_logs
    if not _table_exists("admin_audit_logs"):
        op.create_table(
            "admin_audit_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("admin_id", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(length=100), nullable=False),
            sa.Column("target_type", sa.String(length=50), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=True),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(
                ["admin_id"],
                ["users.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("admin_audit_logs", op.f("ix_admin_audit_logs_admin_id")):
        op.create_index(op.f("ix_admin_audit_logs_admin_id"), "admin_audit_logs", ["admin_id"], unique=False)
    if not _index_exists("admin_audit_logs", op.f("ix_admin_audit_logs_id")):
        op.create_index(op.f("ix_admin_audit_logs_id"), "admin_audit_logs", ["id"], unique=False)


def downgrade() -> None:
    if _table_exists("admin_audit_logs"):
        if _index_exists("admin_audit_logs", op.f("ix_admin_audit_logs_id")):
            op.drop_index(op.f("ix_admin_audit_logs_id"), table_name="admin_audit_logs")
        if _index_exists("admin_audit_logs", op.f("ix_admin_audit_logs_admin_id")):
            op.drop_index(op.f("ix_admin_audit_logs_admin_id"), table_name="admin_audit_logs")
        op.drop_table("admin_audit_logs")
    if _table_exists("post_views"):
        if _index_exists("post_views", op.f("ix_post_views_user_id")):
            op.drop_index(op.f("ix_post_views_user_id"), table_name="post_views")
        if _index_exists("post_views", op.f("ix_post_views_post_id")):
            op.drop_index(op.f("ix_post_views_post_id"), table_name="post_views")
        if _index_exists("post_views", op.f("ix_post_views_id")):
            op.drop_index(op.f("ix_post_views_id"), table_name="post_views")
        op.drop_table("post_views")
    if _table_exists("event_registrations"):
        if _index_exists("event_registrations", op.f("ix_event_registrations_user_id")):
            op.drop_index(op.f("ix_event_registrations_user_id"), table_name="event_registrations")
        if _index_exists("event_registrations", op.f("ix_event_registrations_post_id")):
            op.drop_index(op.f("ix_event_registrations_post_id"), table_name="event_registrations")
        if _index_exists("event_registrations", op.f("ix_event_registrations_id")):
            op.drop_index(op.f("ix_event_registrations_id"), table_name="event_registrations")
        op.drop_table("event_registrations")
    if _table_exists("posts"):
        if _index_exists("posts", op.f("ix_posts_instagram_id")):
            op.drop_index(op.f("ix_posts_instagram_id"), table_name="posts")
        if _index_exists("posts", op.f("ix_posts_id")):
            op.drop_index(op.f("ix_posts_id"), table_name="posts")
        op.drop_table("posts")
    if _table_exists("users"):
        if _index_exists("users", op.f("ix_users_id")):
            op.drop_index(op.f("ix_users_id"), table_name="users")
        if _index_exists("users", op.f("ix_users_email")):
            op.drop_index(op.f("ix_users_email"), table_name="users")
        op.drop_table("users")
