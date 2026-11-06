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

    # Normalizacion de URLs con nombre de usuario intermedio (/upalemana/p/... y /upalemana/reel/...) y prioridad de image_url
    raw_upalemana = {
        "id": "DfC-9wJFV6u",
        "pic_text_raw": "Charla sobre Storytelling en la UPA",
        "pic_type": "carousel",
        "image_url": "https://data-image.sociablekit.com/sources/instagram-feed/upalemana/DfC-9wJFV6u-thumbnail.webp",
        "thumbnail": "https://instagram.fmnl4-1.fna.fbcdn.net/v/t39.30808-6/expired.jpg",
        "link": "https://www.instagram.com/upalemana/p/DfC-9wJFV6u/",
        "date_time_posted": "2026-10-29T01:36:35+08:00",
    }
    parsed_upa = service.parse_sociablekit_item(raw_upalemana)
    assert parsed_upa.permalink == "https://www.instagram.com/p/DfC-9wJFV6u/"
    assert parsed_upa.media_url == "https://data-image.sociablekit.com/sources/instagram-feed/upalemana/DfC-9wJFV6u-thumbnail.webp"
    assert parsed_upa.image_url == "https://data-image.sociablekit.com/sources/instagram-feed/upalemana/DfC-9wJFV6u-thumbnail.webp"


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


def test_admin_news_sync_endpoint_auth(monkeypatch):
    import src.config

    monkeypatch.setattr(src.config.settings, "INSTAGRAM_ACCESS_TOKEN", "")
    monkeypatch.setattr(src.config.settings, "SOCIABLEKIT_EMBED_ID", "")

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


def test_video_thumbnail_persisted_in_image_url_and_exposed_in_feed_and_publications(monkeypatch):
    import httpx

    sample_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    def _mock_sync_get(url, *args, **kwargs):
        return httpx.Response(
            200,
            content=sample_jpg,
            headers={"content-type": "image/jpeg"},
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx, "get", _mock_sync_get)

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

    # Verificar en nueva sesion que media_url conserva el stream MP4 e image_url apunta al archivo local en /uploads/instagram/
    db_check = TestingSessionLocal()
    saved_reel = db_check.query(Post).filter(Post.instagram_id == "ig_reel_niif18").first()
    assert saved_reel is not None
    assert saved_reel.media_type == "VIDEO"
    assert saved_reel.media_url == "https://cdn.instagram.com/videos/niif18.mp4"
    assert saved_reel.image_url == "/uploads/instagram/ig_reel_niif18.jpg"

    saved_fallback = db_check.query(Post).filter(Post.instagram_id == "ig_reel_no_thumb").first()
    assert saved_fallback is not None
    assert saved_fallback.media_url == "https://cdn.instagram.com/videos/recorrido.mp4"
    assert saved_fallback.image_url == "/campus/icons/icon-512.png"
    db_check.close()

    # El archivo descargado localmente se sirve bajo /uploads/instagram/
    static_res = client.get("/uploads/instagram/ig_reel_niif18.jpg")
    assert static_res.status_code == 200
    assert static_res.content == sample_jpg

    # Verificar FeedItemResponse (/api/v1/feed)
    feed_res = client.get("/api/v1/feed")
    assert feed_res.status_code == 200
    feed_posts = {p["instagram_id"]: p for p in feed_res.json()["posts"]}
    assert feed_posts["ig_reel_niif18"]["media_url"] == "https://cdn.instagram.com/videos/niif18.mp4"
    assert feed_posts["ig_reel_niif18"]["image_url"] == "/uploads/instagram/ig_reel_niif18.jpg"
    assert feed_posts["ig_reel_no_thumb"]["media_url"] == "https://cdn.instagram.com/videos/recorrido.mp4"
    assert feed_posts["ig_reel_no_thumb"]["image_url"] == "/campus/icons/icon-512.png"

    # Verificar PublicationResponse (/api/publications)
    admin_token = create_access_token({"sub": "1", "email": "admin@upa.edu.py", "role": "admin"})
    pub_res = client.get("/api/publications", headers={"Authorization": f"Bearer {admin_token}"})
    assert pub_res.status_code == 200
    pub_posts = {p["instagram_id"]: p for p in pub_res.json() if p.get("instagram_id")}
    assert pub_posts["ig_reel_niif18"]["media_url"] == "https://cdn.instagram.com/videos/niif18.mp4"
    assert pub_posts["ig_reel_niif18"]["image_url"] == "/uploads/instagram/ig_reel_niif18.jpg"
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


def test_graph_api_v21_endpoint_and_auto_discovery(monkeypatch):
    import asyncio

    import httpx

    service = InstagramSyncService()
    called_urls: list[str] = []
    sample_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    real_payload = {
        "data": [
            {
                "id": "18114511375879455",
                "caption": "🇩🇪✨ Pasantía internacional: una experiencia que trasciende fronteras.\n\nFlorencia Luzko, estudiante de Ingeniería Empresarial de la Universidad Paraguayo Alemana (UPA).",
                "media_type": "CAROUSEL_ALBUM",
                "media_url": "https://scontent.cdninstagram.com/v/t39.30808-6/885659832_n.jpg",
                "permalink": "https://www.instagram.com/p/DfSG3s8jsFy/",
                "timestamp": "2026-11-03T14:34:17+0000",
            },
            {
                "id": "18105980801628640",
                "caption": "En el marco del módulo de Ética y Negocios Sociales en la UPA.\nTres charlas magistrales con referentes del ámbito empresarial.",
                "media_type": "CAROUSEL_ALBUM",
                "media_url": "https://scontent.cdninstagram.com/v/t39.30808-6/878081348_n.jpg",
                "permalink": "https://www.instagram.com/p/DfITcEbo0om/",
                "timestamp": "2026-10-30T19:11:42+0000",
            },
        ]
    }

    async def _graph_get(self, url, *args, **kwargs):
        called_urls.append(str(url))
        request = httpx.Request("GET", url)
        if "/me/accounts" in str(url):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "instagram_business_account": {"id": "17841402165726045"},
                            "id": "1430225163860663",
                        }
                    ]
                },
                request=request,
            )
        if "scontent.cdninstagram.com" in str(url):
            return httpx.Response(
                200,
                content=sample_jpg,
                headers={"content-type": "image/jpeg"},
                request=request,
            )
        return httpx.Response(200, json=real_payload, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", _graph_get)
    loop = asyncio.new_event_loop()
    db = TestingSessionLocal()
    try:
        # 1. Auto-Discovery (account_id leer) löst 17841402165726045 über v21.0/me/accounts auf und spiegelt Bilder lokal
        posts = loop.run_until_complete(service.fetch_from_graph_api(token="valid-token", account_id=""))
        assert len(posts) == 2
        assert any("https://graph.facebook.com/v21.0/me/accounts" in u for u in called_urls)
        assert any("https://graph.facebook.com/v21.0/17841402165726045/media" in u for u in called_urls)
        assert any("https://scontent.cdninstagram.com/v/t39.30808-6/885659832_n.jpg" in u for u in called_urls)
        assert posts[0].instagram_id == "18114511375879455"
        assert posts[0].permalink == "https://www.instagram.com/p/DfSG3s8jsFy/"
        assert posts[0].media_url == "/uploads/instagram/18114511375879455.jpg"
        assert posts[0].image_url == "/uploads/instagram/18114511375879455.jpg"
        assert posts[1].media_url == "/uploads/instagram/18105980801628640.jpg"
        assert posts[1].image_url == "/uploads/instagram/18105980801628640.jpg"

        # 2. Persistenz in DB & Fallback bei HTTP 401
        sync_res = service.sync_posts(db, posts, author_id=1)
        assert sync_res["created_count"] == 2

        async def _unauthorized_get(self, url, *args, **kwargs):
            return httpx.Response(
                401,
                json={"error": {"message": "Invalid OAuth access token.", "code": 190}},
                request=httpx.Request("GET", url),
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", _unauthorized_get)
        posts_401 = loop.run_until_complete(
            service.fetch_from_graph_api(token="expired-token", account_id="17841402165726045")
        )
        assert posts_401 == []

        # Bereits persistierte Beiträge bleiben mit lokalen Bildpfaden über /api/v1/feed abrufbar
        feed_res = client.get("/api/v1/feed")
        assert feed_res.status_code == 200
        feed_by_id = {p["instagram_id"]: p for p in feed_res.json()["posts"]}
        assert "18114511375879455" in feed_by_id
        assert "18105980801628640" in feed_by_id
        assert feed_by_id["18114511375879455"]["media_url"] == "/uploads/instagram/18114511375879455.jpg"
        assert feed_by_id["18114511375879455"]["image_url"] == "/uploads/instagram/18114511375879455.jpg"
        assert client.get("/uploads/instagram/18114511375879455.jpg").status_code == 200
    finally:
        db.close()
        loop.close()


def test_sync_posts_deduplicates_sociablekit_shortcode_and_graph_api_id(monkeypatch):
    import httpx

    sample_webp = b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x000\x01\x00\x9d\x01*\x01\x00\x01\x00\x00"
    sample_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    def _mock_get(url, *args, **kwargs):
        url_str = str(url)
        if url_str.endswith(".webp"):
            return httpx.Response(
                200,
                content=sample_webp,
                headers={"content-type": "image/webp"},
                request=httpx.Request("GET", url_str),
            )
        return httpx.Response(
            200,
            content=sample_jpg,
            headers={"content-type": "image/jpeg"},
            request=httpx.Request("GET", url_str),
        )

    monkeypatch.setattr(httpx, "get", _mock_get)

    service = InstagramSyncService()
    db = TestingSessionLocal()
    try:
        # 1. Bestehender SociableKIT-Eintrag mit Shortcode als instagram_id
        sk_item = NormalizedSocialPost(
            instagram_id="DfSG3s8jsFy",
            caption="Pasantía internacional UPA",
            media_type="carousel",
            media_url="https://data-image.sociablekit.com/old.webp",
            permalink="https://www.instagram.com/p/DfSG3s8jsFy/",
            timestamp=datetime.now(UTC),
        )
        res1 = service.sync_posts(db, [sk_item], author_id=1)
        assert res1["created_count"] == 1

        # 2. Graph API liefert denselben Post mit numerischer ID und identischem Permalink
        graph_item = NormalizedSocialPost(
            instagram_id="18114511375879455",
            caption="Pasantía internacional UPA (Graph API v21.0)",
            media_type="CAROUSEL_ALBUM",
            media_url="https://scontent.cdninstagram.com/v/fresh.jpg",
            permalink="https://www.instagram.com/p/DfSG3s8jsFy/",
            timestamp=datetime.now(UTC),
        )
        res2 = service.sync_posts(db, [graph_item], author_id=1)
        assert res2["created_count"] == 0
        assert res2["updated_count"] == 1

        all_posts = db.query(Post).filter(Post.permalink == "https://www.instagram.com/p/DfSG3s8jsFy/").all()
        assert len(all_posts) == 1
        assert all_posts[0].instagram_id == "18114511375879455"
        assert all_posts[0].media_url == "/uploads/instagram/18114511375879455.jpg"
        assert all_posts[0].image_url == "/uploads/instagram/18114511375879455.jpg"
    finally:
        db.close()


def test_existing_scontent_posts_migrated_to_local_uploads_and_timeout_does_not_abort_sync(monkeypatch):
    import httpx

    sample_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    service = InstagramSyncService()
    db = TestingSessionLocal()
    try:
        # 1. Bestehender Post in der DB mit flüchtiger scontent.cdninstagram.com URL
        legacy_post = Post(
            title="Jornada Académica UPA",
            caption="Jornada Académica UPA",
            content="Jornada Académica UPA en el campus.",
            post_type="INSTAGRAM",
            is_news=True,
            is_event=False,
            target_groups=["ALL"],
            instagram_id="17999888777666",
            media_type="IMAGE",
            media_url="https://scontent.cdninstagram.com/v/t51.2885-15/legacy_cdn.jpg?oe=654321",
            image_url="https://scontent.cdninstagram.com/v/t51.2885-15/legacy_cdn.jpg?oe=654321",
            permalink="https://www.instagram.com/p/Clegacy123/",
            link_url="https://www.instagram.com/p/Clegacy123/",
            link_label="Ver en Instagram",
            author_id=1,
            created_at=datetime.now(UTC),
            published_at=datetime.now(UTC),
        )
        db.add(legacy_post)
        db.commit()

        # 2. Beim Sync schlägt ein Bilddownload mit Timeout fehl, während andere (inkl. Bestands-Post) geladen werden
        def _selective_get(url, *args, **kwargs):
            url_str = str(url)
            if "timeout_media.jpg" in url_str:
                raise httpx.TimeoutException("Image download timed out after 10s")
            return httpx.Response(
                200,
                content=sample_jpg,
                headers={"content-type": "image/jpeg"},
                request=httpx.Request("GET", url_str),
            )

        monkeypatch.setattr(httpx, "get", _selective_get)

        timeout_item = NormalizedSocialPost(
            instagram_id="18000111222333",
            caption="Post con timeout en descarga de imagen",
            media_type="IMAGE",
            media_url="https://scontent.cdninstagram.com/v/t51.2885-15/timeout_media.jpg",
            permalink="https://www.instagram.com/p/Ctimeout1/",
            timestamp=datetime.now(UTC),
        )
        ok_item = NormalizedSocialPost(
            instagram_id="18000444555666",
            caption="Post con descarga local exitosa",
            media_type="IMAGE",
            media_url="https://scontent.cdninstagram.com/v/t51.2885-15/ok_media.jpg",
            permalink="https://www.instagram.com/p/Cok1/",
            timestamp=datetime.now(UTC),
        )

        sync_res = service.sync_posts(db, [timeout_item, ok_item], author_id=1)
        assert sync_res["status"] == "success"
        assert sync_res["created_count"] == 2
        # Der bestehende scontent-Post in der DB wurde im selben Durchlauf auf /uploads/instagram/ aktualisiert
        assert sync_res["updated_count"] == 1

        saved_legacy = db.query(Post).filter(Post.instagram_id == "17999888777666").first()
        assert saved_legacy is not None
        assert saved_legacy.media_url == "/uploads/instagram/17999888777666.jpg"
        assert saved_legacy.image_url == "/uploads/instagram/17999888777666.jpg"

        saved_ok = db.query(Post).filter(Post.instagram_id == "18000444555666").first()
        assert saved_ok is not None
        assert saved_ok.media_url == "/uploads/instagram/18000444555666.jpg"
        assert saved_ok.image_url == "/uploads/instagram/18000444555666.jpg"

        # Der Post mit Timeout wurde trotzdem erfolgreich in der Transaktion gespeichert
        saved_timeout = db.query(Post).filter(Post.instagram_id == "18000111222333").first()
        assert saved_timeout is not None
        assert saved_timeout.title == "Post con timeout en descarga de imagen"
    finally:
        db.close()
