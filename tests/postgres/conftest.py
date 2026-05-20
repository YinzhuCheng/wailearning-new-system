"""PostgreSQL-only suite autouse fixtures (schema reset). Skip decision lives on each test module via pytestmark."""

from __future__ import annotations

import pytest

from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates
from apps.backend.courseeval_backend.db.database import SessionLocal, engine
from tests.db_reset import reset_test_database_schema


@pytest.fixture(autouse=True)
def _postgres_reset_schema():
    if engine.dialect.name != "postgresql":
        yield
        return
    reset_test_database_schema()
    ensure_schema_updates()
    yield
    SessionLocal().close()


@pytest.fixture
def client():
    """HTTP client against the live FastAPI app (same process as other API tests)."""
    from fastapi.testclient import TestClient

    from apps.backend.courseeval_backend.main import app

    return TestClient(app)
