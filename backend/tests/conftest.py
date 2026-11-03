"""Configuracion del entorno de pruebas: aislamiento de procesos y limpieza determinista de recursos."""

from __future__ import annotations

import atexit
import gc
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

_MAIN_PID = os.getpid()
_UPLOAD_DIR_PID_RE = re.compile(r"^upa-test-uploads-(\d+)-")

# Debe fijarse antes de importar src.main, porque /uploads se monta durante la importacion
_UPLOAD_TMP = tempfile.mkdtemp(prefix=f"upa-test-uploads-{_MAIN_PID}-")
os.environ.setdefault("UPLOAD_DIR", _UPLOAD_TMP)

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

_ACTIVE_SUBPROCESSES: set[subprocess.Popen[Any]] = set()


def _is_pid_alive(pid: int) -> bool:
    """Comprueba si un proceso del sistema sigue activo."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def cleanup_orphaned_upload_dirs(
    *,
    include_current: bool = False,
    temp_root: Path | None = None,
) -> list[Path]:
    """
    Elimina directorios temporales /tmp/upa-test-uploads-* que no pertenezcan a un proceso activo.
    Si include_current=True, elimina tambien el directorio _UPLOAD_TMP de la sesion actual.
    """
    removed: list[Path] = []
    roots = [temp_root] if temp_root is not None else list({Path(tempfile.gettempdir()), Path("/tmp")})

    if include_current and temp_root is None:
        current_path = Path(_UPLOAD_TMP)
        if current_path.exists():
            shutil.rmtree(current_path, ignore_errors=True)
            removed.append(current_path)

    for root in roots:
        if not root.is_dir():
            continue
        for candidate in root.glob("upa-test-uploads-*"):
            if not candidate.is_dir():
                continue
            if not include_current and temp_root is None and candidate.resolve() == Path(_UPLOAD_TMP).resolve():
                continue
            match = _UPLOAD_DIR_PID_RE.match(candidate.name)
            if match:
                owner_pid = int(match.group(1))
                if owner_pid == _MAIN_PID and not include_current:
                    continue
                if owner_pid != _MAIN_PID and _is_pid_alive(owner_pid):
                    continue
            shutil.rmtree(candidate, ignore_errors=True)
            removed.append(candidate)

    return removed


def free_tcp_port() -> int:
    """Obtiene un puerto TCP local libre en 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def register_subprocess(
    proc: subprocess.Popen[Any],
    request: pytest.FixtureRequest | None = None,
) -> subprocess.Popen[Any]:
    """Registra un subproceso activo y vincula su finalizador determinista a pytest."""
    _ACTIVE_SUBPROCESSES.add(proc)
    if request is not None:
        request.addfinalizer(lambda: terminate_subprocess(proc))
    return proc


def terminate_subprocess(proc: subprocess.Popen[Any] | None, timeout: float = 10.0) -> None:
    """
    Termina de forma determinista un subproceso (y su grupo de procesos si fue aislado),
    aplicando SIGTERM seguido de SIGKILL en caso de timeout y recolectando el estado hijo
    para evitar procesos zombi (<defunct>).
    """
    if proc is None:
        return

    _ACTIVE_SUBPROCESSES.discard(proc)

    if proc.poll() is None:
        pgid: int | None = None
        if hasattr(os, "killpg") and hasattr(os, "getpgid"):
            try:
                candidate_pgid = os.getpgid(proc.pid)
                if candidate_pgid != os.getpgrp():
                    pgid = candidate_pgid
            except OSError:
                pgid = None

        try:
            if pgid is not None:
                os.killpg(pgid, signal.SIGTERM)
            else:
                proc.terminate()
        except OSError:
            pass

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                if pgid is not None:
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    proc.kill()
            except OSError:
                pass
            try:
                proc.wait(timeout=5.0)
            except Exception:
                pass
    else:
        try:
            proc.wait(timeout=1.0)
        except Exception:
            pass

    for stream in (proc.stdout, proc.stderr, proc.stdin):
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def run_managed_command(
    cmd: list[str],
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 180.0,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Ejecuta un comando externo en una sesion de proceso aislada, garantizando que en caso de
    timeout o senal externa (SIGTERM/SIGINT) todo el arbol del subproceso sea terminado y limpiado.
    """
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    register_subprocess(proc)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        terminate_subprocess(proc, timeout=2.0)
        raise
    except BaseException:
        terminate_subprocess(proc, timeout=2.0)
        raise
    finally:
        terminate_subprocess(proc, timeout=2.0)

    returncode = proc.returncode if proc.returncode is not None else -1
    if check and returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)


def seed_sqlite_database(db_path: Path, users: list[Any]) -> str:
    """
    Inicializa una base de datos SQLite en disco aplicando migraciones Alembic y usuarios semilla
    en el mismo proceso (sin levantar un interprete Python adicional).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.database import run_alembic_migrations

    db_url = f"sqlite:///{db_path}"
    seed_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    try:
        run_alembic_migrations(seed_engine)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=seed_engine)
        with session_factory() as db:
            db.add_all(users)
            db.commit()
    finally:
        seed_engine.dispose()
    return db_url


@contextmanager
def managed_uvicorn_server(
    workdir: Path,
    env: dict[str, str],
    port: int,
    *,
    request: pytest.FixtureRequest | None = None,
    startup_timeout: float = 45.0,
    command: list[str] | None = None,
) -> Generator[subprocess.Popen[Any], None, None]:
    """
    Context manager que inicia un servidor uvicorn aislado en su propio grupo de procesos,
    espera a que /health responda 200 y garantiza su terminacion determinista al salir o fallar.
    """
    base_url = f"http://127.0.0.1:{port}"
    log_path = workdir / "uvicorn.log"
    cmd = command or [
        sys.executable,
        "-m",
        "uvicorn",
        "src.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--workers",
        "1",
        "--no-access-log",
    ]

    with open(log_path, "wb") as log_file:
        server = subprocess.Popen(
            cmd,
            cwd=BACKEND_DIR,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    register_subprocess(server, request=request)
    try:
        deadline = time.monotonic() + startup_timeout
        while True:
            if server.poll() is not None:
                log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:] if log_path.exists() else ""
                pytest.fail(f"uvicorn termino prematuramente (codigo {server.returncode}):\n{log_tail}")
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                pass
            if time.monotonic() > deadline:
                log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:] if log_path.exists() else ""
                pytest.fail(f"uvicorn no respondio en {startup_timeout} s:\n{log_tail}")
            time.sleep(0.2)
        yield server
    finally:
        terminate_subprocess(server, timeout=10.0)


def cleanup_test_environment() -> None:
    """Termina todos los subprocesos activos de pruebas y elimina los directorios temporales."""
    if os.getpid() != _MAIN_PID:
        return
    for proc in list(_ACTIVE_SUBPROCESSES):
        terminate_subprocess(proc, timeout=3.0)
    cleanup_orphaned_upload_dirs(include_current=True)


# Limpiar al inicio cualquier directorio huerfano de ejecuciones previas abortadas
cleanup_orphaned_upload_dirs(include_current=False)
atexit.register(cleanup_test_environment)


def _install_signal_cleanup_handlers() -> None:
    """Instala manejadores para SIGTERM/SIGINT que limpian subprocesos antes de salir."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous_handler = signal.getsignal(sig)

        def _handler(signum: int, frame: Any, prev: Any = previous_handler) -> None:
            cleanup_test_environment()
            if callable(prev) and prev not in (signal.SIG_IGN, signal.SIG_DFL):
                prev(signum, frame)
            raise SystemExit(128 + signum)

        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass


_install_signal_cleanup_handlers()


@pytest.fixture(scope="module", autouse=True)
def _dispose_module_sqlalchemy_resources(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Libera conexiones SQLite en memoria (StaticPool) y ejecuta GC al terminar cada modulo."""
    yield
    mod_engine = getattr(request.module, "engine", None)
    if mod_engine is not None and hasattr(mod_engine, "dispose"):
        try:
            from src.database import engine as app_engine

            if mod_engine is not app_engine:
                mod_engine.dispose()
        except Exception:
            pass
    gc.collect()


@pytest.fixture(scope="session", autouse=True)
def _session_resource_guard(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Garantiza la limpieza de subprocesos y carpetas de subida al finalizar la sesion."""
    request.addfinalizer(cleanup_test_environment)
    yield
    cleanup_test_environment()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Hook final de pytest para asegurar limpieza incluso tras fallos o interrupciones."""
    cleanup_test_environment()
