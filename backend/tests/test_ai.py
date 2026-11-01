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
