"""Pruebas de contrato, backend y extremo a extremo (DOM real contra uvicorn) de la PWA UPA Campus."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import User

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
WEB_APP = REPO_ROOT / "web-app"
WEB_TESTS = WEB_APP / "tests"

SEED_SCRIPT = """
from src.database import Base, SessionLocal, engine, ensure_schema_upgrades
from src.models import User

Base.metadata.create_all(bind=engine)
ensure_schema_upgrades(engine)
db = SessionLocal()
db.add_all(
    [
        User(id=1, email="admin@upa.edu.py", full_name="Admin UPA", role="admin", groups=["ALL", "TIE"]),
        User(id=2, email="redaccion@upa.edu.py", full_name="Redaccion Marketing", role="editor", groups=["ALL"]),
        User(id=3, email="ana.gomez@upa.edu.py", full_name="Ana Gomez", role="user", groups=["ALL", "TIE"]),
    ]
)
db.commit()
db.close()
"""


def _png_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} no tiene firma PNG valida"
    width, height = struct.unpack(">II", raw[16:24])
    return width, height


def test_campus_pwa_manifest_icons_and_service_worker_contract():
    manifest = json.loads((WEB_APP / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone"
    assert manifest["lang"] == "es-PY"
    assert manifest["start_url"] == "/?source=pwa"
    assert manifest["scope"] == "/"

    purposes = {icon["purpose"] for icon in manifest["icons"]}
    assert {"any", "maskable"}.issubset(purposes)
    for icon in manifest["icons"]:
        rel = icon["src"].removeprefix("/campus/")
        icon_path = WEB_APP / rel
        assert icon_path.is_file(), f"Falta el icono declarado en el manifiesto: {icon_path}"
        w, h = _png_dimensions(icon_path)
        assert f"{w}x{h}" == icon["sizes"]

    assert _png_dimensions(WEB_APP / "icons" / "apple-touch-icon.png") == (180, 180)
    assert _png_dimensions(WEB_APP / "icons" / "favicon-32.png") == (32, 32)
    assert json.loads((WEB_APP / ".well-known" / "assetlinks.json").read_text(encoding="utf-8")) == []

    html = (WEB_APP / "index.html").read_text(encoding="utf-8")
    assert "viewport-fit=cover" in html
    assert 'name="apple-mobile-web-app-capable"' in html
    assert 'href="/manifest.webmanifest"' in html
    for expected in (
        "Escanea con tu celular para abrir la app",
        "Acceso Administrativo",
        "Instalar en pantalla de inicio",
        "Inicio",
        "Agenda",
        "Perfil",
        "Sistema",
        "Modo Claro",
        "Modo Oscuro",
        "Cerrar sesión",
        "Volver al código QR",
        "phone-mockup",
    ):
        assert expected in html
    assert "profile-groups" not in html

    html_versions = set(re.findall(r"/campus/[\w./-]+\.(?:js|css)\?v=([\d.]+)", html))
    assert html_versions == {"1.0.0"}

    sw = (WEB_APP / "sw.js").read_text(encoding="utf-8")
    shell_files = re.findall(r'"(/[^"]*)"', sw.split("SHELL_FILES")[1].split("];")[0])
    assert "/" in shell_files and "/manifest.webmanifest" in shell_files
    for entry in shell_files:
        clean = entry.split("?")[0]
        if clean == "/":
            target = WEB_APP / "index.html"
        elif clean == "/manifest.webmanifest":
            target = WEB_APP / "manifest.webmanifest"
        else:
            target = WEB_APP / clean.removeprefix("/campus/")
        assert target.is_file(), f"Archivo precacheado por sw.js no existe: {entry}"

    css = (WEB_APP / "campus.css").read_text(encoding="utf-8")
    assert "env(safe-area-inset-top" in css
    assert "env(safe-area-inset-bottom" in css
    assert "100dvh" in css
    assert ':root[data-theme="dark"]' in css
    assert ".badge-instagram" in css
    assert "grid-auto-rows: 30px" in css

    nginx = (REPO_ROOT / "web-admin" / "nginx.conf").read_text(encoding="utf-8")
    for snippet in (
        "try_files /campus/index.html =404;",
        "location = /sw.js",
        'add_header Service-Worker-Allowed "/" always;',
        "location = /manifest.webmanifest",
        "location = /.well-known/assetlinks.json",
        "location ^~ /campus/",
    ):
        assert snippet in nginx


@pytest.fixture()
def isolated_db():
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = session_factory()
    db.add(User(id=1, email="pascal.thommen@upa.edu.py", full_name="Pascal Thommen", role="admin", groups=["ALL", "TIE"]))
    db.commit()
    db.close()

    def _override():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)


def test_oauth_campus_return_to_and_callback_fragment(monkeypatch, isolated_db):
    client = TestClient(app)

    campus_login = client.get("/api/auth/login-google?return_to=campus", follow_redirects=False)
    assert campus_login.status_code == 307
    assert "state=campus" in campus_login.headers["location"]

    admin_login = client.get("/api/auth/login-google", follow_redirects=False)
    assert admin_login.status_code == 307
    assert "state=campus" not in admin_login.headers["location"]

    err_cb = client.get("/api/auth/google?state=campus&error=access_denied", follow_redirects=False)
    assert err_cb.status_code == 307
    assert err_cb.headers["location"] == "/#auth_error=access_denied"

    class _TokenResp:
        status_code = 200

        @staticmethod
        def json():
            return {"id_token": "id-ok", "access_token": "cls-tok", "refresh_token": "cls-ref"}

    async def _post(self, *args, **kwargs):
        return _TokenResp()

    async def _verify(_id_token):
        return {"email": "estudiante.pwa@upa.edu.py", "name": "Estudiante PWA"}

    async def _groups(_email):
        return []

    monkeypatch.setattr("httpx.AsyncClient.post", _post)
    monkeypatch.setattr("src.api.auth.verify_google_id_token", _verify)
    monkeypatch.setattr("src.api.auth.get_google_groups_for_user", _groups)

    ok_cb = client.get("/api/auth/google?state=campus&code=valid_code", follow_redirects=False)
    assert ok_cb.status_code == 307
    assert ok_cb.headers["location"].startswith("/#token=eyJ")


def test_feed_includes_event_registration_status_for_user(isolated_db):
    client = TestClient(app)
    admin_token = create_access_token({"sub": "1", "email": "pascal.thommen@upa.edu.py", "role": "admin"})
    start = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    end = (datetime.now(UTC) + timedelta(days=2, hours=2)).isoformat()

    created = client.post(
        "/api/publications",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "title": "Seminario PWA Campus",
            "content": "Prueba de estado de inscripcion en el feed",
            "is_news": True,
            "is_event": True,
            "event_start": start,
            "event_end": end,
            "location": "Aula Magna",
            "has_registration": True,
            "target_groups": ["ALL"],
        },
    )
    assert created.status_code == 201
    event_id = created.json()["id"]

    try:
        before = client.get("/api/v1/feed", headers={"Authorization": f"Bearer {admin_token}"}).json()["posts"]
        item = next(p for p in before if p["id"] == event_id)
        assert item["is_registered"] is False
        assert item["registered_count"] == 0

        reg = client.post(f"/api/events/{event_id}/register", headers={"Authorization": f"Bearer {admin_token}"})
        assert reg.status_code == 200

        after = client.get("/api/v1/feed", headers={"Authorization": f"Bearer {admin_token}"}).json()["posts"]
        item = next(p for p in after if p["id"] == event_id)
        assert item["is_registered"] is True
        assert item["registered_count"] == 1
    finally:
        client.delete(f"/api/publications/{event_id}", headers={"Authorization": f"Bearer {admin_token}"})


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_node(file: Path, env: dict[str, str]) -> int:
    node = shutil.which("node")
    assert node is not None, "Node.js es necesario para ejecutar las pruebas de la PWA"
    result = subprocess.run(
        [node, "--test", "--test-reporter=tap", str(file)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"Fallo en {file.name}:\n{output[-4000:]}"
    passed = int(re.search(r"^#\s+pass\s+(\d+)\s*$", result.stdout, re.MULTILINE).group(1))
    failed = int(re.search(r"^#\s+fail\s+(\d+)\s*$", result.stdout, re.MULTILINE).group(1))
    skipped = int(re.search(r"^#\s+skipped\s+(\d+)\s*$", result.stdout, re.MULTILINE).group(1))
    assert failed == 0 and skipped == 0 and passed > 0, output[-4000:]
    return passed


@pytest.fixture(scope="module")
def live_backend(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("campus-live")
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PYTHONPATH": str(BACKEND_DIR),
        "DATABASE_URL": f"sqlite:///{workdir / 'campus.db'}",
        "UPLOAD_DIR": str(workdir / "uploads"),
        "PUBLIC_BASE_URL": base_url,
        "FEED_SYNC_ENABLED": "false",
        "INSTAGRAM_ACCESS_TOKEN": "",
        "SOCIABLEKIT_EMBED_ID": "",
        "GOOGLE_SERVICE_ACCOUNT_FILE": str(workdir / "no-sa.json"),
        "FCM_SERVICE_ACCOUNT_FILE": str(workdir / "no-fcm.json"),
    }
    subprocess.run([sys.executable, "-c", SEED_SCRIPT], cwd=BACKEND_DIR, env=env, check=True, timeout=60)
    log_path = workdir / "uvicorn.log"
    with open(log_path, "wb") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=BACKEND_DIR,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.time() + 45
            while True:
                assert server.poll() is None, log_path.read_text()[-2000:]
                try:
                    with urllib.request.urlopen(f"{base_url}/health", timeout=2) as resp:
                        if resp.status == 200:
                            break
                except (urllib.error.URLError, ConnectionError, TimeoutError):
                    pass
                assert time.time() < deadline, "uvicorn no inicio a tiempo"
                time.sleep(0.25)
            yield base_url
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()


def test_campus_core_unit_tests_pass():
    assert _run_node(WEB_TESTS / "campus-core.test.js", dict(os.environ)) >= 8


def test_campus_dom_end_to_end_against_real_backend(live_backend):
    expired = create_access_token(
        {"sub": "3", "email": "ana.gomez@upa.edu.py", "role": "user"},
        expires_delta=timedelta(minutes=-5),
    )
    tokens = {
        "admin@upa.edu.py": create_access_token({"sub": "1", "email": "admin@upa.edu.py", "role": "admin"}),
        "redaccion@upa.edu.py": create_access_token({"sub": "2", "email": "redaccion@upa.edu.py", "role": "editor"}),
        "ana.gomez@upa.edu.py": create_access_token({"sub": "3", "email": "ana.gomez@upa.edu.py", "role": "user"}),
    }
    env = {
        **os.environ,
        "UPA_BASE_URL": live_backend,
        "UPA_EXPIRED_TOKEN": expired,
        "UPA_TEST_TOKENS": json.dumps(tokens),
    }
    assert _run_node(WEB_TESTS / "campus-dom.test.js", env) >= 6
