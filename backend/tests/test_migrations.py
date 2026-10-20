"""Unit tests for Alembic database migrations.

Validates upgrade head and downgrade base schema lifecycles without mocks.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_migrations_lifecycle(tmp_path: Path):
    """Verifies that Alembic successfully executes upgrade head and downgrade base."""
    db_file = tmp_path / "migration_test.db"
    db_url = f"sqlite:///{db_file}"

    backend_dir = Path(__file__).resolve().parent.parent
    alembic_ini = backend_dir / "alembic.ini"

    alembic_cfg = Config(str(alembic_ini))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # 1. Run upgrade head
    command.upgrade(alembic_cfg, "head")

    # 2. Inspect created database schema
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    assert "users" in tables
    assert "posts" in tables
    assert "event_registrations" in tables
    assert "post_views" in tables
    assert "admin_audit_logs" in tables

    # Verify columns in posts table
    columns = {col["name"]: col for col in inspector.get_columns("posts")}
    assert "id" in columns
    assert "title" in columns
    assert "is_news" in columns
    assert "target_groups" in columns
    assert "instagram_id" in columns
    assert "media_url" in columns

    engine.dispose()

    # 3. Run downgrade base
    command.downgrade(alembic_cfg, "base")

    engine2 = create_engine(db_url)
    inspector2 = inspect(engine2)
    remaining_tables = set(inspector2.get_table_names()) - {"alembic_version"}
    assert len(remaining_tables) == 0
    engine2.dispose()
