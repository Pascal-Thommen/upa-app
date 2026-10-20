"""Tests for backend campus feed endpoint."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import Post, User

# In-Memory SQLite Engine für isolierte Feed-Tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_feed_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Admin Nutzer anlegen
    admin = User(id=1, email="admin@upa.edu.py", full_name="Admin User", role="admin", groups=["ALL"])
    student = User(id=2, email="student@upa.edu.py", full_name="Student User", role="user", groups=["TIE"])
    db.add_all([admin, student])
    db.commit()

    # 1. Instagram Post
    insta = Post(
        id=10,
        title="Búsqueda Laboral: Recepcionista",
        caption="¡Estamos buscando Recepcionista! Enviá tu CV a rrhh@upa.edu.py",
        content="Principales funciones: Atención al público...",
        post_type="INSTAGRAM",
        is_news=True,
        is_event=False,
        is_pinned=False,
        target_groups=["ALL"],
        instagram_id="insta_test_123",
        media_type="IMAGE",
        media_url="https://upa.edu.py/static/images/recepcionista.png",
        permalink="https://www.instagram.com/p/test123/",
        author_id=admin.id,
        created_at=datetime.now(UTC) - timedelta(hours=2)
    )

    # 2. Campus Event
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    event = Post(
        id=11,
        title="Charla IA: Daniel Romero",
        caption="Mañana tenemos charla",
        content="Inteligencia artificial en auditorio",
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        is_pinned=True,
        event_start=tomorrow,
        location="Auditorio Edificio 1",
        has_registration=True,
        target_groups=["TIE"],
        author_id=admin.id,
        created_at=datetime.now(UTC) - timedelta(hours=1)
    )

    # 3. Emergency Banner (aktiv)
    banner_active = Post(
        id=12,
        title="Aviso de Emergencia: Suspensión por Tormenta",
        caption="Clases suspendidas en el turno noche",
        content="Debido a las intensas lluvias se suspenden las actividades presenciales",
        post_type="EMERGENCY_BANNER",
        is_news=True,
        is_event=False,
        is_pinned=True,
        expires_at=datetime.now(UTC) + timedelta(hours=5),
        target_groups=["ALL"],
        author_id=admin.id,
        created_at=datetime.now(UTC)
    )

    # 4. Emergency Banner (abgelaufen)
    banner_expired = Post(
        id=13,
        title="Aviso Expirado: Viento fuerte",
        caption="Cuidado en el campus",
        post_type="EMERGENCY_BANNER",
        is_news=True,
        is_event=False,
        is_pinned=False,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
        target_groups=["ALL"],
        author_id=admin.id,
        created_at=datetime.now(UTC) - timedelta(days=1)
    )

    db.add_all([insta, event, banner_active, banner_expired])
    db.commit()

    yield

    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def test_feed_status_code():
    response = client.get("/api/v1/feed")
    assert response.status_code == 200


def test_feed_response_structure():
    response = client.get("/api/v1/feed")
    assert response.status_code == 200
    data = response.json()
    assert "urgent_banners" in data
    assert isinstance(data["urgent_banners"], list)
    assert "posts" in data
    assert isinstance(data["posts"], list)


def test_feed_urgent_banners_filtering():
    response = client.get("/api/v1/feed")
    assert response.status_code == 200
    data = response.json()

    # Nur der aktive Banner darf auftauchen, nicht der abgelaufene
    urgent = data["urgent_banners"]
    assert len(urgent) == 1
    assert urgent[0]["title"] == "Aviso de Emergencia: Suspensión por Tormenta"
    assert urgent[0]["post_type"] == "EMERGENCY_BANNER"


def test_feed_posts_contains_instagram_and_events():
    response = client.get("/api/v1/feed")
    assert response.status_code == 200
    data = response.json()

    posts = data["posts"]
    assert len(posts) == 2

    # Angepinnter Event muss zuerst kommen
    assert posts[0]["title"] == "Charla IA: Daniel Romero"
    assert posts[0]["is_pinned"] is True
    assert posts[0]["is_event"] is True

    # Zweiter ist der Instagram Post
    assert posts[1]["title"] == "Búsqueda Laboral: Recepcionista"
    assert posts[1]["post_type"] == "INSTAGRAM"
    assert posts[1]["instagram_id"] == "insta_test_123"
    assert posts[1]["media_type"] == "IMAGE"
    assert posts[1]["media_url"] == "https://upa.edu.py/static/images/recepcionista.png"
    assert posts[1]["image_url"] == "https://upa.edu.py/static/images/recepcionista.png"
    assert posts[1]["permalink"] == "https://www.instagram.com/p/test123/"


def test_feed_group_filtering():
    # Filter nach TIE: Muss Charla (TIE) und Instagram (ALL) liefern
    response = client.get("/api/v1/feed?group=TIE")
    assert response.status_code == 200
    posts = response.json()["posts"]
    assert len(posts) == 2

    # Filter nach nicht existierender Gruppe MECHATRONIK: Muss nur ALL (Instagram) liefern
    response_other = client.get("/api/v1/feed?group=MECHATRONIK")
    assert response_other.status_code == 200
    posts_other = response_other.json()["posts"]
    assert len(posts_other) == 1
    assert posts_other[0]["title"] == "Búsqueda Laboral: Recepcionista"


def test_feed_pagination():
    response = client.get("/api/v1/feed?limit=1&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["posts"]) == 1
    assert data["posts"][0]["title"] == "Charla IA: Daniel Romero"

    response_page2 = client.get("/api/v1/feed?limit=1&offset=1")
    assert response_page2.status_code == 200
    data_page2 = response_page2.json()
    assert len(data_page2["posts"]) == 1
    assert data_page2["posts"][0]["title"] == "Búsqueda Laboral: Recepcionista"


def test_feed_sync_requires_admin_auth():
    # Unauthentifiziert
    res_unauth = client.post("/api/v1/feed/sync")
    assert res_unauth.status_code == 401

    # Als normaler Student
    student_token = create_access_token({"sub": "2", "email": "student@upa.edu.py", "role": "user"})
    res_forbidden = client.post(
        "/api/v1/feed/sync",
        headers={"Authorization": f"Bearer {student_token}"}
    )
    assert res_forbidden.status_code == 403

    # Als Admin
    admin_token = create_access_token({"sub": "1", "email": "admin@upa.edu.py", "role": "admin"})
    res_admin = client.post(
        "/api/v1/feed/sync",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert "status" in data
