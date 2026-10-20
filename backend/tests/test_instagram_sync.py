"""Tests for Instagram and Social Feed ingestion service."""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from src.main import app
from src.database import Base, get_db
from src.models import Post, User
from src.auth import create_access_token
from src.services.instagram import InstagramSyncService, NormalizedSocialPost

# In-Memory SQLite Engine für isolierte Tests
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
def setup_sync_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    admin = User(id=1, email="admin@upa.edu.py", full_name="Admin User", role="admin", groups=["ALL"])
    student = User(id=2, email="student@upa.edu.py", full_name="Student", role="user", groups=["TIE"])
    db.add_all([admin, student])
    db.commit()

    yield

    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def test_title_extraction_from_caption():
    service = InstagramSyncService()

    # Normaler mehrzeiliger Caption
    caption1 = "Búsqueda Laboral: Recepcionista\n\nSi sos una persona proactiva, sumate al equipo!"
    title1 = service.extract_title_from_caption(caption1)
    assert title1 == "Búsqueda Laboral: Recepcionista"

    # Sehr lange erste Zeile
    caption_long = "A" * 250 + "\nZweite Zeile"
    title_long = service.extract_title_from_caption(caption_long)
    assert len(title_long) <= 200
    assert title_long.endswith("...")

    # Leerer Caption Fallback
    assert service.extract_title_from_caption("") == "Instagram Post @upalemana"
    assert service.extract_title_from_caption("   \n   ") == "Instagram Post @upalemana"


def test_parse_graph_api_item():
    service = InstagramSyncService()
    raw = {
        "id": "17895695668004550",
        "caption": "Feria de Ciencias UPA 2026\nDescubrí todos los proyectos.",
        "media_type": "CAROUSEL_ALBUM",
        "media_url": "https://instagram.com/p/media123.jpg",
        "permalink": "https://www.instagram.com/p/Cxyz123/",
        "timestamp": "2026-10-20T10:00:00+0000"
    }

    parsed = service.parse_graph_api_item(raw)
    assert parsed.instagram_id == "17895695668004550"
    assert "Feria de Ciencias" in parsed.caption
    assert parsed.media_type == "CAROUSEL_ALBUM"
    assert parsed.media_url == "https://instagram.com/p/media123.jpg"
    assert parsed.permalink == "https://www.instagram.com/p/Cxyz123/"
    assert parsed.timestamp is not None


def test_parse_sociablekit_item():
    service = InstagramSyncService()
    raw = {
        "post_id": "sk_post_999",
        "content": "Charla Magistral de Robótica\nInscripciones abiertas.",
        "media_type": "VIDEO",
        "picture": "https://sociablekit.com/images/robotica.jpg",
        "link": "https://instagram.com/p/sk999/",
        "date": "2026-10-20T11:30:00+00:00"
    }

    parsed = service.parse_sociablekit_item(raw)
    assert parsed.instagram_id == "sk_post_999"
    assert "Charla Magistral de Robótica" in parsed.caption
    assert parsed.media_type == "VIDEO"
    assert parsed.media_url == "https://sociablekit.com/images/robotica.jpg"
    assert parsed.permalink == "https://instagram.com/p/sk999/"


def test_sync_posts_persistence_and_idempotence():
    service = InstagramSyncService()
    db = TestingSessionLocal()

    post_item = NormalizedSocialPost(
        instagram_id="insta_fresh_42",
        caption="Nuevo Convenio con SRH Heidelberg\nIntercambio para estudiantes de TIE.",
        media_type="IMAGE",
        media_url="https://upa.edu.py/static/heidelberg.jpg",
        permalink="https://instagram.com/p/fresh42/",
        timestamp=datetime.now(timezone.utc)
    )

    # 1. Erster Sync: Erstellt den Post
    res1 = service.sync_posts(db, [post_item], author_id=1)
    assert res1["status"] == "success"
    assert res1["created_count"] == 1
    assert res1["updated_count"] == 0

    # In DB prüfen
    saved = db.query(Post).filter(Post.instagram_id == "insta_fresh_42").first()
    assert saved is not None
    assert saved.title == "Nuevo Convenio con SRH Heidelberg"
    assert saved.post_type == "INSTAGRAM"
    assert saved.is_news is True
    assert saved.media_type == "IMAGE"
    assert saved.media_url == "https://upa.edu.py/static/heidelberg.jpg"
    assert saved.permalink == "https://instagram.com/p/fresh42/"

    # 2. Zweiter Sync mit aktualisierter Bild-URL: Muss aktualisieren, nicht duplizieren (Idempotenz)
    updated_item = NormalizedSocialPost(
        instagram_id="insta_fresh_42",
        caption="Nuevo Convenio con SRH Heidelberg (Actualizado)\nIntercambio para estudiantes.",
        media_type="CAROUSEL_ALBUM",
        media_url="https://upa.edu.py/static/heidelberg_v2.jpg",
        permalink="https://instagram.com/p/fresh42_v2/",
        timestamp=datetime.now(timezone.utc)
    )

    res2 = service.sync_posts(db, [updated_item], author_id=1)
    assert res2["status"] == "success"
    assert res2["created_count"] == 0
    assert res2["updated_count"] == 1

    # In DB prüfen: Es gibt weiterhin nur genau 1 Eintrag mit dieser ID
    all_matching = db.query(Post).filter(Post.instagram_id == "insta_fresh_42").all()
    assert len(all_matching) == 1
    assert all_matching[0].media_url == "https://upa.edu.py/static/heidelberg_v2.jpg"
    assert all_matching[0].media_type == "CAROUSEL_ALBUM"

    db.close()


def test_sync_instagram_skipped_without_credentials():
    service = InstagramSyncService()
    db = TestingSessionLocal()

    # Wenn keine Credentials gesetzt sind
    import src.config
    old_token = src.config.settings.INSTAGRAM_ACCESS_TOKEN
    old_embed = src.config.settings.SOCIABLEKIT_EMBED_ID
    src.config.settings.INSTAGRAM_ACCESS_TOKEN = ""
    src.config.settings.SOCIABLEKIT_EMBED_ID = ""

    try:
        import asyncio
        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(service.sync_instagram(db))
        loop.close()

        assert res["status"] == "skipped"
        assert res["synced_count"] == 0
    finally:
        src.config.settings.INSTAGRAM_ACCESS_TOKEN = old_token
        src.config.settings.SOCIABLEKIT_EMBED_ID = old_embed
        db.close()


def test_admin_news_sync_endpoint_auth():
    # Unauthentifiziert
    res_unauth = client.post("/api/news/sync-instagram")
    assert res_unauth.status_code == 401

    # Normaler Student darf nicht synchronisieren (403)
    student_token = create_access_token({"sub": "2", "email": "student@upa.edu.py", "role": "user"})
    res_forbidden = client.post(
        "/api/news/sync-instagram",
        headers={"Authorization": f"Bearer {student_token}"}
    )
    assert res_forbidden.status_code == 403

    # Admin darf synchronisieren
    admin_token = create_access_token({"sub": "1", "email": "admin@upa.edu.py", "role": "admin"})
    res_admin = client.post(
        "/api/news/sync-instagram",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert "status" in data
