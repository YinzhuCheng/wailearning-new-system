"""E2E dev seed endpoint (disabled by default)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.core.config import settings
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import User, UserRole


@pytest.fixture(autouse=True)
def _reset_e2e_settings():
    yield
    settings.E2E_DEV_SEED_ENABLED = False
    settings.E2E_DEV_SEED_TOKEN = ""


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "adm").first():
            db.add(
                User(
                    username="adm",
                    hashed_password=get_password_hash("a"),
                    real_name="Admin",
                    role=UserRole.ADMIN.value,
                )
            )
            db.commit()
    finally:
        db.close()
    yield
    SessionLocal().close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize(
    ("enabled", "configured_token", "request_token", "expected_status"),
    [
        (False, "", "any", 404),
        (True, "secret-xyz", "wrong", 403),
    ],
)
def test_e2e_seed_rejects_disabled_or_wrong_token(
    client: TestClient, enabled: bool, configured_token: str, request_token: str, expected_status: int
):
    settings.E2E_DEV_SEED_ENABLED = enabled
    settings.E2E_DEV_SEED_TOKEN = configured_token
    r = client.post("/api/e2e/dev/reset-scenario", headers={"X-E2E-Seed-Token": request_token})
    assert r.status_code == expected_status


def test_e2e_seed_ok_when_enabled(client: TestClient):
    settings.E2E_DEV_SEED_ENABLED = True
    settings.E2E_DEV_SEED_TOKEN = "tok-e2e-1"
    r = client.post("/api/e2e/dev/reset-scenario", headers={"X-E2E-Seed-Token": "tok-e2e-1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "suffix" in body
    assert "course_required_id" in body


def test_e2e_seed_builds_material_reader_showcase_shape(client: TestClient):
    settings.E2E_DEV_SEED_ENABLED = True
    settings.E2E_DEV_SEED_TOKEN = "tok-e2e-2"
    r = client.post("/api/e2e/dev/reset-scenario", headers={"X-E2E-Seed-Token": "tok-e2e-2"})
    assert r.status_code == 200, r.text
    body = r.json()

    db = SessionLocal()
    try:
        chapter_rows = db.execute(
            text(
                """
                SELECT title, is_uncategorized
                FROM course_material_chapters
                WHERE subject_id = :subject_id
                ORDER BY id
                """
            ),
            {"subject_id": body["course_required_id"]},
        ).mappings().all()
        assert any(row["is_uncategorized"] for row in chapter_rows)
        assert sum(1 for row in chapter_rows if not row["is_uncategorized"]) >= 2

        homework_link_rows = db.execute(
            text(
                """
                SELECT c.is_uncategorized AS is_uncategorized, l.homework_id
                FROM course_material_homework_links AS l
                JOIN course_material_chapters AS c ON c.id = l.chapter_id
                WHERE c.subject_id = :subject_id
                ORDER BY l.id
                """
            ),
            {"subject_id": body["course_required_id"]},
        ).mappings().all()
        assert any(not row["is_uncategorized"] for row in homework_link_rows)
        assert any(row["is_uncategorized"] for row in homework_link_rows)

        material_rows = db.execute(
            text(
                """
                SELECT c.is_uncategorized AS is_uncategorized, COUNT(*) AS material_count
                FROM course_material_sections AS s
                JOIN course_material_chapters AS c ON c.id = s.chapter_id
                WHERE c.subject_id = :subject_id
                GROUP BY c.id, c.is_uncategorized
                """
            ),
            {"subject_id": body["course_required_id"]},
        ).mappings().all()
        assert any((not row["is_uncategorized"]) and int(row["material_count"]) >= 2 for row in material_rows)
        assert any(row["is_uncategorized"] for row in material_rows)
    finally:
        db.close()
