"""Unit and integration tests for GET /api/events endpoint.

Validates chronological sorting, room/location information, registration status,
attendee counting, upcoming-only filtering, and target group filtering without mocks.
Strictly complies with the Zero Mock Doktrin and software-testing-audit requirements.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from src.database import Base, get_db
from src.main import app
from src.models import EventRegistration, Post, User
from src.schemas.event import EventResponse


@pytest.fixture
def test_db():
    """Provides a fresh, isolated in-memory SQLite database for testing."""
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
    """Provides a FastAPI TestClient with the database session overridden."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seed_user(test_db: Session) -> User:
    """Creates a sample university user for authoring and registration."""
    user = User(
        email="test.student@upa.edu.py",
        full_name="Max Mustermann",
        role="student",
        career="TIE",
        semester=4,
        groups=["TIE", "Semester_4"],
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def test_get_events_empty(client: TestClient):
    """GET /api/events should return an empty list when no events are recorded."""
    response = client.get("/api/events")
    assert response.status_code == 200
    assert response.json() == []


def test_get_events_filters_only_events(client: TestClient, test_db: Session, seed_user: User):
    """Ensures that only records with is_event=True are returned by /api/events."""
    now = datetime.now(UTC)

    # Regular news post (not an event)
    news_post = Post(
        title="Wichtige Bibliotheks-Mitteilung",
        caption="Neue Öffnungszeiten",
        is_news=True,
        is_event=False,
        author_id=seed_user.id,
    )
    # Event post
    event_post = Post(
        title="Career Fair 2026",
        caption="Treffe internationale Unternehmen",
        is_news=True,
        is_event=True,
        event_start=now + timedelta(days=5),
        event_end=now + timedelta(days=5, hours=4),
        location="Campus Aula Magna",
        has_registration=True,
        author_id=seed_user.id,
    )
    test_db.add_all([news_post, event_post])
    test_db.commit()

    response = client.get("/api/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Career Fair 2026"
    assert data[0]["is_event"] is True
    assert data[0]["location"] == "Campus Aula Magna"
    assert data[0]["room"] == "Campus Aula Magna"


def test_get_events_chronological_ordering(client: TestClient, test_db: Session, seed_user: User):
    """Validates that events are ordered chronologically by event_start ascending."""
    now = datetime.now(UTC)

    event_in_3_days = Post(
        title="Event in 3 Tagen",
        is_event=True,
        event_start=now + timedelta(days=3),
        location="Raum 101",
        author_id=seed_user.id,
    )
    event_in_1_day = Post(
        title="Event morgen",
        is_event=True,
        event_start=now + timedelta(days=1),
        location="Auditorium",
        author_id=seed_user.id,
    )
    event_in_7_days = Post(
        title="Event nächste Woche",
        is_event=True,
        event_start=now + timedelta(days=7),
        location="Labor 2",
        author_id=seed_user.id,
    )

    test_db.add_all([event_in_3_days, event_in_1_day, event_in_7_days])
    test_db.commit()

    response = client.get("/api/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert data[0]["title"] == "Event morgen"
    assert data[1]["title"] == "Event in 3 Tagen"
    assert data[2]["title"] == "Event nächste Woche"


def test_get_events_upcoming_only_filtering(client: TestClient, test_db: Session, seed_user: User):
    """Verifies that upcoming_only filters out past events while upcoming_only=false returns all."""
    now = datetime.now(UTC)

    past_event = Post(
        title="Vergangenes Event",
        is_event=True,
        event_start=now - timedelta(days=10),
        event_end=now - timedelta(days=10, hours=2),
        location="Altes Auditorium",
        author_id=seed_user.id,
    )
    future_event = Post(
        title="Zukünftiges Event",
        is_event=True,
        event_start=now + timedelta(days=2),
        event_end=now + timedelta(days=2, hours=3),
        location="Neues Labor",
        author_id=seed_user.id,
    )
    test_db.add_all([past_event, future_event])
    test_db.commit()

    # Default upcoming_only=True
    resp_upcoming = client.get("/api/events")
    assert resp_upcoming.status_code == 200
    upcoming_data = resp_upcoming.json()
    assert len(upcoming_data) == 1
    assert upcoming_data[0]["title"] == "Zukünftiges Event"

    # With upcoming_only=false
    resp_all = client.get("/api/events?upcoming_only=false")
    assert resp_all.status_code == 200
    all_data = resp_all.json()
    assert len(all_data) == 2
    assert all_data[0]["title"] == "Vergangenes Event"
    assert all_data[1]["title"] == "Zukünftiges Event"


def test_get_events_registration_status_and_attendees_count(
    client: TestClient, test_db: Session, seed_user: User
):
    """Tests has_registration status and dynamic attendees_count calculation."""
    now = datetime.now(UTC)

    # Second user for registrations
    user_2 = User(
        email="maria.gonzalez@upa.edu.py",
        full_name="María González",
        role="student",
        career="TIE",
        semester=2,
    )
    user_3 = User(
        email="carlos.benitez@upa.edu.py",
        full_name="Carlos Benítez",
        role="student",
        career="IPI",
        semester=6,
    )
    test_db.add_all([user_2, user_3])
    test_db.commit()

    event_with_reg = Post(
        title="KI Workshop mit Daniel Romero",
        content="Interaktiver Workshop zu generativer KI",
        is_event=True,
        event_start=now + timedelta(days=4),
        location="Auditorio Edificio 1, Piso 1",
        has_registration=True,
        author_id=seed_user.id,
    )
    event_without_reg = Post(
        title="Infoveranstaltung Bibliothek",
        content="Offener Rundgang",
        is_event=True,
        event_start=now + timedelta(days=6),
        location="Bibliothek",
        has_registration=False,
        author_id=seed_user.id,
    )
    test_db.add_all([event_with_reg, event_without_reg])
    test_db.commit()

    # Add 2 attending registrations and 1 declined registration
    reg_1 = EventRegistration(post_id=event_with_reg.id, user_id=seed_user.id, status="attending")
    reg_2 = EventRegistration(post_id=event_with_reg.id, user_id=user_2.id, status="attending")
    reg_3 = EventRegistration(post_id=event_with_reg.id, user_id=user_3.id, status="declined")
    test_db.add_all([reg_1, reg_2, reg_3])
    test_db.commit()

    response = client.get("/api/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    ki_event = next(e for e in data if e["title"] == "KI Workshop mit Daniel Romero")
    assert ki_event["has_registration"] is True
    assert ki_event["attendees_count"] == 2
    assert ki_event["location"] == "Auditorio Edificio 1, Piso 1"
    assert ki_event["room"] == "Auditorio Edificio 1, Piso 1"

    bib_event = next(e for e in data if e["title"] == "Infoveranstaltung Bibliothek")
    assert bib_event["has_registration"] is False
    assert bib_event["attendees_count"] == 0


def test_get_events_target_group_filtering(
    client: TestClient, test_db: Session, seed_user: User
):
    """Validates target group filtering (?group=TIE) on event listing."""
    now = datetime.now(UTC)

    event_tie = Post(
        title="TIE Fachschaftstreffen",
        is_event=True,
        event_start=now + timedelta(days=1),
        target_groups=["TIE"],
        location="Raum 204",
        author_id=seed_user.id,
    )
    event_all = Post(
        title="Allgemeines Sommerfest",
        is_event=True,
        event_start=now + timedelta(days=2),
        target_groups=["ALL"],
        location="Campus Garten",
        author_id=seed_user.id,
    )
    event_med = Post(
        title="Medizin Vortrag",
        is_event=True,
        event_start=now + timedelta(days=3),
        target_groups=["MED"],
        location="Hörsaal 3",
        author_id=seed_user.id,
    )
    test_db.add_all([event_tie, event_all, event_med])
    test_db.commit()

    response = client.get("/api/events?group=TIE")
    assert response.status_code == 200
    data = response.json()
    titles = [e["title"] for e in data]
    assert "TIE Fachschaftstreffen" in titles
    assert "Allgemeines Sommerfest" in titles
    assert "Medizin Vortrag" not in titles


def test_get_events_pagination(client: TestClient, test_db: Session, seed_user: User):
    """Tests limit, offset, and page pagination parameters."""
    now = datetime.now(UTC)

    for i in range(1, 11):
        event = Post(
            title=f"Event {i:02d}",
            is_event=True,
            event_start=now + timedelta(days=i),
            location=f"Raum {i}",
            author_id=seed_user.id,
        )
        test_db.add(event)
    test_db.commit()

    # Limit 4, offset 0 -> Events 1 to 4
    resp_1 = client.get("/api/events?limit=4&offset=0")
    assert resp_1.status_code == 200
    data_1 = resp_1.json()
    assert len(data_1) == 4
    assert data_1[0]["title"] == "Event 01"
    assert data_1[3]["title"] == "Event 04"

    # Limit 4, page 2 -> Events 5 to 8
    resp_2 = client.get("/api/events?limit=4&page=2")
    assert resp_2.status_code == 200
    data_2 = resp_2.json()
    assert len(data_2) == 4
    assert data_2[0]["title"] == "Event 05"
    assert data_2[3]["title"] == "Event 08"


def test_get_event_by_id_and_not_found(client: TestClient, test_db: Session, seed_user: User):
    """Tests GET /api/events/{id} for single event retrieval and 404 for missing event."""
    now = datetime.now(UTC)

    event = Post(
        title="Exkursion Itaipu",
        caption="Besichtigung Wasserkraftwerk",
        content="Ganztägige technische Exkursion nach Hernandarias.",
        is_event=True,
        event_start=now + timedelta(days=14),
        event_end=now + timedelta(days=14, hours=10),
        location="Itaipu Binacional",
        has_registration=True,
        author_id=seed_user.id,
    )
    test_db.add(event)
    test_db.commit()

    resp = client.get(f"/api/events/{event.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == event.id
    assert data["title"] == "Exkursion Itaipu"
    assert data["location"] == "Itaipu Binacional"
    assert data["room"] == "Itaipu Binacional"
    assert data["has_registration"] is True

    # Non-existent ID
    resp_404 = client.get("/api/events/999999")
    assert resp_404.status_code == 404
    assert "no encontrado" in resp_404.json()["detail"].lower()


def test_event_registration_flow(client: TestClient, test_db: Session, seed_user: User):
    """Validates 1-click registration and changing status via POST /api/events/{id}/register."""
    now = datetime.now(UTC)

    event = Post(
        title="Hackathon UPA 2026",
        is_event=True,
        event_start=now + timedelta(days=7),
        location="Campus Tech Lab",
        has_registration=True,
        author_id=seed_user.id,
    )
    test_db.add(event)
    test_db.commit()

    # Initial register as attending
    payload = {"user_id": seed_user.id, "status": "attending"}
    reg_resp = client.post(f"/api/events/{event.id}/register", json=payload)
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    assert reg_data["post_id"] == event.id
    assert reg_data["user_id"] == seed_user.id
    assert reg_data["status"] == "attending"

    # Verify event attendees_count increased to 1
    event_resp = client.get(f"/api/events/{event.id}")
    assert event_resp.status_code == 200
    assert event_resp.json()["attendees_count"] == 1

    # Update registration to declined
    payload_declined = {"user_id": seed_user.id, "status": "declined"}
    reg_resp_2 = client.post(f"/api/events/{event.id}/register", json=payload_declined)
    assert reg_resp_2.status_code == 200
    assert reg_resp_2.json()["status"] == "declined"

    # Verify attendees_count dropped back to 0
    event_resp_2 = client.get(f"/api/events/{event.id}")
    assert event_resp_2.status_code == 200
    assert event_resp_2.json()["attendees_count"] == 0


def test_event_registration_rejected_when_not_allowed(
    client: TestClient, test_db: Session, seed_user: User
):
    """Ensures registration is rejected with 400 when has_registration is False."""
    now = datetime.now(UTC)

    event = Post(
        title="Feiertag Campus geschlossen",
        is_event=True,
        event_start=now + timedelta(days=1),
        has_registration=False,
        author_id=seed_user.id,
    )
    test_db.add(event)
    test_db.commit()

    payload = {"user_id": seed_user.id, "status": "attending"}
    resp = client.post(f"/api/events/{event.id}/register", json=payload)
    assert resp.status_code == 400
    assert "no admite registros" in resp.json()["detail"].lower()


def test_event_response_schema_mapping(seed_user: User):
    """Directly verifies EventResponse.from_orm_post schema transformation."""
    now = datetime.now(UTC)
    post = Post(
        id=42,
        title="Direktes Model Mapping Test",
        caption="Kurze Vorschau",
        content="Ausführlicher Beschreibungstext für Teilnehmer.",
        is_event=True,
        event_start=now,
        event_end=now + timedelta(hours=2),
        location="Hörsaal 1",
        has_registration=True,
        is_pinned=True,
        target_groups=["TIE", "IPI"],
        author_id=seed_user.id,
        created_at=now,
    )

    dto = EventResponse.from_orm_post(post, attendees_count=5)
    assert dto.id == 42
    assert dto.title == "Direktes Model Mapping Test"
    assert dto.description == "Ausführlicher Beschreibungstext für Teilnehmer."
    assert dto.location == "Hörsaal 1"
    assert dto.room == "Hörsaal 1"
    assert dto.has_registration is True
    assert dto.attendees_count == 5
    assert dto.is_pinned is True
    assert "TIE" in dto.target_groups
