"""Pruebas integrales del modulo IA (SRV-222): cadena oficial Gemini 2.0/1.5 Flash, 1-Klick-Save y prompts predeterminados."""

import json
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
from src.services import gemini

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
        ]
    )
    db.commit()
    db.close()
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
    yield
    app.dependency_overrides.clear()


def test_preferred_flash_models_exclude_phantom_2_5_and_prioritize_2_0_then_1_5():
    assert "gemini-2.5-flash" not in gemini.PREFERRED_FLASH_MODELS
    assert gemini.PREFERRED_FLASH_MODELS == ("gemini-2.0-flash", "gemini-1.5-flash")
    assert gemini.DEFAULT_FLASH_MODEL == "gemini-2.0-flash"

    # Incluso si en la base de datos hubiera quedado guardado el modelo fantasma gemini-2.5-flash,
    # resolve_active_model lo descarta y devuelve gemini-2.0-flash.
    db = TestingSessionLocal()
    db.add(AppSetting(key=gemini.GEMINI_MODEL_SETTING, value="gemini-2.5-flash", updated_by="legacy"))
    db.commit()
    assert gemini.resolve_active_model(db) == "gemini-2.0-flash"
    db.close()


def test_default_prompts_exposed_and_one_click_save_with_fallback_from_2_0_to_1_5(monkeypatch):
    called_paths: list[str] = []
    fail_2_0_with_404 = {"enabled": False}

    class FallbackGeminiStub(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/v1beta/models"):
                payload = json.dumps(
                    {
                        "models": [
                            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                            {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
                            {"name": "models/gemini-1.5-flash", "supportedGenerationMethods": ["generateContent"]},
                        ]
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            called_paths.append(self.path)
            if fail_2_0_with_404["enabled"] and "gemini-2.0-flash" in self.path:
                err = json.dumps({"error": {"code": 404, "message": "Model not found"}}).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err)))
                self.end_headers()
                self.wfile.write(err)
                return

            suggestion_json = json.dumps(
                {
                    "caption": "Síntesis institucional generada por Gemini Flash",
                    "location": "Campus UPA San Lorenzo",
                    "event_start": "2026-11-28T18:00",
                    "is_event": True,
                },
                ensure_ascii=False,
            )
            payload = json.dumps(
                {"candidates": [{"content": {"parts": [{"text": suggestion_json}]}}]}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), FallbackGeminiStub)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        monkeypatch.setattr(settings, "GEMINI_API_BASE_URL", f"http://127.0.0.1:{port}")
        headers = auth(EDITOR_ID, EDITOR_EMAIL, "editor")

        # 1. GET /api/ai/config devuelve los prompts predeterminados de la UPA y modelo gemini-2.0-flash
        initial = client.get("/api/ai/config", headers=headers).json()
        assert initial["model"] == "gemini-2.0-flash"
        assert initial["default_system_prompt_autocomplete"] == gemini.DEFAULT_SYSTEM_PROMPT_AUTOCOMPLETE
        assert initial["default_system_prompt_instagram"] == gemini.DEFAULT_SYSTEM_PROMPT_INSTAGRAM
        assert initial["system_prompt_autocomplete"] == gemini.DEFAULT_SYSTEM_PROMPT_AUTOCOMPLETE
        assert initial["system_prompt_instagram"] == gemini.DEFAULT_SYSTEM_PROMPT_INSTAGRAM

        # 2. 1-Klick-Save: Guardar clave y ambos prompts simultáneamente + probar conexión con gemini-2.0-flash
        save_res = client.post(
            "/api/ai/config",
            json={
                "api_key": "AIzaOneClickSaveKey2026Valid",
                "system_prompt_autocomplete": "Prompt UPA Autocompletado Personalizado.",
                "system_prompt_instagram": "Prompt UPA Instagram Personalizado.",
            },
            headers=headers,
        )
        assert save_res.status_code == 200
        saved = save_res.json()
        assert saved["configured"] is True
        assert saved["system_prompt_autocomplete"] == "Prompt UPA Autocompletado Personalizado."
        assert saved["system_prompt_instagram"] == "Prompt UPA Instagram Personalizado."

        test_res = client.post("/api/ai/test-connection", headers=headers).json()
        assert test_res["ok"] is True
        assert test_res["model"] == "gemini-2.0-flash"
        assert called_paths[-1] == "/v1beta/models/gemini-2.0-flash:generateContent"

        # 3. Fallback automatico a gemini-1.5-flash cuando gemini-2.0-flash responde 404 en test-connection y autocomplete
        fail_2_0_with_404["enabled"] = True
        called_paths.clear()
        fallback_test = client.post("/api/ai/test-connection", headers=headers).json()
        assert fallback_test["ok"] is True
        assert fallback_test["model"] == "gemini-1.5-flash"
        assert called_paths == [
            "/v1beta/models/gemini-2.0-flash:generateContent",
            "/v1beta/models/gemini-1.5-flash:generateContent",
        ]

        auto_res = client.post(
            "/api/publications/autocomplete-ai",
            json={"title": "Conferencia Anual UPA", "caption": "", "location": ""},
            headers=headers,
        )
        assert auto_res.status_code == 200
        auto_body = auto_res.json()
        assert auto_body["caption"] == "Síntesis institucional generada por Gemini Flash"
        assert auto_body["location"] == "Campus UPA San Lorenzo"

        # 4. Restaurar prompts predeterminados enviando cadena vacía sin borrar la clave guardada
        restore_res = client.post(
            "/api/ai/config",
            json={
                "system_prompt_autocomplete": "",
                "system_prompt_instagram": "",
            },
            headers=headers,
        )
        assert restore_res.status_code == 200
        restored = restore_res.json()
        assert restored["configured"] is True
        assert restored["system_prompt_autocomplete"] == gemini.DEFAULT_SYSTEM_PROMPT_AUTOCOMPLETE
        assert restored["system_prompt_instagram"] == gemini.DEFAULT_SYSTEM_PROMPT_INSTAGRAM
    finally:
        server.shutdown()
        server.server_close()


def test_encrypted_token_persistence_and_modern_flash_discovery_with_503_fallback(monkeypatch):
    """
    SRV-225:
    1. La clave de API se guarda cifrada (enc:v1:...) en app_settings y nunca en texto plano.
    2. Ningun endpoint expone el token en texto plano, y usuarios sin permiso 'ia'/'apis' no ven ni siquiera masked_key.
    3. Rechaza intentos de sobreescribir la clave con una mascara 'AIza********1234'.
    4. Descubre modelos actuales de Google AI Studio (ej. gemini-3.6-flash, gemini-3.5-flash) y hace fallback ante 404 o 503.
    """
    called_paths: list[str] = []

    class ModernGoogleStudioStub(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/v1beta/models"):
                payload = json.dumps(
                    {
                        "models": [
                            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                            {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
                            {"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]},
                            {"name": "models/gemini-3.5-flash", "supportedGenerationMethods": ["generateContent"]},
                        ]
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            called_paths.append(self.path)
            if "gemini-3.6-flash" in self.path:
                err = json.dumps({"error": {"code": 503, "message": "High demand", "status": "UNAVAILABLE"}}).encode(
                    "utf-8"
                )
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err)))
                self.end_headers()
                self.wfile.write(err)
                return

            payload = json.dumps(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"thought": True, "text": "Razonamiento interno que debe ignorarse"},
                                    {"text": json.dumps({"caption": "Resumen IA 3.5 Flash", "location": "Aula Magna"})},
                                ]
                            }
                        }
                    ]
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), ModernGoogleStudioStub)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        monkeypatch.setattr(settings, "GEMINI_API_BASE_URL", f"http://127.0.0.1:{port}")
        admin_headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")

        raw_secret_key = "AQ.Ab8RN6L_TestGoogleAiStudioKey2026_Sy7Q"
        save_res = client.post(
            "/api/ai/config",
            json={"api_key": raw_secret_key},
            headers=admin_headers,
        )
        assert save_res.status_code == 200
        body = save_res.json()
        assert body["configured"] is True
        assert body["masked_key"] == "AQ.A********Sy7Q"
        assert raw_secret_key not in json.dumps(body)

        # Verificar que en la base de datos el valor esta cifrado y no en texto plano
        db = TestingSessionLocal()
        row = db.get(AppSetting, gemini.GEMINI_KEY_SETTING)
        assert row is not None
        assert row.value.startswith(gemini.ENCRYPTED_KEY_PREFIX)
        assert raw_secret_key not in row.value
        assert gemini.get_stored_key(db) == raw_secret_key

        # Usuario solo con permiso 'publicaciones' ve configured=True pero NO ve masked_key
        db.add(User(id=9, email="redactor.pub@upa.edu.py", full_name="Redactor", role="editor"))
        db.add(UserRole(id=9, email="redactor.pub@upa.edu.py", name="Redactor", permissions=["publicaciones"]))
        db.commit()
        db.close()

        pub_headers = auth(9, "redactor.pub@upa.edu.py", "editor")
        pub_cfg = client.get("/api/ai/config", headers=pub_headers).json()
        assert pub_cfg["configured"] is True
        assert pub_cfg["masked_key"] == ""

        # Intentar guardar una clave enmascarada con '****' se rechaza con 422
        masked_attempt = client.post(
            "/api/ai/config",
            json={"api_key": "AQ.A********Sy7Q"},
            headers=admin_headers,
        )
        assert masked_attempt.status_code == 422

        # Probar conexion en vivo: intenta gemini-3.6-flash (503) y hace fallback a gemini-3.5-flash (200)
        test_conn = client.post("/api/ai/test-connection", headers=admin_headers).json()
        assert test_conn["ok"] is True
        assert test_conn["model"] == "gemini-3.5-flash"
        assert called_paths == [
            "/v1beta/models/gemini-3.6-flash:generateContent",
            "/v1beta/models/gemini-3.5-flash:generateContent",
        ]

        # Autocompletar ignora partes con thought=True y extrae el JSON limpio
        auto_res = client.post(
            "/api/publications/autocomplete-ai",
            json={"title": "Foro IA", "caption": "", "location": ""},
            headers=pub_headers,
        )
        assert auto_res.status_code == 200
        assert auto_res.json()["caption"] == "Resumen IA 3.5 Flash"
        assert auto_res.json()["location"] == "Aula Magna"
    finally:
        server.shutdown()
        server.server_close()
