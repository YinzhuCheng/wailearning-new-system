"""Emit structured validation capability reports for local and CI use."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_API_PORT = 8012
DEFAULT_UI_PORT = 3012
REQUIRED_BACKEND_MODULES = (
    "uvicorn",
    "fastapi",
    "sqlalchemy",
    "pydantic",
    "pydantic_settings",
    "jose",
    "passlib",
    "multipart",
    "httpx",
)
REQUIRED_FRONTEND_COMMANDS = (
    "node",
    "npm.cmd" if os.name == "nt" else "npm",
    "npx.cmd" if os.name == "nt" else "npx",
)
RAR_EXTRACTOR_CANDIDATES = ("unrar", "unrar-free", "bsdtar", "tar")
CATEGORY_TO_CAPABILITIES = {
    "school-playwright": ["playwright-managed"],
    "parent-playwright": ["playwright-managed"],
    "postgres-pytest": ["postgres-test-env"],
    "full-suite": ["postgres-test-env"],
}
TARGET_TO_CAPABILITIES = {
    "backend.llm.attachment_formats": ["rar-extraction"],
    "backend.files.attachment_api": ["rar-extraction"],
}


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    summary: str
    detail: str = ""


def git_repo_root(start: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return Path(result.stdout.strip()).resolve()


def placeholder_path(repo_root: Path, path: Path | None, include_private: bool) -> str:
    if path is None:
        return ""
    if path.resolve() == repo_root.resolve():
        return "<repo>"
    resolved = path.resolve() if path.exists() else path.absolute()
    if include_private:
        return str(resolved)
    try:
        rel = resolved.relative_to(repo_root.resolve())
    except ValueError:
        return "<local-path>"
    return "<repo>/" + rel.as_posix()


def check_path_exists(name: str, path: Path, repo_root: Path, include_private: bool) -> Check:
    shown = placeholder_path(repo_root, path, include_private)
    if path.exists():
        return Check(name, "pass", f"found {shown}")
    if os.path.lexists(path):
        return Check(name, "fail", f"path entry exists but target is unavailable: {shown}")
    return Check(name, "fail", f"missing {shown}")


def is_windows_junction(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            return bool(is_junction())
        except OSError:
            return False
    return False


def describe_venv(repo_root: Path, include_private: bool, required: bool) -> Check:
    venv = repo_root / ".venv"
    if not (venv.exists() or os.path.lexists(venv)):
        status = "fail" if required else "warn"
        return Check("repository-venv", status, "missing <repo>/.venv")

    link_kind = []
    if venv.is_symlink():
        link_kind.append("symlink")
    if is_windows_junction(venv):
        link_kind.append("junction")
    kind = "/".join(link_kind) if link_kind else "directory"
    detail = ""
    if link_kind:
        try:
            target = venv.resolve(strict=False)
        except OSError as exc:
            target = None
            detail = f"unable to resolve target: {exc}"
        if target is not None:
            detail = f"target={placeholder_path(repo_root, target, include_private)}"
    status = "pass" if venv.exists() else ("fail" if required else "warn")
    summary = f"<repo>/.venv exists ({kind})" if venv.exists() else f"<repo>/.venv entry exists but target is unavailable ({kind})"
    return Check("repository-venv", status, summary, detail)


def default_python(repo_root: Path) -> Path:
    if os.name == "nt":
        return repo_root / ".venv" / "Scripts" / "python.exe"
    return repo_root / ".venv" / "bin" / "python"


def selected_python(repo_root: Path) -> tuple[Path, str]:
    configured = os.environ.get("E2E_PYTHON")
    if configured:
        return Path(configured), "E2E_PYTHON"
    return default_python(repo_root), "playwright default"


def check_python_exists(repo_root: Path, include_private: bool) -> tuple[Check, Path | None]:
    python_path, source = selected_python(repo_root)
    shown = placeholder_path(repo_root, python_path, include_private)
    if python_path.exists():
        return Check("e2e-python", "pass", f"{source} exists: {shown}"), python_path
    return Check("e2e-python", "fail", f"{source} missing: {shown}"), None


def python_probe(python_path: Path | None, code: str, timeout: int = 20) -> subprocess.CompletedProcess[str] | None:
    if python_path is None:
        return None
    try:
        return subprocess.run(
            [str(python_path), "-c", code],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_backend_imports(python_path: Path | None) -> Check:
    if python_path is None:
        return Check("backend-imports", "fail", "cannot check backend imports without a Python executable")
    code = (
        "import importlib.util, sys; "
        f"missing=[m for m in {REQUIRED_BACKEND_MODULES!r} if importlib.util.find_spec(m) is None]; "
        "print('\\n'.join(missing)); "
        "sys.exit(1 if missing else 0)"
    )
    result = python_probe(python_path, code)
    if result is None:
        return Check("backend-imports", "fail", "backend import check could not run")
    missing = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode == 0 and not missing:
        return Check("backend-imports", "pass", "Python can import backend modules required for managed E2E startup and seed")
    detail = result.stderr.strip()
    if missing:
        detail = f"missing modules: {', '.join(missing)}"
    return Check("backend-imports", "fail", "Python is missing backend dependencies", detail)


def check_python_version(python_path: Path | None) -> Check:
    result = python_probe(
        python_path,
        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
    )
    if result is None:
        return Check("python-version", "fail", "cannot inspect Python version without a runnable E2E Python")
    version = result.stdout.strip() or "unknown"
    if result.returncode != 0:
        return Check("python-version", "fail", "Python version probe failed", result.stderr.strip())
    major_minor = tuple(int(part) for part in version.split(".")[:2] if part.isdigit())
    if major_minor >= (3, 14):
        return Check(
            "python-version",
            "pass",
            f"E2E Python is {version}; usable for local smoke when dependencies are installed",
            "Python 3.14 requires dependency pins that publish cp314 wheels; requirements-python-compat reports known stale pins.",
        )
    if major_minor < (3, 11):
        return Check("python-version", "warn", f"E2E Python is {version}; expected Python 3.11/3.12 for current validation")
    return Check("python-version", "pass", f"E2E Python is {version}")


def check_pinned_requirements_python314(python_path: Path | None, repo_root: Path) -> Check:
    result = python_probe(python_path, "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if result is None or result.returncode != 0:
        return Check("requirements-python-compat", "fail", "cannot inspect Python version for requirements compatibility")
    version = result.stdout.strip()
    if version != "3.14":
        return Check("requirements-python-compat", "pass", "E2E Python is not 3.14; no Python-3.14 pin warning needed")
    requirements = repo_root / "requirements.txt"
    if not requirements.exists():
        return Check("requirements-python-compat", "warn", "requirements.txt missing; cannot check Python 3.14 pin risks")
    text = requirements.read_text(encoding="utf-8", errors="replace")
    risky = []
    if "pydantic==2.5.3" in text:
        risky.append("pydantic==2.5.3 requires pydantic-core==2.14.6, which has no Python 3.14 wheel")
    if "psycopg2-binary==2.9.9" in text:
        risky.append("psycopg2-binary==2.9.9 may source-build on Python 3.14 and require pg_config")
    if risky:
        return Check("requirements-python-compat", "pass", "requirements.txt contains stale pins with known Python 3.14 install risk", "; ".join(risky))
    return Check("requirements-python-compat", "pass", "no known Python 3.14 pin risks found in requirements.txt")


def check_password_hash_smoke(python_path: Path | None) -> Check:
    code = (
        "from passlib.context import CryptContext; "
        "ctx=CryptContext(schemes=['bcrypt'], deprecated='auto'); "
        "hashed=ctx.hash('test-playwright-seed-admin-password'); "
        "print(hashed[:4])"
    )
    result = python_probe(python_path, code)
    if result is None:
        return Check("password-hash-smoke", "fail", "password hash smoke could not run")
    if result.returncode == 0 and result.stdout.strip().startswith("$2"):
        return Check("password-hash-smoke", "pass", "passlib bcrypt hash smoke passed for E2E seed-style password")
    detail = (result.stderr or result.stdout).strip()
    return Check("password-hash-smoke", "fail", "passlib bcrypt hash smoke failed; E2E reset-scenario may return 500", detail)


def check_command(name: str, command: str) -> Check:
    found = shutil.which(command)
    if found:
        return Check(name, "pass", f"{command} found on PATH")
    return Check(name, "fail", f"{command} not found on PATH")


def check_port(port: int) -> Check:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex(("127.0.0.1", port))
    if result == 0:
        return Check(f"port-{port}", "warn", f"127.0.0.1:{port} already accepts TCP connections")
    return Check(f"port-{port}", "pass", f"127.0.0.1:{port} appears free")


def playwright_sqlite_path(api_port: int) -> Path:
    return Path(tempfile.gettempdir()) / f"playwright_e2e_{api_port}.sqlite"


def check_playwright_sqlite(api_port: int, repo_root: Path, include_private: bool) -> Check:
    db_path = playwright_sqlite_path(api_port)
    if not db_path.exists():
        return Check("playwright-sqlite", "pass", f"default Playwright SQLite file is absent for port {api_port}")
    shown = placeholder_path(repo_root, db_path, include_private)
    try:
        size = db_path.stat().st_size
    except OSError as exc:
        return Check("playwright-sqlite", "warn", f"default Playwright SQLite file exists but cannot be inspected: {shown}", str(exc))
    return Check("playwright-sqlite", "pass", f"default Playwright SQLite file already exists: {shown}", f"size={size}; if a previous reset-scenario failed, rerun with a fresh E2E_API_PORT or remove this local artifact after confirming no Playwright process is using it.")


def playwright_external_servers_enabled() -> bool:
    value = os.environ.get("PLAYWRIGHT_USE_EXTERNAL_SERVERS", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def check_env_var(name: str) -> Check:
    value = os.environ.get(name, "").strip()
    if value:
        return Check(name.lower(), "pass", f"{name} is set")
    return Check(name.lower(), "fail", f"{name} is not set")


def check_postgres_listener(url: str) -> Check:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex((host, port))
    if result == 0:
        return Check("postgres-listener", "pass", f"PostgreSQL listener accepts TCP on {host}:{port}")
    return Check("postgres-listener", "fail", f"PostgreSQL listener is not reachable on {host}:{port}")


def check_rar_extractor() -> Check:
    found = [command for command in RAR_EXTRACTOR_CANDIDATES if shutil.which(command)]
    if found:
        return Check("rar-extractor", "pass", f"RAR extractor available via {', '.join(found)}")
    return Check("rar-extractor", "warn", "no unrar / unrar-free / bsdtar / tar extractor found on PATH")


def summarize_capability(name: str, checks: list[Check]) -> dict[str, Any]:
    if any(check.status == "fail" for check in checks):
        status = "fail"
    elif any(check.status == "warn" for check in checks):
        status = "warn"
    else:
        status = "pass"
    return {"name": name, "status": status, "checks": [asdict(check) for check in checks]}


def build_playwright_capability(repo_root: Path, include_private: bool) -> dict[str, Any]:
    school_root = repo_root / "apps" / "web" / "school"
    vite_bin = school_root / "node_modules" / "vite" / "bin" / "vite.js"
    playwright_config = school_root / "playwright.config.cjs"
    package_lock = school_root / "package-lock.json"
    use_managed_web_server = not playwright_external_servers_enabled()
    checks: list[Check] = [
        check_path_exists("school-root", school_root, repo_root, include_private),
        check_path_exists("playwright-config", playwright_config, repo_root, include_private),
        check_path_exists("school-package-lock", package_lock, repo_root, include_private),
        check_path_exists("vite-bin", vite_bin, repo_root, include_private),
        describe_venv(repo_root, include_private, use_managed_web_server),
    ]
    for command in REQUIRED_FRONTEND_COMMANDS:
        checks.append(check_command(command, command))
    if use_managed_web_server:
        python_check, python_path = check_python_exists(repo_root, include_private)
        checks.extend([python_check, check_python_version(python_path), check_pinned_requirements_python314(python_path, repo_root), check_backend_imports(python_path), check_password_hash_smoke(python_path)])
    else:
        checks.extend([
            Check("e2e-python", "warn", "skipped because PLAYWRIGHT_USE_EXTERNAL_SERVERS is enabled", "managed webServer will not start the backend"),
            Check("python-version", "warn", "skipped because PLAYWRIGHT_USE_EXTERNAL_SERVERS is enabled", "managed webServer will not start the backend"),
            Check("requirements-python-compat", "warn", "skipped because PLAYWRIGHT_USE_EXTERNAL_SERVERS is enabled", "managed webServer will not start the backend"),
            Check("backend-imports", "warn", "skipped because PLAYWRIGHT_USE_EXTERNAL_SERVERS is enabled", "managed webServer will not start the backend"),
            Check("password-hash-smoke", "warn", "skipped because PLAYWRIGHT_USE_EXTERNAL_SERVERS is enabled", "managed webServer will not run reset-scenario"),
        ])
    api_port = int(os.environ.get("E2E_API_PORT", DEFAULT_API_PORT))
    ui_port = int(os.environ.get("E2E_UI_PORT", DEFAULT_UI_PORT))
    checks.extend([check_port(api_port), check_port(ui_port)])
    if use_managed_web_server:
        checks.append(check_playwright_sqlite(api_port, repo_root, include_private))
    capability = summarize_capability("playwright-managed", checks)
    capability["managed_web_server"] = use_managed_web_server
    capability["school_root"] = placeholder_path(repo_root, school_root, include_private)
    return capability


def build_postgres_capability() -> dict[str, Any]:
    env_check = check_env_var("TEST_DATABASE_URL")
    checks = [env_check]
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if url:
        checks.append(check_postgres_listener(url))
    return summarize_capability("postgres-test-env", checks)


def build_rar_capability() -> dict[str, Any]:
    return summarize_capability("rar-extraction", [check_rar_extractor()])


def build_text_safety_capability() -> dict[str, Any]:
    if os.name != "nt":
        checks = [Check("powershell-text-safety", "pass", "non-Windows shell; PowerShell UTF-8 session guard is not required")]
    else:
        checks = [Check("powershell-text-safety", "warn", "Windows shell detected; use safe-text workflow for multilingual edits")]
    return summarize_capability("text-safety", checks)


def build_capabilities(repo_root: Path, include_private: bool) -> dict[str, Any]:
    capabilities = [
        build_playwright_capability(repo_root, include_private),
        build_postgres_capability(),
        build_rar_capability(),
        build_text_safety_capability(),
    ]
    if any(item["status"] == "fail" for item in capabilities):
        exit_code = 1
    elif any(item["status"] == "warn" for item in capabilities):
        exit_code = 2
    else:
        exit_code = 0
    return {"schema_version": 1, "repo_root": placeholder_path(repo_root, repo_root, include_private), "exit_code": exit_code, "capabilities": capabilities}


def required_capability_names(target: dict[str, Any]) -> list[str]:
    names = list(CATEGORY_TO_CAPABILITIES.get(str(target.get("category") or ""), []))
    target_id = str(target.get("id") or "")
    names.extend(TARGET_TO_CAPABILITIES.get(target_id, []))
    deduped: list[str] = []
    for name in names:
        if name not in deduped:
            deduped.append(name)
    return deduped


def evaluate_target_capabilities(report: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    capabilities = {str(item.get("name")): item for item in report.get("capabilities", []) if isinstance(item, dict)}
    results: list[dict[str, Any]] = []
    for name in required_capability_names(target):
        capability = capabilities.get(name)
        if capability is None:
            results.append({"name": name, "status": "fail", "reason": "capability report did not include this capability"})
            continue
        first_check = capability.get("checks", [{}])[0] if capability.get("checks") else {}
        results.append({"name": name, "status": capability.get("status"), "reason": first_check.get("summary", ""), "capability": capability})
    return results


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to git rev-parse.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--include-private-paths", action="store_true", help="Print absolute local paths.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else git_repo_root(Path.cwd())
    payload = build_capabilities(repo_root, args.include_private_paths)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("# Validation Capability Report")
        print(f"Repository: {payload['repo_root']}")
        for capability in payload["capabilities"]:
            print(f"[{str(capability['status']).upper()}] {capability['name']}")
            for check in capability["checks"]:
                detail = f" ({check['detail']})" if check.get("detail") else ""
                print(f"  - [{str(check['status']).upper()}] {check['name']}: {check['summary']}{detail}")
        if payload["exit_code"] == 1:
            print("Result: failed capability report.")
        elif payload["exit_code"] == 2:
            print("Result: capability report passed with warnings.")
        else:
            print("Result: capability report passed.")
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
