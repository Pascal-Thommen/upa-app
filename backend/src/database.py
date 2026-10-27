from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columnas adicionales que create_all() no agrega en tablas ya creadas: (tabla, columna, tipo SQL).
# Expresiones compatibles tanto con SQLite como con PostgreSQL (ver migraciones Alembic 004 y 005).
_COLUMN_UPGRADES: tuple[tuple[str, str, str], ...] = (
    ("posts", "category", "VARCHAR(50)"),
    ("posts", "published_at", "TIMESTAMP"),
    ("posts", "reminders", "JSON"),
    ("posts", "notify_groups", "JSON"),
    ("posts", "event_notify_groups", "JSON"),
    ("posts", "detail_text", "TEXT"),
    ("posts", "link_url", "TEXT"),
    ("posts", "link_label", "VARCHAR(100)"),
    ("posts", "is_edited", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("audience_groups", "google_groups", "JSON"),
    ("audience_groups", "parent_id", "VARCHAR(50)"),
    ("admin_audit_logs", "target_key", "VARCHAR(255)"),
)


def ensure_schema_upgrades(bind_engine=None) -> None:
    """
    Agrega de forma idempotente las columnas nuevas en bases de datos preexistentes.
    Las publicaciones editoriales existentes (distintas de Instagram) quedan marcadas como revisadas.
    """
    from sqlalchemy import inspect, text

    target = bind_engine or engine
    inspector = inspect(target)
    existing_tables = set(inspector.get_table_names())

    for table, column, ddl_type in _COLUMN_UPGRADES:
        if table not in existing_tables:
            continue
        columns = {col["name"] for col in inspector.get_columns(table)}
        if column in columns:
            continue
        with target.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
            if table == "posts" and column == "is_edited" and "post_type" in columns:
                conn.execute(text("UPDATE posts SET is_edited = TRUE WHERE post_type <> 'INSTAGRAM'"))
