"""Shared fixtures for API-level LLM behavior tests under tests/behavior/."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    yield
    SessionLocal().close()


@pytest.fixture
def client() -> TestClient:
    from apps.backend.courseeval_backend.main import app

    return TestClient(app)


@pytest.fixture(scope="session")
def behavior_base_url() -> str:
    """Reserved for future Playwright runs; API tests use TestClient."""
    return "http://127.0.0.1:5174"


@pytest.fixture(scope="session")
def behavior_api_base_url() -> str:
    return "http://127.0.0.1:8001/api"
