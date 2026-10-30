"""Pruebas integrales de extraccion multimodal de eventos con Gemini en Instagram Sync (SRV-180)."""

import base64
import json
import socket
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.config import settings
from src.database import Base, get_db
from src.main import app
from src.models import AppSetting, AudienceGroup, Post, User, UserRole
from src.services.ai_extractor import (
    AIEventExtractionResult,
    enforce_same_day_rule,
    extract_event_from_instagram_post,
)
from src.services.instagram import InstagramSyncService, NormalizedSocialPost

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)

ADMIN_ID = 1
ADMIN_EMAIL = "pascal.thommen@upa.edu.py"

SAMPLE_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def auth_headers() -> dict[str, str]:
    token = create_access_token({"sub": str(ADMIN_ID), "email": ADMIN_EMAIL, "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def setup_database(monkeypatch):
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.query(Post).delete()
    db.query(AppSetting).delete()
    db.query(AudienceGroup).delete()
    db.query(UserRole).delete()
    db.query(User).delete()
    db.add_all(
        [
            User(id=ADMIN_ID, email=ADMIN_EMAIL, full_name="Pascal Thommen", role="admin"),
            UserRole(
                id=1,
                email=ADMIN_EMAIL,
                name="Pascal Thommen",
                role="admin",
                permissions=["publicaciones", "grupos", "roles", "apis", "historial"],
                is_primary=True,
            ),
            AudienceGroup(
                id="estudiantes",
                name="Estudiantes",
                google_group="estudiantes@upa.edu.py",
                google_groups=["estudiantes@upa.edu.py"],
                emails=[],
            ),
            AudienceGroup(
                id="docentes",
                name="Docentes",
                google_group="docentes@upa.edu.py",
                google_groups=["docentes@upa.edu.py"],
                emails=[],
            ),
        ]
    )
    db.commit()
    db.close()
    monkeypatch.setattr(settings, "AI_EVENT_EXTRACTION_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-1.5-flash")
    yield
    app.dependency_overrides.clear()


def test_plausibility_rule_same_calendar_day():
    # Mismo dia calendario -> conserva end_time
    same_day = AIEventExtractionResult(
        is_event=True,
        event_title="Foro de Innovación UPA",
        start_time="2026-11-15T18:00:00-03:00",
        end_time="2026-11-15T20:30:00-03:00",
        location="Aula Magna",
        allow_registration=True,
        target_groups=["estudiantes"],
        notify_push=True,
    )
    assert same_day.is_event is True
    assert same_day.start_time == "2026-11-15T18:00:00-03:00"
    assert same_day.end_time == "2026-11-15T20:30:00-03:00"

    # Fin en dia siguiente -> end_time se filtra estrictamente a None
    next_day = AIEventExtractionResult(
        is_event=True,
        event_title="Congreso Multidia",
        start_time="2026-11-15T09:00:00-03:00",
        end_time="2026-11-16T18:00:00-03:00",
        location="Campus UPA",
        allow_registration=False,
        target_groups=[],
        notify_push=False,
    )
    assert next_day.is_event is True
    assert next_day.start_time == "2026-11-15T09:00:00-03:00"
    assert next_day.end_time is None

    # Fin anterior al inicio en el mismo dia -> end_time se filtra a None
    reversed_hours = AIEventExtractionResult(
        is_event=True,
        event_title="Taller",
        start_time="2026-11-15T18:00:00Z",
        end_time="2026-11-15T16:00:00Z",
    )
    assert reversed_hours.end_time is None
    assert enforce_same_day_rule("2026-11-15T10:00:00Z", "2026-11-16T10:00:00Z") is None


def test_multimodal_event_extraction_and_direct_publication_on_sync(monkeypatch):
    captured_gemini_calls: list[dict] = []
    gemini_json_queue: list[tuple[int, dict]] = []

    class MultimodalStubHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/media/flyer.png"):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(SAMPLE_PNG_BYTES)))
                self.end_headers()
                self.wfile.write(SAMPLE_PNG_BYTES)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            captured_gemini_calls.append(
                {
                    "path": self.path,
                    "api_key": self.headers.get("x-goog-api-key", ""),
                    "body": json.loads(raw),
                }
            )
            status_code, body_dict = gemini_json_queue.pop(0)
            payload = json.dumps(body_dict).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), MultimodalStubHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{port}"
        monkeypatch.setattr(settings, "GEMINI_API_BASE_URL", base_url)
        client.post(
            "/api/ai/config",
            json={"api_key": "AIzaMultimodalLiveKey9999"},
            headers=auth_headers(),
        )

        # Caso 1: Evento detectado con start_time y end_time en el mismo dia + grupos conservadores + push
        gemini_json_queue.append(
            (
                200,
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "is_event": True,
                                                "event_title": "Charla Magistral de IA Aplicada",
                                                "start_time": "2026-11-20T18:00:00Z",
                                                "end_time": "2026-11-20T20:00:00Z",
                                                "location": "Aula Magna UPA",
                                                "allow_registration": True,
                                                "target_groups": ["estudiantes"],
                                                "notify_push": True,
                                            }
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        )

        # Caso 2: Evento con end_time en el dia siguiente (debe filtrarse end_time a None) y sin push
        gemini_json_queue.append(
            (
                200,
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "is_event": True,
                                                "event_title": "Hackathon UPA",
                                                "start_time": "2026-11-25T14:00:00Z",
                                                "end_time": "2026-11-26T18:00:00Z",
                                                "location": "Campus UPA",
                                                "allow_registration": False,
                                                "target_groups": [],
                                                "notify_push": False,
                                            }
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        )

        # Caso 3: Publicacion normal que NO es un evento (is_event=False)
        gemini_json_queue.append(
            (
                200,
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "is_event": False,
                                                "event_title": None,
                                                "start_time": None,
                                                "end_time": None,
                                                "location": None,
                                                "allow_registration": False,
                                                "target_groups": [],
                                                "notify_push": False,
                                            }
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        )

        service = InstagramSyncService()
        db = TestingSessionLocal()
        posts_input = [
            NormalizedSocialPost(
                instagram_id="ig_ai_event_1",
                caption="Te esperamos este viernes 20/11 a las 18:00 en el Aula Magna para la Charla de IA.",
                media_type="IMAGE",
                media_url=f"{base_url}/media/flyer.png",
                permalink="https://www.instagram.com/p/ai_event_1/",
                timestamp=datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
            ),
            NormalizedSocialPost(
                instagram_id="ig_ai_event_2",
                caption="Hackathon UPA desde el 25 de noviembre a las 14:00 hs.",
                media_type="IMAGE",
                media_url=f"{base_url}/media/flyer.png",
                permalink="https://www.instagram.com/p/ai_event_2/",
                timestamp=datetime(2026, 11, 10, 13, 0, tzinfo=UTC),
            ),
            NormalizedSocialPost(
                instagram_id="ig_regular_news_3",
                caption="Felicitamos a nuestros graduados de la promoción 2026.",
                media_type="IMAGE",
                media_url=f"{base_url}/media/flyer.png",
                permalink="https://www.instagram.com/p/news_3/",
                timestamp=datetime(2026, 11, 10, 14, 0, tzinfo=UTC),
            ),
        ]

        result = service.sync_posts(db, posts_input, author_id=ADMIN_ID)
        assert result["status"] == "success"
        assert result["created_count"] == 3
        assert result["ai_events_count"] == 2

        # Verificar que Gemini recibio tanto el texto (caption) como los bytes de la imagen (inline_data)
        assert len(captured_gemini_calls) == 3
        first_parts = captured_gemini_calls[0]["body"]["contents"][0]["parts"]
        assert len(first_parts) == 2
        assert "Aula Magna" in first_parts[0]["text"]
        assert first_parts[1]["inline_data"]["mime_type"] == "image/png"
        assert base64.b64decode(first_parts[1]["inline_data"]["data"]) == SAMPLE_PNG_BYTES

        # Verificar Post 1: Evento publicado directamente (sin borrador) con badge IA
        ev1 = db.query(Post).filter(Post.instagram_id == "ig_ai_event_1").first()
        assert ev1 is not None
        assert ev1.is_event is True
        assert ev1.is_news is True
        assert ev1.is_ai_generated is True
        assert ev1.status == "ai"
        assert ev1.title == "Charla Magistral de IA Aplicada"
        assert ev1.location == "Aula Magna UPA"
        assert ev1.event_location == "Aula Magna UPA"
        assert ev1.has_registration is True
        assert ev1.target_groups == ["estudiantes"]
        assert ev1.send_push_notification is True
        assert ev1.notify_push is True
        assert ev1.notify_groups == ["estudiantes"]
        assert ev1.event_notify_groups == ["estudiantes"]
        assert ev1.event_start.replace(tzinfo=UTC) == datetime(2026, 11, 20, 18, 0, tzinfo=UTC)
        assert ev1.event_end.replace(tzinfo=UTC) == datetime(2026, 11, 20, 20, 0, tzinfo=UTC)

        # Verificar Post 2: End date en dia distinto fue filtrado a None
        ev2 = db.query(Post).filter(Post.instagram_id == "ig_ai_event_2").first()
        assert ev2 is not None
        assert ev2.is_event is True
        assert ev2.is_ai_generated is True
        assert ev2.event_start.replace(tzinfo=UTC) == datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
        assert ev2.event_end is None
        assert ev2.event_end_date is None
        assert ev2.target_groups == ["ALL"]
        assert ev2.send_push_notification is False
        assert ev2.notify_groups == []

        # Verificar Post 3: Noticia normal de Instagram
        news3 = db.query(Post).filter(Post.instagram_id == "ig_regular_news_3").first()
        assert news3 is not None
        assert news3.is_event is False
        assert news3.is_news is True
        assert news3.is_ai_generated is False
        assert news3.status == "pending"
        assert news3.event_start is None
        db.close()

        # Verificar API /api/publications expone is_ai_generated=True y status='ai'
        pubs_res = client.get("/api/publications", headers=auth_headers())
        assert pubs_res.status_code == 200
        pubs_by_ig = {p["instagram_id"]: p for p in pubs_res.json()}
        assert pubs_by_ig["ig_ai_event_1"]["is_ai_generated"] is True
        assert pubs_by_ig["ig_ai_event_1"]["status"] == "ai"
        assert pubs_by_ig["ig_ai_event_2"]["event_end"] is None
        assert pubs_by_ig["ig_regular_news_3"]["is_ai_generated"] is False
        assert pubs_by_ig["ig_regular_news_3"]["status"] == "pending"
    finally:
        server.shutdown()
        server.server_close()


def test_fallback_when_ai_disabled_or_quota_or_timeout(monkeypatch):
    service = InstagramSyncService()
    db = TestingSessionLocal()

    # 1. Sin clave de Gemini configurada (IA desactivada) -> Fallback sin error
    res_no_key = service.sync_posts(
        db,
        [
            NormalizedSocialPost(
                instagram_id="ig_fallback_no_key",
                caption="Conferencia Anual UPA\nMañana a las 10:00 hs.",
                media_type="IMAGE",
                media_url="https://upa.edu.py/static/conf.jpg",
                permalink="https://www.instagram.com/p/no_key/",
            )
        ],
    )
    assert res_no_key["status"] == "success"
    assert res_no_key["created_count"] == 1
    assert res_no_key["ai_events_count"] == 0
    post_no_key = db.query(Post).filter(Post.instagram_id == "ig_fallback_no_key").first()
    assert post_no_key is not None
    assert post_no_key.is_news is True
    assert post_no_key.is_event is False
    assert post_no_key.is_ai_generated is False

    # 2. Clave configurada pero AI_EVENT_EXTRACTION_ENABLED=False -> Fallback inmediato
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "AIzaConfiguredButDisabledKey")
    monkeypatch.setattr(settings, "AI_EVENT_EXTRACTION_ENABLED", False)
    disabled_ext = extract_event_from_instagram_post("Evento mañana 10 hs", db=db)
    assert disabled_ext.is_event is False

    # 3. Error HTTP 429 Quota Exceeded en Gemini -> Fallback limpio como News-Post
    monkeypatch.setattr(settings, "AI_EVENT_EXTRACTION_ENABLED", True)

    class QuotaHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.dumps(
                {"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
            ).encode("utf-8")
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            return

    quota_server = HTTPServer(("127.0.0.1", 0), QuotaHandler)
    quota_port = quota_server.server_address[1]
    threading.Thread(target=quota_server.serve_forever, daemon=True).start()

    try:
        monkeypatch.setattr(settings, "GEMINI_API_BASE_URL", f"http://127.0.0.1:{quota_port}")
        res_quota = service.sync_posts(
            db,
            [
                NormalizedSocialPost(
                    instagram_id="ig_fallback_quota",
                    caption="Seminario Internacional UPA\nViernes 19:00 hs.",
                    media_type="IMAGE",
                    media_url="",
                    permalink="https://www.instagram.com/p/quota/",
                )
            ],
        )
        assert res_quota["status"] == "success"
        assert res_quota["created_count"] == 1
        assert res_quota["ai_events_count"] == 0
        post_quota = db.query(Post).filter(Post.instagram_id == "ig_fallback_quota").first()
        assert post_quota is not None
        assert post_quota.is_news is True
        assert post_quota.is_event is False
        assert post_quota.is_ai_generated is False
    finally:
        quota_server.shutdown()
        quota_server.server_close()

    # 4. Timeout de red contra Gemini -> Fallback limpio sin abortar sincronizacion
    hanging_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    hanging_sock.bind(("127.0.0.1", 0))
    hanging_sock.listen(1)
    hanging_port = hanging_sock.getsockname()[1]
    accepted = []

    def accept_and_hold():
        try:
            conn, _ = hanging_sock.accept()
            accepted.append(conn)
        except OSError:
            pass

    threading.Thread(target=accept_and_hold, daemon=True).start()
    try:
        monkeypatch.setattr(settings, "GEMINI_API_BASE_URL", f"http://127.0.0.1:{hanging_port}")
        monkeypatch.setattr(settings, "GEMINI_TIMEOUT_SECONDS", 0.15)
        res_timeout = service.sync_posts(
            db,
            [
                NormalizedSocialPost(
                    instagram_id="ig_fallback_timeout",
                    caption="Jornada de Puertas Abiertas UPA\nSábado 09:00 hs.",
                    media_type="IMAGE",
                    media_url="",
                    permalink="https://www.instagram.com/p/timeout/",
                )
            ],
        )
        assert res_timeout["status"] == "success"
        assert res_timeout["created_count"] == 1
        assert res_timeout["ai_events_count"] == 0
        post_timeout = db.query(Post).filter(Post.instagram_id == "ig_fallback_timeout").first()
        assert post_timeout is not None
        assert post_timeout.is_news is True
        assert post_timeout.is_event is False
        assert post_timeout.is_ai_generated is False
    finally:
        for conn in accepted:
            conn.close()
        hanging_sock.close()
        db.close()
