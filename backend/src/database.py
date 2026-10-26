from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

# Engine configuration
# pool_pre_ping ensures connections are healthy before executing queries
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency for yielding database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema_upgrades(bind_engine=None) -> None:
    """
    Ergaenzt idempotent Spalten, die create_all() bei bestehenden Tabellen nicht nachzieht.
    Aktuell: posts.category (Redaktionskategorie, siehe Alembic 004).
    """
    from sqlalchemy import inspect, text

    target = bind_engine or engine
    inspector = inspect(target)
    if "posts" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("posts")}
    if "category" not in columns:
        with target.begin() as conn:
            conn.execute(text("ALTER TABLE posts ADD COLUMN category VARCHAR(50)"))
