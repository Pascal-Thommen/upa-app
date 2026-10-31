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
PUB_ONLY_ID = 4
PUB_ONLY_EMAIL = "redactor.solo@upa.edu.py"


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
            User(id=PUB_ONLY_ID, email=PUB_ONLY_EMAIL, full_name="Redactor Solo", role="admin"),
            UserRole(
                id=1,
                email=ADMIN_EMAIL,
                name="Pascal Thommen",
                permissions=["publicaciones", "grupos", "roles", "apis", "historial"],
                is_primary=True,
            ),
            UserRole(
                id=2,
                email=EDITOR_EMAIL,
                name="Editor Prensa",
                permissions=["publicaciones", "apis"],
                is_primary=False,
            ),
            UserRole(
                id=3,
                email=PUB_ONLY_EMAIL,
                name="Redactor Solo Publicaciones",
                permissions=["publicaciones"],
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

    # Estudiante regular sin permisos -> 403
    student_headers = auth(STUDENT_ID, STUDENT_EMAIL, "user")
    assert client.get("/api/ai/config", headers=student_headers).status_code == 403
    assert client.post("/api/ai/config", json={"api_key": "AIzaSyKey1234567890"}, headers=student_headers).status_code == 403

    # Cuenta con permiso 'publicaciones' pero SIN 'apis' (incluso con role='admin' en User) -> puede leer GET (200), pero NO modificar ni probar (403)
    pub_only_headers = auth(PUB_ONLY_ID, PUB_ONLY_EMAIL, "admin")
    assert client.get("/api/ai/config", headers=pub_only_headers).status_code == 200
    assert client.post("/api/ai/config", json={"api_key": "AIzaSyKey1234567890"}, headers=pub_only_headers).status_code == 403
    assert client.post("/api/ai/system-prompt", json={"system_prompt_autocomplete": "Test"}, headers=pub_only_headers).status_code == 403
    assert client.post("/api/ai/test-connection", headers=pub_only_headers).status_code == 403

    # Editor con permiso 'apis' (role='editor', sin rol admin) PUEDE consultar y gestionar la configuracion de IA (200)
    editor_headers = auth(EDITOR_ID, EDITOR_EMAIL, "editor")
    assert client.get("/api/ai/config", headers=editor_headers).status_code == 200
    editor_save = client.post(
        "/api/ai/config",
        json={
            "api_key": "AIzaEditorKeyWithApisPerm1",
            "system_prompt_autocomplete": "Prompt autocomplete guardado por operador con permiso apis.",
            "system_prompt_instagram": "Prompt instagram guardado por operador con permiso apis.",
        },
        headers=editor_headers,
    )
    assert editor_save.status_code == 200
    assert editor_save.json()["masked_key"] == "AIza********erm1"
    assert editor_save.json()["system_prompt_autocomplete"] == "Prompt autocomplete guardado por operador con permiso apis."
    assert editor_save.json()["system_prompt_instagram"] == "Prompt instagram guardado por operador con permiso apis."

    # Resetear la base de datos de AppSetting para verificar estado inicial limpio
    db = TestingSessionLocal()
    db.query(AppSetting).delete()
    db.commit()
    db.close()

    admin_headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")

    # Estado inicial sin configurar
    initial = client.get("/api/ai/config", headers=admin_headers).json()
    assert initial["configured"] is False
    assert initial["masked_key"] == ""
    assert initial["source"] == "none"
    assert initial["model"] == "gemini-1.5-flash"
    assert initial["quota_rpm"] == 15
    assert "Universidad Paraguayo Alemana" in initial["system_prompt"]
    assert "Universidad Paraguayo Alemana" in initial["system_prompt_autocomplete"]
    assert "Instagram" in initial["system_prompt_instagram"]

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

    # Prompts demasiado largos (>4000 caracteres) -> 422
    too_long = "X" * 4001
    assert (
        client.post(
            "/api/ai/config",
            json={"system_prompt_autocomplete": too_long},
            headers=admin_headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/ai/config",
            json={"system_prompt_instagram": too_long},
            headers=admin_headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/ai/system-prompt",
            json={"system_prompt_instagram": too_long},
            headers=admin_headers,
        ).status_code
        == 422
    )

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

    # Actualizar clave existente y ambos System Prompts personalizados de forma independiente
    updated = client.post(
        "/api/ai/config",
        json={
            "api_key": "AIzaUpdatedKeyWXYZ5678",
            "system_prompt_autocomplete": "Instrucción personalizada UPA: priorizar tono académico formal.",
            "system_prompt_instagram": "Directriz exclusiva para análisis de flyers de Instagram UPA.",
        },
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["masked_key"] == "AIza********5678"
    assert updated.json()["system_prompt"] == "Instrucción personalizada UPA: priorizar tono académico formal."
    assert updated.json()["system_prompt_autocomplete"] == "Instrucción personalizada UPA: priorizar tono académico formal."
    assert updated.json()["system_prompt_instagram"] == "Directriz exclusiva para análisis de flyers de Instagram UPA."

    # Actualizar únicamente system_prompt_autocomplete sin alterar la clave ni system_prompt_instagram
    prompt_auto_only = client.post(
        "/api/ai/config",
        json={"system_prompt_autocomplete": "Prompt editorial exclusivo UPA 2026."},
        headers=admin_headers,
    )
    assert prompt_auto_only.status_code == 200
    assert prompt_auto_only.json()["masked_key"] == "AIza********5678"
    assert prompt_auto_only.json()["system_prompt_autocomplete"] == "Prompt editorial exclusivo UPA 2026."
    assert prompt_auto_only.json()["system_prompt_instagram"] == "Directriz exclusiva para análisis de flyers de Instagram UPA."

    # Actualizar únicamente system_prompt_instagram sin alterar system_prompt_autocomplete
    prompt_ig_only = client.post(
        "/api/ai/config",
        json={"system_prompt_instagram": "Prompt multimodal Instagram actualizado 2026."},
        headers=admin_headers,
    )
    assert prompt_ig_only.status_code == 200
    assert prompt_ig_only.json()["system_prompt_autocomplete"] == "Prompt editorial exclusivo UPA 2026."
    assert prompt_ig_only.json()["system_prompt_instagram"] == "Prompt multimodal Instagram actualizado 2026."


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


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_publication_autocomplete_ai_multimodal_fills_only_empty_fields(monkeypatch, tmp_path):
    received_requests: list[dict] = []
    stub_suggestions = {
        "title": "Título sugerido por IA que NO debe sobreescribir",
        "caption": "Resumen generado por IA",
        "content": "Contenido que NO debe sobreescribir",
        "is_event": True,
        "event_start": "2026-11-20T18:30",
        "event_end": "2026-11-20T20:30",
        "location": "Auditorio Principal UPA",
        "target_groups": ["TIE", "TI"],
        "has_registration": True,
    }
    next_response = {
        "status": 200,
        "body": {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(stub_suggestions, ensure_ascii=False)}],
                    }
                }
            ]
        },
    }

    class GeminiAutocompleteStubHandler(BaseHTTPRequestHandler):
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

    server = HTTPServer(("127.0.0.1", 0), GeminiAutocompleteStubHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setattr(settings, "GEMINI_API_BASE_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))

        admin_headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")
        editor_headers = auth(EDITOR_ID, EDITOR_EMAIL, "editor")
        student_headers = auth(STUDENT_ID, STUDENT_EMAIL, "user")

        # 1. Permisos: sin auth -> 401, estudiante -> 403
        assert client.post("/api/publications/autocomplete-ai", json={"title": "Test"}).status_code == 401
        assert (
            client.post("/api/publications/autocomplete-ai", json={"title": "Test"}, headers=student_headers).status_code
            == 403
        )

        # 2. Sin clave de IA configurada -> 400 con mensaje claro de Control de IA
        no_key_res = client.post(
            "/api/publications/autocomplete-ai",
            json={"title": "Charla IA", "content": "El 20/11 a las 18:30 en el Auditorio Principal"},
            headers=editor_headers,
        )
        assert no_key_res.status_code == 400
        assert (
            "No se pudo autocompletar: Verifique la clave de IA en Control de IA" in no_key_res.json()["detail"]
        )

        # 3. Configurar clave de IA y prompt personalizado, y subir imagen real a /api/media/upload
        client.post(
            "/api/ai/config",
            json={
                "api_key": "AIzaValidAutocompleteKey99",
                "system_prompt": "Directriz editorial personalizada de prueba UPA.",
            },
            headers=admin_headers,
        )
        upload_res = client.post(
            "/api/media/upload",
            files={"file": ("flyer.png", PNG_1X1, "image/png")},
            headers=editor_headers,
        )
        assert upload_res.status_code == 201
        media_url = upload_res.json()["url"]

        # 4. Autocompletar con JSON + media_url: title y content ya tienen valor, el resto está vacío
        auto_res = client.post(
            "/api/publications/autocomplete-ai",
            json={
                "title": "Foro Anual de Ingeniería (Título del Usuario)",
                "caption": "",
                "content": "Invitamos a estudiantes de TIE y TI el 20 de noviembre a las 18:30 hs.",
                "location": "",
                "event_start": "",
                "event_end": "",
                "target_groups": [],
                "media_url": media_url,
            },
            headers=editor_headers,
        )
        assert auto_res.status_code == 200
        suggestions = auto_res.json()

        # Los campos ya ingresados por el usuario (title, content) NO se sobreescriben
        assert "title" not in suggestions
        assert "content" not in suggestions

        # Los campos vacíos sí se completan
        assert suggestions["caption"] == "Resumen generado por IA"
        assert suggestions["is_event"] is True
        assert suggestions["event_start"] == "2026-11-20T18:30"
        assert suggestions["event_end"] == "2026-11-20T20:30"
        assert suggestions["location"] == "Auditorio Principal UPA"
        assert suggestions["target_groups"] == ["TIE", "TI"]
        assert suggestions["has_registration"] is True

        # Verificar que Gemini recibió tanto el prompt personalizado como la imagen inline_data en base64
        assert len(received_requests) == 1
        parts = received_requests[0]["body"]["contents"][0]["parts"]
        assert len(parts) == 2
        assert "Directriz editorial personalizada de prueba UPA." in parts[0]["text"]
        assert "Foro Anual de Ingeniería" in parts[0]["text"]
        assert parts[1]["inline_data"]["mime_type"] == "image/png"
        assert len(parts[1]["inline_data"]["data"]) > 10

        # 5. Autocompletar vía multipart/form-data con archivo directo y location/target_groups ya fijados
        multipart_res = client.post(
            "/api/publications/autocomplete-ai",
            data={
                "data": json.dumps(
                    {
                        "title": "",
                        "content": "Texto en afiche",
                        "location": "Campus San Lorenzo (Fijado por usuario)",
                        "target_groups": ["PI"],
                    }
                )
            },
            files={"file": ("afiche.png", PNG_1X1, "image/png")},
            headers=editor_headers,
        )
        assert multipart_res.status_code == 200
        mp_body = multipart_res.json()
        assert mp_body["title"] == "Título sugerido por IA que NO debe sobreescribir"
        assert "location" not in mp_body
        assert "target_groups" not in mp_body
        assert mp_body["event_start"] == "2026-11-20T18:30"

        # 6. Error de cuota o clave inválida en Gemini durante autocompletado -> mensaje claro
        next_response["status"] = 403
        next_response["body"] = {"error": {"code": 403, "message": "Invalid key", "status": "PERMISSION_DENIED"}}
        err_res = client.post(
            "/api/publications/autocomplete-ai",
            json={"title": "Prueba error"},
            headers=editor_headers,
        )
        assert err_res.status_code == 400
        assert "No se pudo autocompletar: Verifique la clave de IA en Control de IA" in err_res.json()["detail"]

        # 7. Prompt de sistema configurable: guardar en DB y verificar su uso en Gemini
        custom_prompt = "Usa tono formal académico y resume en una sola oración."
        prompt_res = client.post(
            "/api/ai/system-prompt",
            json={"system_prompt": custom_prompt},
            headers=admin_headers,
        )
        assert prompt_res.status_code == 200
        assert prompt_res.json()["system_prompt"] == custom_prompt

        next_response["status"] = 200
        next_response["body"] = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "title": "Jornada con Prompt Personalizado",
                                        "event_start": "2026-11-26T10:00",
                                        "event_end": "2026-11-27T18:00",  # dia distinto -> debe descartarse
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        ]
                    }
                }
            ]
        }
        auto_custom = client.post(
            "/api/publications/autocomplete-ai",
            json={"title": "", "content": "Jornada el 26/11"},
            headers=editor_headers,
        )
        assert auto_custom.status_code == 200
        custom_body = auto_custom.json()
        assert custom_body["title"] == "Jornada con Prompt Personalizado"
        assert custom_body["event_date"] == "26/11/2026"
        assert custom_body["event_start_time"] == "10:00"
        assert "event_end" not in custom_body
        assert "event_end_time" not in custom_body
        assert received_requests[-1]["body"]["systemInstruction"]["parts"][0]["text"] == custom_prompt
    finally:
        server.shutdown()
        server.server_close()


def test_gemini_automatic_latest_free_flash_model_discovery(monkeypatch):
    """
    Verifica que el backend consulta GET /v1beta/models y selecciona automaticamente
    el modelo Gemini Flash gratuito mas reciente disponible (ej. gemini-2.5-flash),
    devolviendo su nombre como estado en /api/ai/test-connection y /api/ai/config.
    """
    post_paths: list[str] = []

    class DiscoveryStubHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/v1beta/models"):
                catalog = {
                    "models": [
                        {
                            "name": "models/gemini-1.5-flash",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {
                            "name": "models/gemini-2.0-flash",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {
                            "name": "models/gemini-2.5-flash",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {
                            "name": "models/gemini-2.5-pro",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                    ]
                }
                payload = json.dumps(catalog).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            post_paths.append(self.path)
            payload = json.dumps({"candidates": [{"content": {"parts": [{"text": "pong"}]}}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), DiscoveryStubHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setattr(settings, "GEMINI_API_BASE_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-1.5-flash")
        admin_headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")

        client.post("/api/ai/config", json={"api_key": "AIzaAutoDiscoveryFlashKey123"}, headers=admin_headers)
        test_res = client.post("/api/ai/test-connection", headers=admin_headers)
        assert test_res.status_code == 200
        body = test_res.json()
        assert body["ok"] is True
        assert body["model"] == "gemini-2.5-flash"
        assert body["quota_rpm"] == 15
        assert "gemini-2.5-flash" in body["message"]
        assert post_paths == ["/v1beta/models/gemini-2.5-flash:generateContent"]

        cfg_res = client.get("/api/ai/config", headers=admin_headers).json()
        assert cfg_res["model"] == "gemini-2.5-flash"
        assert cfg_res["quota_rpm"] == 15
    finally:
        server.shutdown()
        server.server_close()


def test_ai_group_fallbacks_have_no_legacy_all_or_tie():
    from src.services.ai_extractor import _available_group_tags
    from src.services.gemini import _build_autocomplete_prompt

    prompt_text = _build_autocomplete_prompt(
        form_data={"title": "Evento UPA"},
        empty_fields=["target_groups"],
        available_groups=[],
        has_image=False,
    )
    assert "ALL:" not in prompt_text
    assert "TIE:" not in prompt_text

    fallback_tags = _available_group_tags(None)
    assert "TIE" not in fallback_tags
    assert "ALL" not in fallback_tags
