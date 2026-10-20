"""Unit tests for SQLAlchemy User and News models without mocks.

Strictly adheres to Zero Mock Doktrin and software-testing-audit requirements.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from src.database import Base
from src.models import News, User


@pytest.fixture
def db_session():
    """Provides an isolated in-memory transactional database session with SQLite foreign keys enabled."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    # Enable SQLite foreign key enforcement
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session: Session = session_factory()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_user_creation_and_attributes(db_session: Session):
    """Validates user creation with all defined campus profile fields."""
    user = User(
        email="estudiante.prueba@upa.edu.py",
        full_name="Maria Belen Gomez",
        role="student",
        career="Wirtschaftsinformatik",
        semester=6,
        profile_picture_url="https://upa.edu.py/img/mbg.jpg",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.id is not None
    assert user.email == "estudiante.prueba@upa.edu.py"
    assert user.full_name == "Maria Belen Gomez"
    assert user.role == "student"
    assert user.career == "Wirtschaftsinformatik"
    assert user.semester == 6
    assert user.profile_picture_url == "https://upa.edu.py/img/mbg.jpg"
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None

    user_dict = user.to_dict()
    assert user_dict["email"] == "estudiante.prueba@upa.edu.py"
    assert user_dict["career"] == "Wirtschaftsinformatik"
    assert "id" in user_dict


def test_user_email_uniqueness_enforced(db_session: Session):
    """Ensures database-level unique constraint prevents duplicate emails."""
    user1 = User(
        email="duplicado@upa.edu.py",
        full_name="Primer Usuario",
        role="student",
    )
    db_session.add(user1)
    db_session.commit()

    user2 = User(
        email="duplicado@upa.edu.py",
        full_name="Segundo Usuario",
        role="docente",
    )
    db_session.add(user2)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_news_creation_and_author_relationship(db_session: Session):
    """Validates news post creation and bidirectional foreign key relationship to author."""
    author = User(
        email="marketing@upa.edu.py",
        full_name="Equipo Marketing UPA",
        role="admin",
        career="Marketing",
    )
    db_session.add(author)
    db_session.commit()
    db_session.refresh(author)

    news_item = News(
        title="Torneo Interfacultades 2026",
        content="Convocatoria general para todas las carreras en el campus central.",
        summary="Apertura de inscripciones para el torneo deportivo.",
        category="event",
        image_url="https://upa.edu.py/media/torneo.png",
        is_urgent=False,
        visible_until=datetime(2026, 11, 1, 18, 0, tzinfo=UTC),
        target_audience="all",
        author_id=author.id,
        is_published=True,
    )
    db_session.add(news_item)
    db_session.commit()
    db_session.refresh(news_item)

    assert news_item.id is not None
    assert news_item.author_id == author.id
    assert news_item.author.email == "marketing@upa.edu.py"
    assert len(author.news) == 1
    assert author.news[0].title == "Torneo Interfacultades 2026"

    news_dict = news_item.to_dict()
    assert news_dict["title"] == "Torneo Interfacultades 2026"
    assert news_dict["author_id"] == author.id
    assert news_dict["category"] == "event"


def test_foreign_key_violation_raises_integrity_error(db_session: Session):
    """Validates that creating a news post with a non-existent author_id fails immediately."""
    invalid_news = News(
        title="Noticia Huerfana",
        content="Contenido sin autor registrado.",
        author_id=999999,  # Non-existent user
    )
    db_session.add(invalid_news)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_author_cascade_delete(db_session: Session):
    """Validates that deleting an author cascades and deletes associated news entries."""
    author = User(
        email="temporal@upa.edu.py",
        full_name="Profesor Visitante",
        role="professor",
    )
    db_session.add(author)
    db_session.commit()
    db_session.refresh(author)

    news1 = News(
        title="Charla Magistral de IA",
        content="Conferencia en el Aula Magna.",
        author_id=author.id,
    )
    news2 = News(
        title="Material Complementario",
        content="Diapositivas y referencias bibliograficas.",
        author_id=author.id,
    )
    db_session.add_all([news1, news2])
    db_session.commit()

    news1_id = news1.id
    news2_id = news2.id

    # Delete author and verify cascade
    db_session.delete(author)
    db_session.commit()

    deleted_news1 = db_session.get(News, news1_id)
    deleted_news2 = db_session.get(News, news2_id)
    assert deleted_news1 is None
    assert deleted_news2 is None
