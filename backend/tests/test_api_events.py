"""Tests for GET /api/events and Event schemas.

Verifies:
1. Retrieval of calendar events filtered by is_event = True.
2. Exclusion of non-event news posts (like pure Instagram job postings).
3. Field validation: title, location, has_registration, attendee_count.
4. Target group filtering and pagination.
5. GET /api/events/{id} detail retrieval and 404 handling.
6. Integration with real database seeding.

Adheres strictly to the Zero Mock Doktrin.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from src.database import Base, get_db
from src.main import app
from src.models import EventRegistration, Post, User
from src.seed import seed_database


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


def test_get_events_empty_database(client: TestClient):
    response = client.get("/api/events")
    assert response.status_code == 200
    assert response.json() == []


def test_get_events_with_seeded_real_data(client: TestClient, test_db: Session):
    """Seed real campus data and verify GET /api/events returns Charla IA event completely."""
    seed_database(test_db)

    response = client.get("/api/events")
    assert response.status_code == 200
    data = response.json()

    # Exactly 1 event (Charla IA), since Instagram post has is_event = False
    assert len(data) == 1
    event_item = data[0]

    assert event_item["title"] == "¿Qué significa seguir siendo humanos en la era de la IA?"
    assert event_item["post_type"] == "MANUAL"
    assert event_item["is_news"] is True
    assert event_item["is_event"] is True
    assert event_item["has_registration"] is True
    assert event_item["location"] == "Auditorio Edificio 1, Piso 1"
    assert "Daniel Romero" in event_item["caption"]
    assert "01a15981-8ac8-7b1b-80a7-3ce474ccc846" in event_item["media_url"]
    assert event_item["attendee_count"] == 0
    assert event_item["target_groups"] == ["ALL"]
    assert event_item["event_start"] is not None


def test_get_events_excludes_pure_news(client: TestClient, test_db: Session):
    """Ensure posts with is_event = False are never included in GET /api/events."""
    author = User(email="test@upa.edu.py", full_name="Test Author", role="admin")
    test_db.add(author)
    test_db.flush()

    # Pure news post
    news = Post(
        title="Campus Cafeteria Notice",
        caption="Horarios de almuerzo",
        post_type="MANUAL",
        is_news=True,
        is_event=False,
        author_id=author.id,
    )
    # Event post
    event_post = Post(
        title="Hackathon UPA 2026",
        caption="Competencia de programacion",
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        location="Lab 3",
        has_registration=True,
        author_id=author.id,
    )
    test_db.add_all([news, event_post])
    test_db.commit()

    response = client.get("/api/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Hackathon UPA 2026"


def test_get_events_attendee_count_calculation(client: TestClient, test_db: Session):
    """Ensure attendee_count reflects confirmed registrations in real time."""
    author = User(email="prof@upa.edu.py", full_name="Profesor", role="faculty")
    student1 = User(email="s1@upa.edu.py", full_name="Student 1", role="student")
    student2 = User(email="s2@upa.edu.py", full_name="Student 2", role="student")
    test_db.add_all([author, student1, student2])
    test_db.flush()

    event_post = Post(
        title="Charla Abierta",
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        has_registration=True,
        author_id=author.id,
    )
    test_db.add(event_post)
    test_db.flush()

    reg1 = EventRegistration(post_id=event_post.id, user_id=student1.id, status="attending")
    reg2 = EventRegistration(post_id=event_post.id, user_id=student2.id, status="attending")
    test_db.add_all([reg1, reg2])
    test_db.commit()
    event_id = event_post.id

    response = client.get("/api/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["attendee_count"] == 2

    # Verify single event endpoint
    detail_res = client.get(f"/api/events/{event_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["attendee_count"] == 2


def test_get_events_by_id_not_found_and_non_event(client: TestClient, test_db: Session):
    """Verify 404 behavior for unknown IDs and non-event posts."""
    author = User(email="author@upa.edu.py", full_name="Author", role="admin")
    test_db.add(author)
    test_db.flush()

    pure_news = Post(
        title="Solo Noticia",
        post_type="MANUAL",
        is_news=True,
        is_event=False,
        author_id=author.id,
    )
    test_db.add(pure_news)
    test_db.commit()
    news_id = pure_news.id

    # Unknown ID -> 404
    res_404 = client.get("/api/events/99999")
    assert res_404.status_code == 404

    # Existing post, but is_event = False -> 404 on /api/events/{id}
    res_non_event = client.get(f"/api/events/{news_id}")
    assert res_non_event.status_code == 404


def test_get_events_target_group_filtering(client: TestClient, test_db: Session):
    """Verify group-based filtering for events."""
    author = User(email="admin@upa.edu.py", full_name="Admin", role="admin")
    test_db.add(author)
    test_db.flush()

    tie_event = Post(
        title="Taller Ingenieria Industrial",
        is_event=True,
        target_groups=["TIE"],
        author_id=author.id,
    )
    all_event = Post(
        title="Bienvenida General UPA",
        is_event=True,
        target_groups=["ALL"],
        author_id=author.id,
    )
    test_db.add_all([tie_event, all_event])
    test_db.commit()

    res_tie = client.get("/api/events?group=TIE")
    assert res_tie.status_code == 200
    titles = [e["title"] for e in res_tie.json()]
    assert "Taller Ingenieria Industrial" in titles
    assert "Bienvenida General UPA" in titles

    res_other = client.get("/api/events?group=INFORMATICA")
    assert res_other.status_code == 200
    other_titles = [e["title"] for e in res_other.json()]
    assert "Taller Ingenieria Industrial" not in other_titles
    assert "Bienvenida General UPA" in other_titles


def test_get_news_and_events_integration_with_seed(client: TestClient, test_db: Session):
    """End-to-end acceptance test: GET /api/news returns both records, GET /api/events returns event."""
    seed_database(test_db)

    # GET /api/news: both real records are news (is_news = true)
    news_res = client.get("/api/news")
    assert news_res.status_code == 200
    news_items = news_res.json()
    assert len(news_items) == 2

    news_titles = [n["title"] for n in news_items]
    assert "Búsqueda Laboral: Recepcionista" in news_titles
    assert "¿Qué significa seguir siendo humanos en la era de la IA?" in news_titles

    # GET /api/events: only Charla IA is an event (is_event = true)
    events_res = client.get("/api/events")
    assert events_res.status_code == 200
    event_items = events_res.json()
    assert len(event_items) == 1
    assert event_items[0]["title"] == "¿Qué significa seguir siendo humanos en la era de la IA?"
    assert event_items[0]["has_registration"] is True
    assert event_items[0]["location"] == "Auditorio Edificio 1, Piso 1"
