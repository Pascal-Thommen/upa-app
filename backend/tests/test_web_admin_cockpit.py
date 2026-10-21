"""
Pruebas de integracion del Cockpit de Redaccion (web-admin) contra el backend real.

Levanta un servidor uvicorn real (base de datos SQLite persistente en disco, carpeta de subidas real,
sin credenciales de Instagram/FCM) y ejecuta con Node las pruebas de `web-admin/tests/`:
- editorial-core.test.js: logica pura y casos de red (timeout, servidor inaccesible).
- editorial-live.test.js: subida, noticias, eventos, RSVP, Instagram, permisos y sesion expirada
  usando el mismo cliente `editorial-core.js` que el navegador.

En CI la ausencia de Node es un fallo; en local la prueba se omite con un aviso explicito.
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path

import pytest
from src.auth import create_access_token

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
WEB_TESTS = REPO_ROOT / "web-admin" / "tests"

SEED_SCRIPT = """
from src.database import Base, SessionLocal, engine, ensure_schema_upgrades
from src.models import User

Base.metadata.create_all(bind=engine)
ensure_schema_upgrades(engine)
db = SessionLocal()
db.add(User(email="redaccion@upa.edu.py", full_name="Redaccion Marketing", role="editor", groups=["ALL"]))
db.commit()
db.close()
"""


def _require_node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("Node.js es obligatorio en CI para las pruebas del Cockpit de Redaccion.")
        pytest.skip("Node.js no disponible: pruebas del Cockpit omitidas (solo permitido fuera de CI).")
    return node


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _parse_tap_summary(output: str) -> dict[str, int]:
    summary: dict[str, int] = {}
    for key in ("tests", "pass", "fail", "cancelled", "skipped", "todo"):
        match = re.search(rf"^#\s+{key}\s+(\d+)\s*$", output, re.MULTILINE)
        assert match, f"Resumen TAP sin la linea '{key}':\n{output[-2000:]}"
        summary[key] = int(match.group(1))
    return summary


def _run_node_tests(node: str, files: list[Path], env: dict[str, str]) -> dict[str, int]:
    result = subprocess.run(
        [node, "--test", "--test-reporter=tap", *[str(f) for f in files]],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"Fallaron pruebas Node (codigo {result.returncode}):\n{output[-6000:]}"
    summary = _parse_tap_summary(result.stdout)
    assert summary["fail"] == 0 and summary["cancelled"] == 0, output[-4000:]
    assert summary["skipped"] == 0, f"Hay pruebas omitidas, no permitido:\n{output[-4000:]}"
    assert summary["pass"] == summary["tests"] and summary["tests"] > 0, output[-4000:]
    return summary


@pytest.fixture(scope="module")
def live_backend(tmp_path_factory):
    """Servidor uvicorn real con SQLite en disco y directorio de subidas real."""
    workdir = tmp_path_factory.mktemp("cockpit-live")
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PYTHONPATH": str(BACKEND_DIR),
        "DATABASE_URL": f"sqlite:///{workdir / 'cockpit.db'}",
        "UPLOAD_DIR": str(workdir / "uploads"),
        "PUBLIC_BASE_URL": base_url,
        "FEED_SYNC_ENABLED": "false",
        "INSTAGRAM_ACCESS_TOKEN": "",
        "SOCIABLEKIT_EMBED_ID": "",
        "GOOGLE_SERVICE_ACCOUNT_FILE": str(workdir / "no-service-account.json"),
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
                if server.poll() is not None:
                    pytest.fail(f"uvicorn termino prematuramente:\n{log_path.read_text()[-3000:]}")
                try:
                    with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
                        if response.status == 200:
                            break
                except (urllib.error.URLError, ConnectionError, TimeoutError):
                    pass
                if time.time() > deadline:
                    pytest.fail(f"uvicorn no respondio en 45 s:\n{log_path.read_text()[-3000:]}")
                time.sleep(0.3)
            yield {"base_url": base_url, "env": env}
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()


def test_cockpit_core_unit_tests_pass():
    node = _require_node()
    summary = _run_node_tests(node, [WEB_TESTS / "editorial-core.test.js"], dict(os.environ))
    assert summary["tests"] >= 15


def test_cockpit_end_to_end_against_real_backend(live_backend):
    node = _require_node()
    expired_token = create_access_token(
        {"sub": "1", "email": "admin@upa.edu.py", "role": "admin"},
        expires_delta=timedelta(minutes=-5),
    )
    env = {
        **os.environ,
        "UPA_BASE_URL": live_backend["base_url"],
        "UPA_EXPIRED_TOKEN": expired_token,
    }
    summary = _run_node_tests(node, [WEB_TESTS / "editorial-live.test.js"], env)
    assert summary["tests"] >= 15
