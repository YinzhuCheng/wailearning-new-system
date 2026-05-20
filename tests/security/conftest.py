"""Shared DB reset for security regression tests (same contract as behavior/)."""

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
