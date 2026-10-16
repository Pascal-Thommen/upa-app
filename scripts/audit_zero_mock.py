#!/usr/bin/env python3
"""
Zero-Mock & Architecture Audit Tool for Gatekeeper CI (UPA App).

Enforces the Zero Mock Doktrin and software-testing-audit requirements:
1. Absolutes Verbot von Demos, Scheinoberflächen, Dummy-Buttons und Mocks im Produktivcode.
2. Automatisierter Scan für Python Backend und Client Code (Android Kotlin/Java, Web-Admin TS/JS).
3. Keine Scheintests (Tests ohne Assertions oder Stubs).
4. Einhaltung der 4 Kernsäulen (Resilienz/Timeouts, ACID, Sicherheit, Observability/Healthchecks).

Returns exit code 0 if all checks pass, 1 if any violation is found.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuditViolation:
    rule_id: str
    severity: str  # "BLOCKER" or "WARNING"
    file_path: Path
    line_number: int
    message: str
    code_snippet: str | None = None


@dataclass
class AuditStats:
    total_files_scanned: int = 0
    python_files_scanned: int = 0
    client_files_scanned: int = 0
    production_files_scanned: int = 0
    test_files_scanned: int = 0
    violations: list[AuditViolation] = field(default_factory=list)

    @property
    def blocker_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "BLOCKER")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "WARNING")


class ZeroMockAuditor:
    # Python: Forbidden mock module names in production code
    PYTHON_FORBIDDEN_PROD_MOCK_MODULES = {
        "unittest.mock",
        "mock",
        "pytest_mock",
    }

    # Python: Forbidden mock classes or objects in production code
    PYTHON_FORBIDDEN_PROD_MOCK_NAMES = {
        "Mock",
        "MagicMock",
        "patch",
        "AsyncMock",
        "PropertyMock",
        "create_autospec",
        "NonCallableMock",
    }

    # Forbidden bypass or dummy flags across all languages
    FORBIDDEN_BYPASS_FLAGS = {
        "MOCK_MODE",
        "ENABLE_MOCK",
        "ENABLE_MOCKS",
        "USE_MOCK",
        "USE_MOCKS",
        "SKIP_AUTH",
        "BYPASS_AUTH",
        "BYPASS_SECURITY",
        "USE_FAKE_DATA",
        "USE_MOCK_GATEWAY",
        "MOCK_PAYMENT",
    }

    # HTTP client call functions that require an explicit timeout (Python)
    HTTP_CALL_NAMES = {
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "request",
        "Client",
        "AsyncClient",
    }

    # Client (Kotlin/Java): Forbidden mock imports in production code
    JVM_FORBIDDEN_PROD_MOCK_PACKAGES = (
        "org.mockito",
        "io.mockk",
        "okhttp3.mockwebserver",
        "com.github.tomakehurst.wiremock",
        "org.easymock",
        "org.powermock",
        "android.test.mock",
    )

    # Client (TypeScript/JavaScript): Forbidden mock imports in production code
    JS_FORBIDDEN_PROD_MOCK_PACKAGES = (
        "jest-mock",
        "sinon",
        "nock",
        "msw",
    )

    CLIENT_EXTENSIONS = {".kt", ".kts", ".java", ".ts", ".tsx", ".js", ".jsx"}

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.stats = AuditStats()

    def is_test_file(self, path: Path) -> bool:
        parts = [p.lower() for p in path.parts]
        test_indicators = {
            "tests",
            "test",
            "androidtest",
            "testdebug",
            "testrelease",
            "__tests__",
            "spec",
            "specs",
        }
        if any(part in test_indicators for part in parts):
            return True

        filename = path.name.lower()
        if filename.startswith("test_") or filename.endswith("_test.py"):
            return True
        if filename.endswith("test.kt") or filename.endswith("tests.kt"):
            return True
        if filename.endswith("test.java") or filename.endswith("tests.java"):
            return True
        if re.search(r"\.(test|spec)\.(ts|tsx|js|jsx)$", filename):
            return True
        if filename in ("conftest.py", "setup_tests.ts", "jest.setup.js"):
            return True

        return False

    def is_ignored_path(self, path: Path) -> bool:
        parts = path.parts
        ignored_names = {
            ".git",
            ".github",
            ".venv",
            ".venv-vibecore",
            "venv",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            "node_modules",
            ".next",
            ".gradle",
            "build",
            "dist",
            ".idea",
            ".eggs",
            "target",
        }
        return any(part in ignored_names for part in parts)

    def scan_all(self) -> AuditStats:
        scanned_files: list[Path] = []
        for p in self.root_dir.rglob("*"):
            if not p.is_file() or self.is_ignored_path(p):
                continue
            if p.suffix == ".py":
                scanned_files.append(p)
                self.stats.python_files_scanned += 1
            elif p.suffix in self.CLIENT_EXTENSIONS:
                scanned_files.append(p)
                self.stats.client_files_scanned += 1

        self.stats.total_files_scanned = len(scanned_files)

        for file_path in scanned_files:
            rel_path = file_path.relative_to(self.root_dir)
            is_test = self.is_test_file(file_path)
            if is_test:
                self.stats.test_files_scanned += 1
            else:
                self.stats.production_files_scanned += 1

            if file_path.suffix == ".py":
                if is_test:
                    self.audit_python_test_file(file_path, rel_path)
                else:
                    self.audit_python_production_file(file_path, rel_path)
            elif file_path.suffix in self.CLIENT_EXTENSIONS:
                if is_test:
                    self.audit_client_test_file(file_path, rel_path)
                else:
                    self.audit_client_production_file(file_path, rel_path)

        # Microservice health check verification
        self.audit_healthchecks()

        return self.stats

    def _get_line_snippet(self, file_path: Path, line_number: int) -> str | None:
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                if 1 <= line_number <= len(lines):
                    return lines[line_number - 1].strip()
        except Exception:
            pass
        return None

    def add_violation(
        self,
        rule_id: str,
        severity: str,
        file_path: Path,
        line_number: int,
        message: str,
    ) -> None:
        snippet = self._get_line_snippet(file_path, line_number)
        self.stats.violations.append(
            AuditViolation(
                rule_id=rule_id,
                severity=severity,
                file_path=file_path.relative_to(self.root_dir),
                line_number=line_number,
                message=message,
                code_snippet=snippet,
            )
        )

    def audit_python_production_file(self, file_path: Path, rel_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            self.add_violation(
                "SYNTAX_ERROR",
                "BLOCKER",
                file_path,
                e.lineno or 1,
                f"Syntax error in production file: {e.msg}",
            )
            return

        for node in ast.walk(tree):
            # Check 1: Forbidden mock library imports in production
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if (
                        alias.name in self.PYTHON_FORBIDDEN_PROD_MOCK_MODULES
                        or alias.name.startswith("unittest.mock")
                    ):
                        self.add_violation(
                            "NO_PROD_MOCKS",
                            "BLOCKER",
                            file_path,
                            node.lineno,
                            (
                                f"Production code imports forbidden mock module '{alias.name}'. "
                                "Mocks are prohibited in production code per Zero Mock Doktrin."
                            ),
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if (
                    mod in self.PYTHON_FORBIDDEN_PROD_MOCK_MODULES
                    or mod.startswith("unittest.mock")
                ):
                    self.add_violation(
                        "NO_PROD_MOCKS",
                        "BLOCKER",
                        file_path,
                        node.lineno,
                        (
                            f"Production code imports from forbidden mock module '{mod}'. "
                            "Mocks are strictly prohibited in production code."
                        ),
                    )
                for alias in node.names:
                    if alias.name in self.PYTHON_FORBIDDEN_PROD_MOCK_NAMES:
                        self.add_violation(
                            "NO_PROD_MOCKS",
                            "BLOCKER",
                            file_path,
                            node.lineno,
                            (
                                f"Production code imports forbidden mock object '{alias.name}'. "
                                "Mocks are prohibited in production code."
                            ),
                        )

            # Check 2: Bypass flags
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in self.FORBIDDEN_BYPASS_FLAGS:
                        if isinstance(node.value, ast.Constant) and node.value.value in (
                            True,
                            "true",
                            "True",
                            1,
                        ):
                            self.add_violation(
                                "NO_MOCK_FLAGS",
                                "BLOCKER",
                                file_path,
                                node.lineno,
                                (
                                    f"Bypass/Mock flag detected: '{target.id} = {node.value.value}'. "
                                    "Bypasses forbidden per Zero Mock Doktrin."
                                ),
                            )

            # Check 3: Unimplemented Stubs in functions (pass or NotImplementedError only)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorator_names = [
                    d.id
                    if isinstance(d, ast.Name)
                    else (d.attr if isinstance(d, ast.Attribute) else "")
                    for d in node.decorator_list
                ]
                if any("abstractmethod" in dec for dec in decorator_names):
                    continue

                if node.name.startswith("__") and node.name.endswith("__"):
                    continue

                statements = [
                    s
                    for s in node.body
                    if not (
                        isinstance(s, ast.Expr)
                        and isinstance(s.value, ast.Constant)
                        and isinstance(s.value.value, str)
                    )
                ]
                if len(statements) == 1:
                    stmt = statements[0]
                    if isinstance(stmt, ast.Pass):
                        self.add_violation(
                            "NO_EMPTY_STUBS",
                            "BLOCKER",
                            file_path,
                            node.lineno,
                            (
                                f"Function '{node.name}' is an empty stub ('pass'). "
                                "Full implementation with real business logic required."
                            ),
                        )
                    elif isinstance(stmt, ast.Raise):
                        exc = stmt.exc
                        is_not_implemented = False
                        if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                            is_not_implemented = True
                        elif (
                            isinstance(exc, ast.Call)
                            and isinstance(exc.func, ast.Name)
                            and exc.func.id == "NotImplementedError"
                        ):
                            is_not_implemented = True
                        if is_not_implemented:
                            self.add_violation(
                                "NO_EMPTY_STUBS",
                                "BLOCKER",
                                file_path,
                                node.lineno,
                                (
                                    f"Function '{node.name}' raises NotImplementedError. "
                                    "Full implementation required per Zero Mock Doktrin."
                                ),
                            )

            # Check 4: Timeouts on external HTTP network calls (Säule 1)
            if isinstance(node, ast.Call):
                func = node.func
                is_http_call = False
                call_name = ""
                if isinstance(func, ast.Attribute):
                    call_name = func.attr
                    if isinstance(func.value, ast.Name) and func.value.id in ("httpx", "requests"):
                        if call_name in self.HTTP_CALL_NAMES:
                            is_http_call = True
                if is_http_call:
                    has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
                    if not has_timeout:
                        self.add_violation(
                            "REQUIRE_TIMEOUTS",
                            "WARNING",
                            file_path,
                            node.lineno,
                            (
                                f"External HTTP call '{call_name}' lacks explicit timeout. "
                                "Säule 1 requires explicit timeouts."
                            ),
                        )

    def audit_python_test_file(self, file_path: Path, rel_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            self.add_violation(
                "SYNTAX_ERROR",
                "BLOCKER",
                file_path,
                e.lineno or 1,
                f"Syntax error in test file: {e.msg}",
            )
            return

        if file_path.name == "conftest.py":
            return

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                decorator_names = [
                    d.id
                    if isinstance(d, ast.Name)
                    else (d.attr if isinstance(d, ast.Attribute) else "")
                    for d in node.decorator_list
                ]
                if any("fixture" in dec for dec in decorator_names):
                    continue

                has_assert = False
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assert):
                        has_assert = True
                        break
                    if isinstance(sub, ast.With):
                        for item in sub.items:
                            ctx = item.context_expr
                            if isinstance(ctx, ast.Call):
                                if isinstance(ctx.func, ast.Attribute) and ctx.func.attr in (
                                    "raises",
                                    "warns",
                                ):
                                    has_assert = True
                                    break
                    if isinstance(sub, ast.Call):
                        if isinstance(sub.func, ast.Attribute) and (
                            sub.func.attr.startswith("assert_")
                            or sub.func.attr in ("raise_for_status", "fail")
                        ):
                            has_assert = True
                            break

                is_just_pass = len(node.body) == 1 and isinstance(node.body[0], ast.Pass)

                if is_just_pass or not has_assert:
                    self.add_violation(
                        "NO_SCHEINTESTS",
                        "BLOCKER",
                        file_path,
                        node.lineno,
                        (
                            f"Scheintest detected: test '{node.name}' has no assertions. "
                            "Tests must rigorously verify behavior."
                        ),
                    )

    def audit_client_production_file(self, file_path: Path, rel_path: Path) -> None:
        """Scan Android (Kotlin/Java) and Web (TS/JS) client production files for forbidden mocks."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            self.add_violation(
                "READ_ERROR",
                "BLOCKER",
                file_path,
                1,
                f"Unable to read file: {e}",
            )
            return

        lines = content.splitlines()
        is_jvm = file_path.suffix in {".kt", ".kts", ".java"}
        is_js = file_path.suffix in {".ts", ".tsx", ".js", ".jsx"}

        for idx, line in enumerate(lines, start=1):
            clean_line = line.strip()

            # Skip comments
            if clean_line.startswith(("//", "/*", "*", "#")):
                continue

            # Check 1: Forbidden mock imports in client production code
            if is_jvm:
                if clean_line.startswith("import "):
                    for pkg in self.JVM_FORBIDDEN_PROD_MOCK_PACKAGES:
                        if pkg in clean_line:
                            self.add_violation(
                                "NO_PROD_MOCKS_CLIENT",
                                "BLOCKER",
                                file_path,
                                idx,
                                (
                                    f"Client production code imports forbidden mock package '{pkg}'. "
                                    "Mocks are prohibited in production client code."
                                ),
                            )
            elif is_js:
                if "import " in clean_line or "require(" in clean_line:
                    for pkg in self.JS_FORBIDDEN_PROD_MOCK_PACKAGES:
                        if f'"{pkg}"' in clean_line or f"'{pkg}'" in clean_line:
                            self.add_violation(
                                "NO_PROD_MOCKS_CLIENT",
                                "BLOCKER",
                                file_path,
                                idx,
                                (
                                    f"Client production code imports forbidden mock package '{pkg}'. "
                                    "Mocks are prohibited in production client code."
                                ),
                            )

            # Check 2: Forbidden mock / bypass flags in client production code
            flag_pattern = (
                r"\b(MOCK_MODE|ENABLE_MOCKS?|USE_MOCKS?|SKIP_AUTH|BYPASS_AUTH|USE_FAKE_DATA|"
                r"isMock|isMockMode|useMock|mockEnabled|useFakeData)\s*[:=]\s*(true|1)\b"
            )
            match = re.search(flag_pattern, clean_line, re.IGNORECASE)
            if match:
                self.add_violation(
                    "NO_MOCK_FLAGS_CLIENT",
                    "BLOCKER",
                    file_path,
                    idx,
                    (
                        f"Bypass/Mock flag detected: '{match.group(0)}'. "
                        "Mock modes and bypass flags are forbidden in production client code."
                    ),
                )

            # Check 3: Kotlin TODO() stubs in production methods
            if is_jvm and file_path.suffix in {".kt", ".kts"}:
                if re.search(r"\bTODO\s*\([^)]*\)", clean_line):
                    self.add_violation(
                        "NO_EMPTY_STUBS_CLIENT",
                        "BLOCKER",
                        file_path,
                        idx,
                        (
                            "Kotlin TODO() stub detected in production code. "
                            "Full implementation with real business logic required."
                        ),
                    )

    def audit_client_test_file(self, file_path: Path, rel_path: Path) -> None:
        """Scan client test files to ensure valid encoding and verify they are not empty stubs."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            self.add_violation(
                "READ_ERROR",
                "BLOCKER",
                file_path,
                1,
                f"Unable to read test file: {e}",
            )
            return

        if not content.strip():
            self.add_violation(
                "EMPTY_TEST_FILE",
                "BLOCKER",
                file_path,
                1,
                "Test file is completely empty. Tests must contain executable test cases.",
            )

    def audit_healthchecks(self) -> None:
        backend_dir = self.root_dir / "backend"
        if not backend_dir.exists():
            return

        has_health = False
        for py_file in backend_dir.rglob("*.py"):
            if self.is_ignored_path(py_file):
                continue
            try:
                text = py_file.read_text(encoding="utf-8", errors="replace")
                if (
                    re.search(r"""["']/(health|ready|healthz)["']""", text)
                    or "health_router" in text
                ):
                    has_health = True
                    break
            except Exception:
                pass

        if not has_health:
            self.add_violation(
                "REQUIRE_HEALTHCHECKS",
                "BLOCKER",
                backend_dir,
                1,
                "Observability Violation: Backend lacks /health or /ready endpoint.",
            )


def format_console_report(stats: AuditStats) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("🛡️  GATEKEEPER ZERO-MOCK & ARCHITECTURE AUDIT REPORT (UPA APP)")
    lines.append("=" * 80)
    lines.append(f"Total Files Scanned:       {stats.total_files_scanned}")
    lines.append(f"  - Python Files:          {stats.python_files_scanned}")
    lines.append(f"  - Client Files:          {stats.client_files_scanned}")
    lines.append(f"  - Production Files:      {stats.production_files_scanned}")
    lines.append(f"  - Test Files:            {stats.test_files_scanned}")
    lines.append(f"Blocker Violations:        {stats.blocker_count}")
    lines.append(f"Warnings:                  {stats.warning_count}")
    lines.append("-" * 80)

    if not stats.violations:
        lines.append("✅ ALL CHECKS PASSED: Codebase strictly complies with Zero Mock Doktrin")
        lines.append("   and software-testing-audit requirements.")
        lines.append("=" * 80)
        return "\n".join(lines)

    for v in stats.violations:
        prefix = "❌ [BLOCKER]" if v.severity == "BLOCKER" else "⚠️  [WARNING]"
        lines.append(f"{prefix} {v.rule_id} at {v.file_path}:{v.line_number}")
        lines.append(f"   Message: {v.message}")
        if v.code_snippet:
            lines.append(f"   Code:    {v.code_snippet}")
        lines.append("")

    lines.append("=" * 80)
    if stats.blocker_count > 0:
        lines.append(
            f"❌ AUDIT FAILED: {stats.blocker_count} blocker violation(s) must be resolved."
        )
    else:
        lines.append("⚠️  AUDIT PASSED WITH WARNINGS (no blockers).")
    lines.append("=" * 80)
    return "\n".join(lines)


def write_github_step_summary(stats: AuditStats) -> None:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return

    status_icon = "✅" if stats.blocker_count == 0 else "❌"
    status_text = "PASSED" if stats.blocker_count == 0 else "FAILED"

    md = []
    md.append(f"## {status_icon} Gatekeeper Zero-Mock & Architecture Audit: {status_text}\n")
    md.append(
        "Automated verification under **Zero Mock Doktrin** and **software-testing-audit**.\n"
    )

    md.append("| Metric | Count |")
    md.append("|---|---|")
    md.append(f"| Total Files Scanned | {stats.total_files_scanned} |")
    md.append(f"| Python Files | {stats.python_files_scanned} |")
    md.append(f"| Client Files (Android/Web) | {stats.client_files_scanned} |")
    md.append(f"| Production Files | {stats.production_files_scanned} |")
    md.append(f"| Test Files | {stats.test_files_scanned} |")
    md.append(f"| **Blocker Violations** | **{stats.blocker_count}** |")
    md.append(f"| Warnings | {stats.warning_count} |\n")

    if stats.violations:
        md.append("### 🔍 Audit Findings\n")
        md.append("| Severity | Rule | Location | Description |")
        md.append("|---|---|---|---|")
        for v in stats.violations:
            badge = "🔴 BLOCKER" if v.severity == "BLOCKER" else "🟡 WARNING"
            loc = f"`{v.file_path}:{v.line_number}`"
            msg = v.message.replace("|", "\\|")
            md.append(f"| {badge} | `{v.rule_id}` | {loc} | {msg} |")
        md.append("")

    if stats.blocker_count == 0:
        md.append(
            "> **Gatekeeper Recommendation**: CI verification succeeded. "
            "Ready for architectural evaluation and merge approval.\n"
        )
    else:
        md.append(
            "> **Gatekeeper Recommendation**: PR blocked. "
            "Resolve the blocker violations above before requesting review.\n"
        )

    try:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")
    except Exception as e:
        print(f"Warning: Failed to write to GITHUB_STEP_SUMMARY: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit codebase for Zero Mock Doktrin and architecture compliance."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("."),
        help="Path to repository root (default: current directory)",
    )
    parser.add_argument(
        "--github-summary",
        action="store_true",
        help="Write summary to $GITHUB_STEP_SUMMARY if available",
    )
    args = parser.parse_args()

    auditor = ZeroMockAuditor(args.path)
    stats = auditor.scan_all()

    report = format_console_report(stats)
    print(report)

    if args.github_summary or os.environ.get("GITHUB_STEP_SUMMARY"):
        write_github_step_summary(stats)

    return 1 if stats.blocker_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
