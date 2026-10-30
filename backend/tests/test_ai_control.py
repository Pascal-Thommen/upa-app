"""Pruebas reales de configuracion de IA (Google Gemini) y prueba de conexion en vivo."""

import json
import socket
import threading
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
from src.models import AppSetting, User, UserRole

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
EDITOR_ID = 2
EDITOR_EMAIL = "editor.prensa@upa.edu.py"
STUDENT_ID = 3
STUDENT_EMAIL = "estudiante.test@upa.edu.py"


def auth(user_id: int, email: str, role: str) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id), "email": email, "role": role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def setup_database(monkeypatch):
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.query(AppSetting).delete()
    db.query(UserRole).delete()
    db.query(User).delete()
    db.add_all(
        [
            User(id=ADMIN_ID, email=ADMIN_EMAIL, full_name="Pascal Thommen", role="admin"),
            User(id=EDITOR_ID, email=EDITOR_EMAIL, full_name="Editor Prensa", role="editor"),
            User(id=STUDENT_ID, email=STUDENT_EMAIL, full_name="Estudiante Test", role="user"),
            UserRole(
                id=1,
                email=ADMIN_EMAIL,
                name="Pascal Thommen",
                role="admin",
                permissions=["publicaciones", "grupos", "roles", "apis", "historial"],
                is_primary=True,
            ),
            UserRole(
                id=2,
                email=EDITOR_EMAIL,
                name="Editor Prensa",
                role="editor",
                permissions=["publicaciones", "apis"],
                is_primary=False,
            ),
        ]
    )
    db.commit()
    db.close()
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-1.5-flash")
    yield
    app.dependency_overrides.clear()


def test_ai_config_permissions_and_persistence(monkeypatch):
    # Sin autenticacion -> 401
    assert client.get("/api/ai/config").status_code == 401
    assert client.post("/api/ai/config", json={"api_key": "AIzaSyKey1234567890"}).status_code == 401

    # Estudiante regular -> 403
    student_headers = auth(STUDENT_ID, STUDENT_EMAIL, "user")
    assert client.get("/api/ai/config", headers=student_headers).status_code == 403
    assert client.post("/api/ai/config", json={"api_key": "AIzaSyKey1234567890"}, headers=student_headers).status_code == 403

    # Editor con permiso 'apis' puede consultar estado (200), pero no modificar ni probar la clave (403)
    editor_headers = auth(EDITOR_ID, EDITOR_EMAIL, "editor")
    assert client.get("/api/ai/config", headers=editor_headers).status_code == 200
    assert client.post("/api/ai/config", json={"api_key": "AIzaSyKey1234567890"}, headers=editor_headers).status_code == 403
    assert client.post("/api/ai/test-connection", headers=editor_headers).status_code == 403

    admin_headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")

    # Estado inicial sin configurar
    initial = client.get("/api/ai/config", headers=admin_headers).json()
    assert initial == {
        "configured": False,
        "masked_key": "",
        "source": "none",
        "model": "gemini-1.5-flash",
    }

    # Fallback a variable de entorno GEMINI_API_KEY cuando no hay registro en base de datos
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "AIzaEnvFallbackKey9876")
    env_state = client.get("/api/ai/config", headers=admin_headers).json()
    assert env_state["configured"] is True
    assert env_state["source"] == "environment"
    assert env_state["masked_key"] == "AIza********9876"

    # Clave invalida (corta o con espacios) -> 422
    bad_short = client.post("/api/ai/config", json={"api_key": "abc"}, headers=admin_headers)
    assert bad_short.status_code == 422
    bad_space = client.post("/api/ai/config", json={"api_key": "AIza con espacios 1234"}, headers=admin_headers)
    assert bad_space.status_code == 422

    # Guardar clave en base de datos tiene prioridad sobre la variable de entorno
    saved = client.post(
        "/api/ai/config",
        json={"api_key": "AIzaDatabaseKeyABCD1234"},
        headers=admin_headers,
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["configured"] is True
    assert body["source"] == "database"
    assert body["masked_key"] == "AIza********1234"
    assert body["model"] == "gemini-1.5-flash"

    # Actualizar clave existente
    updated = client.post(
        "/api/ai/config",
        json={"api_key": "AIzaUpdatedKeyWXYZ5678"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["masked_key"] == "AIza********5678"


def test_ai_live_connection_against_local_gemini_stub(monkeypatch):
    received_requests: list[dict] = []
    next_response = {"status": 200, "body": {"candidates": [{"content": {"parts": [{"text": "pong"}]}}]}}

    class GeminiStubHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            received_requests.append(
                {
                    "path": self.path,
                    "api_key": self.headers.get("x-goog-api-key", ""),
                    "body": json.loads(raw),
                }
            )
            payload = json.dumps(next_response["body"]).encode("utf-8")
            self.send_response(next_response["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), GeminiStubHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setattr(settings, "GEMINI_API_BASE_URL", f"http://127.0.0.1:{port}")
        admin_headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")

        # 1. Sin clave configurada -> NO_KEY
        no_key = client.post("/api/ai/test-connection", headers=admin_headers).json()
        assert no_key["ok"] is False
        assert no_key["code"] == "NO_KEY"

        # 2. Guardar clave y probar exito (200 OK)
        client.post("/api/ai/config", json={"api_key": "AIzaValidLiveKey1234"}, headers=admin_headers)
        ok_res = client.post("/api/ai/test-connection", headers=admin_headers)
        assert ok_res.status_code == 200
        ok_body = ok_res.json()
        assert ok_body["ok"] is True
        assert ok_body["code"] == "OK"
        assert ok_body["message"] == "Conexión exitosa con Google Gemini (Modelo gemini-1.5-flash listo)"
        assert len(received_requests) == 1
        assert received_requests[0]["path"] == "/v1beta/models/gemini-1.5-flash:generateContent"
        assert received_requests[0]["api_key"] == "AIzaValidLiveKey1234"
        assert received_requests[0]["body"]["contents"][0]["parts"][0]["text"] == "ping"

        # 3. Clave invalida o expirada (400 API_KEY_INVALID)
        next_response["status"] = 400
        next_response["body"] = {
            "error": {
                "code": 400,
                "message": "API key not valid.",
                "status": "INVALID_ARGUMENT",
                "details": [{"reason": "API_KEY_INVALID"}],
            }
        }
        invalid_res = client.post("/api/ai/test-connection", headers=admin_headers).json()
        assert invalid_res["ok"] is False
        assert invalid_res["code"] == "INVALID_KEY"
        assert "Clave de API inválida o expirada" in invalid_res["message"]

        # 4. Cuota agotada (429 RESOURCE_EXHAUSTED)
        next_response["status"] = 429
        next_response["body"] = {
            "error": {
                "code": 429,
                "message": "Resource has been exhausted",
                "status": "RESOURCE_EXHAUSTED",
            }
        }
        quota_res = client.post("/api/ai/test-connection", headers=admin_headers).json()
        assert quota_res["ok"] is False
        assert quota_res["code"] == "QUOTA"
        assert "Límite de cuota gratuito agotado (Quota exceeded)" in quota_res["message"]

        # 5. Error 503 del servidor de Google
        next_response["status"] = 503
        next_response["body"] = {"error": {"code": 503, "message": "Service unavailable"}}
        err503 = client.post("/api/ai/test-connection", headers=admin_headers).json()
        assert err503["ok"] is False
        assert err503["code"] == "GOOGLE_ERROR"
        assert "Error de red con Google" in err503["message"]
    finally:
        server.shutdown()
        server.server_close()


def test_ai_live_connection_network_and_timeout(monkeypatch):
    admin_headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")
    client.post("/api/ai/config", json={"api_key": "AIzaValidLiveKey1234"}, headers=admin_headers)

    # Puerto cerrado -> error de red con Google
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        closed_port = s.getsockname()[1]

    monkeypatch.setattr(settings, "GEMINI_API_BASE_URL", f"http://127.0.0.1:{closed_port}")
    monkeypatch.setattr(settings, "GEMINI_TIMEOUT_SECONDS", 0.5)
    net_res = client.post("/api/ai/test-connection", headers=admin_headers).json()
    assert net_res["ok"] is False
    assert net_res["code"] == "NETWORK"
    assert "Error de red con Google" in net_res["message"]

    # Servidor colgado -> timeout
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

    t = threading.Thread(target=accept_and_hold, daemon=True)
    t.start()
    try:
        monkeypatch.setattr(settings, "GEMINI_API_BASE_URL", f"http://127.0.0.1:{hanging_port}")
        monkeypatch.setattr(settings, "GEMINI_TIMEOUT_SECONDS", 0.15)
        timeout_res = client.post("/api/ai/test-connection", headers=admin_headers).json()
        assert timeout_res["ok"] is False
        assert timeout_res["code"] == "TIMEOUT"
        assert "Error de red con Google" in timeout_res["message"]
    finally:
        for c in accepted:
            c.close()
        hanging_sock.close()
