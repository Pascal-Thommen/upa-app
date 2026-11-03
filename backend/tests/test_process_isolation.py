"""
Pruebas de aislamiento de subprocesos, fallback SIGKILL ante timeouts y limpieza de recursos temporales.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.conftest import (
    _ACTIVE_SUBPROCESSES,
    BACKEND_DIR,
    cleanup_orphaned_upload_dirs,
    free_tcp_port,
    managed_uvicorn_server,
    register_subprocess,
    run_managed_command,
    terminate_subprocess,
)


def test_terminate_subprocess_handles_sigterm_and_reaps_process():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    register_subprocess(proc)
    assert proc in _ACTIVE_SUBPROCESSES
    assert proc.poll() is None

    terminate_subprocess(proc, timeout=5.0)
    assert proc not in _ACTIVE_SUBPROCESSES
    assert proc.poll() is not None


def test_terminate_subprocess_falls_back_to_sigkill_when_sigterm_ignored():
    """Verifica que un proceso que ignora SIGTERM es terminado con SIGKILL tras el timeout sin dejar zombis."""
    ignore_sigterm_script = (
        "import signal, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "sys.stdout.write('READY\\n')\n"
        "sys.stdout.flush()\n"
        "time.sleep(60)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", ignore_sigterm_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    register_subprocess(proc)
    assert proc.stdout is not None
    ready_line = proc.stdout.readline().strip()
    assert ready_line == "READY"

    terminate_subprocess(proc, timeout=0.3)
    assert proc not in _ACTIVE_SUBPROCESSES
    assert proc.poll() is not None
    # En POSIX SIGKILL produce codigo -9
    assert proc.returncode != 0


def test_run_managed_command_kills_process_group_on_timeout():
    with pytest.raises(subprocess.TimeoutExpired):
        run_managed_command(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.3,
        )
    assert len(_ACTIVE_SUBPROCESSES) == 0


def test_managed_uvicorn_server_cleans_up_on_startup_timeout(tmp_path: Path):
    """Si el subproceso no responde en /health antes del timeout, se termina y limpia sin dejar huerfanos."""
    port = free_tcp_port()
    hang_cmd = [sys.executable, "-c", "import time; time.sleep(60)"]

    with pytest.raises(pytest.fail.Exception, match="uvicorn no respondio"):
        with managed_uvicorn_server(
            tmp_path,
            dict(os.environ),
            port,
            startup_timeout=0.4,
            command=hang_cmd,
        ):
            pass

    assert len(_ACTIVE_SUBPROCESSES) == 0


def test_managed_uvicorn_server_cleans_up_on_premature_exit(tmp_path: Path):
    """Si el subproceso termina prematuramente durante el arranque, el fallo se reporta y limpia."""
    port = free_tcp_port()
    fail_cmd = [sys.executable, "-c", "import sys; sys.stderr.write('fallo simulado\\n'); sys.exit(2)"]

    with pytest.raises(pytest.fail.Exception, match="uvicorn termino prematuramente"):
        with managed_uvicorn_server(
            tmp_path,
            dict(os.environ),
            port,
            startup_timeout=5.0,
            command=fail_cmd,
        ):
            pass

    assert len(_ACTIVE_SUBPROCESSES) == 0


def test_cleanup_orphaned_upload_dirs_removes_dead_pid_and_legacy_dirs_only(tmp_path: Path):
    dead_pid_dir = tmp_path / "upa-test-uploads-99999999-dead"
    legacy_dir = tmp_path / "upa-test-uploads-legacy123"
    active_pid_dir = tmp_path / f"upa-test-uploads-{os.getpid()}-active"
    unrelated_dir = tmp_path / "otra-carpeta"

    for d in (dead_pid_dir, legacy_dir, active_pid_dir, unrelated_dir):
        d.mkdir(parents=True)
        (d / "dummy.txt").write_text("test", encoding="utf-8")

    removed = cleanup_orphaned_upload_dirs(include_current=False, temp_root=tmp_path)
    removed_names = {p.name for p in removed}

    assert "upa-test-uploads-99999999-dead" in removed_names
    assert "upa-test-uploads-legacy123" in removed_names
    assert not dead_pid_dir.exists()
    assert not legacy_dir.exists()
    assert active_pid_dir.exists()
    assert unrelated_dir.exists()


def test_subprocess_pytest_session_removes_its_temporary_upload_dir(tmp_path: Path):
    """Verifica de extremo a extremo que una sesion de pytest elimina su carpeta /tmp/upa-test-uploads-* al finalizar."""
    mini_test = tmp_path / "test_mini_upload_cleanup.py"
    mini_test.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "def test_upload_dir_exists_during_run():\n"
        "    upload_dir = Path(os.environ['UPLOAD_DIR'])\n"
        "    assert upload_dir.is_dir()\n"
        "    print(f'CREATED_UPLOAD_DIR={upload_dir}')\n",
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if k != "UPLOAD_DIR"}
    env["PYTHONPATH"] = str(BACKEND_DIR)

    result = run_managed_command(
        [
            sys.executable,
            "-m",
            "pytest",
            str(mini_test),
            "-c",
            str(BACKEND_DIR / "pyproject.toml"),
            "-o",
            f"testpaths={BACKEND_DIR / 'tests'}",
            "--confcutdir",
            str(BACKEND_DIR / "tests"),
            "-p",
            "tests.conftest",
            "-s",
            "-q",
        ],
        cwd=BACKEND_DIR,
        env=env,
        timeout=30.0,
        check=True,
    )

    marker = [line for line in result.stdout.splitlines() if line.startswith("CREATED_UPLOAD_DIR=")]
    assert len(marker) == 1
    created_dir = Path(marker[0].split("=", 1)[1].strip())
    # Al terminar el subproceso de pytest, el directorio debe haber sido eliminado
    for _ in range(10):
        if not created_dir.exists():
            break
        time.sleep(0.05)
    assert not created_dir.exists(), f"El directorio temporal no fue eliminado tras finalizar pytest: {created_dir}"
