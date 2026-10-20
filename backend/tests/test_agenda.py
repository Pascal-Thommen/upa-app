"""Tests for backend agenda and calendar endpoint.

Validates /api/v1/agenda:
1. Status code and baseline JSON response structure.
2. Full event serialization: ensures event_start, event_end, location, has_registration are returned.
3. Filtering: ensures only posts with is_event = True appear in agenda.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from src.database import Base, get_db
from src.main import app
from src.models import Post, User


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

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


@pytest.fixture
def client(test_db: Session):
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_agenda_status_code(client: TestClient):
    response = client.get("/api/v1/agenda")
    assert response.status_code == 200


def test_agenda_response_structure(client: TestClient):
    response = client.get("/api/v1/agenda")
    data = response.json()
    assert "events" in data
    assert isinstance(data["events"], list)
    assert "deadlines" in data
    assert isinstance(data["deadlines"], list)


def test_agenda_event_attributes_serialization(client: TestClient, test_db: Session):
    """Verify that events in agenda contain all event attributes: event_start, event_end, location, has_registration."""
    author = User(email="coordinacion@upa.edu.py", full_name="Coordinación UPA", role="admin")
    test_db.add(author)
    test_db.flush()

    start_dt = datetime(2026, 10, 14, 11, 0, 0, tzinfo=UTC)
    end_dt = datetime(2026, 10, 14, 12, 30, 0, tzinfo=UTC)

    event_post = Post(
        title="¿Qué significa seguir siendo humanos en la era de la IA?",
        caption="Charla Magistral Dr. Daniel Romero",
        content="Detalles de la conferencia sobre IA y ética.",
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        event_start=start_dt,
        event_end=end_dt,
        location="Auditorio Edificio 1, Piso 1",
        has_registration=True,
        reminder_minutes_before=30,
        author_id=author.id,
    )
    non_event_post = Post(
        title="Aviso de Biblioteca",
        caption="Devolución de libros",
        post_type="MANUAL",
        is_news=True,
        is_event=False,
        author_id=author.id,
    )
    test_db.add_all([event_post, non_event_post])
    test_db.commit()

    response = client.get("/api/v1/agenda")
    assert response.status_code == 200
    data = response.json()

    # Only the event post is in events
    events = data["events"]
    assert len(events) == 1
    ev = events[0]

    assert ev["title"] == "¿Qué significa seguir siendo humanos en la era de la IA?"
    assert ev["location"] == "Auditorio Edificio 1, Piso 1"
    assert ev["has_registration"] is True
    assert ev["reminder_minutes_before"] == 30
    assert "2026-10-14T11:00:00" in ev["event_start"]
    assert "2026-10-14T12:30:00" in ev["event_end"]
