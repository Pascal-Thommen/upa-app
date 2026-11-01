"""Tests for Instagram and Social Feed ingestion service."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import Post, User
from src.services.instagram import InstagramSyncService, NormalizedSocialPost

# In-Memory SQLite Engine für isolierte Tests
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
        "timestamp": "2026-10-20T10:00:00+0000",
    }

    parsed = service.parse_graph_api_item(raw)
    assert parsed.instagram_id == "17895695668004550"
    assert "Feria de Ciencias" in parsed.caption
    assert parsed.media_type == "CAROUSEL_ALBUM"
    assert parsed.media_url == "https://instagram.com/p/media123.jpg"
    assert parsed.image_url == "https://instagram.com/p/media123.jpg"
    assert parsed.permalink == "https://www.instagram.com/p/Cxyz123/"
    assert parsed.timestamp is not None


def test_parse_graph_api_video_with_thumbnail_and_fallback():
    service = InstagramSyncService()

    # 1. Instagram Reel / VIDEO con media_url (mp4) y thumbnail_url (jpg)
    raw_video = {
        "id": "179000111222333",
        "caption": "Reel de Innovación UPA 2026\nConocé nuestros laboratorios.",
        "media_type": "VIDEO",
        "media_url": "https://cdn.instagram.com/v/reel_innovacion.mp4",
        "thumbnail_url": "https://cdn.instagram.com/v/reel_innovacion_thumb.jpg",
        "permalink": "https://www.instagram.com/reel/Creel2026/",
        "timestamp": "2026-10-25T15:00:00Z",
    }
    parsed_video = service.parse_graph_api_item(raw_video)
    assert parsed_video.media_type == "VIDEO"
    assert parsed_video.media_url == "https://cdn.instagram.com/v/reel_innovacion.mp4"
    assert parsed_video.image_url == "https://cdn.instagram.com/v/reel_innovacion_thumb.jpg"

    # 2. Video sin thumbnail_url utiliza imagen de respaldo estable
    raw_video_no_thumb = {
        "id": "179000999888777",
        "caption": "Video institucional sin miniatura",
        "media_type": "VIDEO",
        "media_url": "https://cdn.instagram.com/v/sin_thumb.mp4",
        "permalink": "https://www.instagram.com/reel/Cnot2026/",
    }
    parsed_no_thumb = service.parse_graph_api_item(raw_video_no_thumb)
    assert parsed_no_thumb.media_type == "VIDEO"
    assert parsed_no_thumb.media_url == "https://cdn.instagram.com/v/sin_thumb.mp4"
    assert parsed_no_thumb.image_url == service.DEFAULT_VIDEO_THUMBNAIL_FALLBACK


def test_parse_sociablekit_item():
    service = InstagramSyncService()
    raw = {
        "post_id": "sk_post_999",
        "content": "Charla Magistral de Robótica\nInscripciones abiertas.",
        "media_type": "VIDEO",
        "picture": "https://sociablekit.com/images/robotica.jpg",
        "link": "https://instagram.com/p/sk999/",
        "date": "2026-10-20T11:30:00+00:00",
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
        timestamp=datetime.now(UTC),
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
        timestamp=datetime.now(UTC),
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
    res_forbidden = client.post("/api/news/sync-instagram", headers={"Authorization": f"Bearer {student_token}"})
    assert res_forbidden.status_code == 403

    # Admin darf synchronisieren
    admin_token = create_access_token({"sub": "1", "email": "admin@upa.edu.py", "role": "admin"})
    res_admin = client.post("/api/news/sync-instagram", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert "status" in data


def test_video_thumbnail_persisted_in_image_url_and_exposed_in_feed_and_publications():
    service = InstagramSyncService()
    db = TestingSessionLocal()

    reel_item = service.parse_graph_api_item(
        {
            "id": "ig_reel_niif18",
            "caption": "¿Sabés cómo adaptar tu estado de resultados a la NIIF 18?\nDescubrí más en la UPA.",
            "media_type": "VIDEO",
            "media_url": "https://cdn.instagram.com/videos/niif18.mp4",
            "thumbnail_url": "https://cdn.instagram.com/thumbs/niif18_poster.jpg",
            "permalink": "https://www.instagram.com/upalemana/reel/De92KpiM8x1/",
            "timestamp": "2026-10-28T12:00:00Z",
        }
    )
    fallback_video_item = service.parse_graph_api_item(
        {
            "id": "ig_reel_no_thumb",
            "caption": "Recorrido por el Campus UPA\nViví la experiencia universitaria.",
            "media_type": "VIDEO",
            "media_url": "https://cdn.instagram.com/videos/recorrido.mp4",
            "permalink": "https://www.instagram.com/upalemana/reel/Drecorrido/",
            "timestamp": "2026-10-27T12:00:00Z",
        }
    )

    res = service.sync_posts(db, [reel_item, fallback_video_item], author_id=1)
    assert res["status"] == "success"
    assert res["created_count"] == 2
    db.close()

    # Verificar en nueva sesion que media_url e image_url persisten sin migracion adicional
    db_check = TestingSessionLocal()
    saved_reel = db_check.query(Post).filter(Post.instagram_id == "ig_reel_niif18").first()
    assert saved_reel is not None
    assert saved_reel.media_type == "VIDEO"
    assert saved_reel.media_url == "https://cdn.instagram.com/videos/niif18.mp4"
    assert saved_reel.image_url == "https://cdn.instagram.com/thumbs/niif18_poster.jpg"

    saved_fallback = db_check.query(Post).filter(Post.instagram_id == "ig_reel_no_thumb").first()
    assert saved_fallback is not None
    assert saved_fallback.media_url == "https://cdn.instagram.com/videos/recorrido.mp4"
    assert saved_fallback.image_url == "/campus/icons/icon-512.png"
    db_check.close()

    # Verificar FeedItemResponse (/api/v1/feed)
    feed_res = client.get("/api/v1/feed")
    assert feed_res.status_code == 200
    feed_posts = {p["instagram_id"]: p for p in feed_res.json()["posts"]}
    assert feed_posts["ig_reel_niif18"]["media_url"] == "https://cdn.instagram.com/videos/niif18.mp4"
    assert feed_posts["ig_reel_niif18"]["image_url"] == "https://cdn.instagram.com/thumbs/niif18_poster.jpg"
    assert feed_posts["ig_reel_no_thumb"]["media_url"] == "https://cdn.instagram.com/videos/recorrido.mp4"
    assert feed_posts["ig_reel_no_thumb"]["image_url"] == "/campus/icons/icon-512.png"

    # Verificar PublicationResponse (/api/publications)
    admin_token = create_access_token({"sub": "1", "email": "admin@upa.edu.py", "role": "admin"})
    pub_res = client.get("/api/publications", headers={"Authorization": f"Bearer {admin_token}"})
    assert pub_res.status_code == 200
    pub_posts = {p["instagram_id"]: p for p in pub_res.json() if p.get("instagram_id")}
    assert pub_posts["ig_reel_niif18"]["media_url"] == "https://cdn.instagram.com/videos/niif18.mp4"
    assert pub_posts["ig_reel_niif18"]["image_url"] == "https://cdn.instagram.com/thumbs/niif18_poster.jpg"
    assert pub_posts["ig_reel_no_thumb"]["image_url"] == "/campus/icons/icon-512.png"


def test_graph_api_timeout_and_error_handling(monkeypatch):
    import asyncio

    import httpx

    service = InstagramSyncService()

    async def _timeout_get(self, *args, **kwargs):
        raise httpx.TimeoutException("Graph API request timed out")

    monkeypatch.setattr(httpx.AsyncClient, "get", _timeout_get)
    loop = asyncio.new_event_loop()
    try:
        posts = loop.run_until_complete(service.fetch_from_graph_api(token="test-token", account_id="12345"))
        assert posts == []
    finally:
        loop.close()
