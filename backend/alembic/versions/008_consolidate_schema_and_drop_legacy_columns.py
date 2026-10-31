"""Consolidacion de esquema, migracion de datos y eliminacion de columnas obsoletas

Revision ID: 008_consolidate_schema_and_drop_legacy_columns
Revises: 007_add_ai_generated_flag
Create Date: 2026-10-30 23:45:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008_consolidate_schema_and_drop_legacy_columns"
down_revision: str | None = "007_add_ai_generated_flag"
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


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Asegurar columnas de cache de Classroom y Google Groups en users
    if _table_exists("users"):
        if not _column_exists("users", "google_groups"):
            op.add_column("users", sa.Column("google_groups", sa.JSON(), server_default="[]", nullable=False))
        if not _column_exists("users", "classroom_deadlines_cache"):
            op.add_column(
                "users",
                sa.Column("classroom_deadlines_cache", sa.JSON(), server_default="[]", nullable=False),
            )
        if not _column_exists("users", "classroom_synced_at"):
            op.add_column("users", sa.Column("classroom_synced_at", sa.DateTime(timezone=True), nullable=True))

    # 2. Migracion de datos previa a la eliminacion de columnas heredadas (Zero Data Loss)
    if _table_exists("users") and _table_exists("device_tokens") and _column_exists("users", "device_token"):
        rows = bind.execute(
            sa.text("SELECT id, device_token FROM users WHERE device_token IS NOT NULL AND device_token <> ''")
        ).fetchall()
        for uid, tok in rows:
            cleaned = str(tok).strip()
            if not cleaned:
                continue
            exists = bind.execute(
                sa.text("SELECT 1 FROM device_tokens WHERE user_id = :uid AND device_token = :tok"),
                {"uid": uid, "tok": cleaned},
            ).first()
            if not exists:
                bind.execute(
                    sa.text(
                        "INSERT INTO device_tokens (user_id, device_token, platform) VALUES (:uid, :tok, 'android')"
                    ),
                    {"uid": uid, "tok": cleaned},
                )

    if (
        _table_exists("posts")
        and _column_exists("posts", "reminder_minutes_before")
        and _column_exists("posts", "reminders")
    ):
        rows = bind.execute(
            sa.text(
                "SELECT id, reminder_minutes_before FROM posts "
                "WHERE is_event = TRUE AND reminders IS NULL AND reminder_minutes_before IS NOT NULL"
            )
        ).fetchall()
        for pid, mins in rows:
            bind.execute(
                sa.text("UPDATE posts SET reminders = :rem WHERE id = :pid"),
                {"rem": json.dumps([int(mins)]), "pid": pid},
            )

    if (
        _table_exists("audience_groups")
        and _column_exists("audience_groups", "google_group")
        and _column_exists("audience_groups", "google_groups")
    ):
        rows = bind.execute(
            sa.text(
                "SELECT id, google_group, google_groups FROM audience_groups "
                "WHERE google_group IS NOT NULL AND google_group <> ''"
            )
        ).fetchall()
        for gid, single_gg, list_gg in rows:
            has_list = False
            if isinstance(list_gg, list) and len(list_gg) > 0:
                has_list = True
            elif isinstance(list_gg, str) and list_gg.strip() not in ("", "[]", "null"):
                has_list = True
            if not has_list:
                bind.execute(
                    sa.text("UPDATE audience_groups SET google_groups = :gg WHERE id = :gid"),
                    {"gg": json.dumps([str(single_gg).strip()]), "gid": gid},
                )

    if _table_exists("admin_audit_logs") and _column_exists("admin_audit_logs", "target_type"):
        bind.execute(sa.text("UPDATE admin_audit_logs SET target_type = 'post' WHERE target_type = 'event'"))

    # 3. Eliminacion de columnas obsoletas (compatible con SQLite y PostgreSQL via batch_alter_table)
    if _table_exists("users") and _column_exists("users", "device_token"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("device_token")

    if _table_exists("posts"):
        cols_to_drop = [
            c
            for c in ("reminder_minutes_before", "push_notification_sent_at", "detail_text")
            if _column_exists("posts", c)
        ]
        if cols_to_drop:
            with op.batch_alter_table("posts") as batch_op:
                for col in cols_to_drop:
                    batch_op.drop_column(col)

    if _table_exists("audience_groups"):
        cols_to_drop = [
            c for c in ("google_group", "is_system", "badge_class") if _column_exists("audience_groups", c)
        ]
        if cols_to_drop:
            with op.batch_alter_table("audience_groups") as batch_op:
                for col in cols_to_drop:
                    batch_op.drop_column(col)

    if _table_exists("user_roles") and _column_exists("user_roles", "role"):
        with op.batch_alter_table("user_roles") as batch_op:
            batch_op.drop_column("role")


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists("user_roles") and not _column_exists("user_roles", "role"):
        with op.batch_alter_table("user_roles") as batch_op:
            batch_op.add_column(sa.Column("role", sa.String(length=50), server_default="editor", nullable=False))
        rows = bind.execute(sa.text("SELECT id, permissions FROM user_roles")).fetchall()
        for rid, raw_perms in rows:
            perms_list = []
            if isinstance(raw_perms, list):
                perms_list = [str(p).lower() for p in raw_perms]
            elif isinstance(raw_perms, str):
                try:
                    parsed = json.loads(raw_perms)
                    if isinstance(parsed, list):
                        perms_list = [str(p).lower() for p in parsed]
                except ValueError:
                    pass
            derived = "admin" if "roles" in perms_list else "editor"
            bind.execute(
                sa.text("UPDATE user_roles SET role = :r WHERE id = :rid"),
                {"r": derived, "rid": rid},
            )

    if _table_exists("audience_groups"):
        with op.batch_alter_table("audience_groups") as batch_op:
            if not _column_exists("audience_groups", "badge_class"):
                batch_op.add_column(
                    sa.Column(
                        "badge_class",
                        sa.String(length=100),
                        server_default="bg-slate-100 text-slate-800 border-slate-200",
                        nullable=False,
                    )
                )
            if not _column_exists("audience_groups", "is_system"):
                batch_op.add_column(sa.Column("is_system", sa.Boolean(), server_default=sa.false(), nullable=False))
            if not _column_exists("audience_groups", "google_group"):
                batch_op.add_column(sa.Column("google_group", sa.String(length=255), nullable=True))

    if _table_exists("posts"):
        with op.batch_alter_table("posts") as batch_op:
            if not _column_exists("posts", "detail_text"):
                batch_op.add_column(sa.Column("detail_text", sa.Text(), nullable=True))
            if not _column_exists("posts", "push_notification_sent_at"):
                batch_op.add_column(sa.Column("push_notification_sent_at", sa.DateTime(timezone=True), nullable=True))
            if not _column_exists("posts", "reminder_minutes_before"):
                batch_op.add_column(
                    sa.Column("reminder_minutes_before", sa.Integer(), server_default="30", nullable=True)
                )

    if _table_exists("users") and not _column_exists("users", "device_token"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("device_token", sa.String(length=512), nullable=True))
        if _column_exists("users", "classroom_synced_at"):
            with op.batch_alter_table("users") as batch_op:
                batch_op.drop_column("classroom_synced_at")
        if _column_exists("users", "classroom_deadlines_cache"):
            with op.batch_alter_table("users") as batch_op:
                batch_op.drop_column("classroom_deadlines_cache")
