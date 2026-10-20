"""Unit tests validating Alembic migrations and database schema without mocks."""

import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.fixture
def alembic_sqlite_env():
    """Sets up a temporary SQLite database and Alembic configuration."""
    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = backend_dir / "alembic.ini"
    alembic_dir = backend_dir / "alembic"

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = tmp_db.name

    db_url = f"sqlite:///{db_path}"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(alembic_dir))
    cfg.set_main_option("sqlalchemy.url", db_url)

    engine = create_engine(db_url)

    yield cfg, engine, db_path

    engine.dispose()
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_alembic_upgrade_head_creates_expected_tables(alembic_sqlite_env):
    """Validates that running Alembic upgrade head creates 'users' and 'news' tables."""
    cfg, engine, _ = alembic_sqlite_env

    # Run migration up to head
    command.upgrade(cfg, "head")

    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    assert "users" in table_names
    assert "news" in table_names
    assert "alembic_version" in table_names


def test_users_table_column_definitions(alembic_sqlite_env):
    """Validates schema and column types of the 'users' table."""
    cfg, engine, _ = alembic_sqlite_env
    command.upgrade(cfg, "head")

    inspector = inspect(engine)
    columns = {col["name"]: col for col in inspector.get_columns("users")}

    expected_columns = {
        "id",
        "email",
        "full_name",
        "role",
        "career",
        "semester",
        "profile_picture_url",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert expected_columns.issubset(set(columns.keys()))

    assert columns["id"]["primary_key"] >= 1
    assert columns["email"]["nullable"] is False
    assert columns["full_name"]["nullable"] is False


def test_news_table_column_and_foreign_key_relationship(alembic_sqlite_env):
    """Validates schema of 'news' table and foreign key linkage to 'users.id'."""
    cfg, engine, _ = alembic_sqlite_env
    command.upgrade(cfg, "head")

    inspector = inspect(engine)
    columns = {col["name"]: col for col in inspector.get_columns("news")}

    expected_columns = {
        "id",
        "title",
        "content",
        "summary",
        "category",
        "image_url",
        "is_urgent",
        "visible_until",
        "target_audience",
        "author_id",
        "is_published",
        "created_at",
        "updated_at",
    }
    assert expected_columns.issubset(set(columns.keys()))

    assert columns["id"]["primary_key"] >= 1
    assert columns["title"]["nullable"] is False
    assert columns["content"]["nullable"] is False
    assert columns["author_id"]["nullable"] is False

    # Foreign key relationship verification
    foreign_keys = inspector.get_foreign_keys("news")
    assert len(foreign_keys) >= 1

    fk = next((f for f in foreign_keys if "author_id" in f["constrained_columns"]), None)
    assert fk is not None
    assert fk["referred_table"] == "users"
    assert fk["referred_columns"] == ["id"]


def test_alembic_migration_reversibility_and_downgrade(alembic_sqlite_env):
    """Validates full lifecycle: upgrade -> downgrade -> re-upgrade."""
    cfg, engine, _ = alembic_sqlite_env

    # 1. Upgrade
    command.upgrade(cfg, "head")
    inspector = inspect(engine)
    assert "users" in inspector.get_table_names()
    assert "news" in inspector.get_table_names()

    # 2. Downgrade to base
    command.downgrade(cfg, "base")
    inspector = inspect(engine)
    remaining_tables = set(inspector.get_table_names())
    assert "users" not in remaining_tables
    assert "news" not in remaining_tables

    # 3. Re-upgrade to head
    command.upgrade(cfg, "head")
    inspector = inspect(engine)
    assert "users" in inspector.get_table_names()
    assert "news" in inspector.get_table_names()
