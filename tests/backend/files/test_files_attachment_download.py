"""Attachment download by stored name: duplicate URLs and access checks."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.attachments import ATTACHMENTS_DIR
from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Class, Homework, HomeworkSubmission, Student, Subject, User, UserRole


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
    return TestClient(app)


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_download_by_stored_name_succeeds_when_multiple_rows_same_file(client: TestClient):
    """Same on-disk name referenced twice; user with class access gets 200 (not 409)."""
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        klass = Class(name=f"fd_{uid}", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username=f"fd_t_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="T",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        course = Subject(name=f"fd_c_{uid}", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.flush()
        s1 = Student(name="A", student_no=f"fd_a_{uid}", class_id=klass.id)
        s2 = Student(name="B", student_no=f"fd_b_{uid}", class_id=klass.id)
        db.add_all([s1, s2])
        db.flush()
        hw = Homework(
            title="hw",
            content="c",
            class_id=klass.id,
            subject_id=course.id,
            max_score=100,
            auto_grading_enabled=False,
            created_by=teacher.id,
        )
        db.add(hw)
        db.flush()
        shared = "dupfile.bin"
        url = f"/uploads/attachments/{shared}"
        db.add(
            HomeworkSubmission(
                homework_id=hw.id,
                student_id=s1.id,
                subject_id=course.id,
                class_id=klass.id,
                attachment_url=url,
            )
        )
        db.add(
            HomeworkSubmission(
                homework_id=hw.id,
                student_id=s2.id,
                subject_id=course.id,
                class_id=klass.id,
                attachment_url=f"/api/files/download/{shared}",
            )
        )
        db.commit()
        teacher_username = teacher.username
    finally:
        db.close()

    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (ATTACHMENTS_DIR / shared).write_bytes(b"shared-bytes")

    headers = _login(client, teacher_username, "tp")
    r = client.get(f"/api/files/download/{shared}", headers=headers)
    assert r.status_code == 200, r.text
