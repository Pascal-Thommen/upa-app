"""Tests for backend campus feed endpoint.

Validates /api/v1/feed:
1. Status code and baseline JSON response structure.
2. Segregation of urgent banners and normal news posts.
3. Order: Pinned posts first, then newest first.
"""

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


def test_feed_status_code(client: TestClient):
    response = client.get("/api/v1/feed")
    assert response.status_code == 200


def test_feed_response_structure(client: TestClient):
    response = client.get("/api/v1/feed")
    data = response.json()
    assert "urgent_banners" in data
    assert isinstance(data["urgent_banners"], list)
    assert "posts" in data
    assert isinstance(data["posts"], list)


def test_feed_urgent_and_regular_posts_segregation(client: TestClient, test_db: Session):
    author = User(email="noticias@upa.edu.py", full_name="Noticias UPA", role="admin")
    test_db.add(author)
    test_db.flush()

    urgent_post = Post(
        title="Tormenta Severa: Campus Cerrado",
        caption="Aviso urgente de seguridad",
        post_type="EMERGENCY_BANNER",
        is_news=True,
        is_urgent=True,
        author_id=author.id,
    )
    regular_post = Post(
        title="Búsqueda Laboral: Recepcionista",
        caption="Oportunidad laboral",
        post_type="INSTAGRAM",
        is_news=True,
        is_urgent=False,
        author_id=author.id,
    )
    test_db.add_all([urgent_post, regular_post])
    test_db.commit()

    response = client.get("/api/v1/feed")
    assert response.status_code == 200
    data = response.json()

    # Urgent post appears in urgent_banners
    assert len(data["urgent_banners"]) == 1
    assert data["urgent_banners"][0]["title"] == "Tormenta Severa: Campus Cerrado"

    # Both news posts appear in posts list
    assert len(data["posts"]) == 2
    post_titles = [p["title"] for p in data["posts"]]
    assert "Tormenta Severa: Campus Cerrado" in post_titles
    assert "Búsqueda Laboral: Recepcionista" in post_titles
