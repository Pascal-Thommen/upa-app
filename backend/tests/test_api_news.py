"""Unit and integration tests for GET /api/news endpoint.

Validates the full interface contract, target group filtering, priority ordering,
expiration handling, and pagination without mocks.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from src.database import Base, get_db
from src.main import app
from src.models import Post, User
from src.schemas.post import NewsResponse


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


def test_get_news_empty_database(client: TestClient):
    """GET /api/news returns an empty list with status 200 when no posts exist."""
    response = client.get("/api/news")
    assert response.status_code == 200
    assert response.json() == []


def test_get_news_response_schema_validation(client: TestClient, test_db: Session):
    """Validates that GET /api/news returns JSON strictly adhering to NewsResponse schema."""
    author = User(email="editor@upa.edu.py", full_name="Campus Editor", role="admin")
    test_db.add(author)
    test_db.commit()

    created_time = datetime(2026, 10, 20, 10, 0, 0, tzinfo=UTC)
    post = Post(
        title="Inauguración del Nuevo Laboratorio de IA",
        caption="Instalaciones de última generación",
        content="La universidad inaugura su nuevo centro de investigación tecnológica.",
        post_type="INSTAGRAM",
        is_news=True,
        is_event=False,
        is_pinned=True,
        is_urgent=True,
        target_groups=["ALL", "TIE"],
        instagram_id="ig_post_987",
        media_type="IMAGE",
        media_url="https://upa.edu.py/media/lab_ia.jpg",
        permalink="https://instagram.com/p/lab_ia",
        author_id=author.id,
        created_at=created_time,
    )
    test_db.add(post)
    test_db.commit()

    response = client.get("/api/news")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    item = data[0]
    validated = NewsResponse.model_validate(item)
    assert validated.id == post.id
    assert validated.title == "Inauguración del Nuevo Laboratorio de IA"
    assert validated.summary == "Instalaciones de última generación"
    assert "investigación" in (validated.content or "")
    assert validated.post_type == "INSTAGRAM"
    assert validated.is_pinned is True
    assert validated.is_urgent is True
    assert validated.target_groups == ["ALL", "TIE"]
    assert validated.image_url == "https://upa.edu.py/media/lab_ia.jpg"
    assert validated.instagram_id == "ig_post_987"
    assert validated.media_type == "IMAGE"
    assert validated.media_url == "https://upa.edu.py/media/lab_ia.jpg"
    assert validated.permalink == "https://instagram.com/p/lab_ia"
    assert validated.author_id == author.id


def test_get_news_excludes_non_news_posts(client: TestClient, test_db: Session):
    """Ensures posts with is_news=False are excluded from the news feed."""
    news_post = Post(title="Noticia Relevante", is_news=True)
    calendar_only_event = Post(title="Entrega de Tarea Privada", is_news=False, is_event=True)
    test_db.add_all([news_post, calendar_only_event])
    test_db.commit()

    response = client.get("/api/news")
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]
    assert "Noticia Relevante" in titles
    assert "Entrega de Tarea Privada" not in titles


def test_get_news_group_filtering_includes_authorized(client: TestClient, test_db: Session):
    """Filters news by group and includes authorized entries (matching group or ALL)."""
    post_all = Post(title="Comunicado General Campus", is_news=True, target_groups=["ALL"])
    post_tie = Post(title="Charla Especial para TIE", is_news=True, target_groups=["TIE"])
    post_inf = Post(title="Taller Exclusivo Informatica", is_news=True, target_groups=["INF"])
    test_db.add_all([post_all, post_tie, post_inf])
    test_db.commit()

    response = client.get("/api/news?group=TIE")
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]

    assert "Comunicado General Campus" in titles
    assert "Charla Especial para TIE" in titles
    assert "Taller Exclusivo Informatica" not in titles


def test_get_news_group_filtering_excludes_unauthorized(client: TestClient, test_db: Session):
    """Strictly excludes posts that target other specific groups."""
    post_med = Post(title="Aviso Medicina", is_news=True, target_groups=["MED"])
    post_tie = Post(title="Aviso TIE", is_news=True, target_groups=["TIE"])
    test_db.add_all([post_med, post_tie])
    test_db.commit()

    response = client.get("/api/news?group=MED")
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]

    assert "Aviso Medicina" in titles
    assert "Aviso TIE" not in titles


def test_get_news_excludes_expired_announcements(client: TestClient, test_db: Session):
    """Ensures emergency banners or announcements whose visible_until/expires_at is past are excluded."""
    now = datetime.now(UTC)
    expired_post = Post(
        title="Tormenta pasada",
        is_news=True,
        expires_at=now - timedelta(hours=2),
    )
    active_post = Post(
        title="Aviso vigente",
        is_news=True,
        expires_at=now + timedelta(hours=2),
    )
    permanent_post = Post(
        title="Noticia permanente sin expiracion",
        is_news=True,
        expires_at=None,
    )
    test_db.add_all([expired_post, active_post, permanent_post])
    test_db.commit()

    response = client.get("/api/news")
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]

    assert "Tormenta pasada" not in titles
    assert "Aviso vigente" in titles
    assert "Noticia permanente sin expiracion" in titles


def test_get_news_sorting_pinned_first(client: TestClient, test_db: Session):
    """Ensures pinned posts appear at the top, followed by newest unpinned posts."""
    t1 = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=UTC)
    t3 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)

    unpinned_newest = Post(title="Noticia Reciente Regular", is_news=True, is_pinned=False, created_at=t3)
    unpinned_oldest = Post(title="Noticia Vieja Regular", is_news=True, is_pinned=False, created_at=t1)
    pinned_older = Post(title="Aviso Fijado Importante", is_news=True, is_pinned=True, created_at=t2)

    test_db.add_all([unpinned_newest, unpinned_oldest, pinned_older])
    test_db.commit()

    response = client.get("/api/news")
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]

    assert titles[0] == "Aviso Fijado Importante"
    assert titles[1] == "Noticia Reciente Regular"
    assert titles[2] == "Noticia Vieja Regular"


def test_get_news_pagination_limit_and_offset(client: TestClient, test_db: Session):
    """Validates offset and limit pagination parameters."""
    for i in range(10):
        test_db.add(Post(title=f"Noticia {i+1:02d}", is_news=True))
    test_db.commit()

    # Request first page of 3
    res1 = client.get("/api/news?limit=3&offset=0")
    assert res1.status_code == 200
    items1 = res1.json()
    assert len(items1) == 3

    # Request second page of 3
    res2 = client.get("/api/news?limit=3&offset=3")
    assert res2.status_code == 200
    items2 = res2.json()
    assert len(items2) == 3

    # Verify no overlap
    ids1 = {x["id"] for x in items1}
    ids2 = {x["id"] for x in items2}
    assert ids1.isdisjoint(ids2)


def test_get_news_pagination_page_parameter(client: TestClient, test_db: Session):
    """Validates 1-based page query parameter."""
    for i in range(6):
        test_db.add(Post(title=f"Noticia {i+1:02d}", is_news=True))
    test_db.commit()

    res_page2 = client.get("/api/news?page=2&limit=2")
    assert res_page2.status_code == 200
    data = res_page2.json()
    assert len(data) == 2


def test_get_news_by_id_success(client: TestClient, test_db: Session):
    """GET /api/news/{id} returns the single requested post."""
    post = Post(title="Noticia por ID", is_news=True, content="Detalles de la noticia.")
    test_db.add(post)
    test_db.commit()

    response = client.get(f"/api/news/{post.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == post.id
    assert data["title"] == "Noticia por ID"
    assert data["content"] == "Detalles de la noticia."


def test_get_news_by_id_not_found(client: TestClient):
    """GET /api/news/{id} returns 404 when the ID does not exist."""
    response = client.get("/api/news/999999")
    assert response.status_code == 404
    assert "no encontrada" in response.json()["detail"].lower()


def test_get_news_by_id_non_news_returns_404(client: TestClient, test_db: Session):
    """GET /api/news/{id} returns 404 when the requested post is not a news item."""
    event_post = Post(title="Solo Evento", is_news=False, is_event=True)
    test_db.add(event_post)
    test_db.commit()

    response = client.get(f"/api/news/{event_post.id}")
    assert response.status_code == 404
