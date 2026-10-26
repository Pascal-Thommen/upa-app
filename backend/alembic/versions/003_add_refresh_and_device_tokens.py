"""Add classroom_refresh_token, device_token and device_tokens table

Revision ID: 003_add_refresh_and_device_tokens
Revises: 002_add_classroom_token
Create Date: 2026-10-21 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_add_refresh_and_device_tokens"
down_revision: str | None = "002_add_classroom_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("classroom_refresh_token", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("device_token", sa.String(length=512), nullable=True))

    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_token", sa.String(length=512), nullable=False),
        sa.Column("platform", sa.String(length=50), server_default="android", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "device_token", name="uq_user_device_token"),
    )
    op.create_index(op.f("ix_device_tokens_id"), "device_tokens", ["id"], unique=False)
    op.create_index(op.f("ix_device_tokens_user_id"), "device_tokens", ["user_id"], unique=False)
    op.create_index(op.f("ix_device_tokens_device_token"), "device_tokens", ["device_token"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_device_tokens_device_token"), table_name="device_tokens")
    op.drop_index(op.f("ix_device_tokens_user_id"), table_name="device_tokens")
    op.drop_index(op.f("ix_device_tokens_id"), table_name="device_tokens")
    op.drop_table("device_tokens")
    op.drop_column("users", "device_token")
    op.drop_column("users", "classroom_refresh_token")
