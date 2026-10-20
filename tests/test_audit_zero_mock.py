"""
Tests for Zero-Mock & Architecture Audit Tool (scripts/audit_zero_mock.py).

Validates:
- Clean production and test code passes without blockers.
- Production mock imports are detected as BLOCKER in Python.
- Bypass flags are detected as BLOCKER in Python.
- Empty dummy stubs are detected as BLOCKER in Python.
- Scheintests with no assertions are detected as BLOCKER in Python.
- Missing /health endpoint in backend is detected as BLOCKER.
- Client (Kotlin/Java) mock imports are detected as BLOCKER in production.
- Client (Kotlin/Java) mock flags are detected as BLOCKER in production.
- Client (Kotlin) TODO() stubs are detected as BLOCKER in production.
- Client (TypeScript/JavaScript) mock imports are detected as BLOCKER in production.
- Client (TypeScript/JavaScript) mock flags are detected as BLOCKER in production.
- Client test files are permitted to use test doubles without blocker violations.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_zero_mock import ZeroMockAuditor  # noqa: E402


def test_clean_codebase_passes(tmp_path: Path) -> None:
    # Python backend with health check and business logic
    backend_file = tmp_path / "backend" / "src" / "service.py"
    backend_file.parent.mkdir(parents=True, exist_ok=True)
    backend_file.write_text(
        "def get_user_status(active: bool) -> str:\n"
        "    if active:\n"
        "        return 'active'\n"
        "    return 'inactive'\n"
    )
    health_file = tmp_path / "backend" / "src" / "main.py"
    health_file.write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/health')\n"
        "def health():\n"
        "    return {'status': 'ok'}\n"
    )

    # Valid test file with assertions
    test_file = tmp_path / "backend" / "tests" / "test_service.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "from src.service import get_user_status\n\n"
        "def test_user_status():\n"
        "    assert get_user_status(True) == 'active'\n"
        "    assert get_user_status(False) == 'inactive'\n"
    )

    # Clean Kotlin client file
    kt_file = tmp_path / "android" / "app" / "src" / "main" / "java" / "com" / "upa" / "Feed.kt"
    kt_file.parent.mkdir(parents=True, exist_ok=True)
    kt_file.write_text(
        "package com.upa\n\n"
        "data class FeedItem(val id: String, val title: String)\n"
    )

    # Clean TypeScript web-admin file
    ts_file = tmp_path / "web-admin" / "src" / "api.ts"
    ts_file.parent.mkdir(parents=True, exist_ok=True)
    ts_file.write_text(
        "export interface FeedItem { id: string; title: string; }\n"
        "export async function fetchFeed(): Promise<FeedItem[]> {\n"
        "    const res = await fetch('/api/v1/feed');\n"
        "    return res.json();\n"
        "}\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    assert stats.blocker_count == 0


def test_python_prod_mock_import_detected(tmp_path: Path) -> None:
    prod_file = tmp_path / "backend" / "src" / "service.py"
    prod_file.parent.mkdir(parents=True, exist_ok=True)
    prod_file.write_text(
        "from unittest.mock import MagicMock\n\n"
        "def get_client():\n"
        "    return MagicMock()\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_PROD_MOCKS"]
    assert len(blockers) >= 1
    assert any("forbidden mock" in b.message.lower() for b in blockers)


def test_python_bypass_flags_detected(tmp_path: Path) -> None:
    prod_file = tmp_path / "backend" / "src" / "config.py"
    prod_file.parent.mkdir(parents=True, exist_ok=True)
    prod_file.write_text(
        "MOCK_MODE = True\n"
        "SKIP_AUTH = True\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_MOCK_FLAGS"]
    assert len(blockers) == 2


def test_python_empty_stubs_detected(tmp_path: Path) -> None:
    prod_file = tmp_path / "backend" / "src" / "stubs.py"
    prod_file.parent.mkdir(parents=True, exist_ok=True)
    prod_file.write_text(
        "def fetch_remote_data():\n"
        "    pass\n\n"
        "def process_payment(amount: float):\n"
        "    raise NotImplementedError('payment gateway not wired')\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_EMPTY_STUBS"]
    assert len(blockers) == 2


def test_python_scheintest_without_assertions_detected(tmp_path: Path) -> None:
    test_file = tmp_path / "backend" / "tests" / "test_fake.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "def test_stub_pass():\n"
        "    pass\n\n"
        "def test_stub_no_assert():\n"
        "    a = 1 + 1\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_SCHEINTESTS"]
    assert len(blockers) == 2


def test_backend_missing_healthcheck_detected(tmp_path: Path) -> None:
    backend_file = tmp_path / "backend" / "src" / "main.py"
    backend_file.parent.mkdir(parents=True, exist_ok=True)
    backend_file.write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "# Missing /health route\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "REQUIRE_HEALTHCHECKS"]
    assert len(blockers) == 1


def test_client_jvm_mock_import_detected(tmp_path: Path) -> None:
    kt_file = tmp_path / "android" / "app" / "src" / "main" / "java" / "com" / "upa" / "Client.kt"
    kt_file.parent.mkdir(parents=True, exist_ok=True)
    kt_file.write_text(
        "package com.upa\n\n"
        "import org.mockito.Mockito\n"
        "import io.mockk.mockk\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_PROD_MOCKS_CLIENT"]
    assert len(blockers) == 2


def test_client_jvm_mock_flag_detected(tmp_path: Path) -> None:
    kt_file = tmp_path / "android" / "app" / "src" / "main" / "java" / "com" / "upa" / "Config.kt"
    kt_file.parent.mkdir(parents=True, exist_ok=True)
    kt_file.write_text(
        "package com.upa\n\n"
        "object Config {\n"
        "    val isMock = true\n"
        "    val MOCK_MODE = true\n"
        "}\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_MOCK_FLAGS_CLIENT"]
    assert len(blockers) == 2


def test_client_jvm_todo_stub_detected(tmp_path: Path) -> None:
    kt_file = tmp_path / "android" / "app" / "src" / "main" / "java" / "com" / "upa" / "Repository.kt"
    kt_file.parent.mkdir(parents=True, exist_ok=True)
    kt_file.write_text(
        "package com.upa\n\n"
        "class Repository {\n"
        "    fun loadPosts(): List<String> = TODO('load from server')\n"
        "}\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_EMPTY_STUBS_CLIENT"]
    assert len(blockers) == 1


def test_client_js_mock_import_detected(tmp_path: Path) -> None:
    ts_file = tmp_path / "web-admin" / "src" / "services.ts"
    ts_file.parent.mkdir(parents=True, exist_ok=True)
    ts_file.write_text(
        "import sinon from 'sinon';\n"
        "import nock from 'nock';\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_PROD_MOCKS_CLIENT"]
    assert len(blockers) == 2


def test_client_js_mock_flag_detected(tmp_path: Path) -> None:
    ts_file = tmp_path / "web-admin" / "src" / "config.ts"
    ts_file.parent.mkdir(parents=True, exist_ok=True)
    ts_file.write_text(
        "export const isMock = true;\n"
        "export const useFakeData = true;\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    blockers = [v for v in stats.violations if v.rule_id == "NO_MOCK_FLAGS_CLIENT"]
    assert len(blockers) == 2


def test_client_test_files_permitted_mocks(tmp_path: Path) -> None:
    # Test directory in Android
    kt_test_file = tmp_path / "android" / "app" / "src" / "test" / "java" / "com" / "upa" / "ClientTest.kt"
    kt_test_file.parent.mkdir(parents=True, exist_ok=True)
    kt_test_file.write_text(
        "package com.upa\n\n"
        "import org.mockito.Mockito\n"
        "import io.mockk.mockk\n"
        "class ClientTest {\n"
        "    val isMock = true\n"
        "}\n"
    )

    # Test file in Web
    ts_test_file = tmp_path / "web-admin" / "src" / "__tests__" / "api.test.ts"
    ts_test_file.parent.mkdir(parents=True, exist_ok=True)
    ts_test_file.write_text(
        "import sinon from 'sinon';\n"
        "const isMock = true;\n"
    )

    auditor = ZeroMockAuditor(tmp_path)
    stats = auditor.scan_all()
    assert stats.blocker_count == 0
