"""Pytest: configure env before importing app (database, worker, test hooks)."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

if os.name == "nt":
    import _pytest.pathlib as pytest_pathlib

    _orig_cleanup_dead_symlinks = pytest_pathlib.cleanup_dead_symlinks
    _orig_rm_rf = pytest_pathlib.rm_rf

    def _safe_cleanup_dead_symlinks(root: Path) -> None:
        try:
            _orig_cleanup_dead_symlinks(root)
        except PermissionError:
            return

    def _safe_rm_rf(path: Path) -> None:
        try:
            _orig_rm_rf(path)
        except PermissionError:
            return

    pytest_pathlib.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks
    pytest_pathlib.rm_rf = _safe_rm_rf


def _env_flag(name: str, default: bool) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return "true" if default else "false"
    return "true" if raw.strip().lower() in {"1", "true", "yes", "on"} else "false"


_tmp_dir = Path(__file__).resolve().parents[1] / ".pytest_tmp"
_tmp_dir.mkdir(exist_ok=True)
_default_sqlite_name = f"test_{os.getpid()}.sqlite"
_sqlite_name = (os.environ.get("PYTEST_SQLITE_BASENAME") or _default_sqlite_name).strip() or _default_sqlite_name
_tmp = _tmp_dir / _sqlite_name
_sqlite_url = "sqlite:///" + _tmp.resolve().as_posix()


def _default_postgres_pytest_url() -> str:
    """URL used by ops/scripts/dev/provision_postgres_pytest.sh (throwaway CI/local DB)."""
    return (
        "postgresql+psycopg2://courseeval_test:courseeval_test@127.0.0.1:5432/courseeval_pytest_all"
    )


def _tcp_postgres_reachable(url: str) -> bool:
    """Cheap probe: can we TCP-connect to host:port (no credentials on wire)."""
    if "127.0.0.1" not in url and "localhost" not in url:
        return False
    try:
        host, port = "127.0.0.1", 5432
        if "@127.0.0.1:" in url:
            rest = url.split("@127.0.0.1:", 1)[1]
            port = int(rest.split("/", 1)[0])
        elif "@localhost:" in url:
            rest = url.split("@localhost:", 1)[1]
            port = int(rest.split("/", 1)[0])
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _auto_pick_postgres_test_url() -> str | None:
    """If COURSEEVAL_AUTO_PG_TESTS is set and Postgres probe URL answers, use it.

    Eliminates skips on ``tests/postgres/*`` and ``test_r3`` without requiring
    every developer to manually export TEST_DATABASE_URL after running
    ``ops/scripts/dev/provision_postgres_pytest.sh``.
    """
    raw = os.environ.get("COURSEEVAL_AUTO_PG_TESTS", "").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return None
    candidate = _default_postgres_pytest_url()
    if not _tcp_postgres_reachable(candidate):
        return None
    try:
        import psycopg2  # noqa: PLC0415

        psycopg2.connect(
            dbname="courseeval_pytest_all",
            user="courseeval_test",
            password="courseeval_test",
            host="127.0.0.1",
            port=5432,
            connect_timeout=2,
        ).close()
    except Exception:
        return None
    return candidate


_explicit_test_db = os.environ.get("TEST_DATABASE_URL", "").strip()
_database_url = _explicit_test_db or _auto_pick_postgres_test_url() or _sqlite_url

os.environ["DATABASE_URL"] = _database_url
os.environ["ENABLE_LLM_GRADING_WORKER"] = _env_flag("TEST_ENABLE_LLM_GRADING_WORKER", False)
os.environ["LLM_GRADING_WORKER_LEADER"] = _env_flag("TEST_LLM_GRADING_WORKER_LEADER", False)
os.environ["INIT_DEFAULT_DATA"] = "false"
# Long enough for production-style REQUIRE_STRONG_SECRETS / APP_ENV=production validation.
os.environ["SECRET_KEY"] = "pytest-secret-key-homework-llm-" + ("x" * 40)
os.environ["TRUSTED_HOSTS"] = "localhost,127.0.0.1,testserver"
os.environ["LLM_GRADING_TEST_SKIP_BACKOFF"] = "1"

_DEFAULT_ENABLE_WORKER = os.environ["ENABLE_LLM_GRADING_WORKER"] == "true"
_DEFAULT_WORKER_LEADER = os.environ["LLM_GRADING_WORKER_LEADER"] == "true"


@pytest.fixture(autouse=True)
def _reset_worker_and_e2e_settings():
    from apps.backend.courseeval_backend.core.config import settings
    from apps.backend.courseeval_backend.domains.llm.runtime import set_test_clock
    from apps.backend.courseeval_backend.llm_grading import worker_manager

    worker_manager.stop()
    set_test_clock(None)
    settings.ENABLE_LLM_GRADING_WORKER = _DEFAULT_ENABLE_WORKER
    settings.LLM_GRADING_WORKER_LEADER = _DEFAULT_WORKER_LEADER
    settings.LLM_GRADING_WORKER_POLL_SECONDS = 2
    settings.E2E_DEV_SEED_ENABLED = False
    settings.E2E_DEV_SEED_TOKEN = ""
    if hasattr(settings, "E2E_DEV_REQUIRE_ADMIN_JWT"):
        settings.E2E_DEV_REQUIRE_ADMIN_JWT = False
    yield
    worker_manager.stop()
    set_test_clock(None)
    settings.ENABLE_LLM_GRADING_WORKER = _DEFAULT_ENABLE_WORKER
    settings.LLM_GRADING_WORKER_LEADER = _DEFAULT_WORKER_LEADER
    settings.LLM_GRADING_WORKER_POLL_SECONDS = 2
    settings.E2E_DEV_SEED_ENABLED = False
    settings.E2E_DEV_SEED_TOKEN = ""
    if hasattr(settings, "E2E_DEV_REQUIRE_ADMIN_JWT"):
        settings.E2E_DEV_REQUIRE_ADMIN_JWT = False
