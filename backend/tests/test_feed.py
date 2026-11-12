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
from src.models import Post, PostView, User

# In-Memory SQLite Engine für isolierte Feed-Tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
        created_at=datetime.now(UTC) - timedelta(hours=2),
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
        created_at=datetime.now(UTC) - timedelta(hours=1),
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
        created_at=datetime.now(UTC),
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
        created_at=datetime.now(UTC) - timedelta(days=1),
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


def test_feed_unauthenticated_returns_only_instagram():
    # Ohne Login dürfen absolut keine internen Eilmeldungen oder Events ausgeliefert werden
    response = client.get("/api/v1/feed")
    assert response.status_code == 200
    data = response.json()
    assert len(data["urgent_banners"]) == 0
    assert len(data["posts"]) == 1
    assert data["posts"][0]["post_type"] == "INSTAGRAM"
    assert data["posts"][0]["title"] == "Búsqueda Laboral: Recepcionista"


def test_feed_urgent_banners_filtering():
    token = create_access_token({"sub": "2", "email": "student@upa.edu.py", "role": "user"})
    response = client.get("/api/v1/feed", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()

    # Nur der aktive Banner darf auftauchen, nicht der abgelaufene
    urgent = data["urgent_banners"]
    assert len(urgent) == 1
    assert urgent[0]["title"] == "Aviso de Emergencia: Suspensión por Tormenta"
    assert urgent[0]["post_type"] == "EMERGENCY_BANNER"


def test_feed_posts_contains_instagram_and_events():
    token = create_access_token({"sub": "2", "email": "student@upa.edu.py", "role": "user"})
    response = client.get("/api/v1/feed", headers={"Authorization": f"Bearer {token}"})
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
    token = create_access_token({"sub": "2", "email": "student@upa.edu.py", "role": "user"})
    # Filter nach TIE: Muss Charla (TIE) und Instagram (ALL) liefern
    response = client.get("/api/v1/feed?group=TIE", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    posts = response.json()["posts"]
    assert len(posts) == 2

    # Filter nach nicht existierender Gruppe MECHATRONIK: Muss nur ALL (Instagram) liefern
    response_other = client.get("/api/v1/feed?group=MECHATRONIK", headers={"Authorization": f"Bearer {token}"})
    assert response_other.status_code == 200
    posts_other = response_other.json()["posts"]
    assert len(posts_other) == 1
    assert posts_other[0]["title"] == "Búsqueda Laboral: Recepcionista"


def test_feed_pagination():
    token = create_access_token({"sub": "2", "email": "student@upa.edu.py", "role": "user"})
    response = client.get("/api/v1/feed?limit=1&offset=0", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["posts"]) == 1
    assert data["posts"][0]["title"] == "Charla IA: Daniel Romero"

    response_page2 = client.get("/api/v1/feed?limit=1&offset=1", headers={"Authorization": f"Bearer {token}"})
    assert response_page2.status_code == 200
    data_page2 = response_page2.json()
    assert len(data_page2["posts"]) == 1
    assert data_page2["posts"][0]["title"] == "Búsqueda Laboral: Recepcionista"


def test_feed_sync_endpoint_removed():
    # El endpoint redundante /api/v1/feed/sync fue consolidado en /api/publications/sync-instagram
    assert client.post("/api/v1/feed/sync").status_code in (404, 405)


def test_feed_automatic_impression_tracking_and_idempotency():
    # Gastnutzer (ohne Auth) ruft Feed ab: kein Fehler und keine PostView-Einträge
    guest_res = client.get("/api/v1/feed")
    assert guest_res.status_code == 200
    assert guest_res.json()["posts"][0]["views_count"] == 0

    db = TestingSessionLocal()
    assert db.query(PostView).count() == 0
    student2 = User(id=3, email="student2@upa.edu.py", full_name="Student Two", role="user", groups=["TIE"])
    db.add(student2)
    db.commit()
    db.close()

    student1_headers = {"Authorization": f"Bearer {create_access_token({'sub': '2', 'email': 'student@upa.edu.py', 'role': 'user'})}"}
    student2_headers = {"Authorization": f"Bearer {create_access_token({'sub': '3', 'email': 'student2@upa.edu.py', 'role': 'user'})}"}
    admin_headers = {"Authorization": f"Bearer {create_access_token({'sub': '1', 'email': 'admin@upa.edu.py', 'role': 'admin'})}"}

    # Eingeloggter Student 1 ruft Feed ab -> ausgelieferte Beiträge (10, 11, 12) erhalten je 1 Impression
    res1 = client.get("/api/v1/feed", headers=student1_headers)
    assert res1.status_code == 200
    body1 = res1.json()
    assert body1["urgent_banners"][0]["views_count"] == 1
    assert [p["views_count"] for p in body1["posts"]] == [1, 1]

    # Wiederholtes Neuladen desselben Studenten erhöht den Zähler nicht (Idempotenz)
    res1_reload = client.get("/api/v1/feed", headers=student1_headers)
    assert res1_reload.status_code == 200
    body1_reload = res1_reload.json()
    assert body1_reload["urgent_banners"][0]["views_count"] == 1
    assert [p["views_count"] for p in body1_reload["posts"]] == [1, 1]

    db = TestingSessionLocal()
    assert db.query(PostView).filter(PostView.user_id == 2).count() == 3
    assert db.query(PostView).filter(PostView.post_id == 13).count() == 0
    db.close()

    # Zweiter Student ruft Feed ab -> Zähler steigt auf 2
    res2 = client.get("/api/v1/feed", headers=student2_headers)
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["urgent_banners"][0]["views_count"] == 2
    assert [p["views_count"] for p in body2["posts"]] == [2, 2]

    # Dashboard (/api/publications) reflektiert views_count korrekt
    pubs_res = client.get("/api/publications", headers=admin_headers)
    assert pubs_res.status_code == 200
    pubs_by_id = {p["id"]: p["views_count"] for p in pubs_res.json()}
    assert pubs_by_id[10] == 2
    assert pubs_by_id[11] == 2
    assert pubs_by_id[12] == 2
    assert pubs_by_id[13] == 0


def test_feed_rapid_paging_and_empty_feed_without_sql_errors():
    student_headers = {"Authorization": f"Bearer {create_access_token({'sub': '2', 'email': 'student@upa.edu.py', 'role': 'user'})}"}

    # Schnelles Paging: Seite 1 zählt nur Banner (12) + ersten Post (11), noch nicht zweiten Post (10)
    p1 = client.get("/api/v1/feed?limit=1&offset=0", headers=student_headers)
    assert p1.status_code == 200
    db = TestingSessionLocal()
    viewed_after_p1 = {row.post_id for row in db.query(PostView).filter(PostView.user_id == 2).all()}
    assert viewed_after_p1 == {11, 12}
    db.close()

    # Seite 2 zählt nun auch Post 10
    p2 = client.get("/api/v1/feed?limit=1&offset=1", headers=student_headers)
    assert p2.status_code == 200
    db = TestingSessionLocal()
    viewed_after_p2 = {row.post_id for row in db.query(PostView).filter(PostView.user_id == 2).all()}
    assert viewed_after_p2 == {10, 11, 12}
    db.close()

    # Paging jenseits des Bestands (leere Post-Liste)
    p_empty = client.get("/api/v1/feed?limit=10&offset=50", headers=student_headers)
    assert p_empty.status_code == 200
    assert p_empty.json()["posts"] == []

    # Komplett leerer Feed (alle Posts entfernt) läuft für eingeloggte Nutzer und Gäste fehlerfrei durch
    db = TestingSessionLocal()
    db.query(PostView).delete()
    db.query(Post).delete()
    db.commit()
    db.close()

    empty_auth = client.get("/api/v1/feed", headers=student_headers)
    assert empty_auth.status_code == 200
    assert empty_auth.json() == {"urgent_banners": [], "posts": []}

    empty_guest = client.get("/api/v1/feed")
    assert empty_guest.status_code == 200
    assert empty_guest.json() == {"urgent_banners": [], "posts": []}
