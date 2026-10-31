from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
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


def get_alembic_config(database_url: str | None = None) -> Config:
    """Construye la configuracion de Alembic apuntando a backend/alembic."""
    backend_dir = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    if database_url:
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    else:
        alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return alembic_cfg


def run_alembic_migrations(bind_engine=None) -> None:
    """
    Ejecuta las migraciones formales de Alembic hasta head sobre el motor indicado.
    Corrige revisiones heredadas en bases de datos preexistentes para garantizar idempotencia.
    """
    target = bind_engine or engine
    inspector = inspect(target)
    tables = set(inspector.get_table_names())
    if "alembic_version" in tables:
        with target.begin() as conn:
            if target.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"))
            conn.execute(
                text(
                    "UPDATE alembic_version SET version_num = '007_add_ai_generated_flag' WHERE version_num = '007'"
                )
            )
    elif target.dialect.name == "postgresql":
        with target.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version ("
                    "version_num VARCHAR(128) NOT NULL, "
                    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                )
            )

    cfg = get_alembic_config(str(target.url))
    with target.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
