"""
Pruebas de integracion del Cockpit de Redaccion (web-admin) contra el backend real.

Levanta un servidor uvicorn real (base de datos SQLite persistente en disco, carpeta de subidas real,
sin credenciales de Instagram/FCM) y ejecuta con Node las pruebas de `web-admin/tests/`:
- editorial-core.test.js: logica pura y casos de red (timeout, servidor inaccesible).
- editorial-live.test.js: subida, noticias, eventos, RSVP, Instagram, permisos y sesion expirada
  usando el mismo cliente `editorial-core.js` que el navegador.

En CI la ausencia de Node es un fallo; en local la prueba se omite con un aviso explicito.
"""

import json
import os
import re
import shutil
from datetime import timedelta
from pathlib import Path

import pytest
from src.auth import create_access_token
from src.models import User, UserRole

from tests.conftest import (
    BACKEND_DIR,
    REPO_ROOT,
    free_tcp_port,
    managed_uvicorn_server,
    run_managed_command,
    seed_sqlite_database,
)

WEB_TESTS = REPO_ROOT / "web-admin" / "tests"


def _require_node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("Node.js es obligatorio en CI para las pruebas del Cockpit de Redaccion.")
        pytest.skip("Node.js no disponible: pruebas del Cockpit omitidas (solo permitido fuera de CI).")
    return node


def _parse_tap_summary(output: str) -> dict[str, int]:
    summary: dict[str, int] = {}
    for key in ("tests", "pass", "fail", "cancelled", "skipped", "todo"):
        match = re.search(rf"^#\s+{key}\s+(\d+)\s*$", output, re.MULTILINE)
        assert match, f"Resumen TAP sin la linea '{key}':\n{output[-2000:]}"
        summary[key] = int(match.group(1))
    return summary


def _ensure_node_modules(test_dir: Path, required_packages: tuple[str, ...] = ("jsdom",)) -> None:
    node_modules = test_dir / "node_modules"
    if all((node_modules / pkg).is_dir() for pkg in required_packages):
        return
    npm = shutil.which("npm")
    assert npm is not None, f"npm es necesario para instalar dependencias de prueba en {test_dir}"
    cmd = "ci" if (test_dir / "package-lock.json").is_file() else "install"
    run_managed_command(
        [npm, "--prefix", str(test_dir), cmd, "--no-audit", "--no-fund"],
        cwd=REPO_ROOT,
        check=True,
        timeout=180,
    )


def _run_node_tests(node: str, files: list[Path], env: dict[str, str]) -> dict[str, int]:
    _ensure_node_modules(WEB_TESTS)
    result = run_managed_command(
        [node, "--test", "--test-concurrency=1", "--test-reporter=tap", *[str(f) for f in files]],
        cwd=REPO_ROOT,
        env=env,
        check=False,
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
def live_backend(tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest):
    """Servidor uvicorn real con SQLite en disco, directorio de subidas real y teardown determinista."""
    workdir = tmp_path_factory.mktemp("cockpit-live")
    port = free_tcp_port()
    base_url = f"http://127.0.0.1:{port}"
    db_url = seed_sqlite_database(
        workdir / "cockpit.db",
        [
            User(id=1, email="admin@upa.edu.py", full_name="Admin UPA", role="admin", groups=["ALL", "TIE"]),
            User(id=2, email="redaccion@upa.edu.py", full_name="Redaccion Marketing", role="editor", groups=["ALL"]),
            User(id=3, email="ana.gomez@upa.edu.py", full_name="Ana Gomez", role="user", groups=["ALL", "TIE"]),
            User(id=4, email="luis.benitez@upa.edu.py", full_name="Luis Benitez", role="user", groups=["ALL", "TIE"]),
            User(id=5, email="dom.estudiante1@upa.edu.py", full_name="Carla Rojas", role="user", groups=["ALL", "TIE"]),
            User(id=6, email="dom.estudiante2@upa.edu.py", full_name="Diego Vera", role="user", groups=["ALL", "TIE"]),
            UserRole(
                id=1,
                email="redaccion@upa.edu.py",
                name="Redaccion Marketing",
                permissions=["publicaciones"],
                is_primary=False,
            ),
        ],
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(BACKEND_DIR),
        "DATABASE_URL": db_url,
        "UPLOAD_DIR": str(workdir / "uploads"),
        "PUBLIC_BASE_URL": base_url,
        "FEED_SYNC_ENABLED": "false",
        "INSTAGRAM_ACCESS_TOKEN": "",
        "SOCIABLEKIT_EMBED_ID": "",
        "GOOGLE_SERVICE_ACCOUNT_FILE": str(workdir / "no-service-account.json"),
        "FCM_SERVICE_ACCOUNT_FILE": str(workdir / "no-fcm.json"),
    }

    with managed_uvicorn_server(workdir, env, port, request=request):
        yield {"base_url": base_url, "env": env}


def test_cockpit_core_unit_tests_pass():
    node = _require_node()
    summary = _run_node_tests(node, [WEB_TESTS / "editorial-core.test.js"], dict(os.environ))
    assert summary["tests"] >= 15


def test_web_admin_router_unit_tests_pass():
    node = _require_node()
    summary = _run_node_tests(node, [WEB_TESTS / "router.test.js"], dict(os.environ))
    assert summary["tests"] >= 10


def test_cockpit_end_to_end_against_real_backend(live_backend):
    node = _require_node()
    expired_token = create_access_token(
        {"sub": "1", "email": "admin@upa.edu.py", "role": "admin"},
        expires_delta=timedelta(minutes=-5),
    )
    test_tokens = {
        "admin@upa.edu.py": create_access_token({"sub": "1", "email": "admin@upa.edu.py", "role": "admin"}),
        "redaccion@upa.edu.py": create_access_token({"sub": "2", "email": "redaccion@upa.edu.py", "role": "editor"}),
        "ana.gomez@upa.edu.py": create_access_token({"sub": "3", "email": "ana.gomez@upa.edu.py", "role": "user"}),
        "luis.benitez@upa.edu.py": create_access_token({"sub": "4", "email": "luis.benitez@upa.edu.py", "role": "user"}),
        "dom.estudiante1@upa.edu.py": create_access_token(
            {"sub": "5", "email": "dom.estudiante1@upa.edu.py", "role": "user"}
        ),
        "dom.estudiante2@upa.edu.py": create_access_token(
            {"sub": "6", "email": "dom.estudiante2@upa.edu.py", "role": "user"}
        ),
    }
    env = {
        **os.environ,
        "UPA_BASE_URL": live_backend["base_url"],
        "UPA_EXPIRED_TOKEN": expired_token,
        "UPA_TEST_TOKENS": json.dumps(test_tokens),
    }
    summary = _run_node_tests(node, [WEB_TESTS / "editorial-live.test.js"], env)
    assert summary["tests"] >= 15
