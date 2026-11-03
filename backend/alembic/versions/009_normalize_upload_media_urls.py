"""Normalizacion de URLs de archivos locales subidos (/uploads/...) en posts y auditoria

Revision ID: 009_normalize_upload_media_urls
Revises: 008_consolidate_schema_and_drop_legacy_columns
Create Date: 2026-11-03 01:00:00.000000

"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_normalize_upload_media_urls"
down_revision: str | None = "008_consolidate_schema_and_drop_legacy_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LINE_UPLOAD_RE = re.compile(r"^https?://[^/\s]+/uploads/", re.IGNORECASE)
_ANY_UPLOAD_RE = re.compile(r"https?://[^/\s\"']+/uploads/", re.IGNORECASE)


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _normalize_multiline_media_url(raw_val: str) -> str:
    lines = raw_val.split("\n")
    normalized_lines = [_LINE_UPLOAD_RE.sub("/uploads/", line.strip()) if line.strip() else "" for line in lines]
    return "\n".join(normalized_lines)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = (bind.dialect.name if bind is not None else "").lower()

    if _table_exists("posts") and _column_exists("posts", "media_url"):
        if dialect == "postgresql":
            bind.execute(
                sa.text(
                    "UPDATE posts "
                    "SET media_url = regexp_replace(media_url, '^https?://[^/]+/uploads/', '/uploads/') "
                    "WHERE media_url ~ '^https?://[^/]+/uploads/'"
                )
            )
            bind.execute(
                sa.text(
                    "UPDATE posts "
                    "SET media_url = regexp_replace(media_url, '(^|\\n)https?://[^/\\s]+/uploads/', '\\1/uploads/', 'g') "
                    "WHERE media_url ~ '(^|\\n)https?://[^/\\s]+/uploads/'"
                )
            )

        rows = bind.execute(
            sa.text("SELECT id, media_url FROM posts WHERE media_url IS NOT NULL AND media_url LIKE '%/uploads/%'")
        ).fetchall()
        for post_id, raw_media in rows:
            if not isinstance(raw_media, str):
                continue
            cleaned = _normalize_multiline_media_url(raw_media)
            if cleaned != raw_media:
                bind.execute(
                    sa.text("UPDATE posts SET media_url = :val WHERE id = :pid"),
                    {"val": cleaned, "pid": post_id},
                )

    if _table_exists("posts") and _column_exists("posts", "image_url"):
        if dialect == "postgresql":
            bind.execute(
                sa.text(
                    "UPDATE posts "
                    "SET image_url = regexp_replace(image_url, '^https?://[^/]+/uploads/', '/uploads/') "
                    "WHERE image_url ~ '^https?://[^/]+/uploads/'"
                )
            )
        img_rows = bind.execute(
            sa.text("SELECT id, image_url FROM posts WHERE image_url IS NOT NULL AND image_url LIKE '%/uploads/%'")
        ).fetchall()
        for post_id, raw_img in img_rows:
            if not isinstance(raw_img, str):
                continue
            cleaned_img = _LINE_UPLOAD_RE.sub("/uploads/", raw_img.strip())
            if cleaned_img != raw_img:
                bind.execute(
                    sa.text("UPDATE posts SET image_url = :val WHERE id = :pid"),
                    {"val": cleaned_img, "pid": post_id},
                )

    if _table_exists("admin_audit_logs") and _column_exists("admin_audit_logs", "details"):
        if dialect == "postgresql":
            bind.execute(
                sa.text(
                    "UPDATE admin_audit_logs "
                    "SET details = regexp_replace(details::text, 'https?://[^/\"\\s]+/uploads/', '/uploads/', 'g')::json "
                    "WHERE details::text ~ 'https?://[^/\"\\s]+/uploads/'"
                )
            )
        else:
            audit_rows = bind.execute(
                sa.text(
                    "SELECT id, details FROM admin_audit_logs "
                    "WHERE details IS NOT NULL AND CAST(details AS TEXT) LIKE '%/uploads/%'"
                )
            ).fetchall()
            for log_id, raw_details in audit_rows:
                if isinstance(raw_details, str):
                    updated_str = _ANY_UPLOAD_RE.sub("/uploads/", raw_details)
                    if updated_str != raw_details:
                        bind.execute(
                            sa.text("UPDATE admin_audit_logs SET details = :det WHERE id = :lid"),
                            {"det": updated_str, "lid": log_id},
                        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists("posts") and _column_exists("posts", "media_url"):
        bind.execute(sa.text("SELECT COUNT(1) FROM posts"))
