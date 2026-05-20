"""Public registration guards when ALLOW_PUBLIC_REGISTRATION is enabled."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    yield


@pytest.fixture
def client(_reset_db) -> TestClient:
    from apps.backend.courseeval_backend.main import app

    return TestClient(app)


def test_public_register_rejects_nonexistent_class_id(client: TestClient, monkeypatch):
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    from apps.backend.courseeval_backend.core.config import settings

    monkeypatch.setattr(settings, "ALLOW_PUBLIC_REGISTRATION", True)

    r = client.post(
        "/api/auth/register",
        json={
            "username": "orphan_reg_user_should_fail",
            "password": "ValidPass9!",
            "real_name": "x",
            "role": "student",
            "class_id": 999_999_991,
        },
    )
    assert r.status_code == 400
    assert "class" in (r.json().get("detail") or "").lower()


def test_public_register_student_immediately_gets_bound_profile_and_quota_summary(client: TestClient, monkeypatch):
    import uuid

    from apps.backend.courseeval_backend.db.database import SessionLocal
    from apps.backend.courseeval_backend.db.models import Class, Student

    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    from apps.backend.courseeval_backend.core.config import settings

    monkeypatch.setattr(settings, "ALLOW_PUBLIC_REGISTRATION", True)

    db = SessionLocal()
    try:
        klass = Class(name=f"公开注册额度班_{uuid.uuid4().hex[:8]}", grade=2026)
        db.add(klass)
        db.flush()
        class_id = klass.id
        db.commit()
    finally:
        db.close()

    username = f"public_quota_student_{uuid.uuid4().hex[:8]}"
    register = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "ValidPass9!",
            "real_name": "公开注册学生",
            "role": "student",
            "class_id": class_id,
        },
    )
    assert register.status_code == 200, register.text

    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.student_no == username, Student.class_id == class_id).first()
        assert st is not None
    finally:
        db.close()

    login = client.post("/api/auth/login", data={"username": username, "password": "ValidPass9!"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    quota = client.get("/api/llm-settings/courses/student-quotas", headers=headers)
    assert quota.status_code == 200, quota.text
    body = quota.json()
    assert body.get("daily_student_token_limit") is not None
    assert "quota_timezone" in body and "usage_date" in body


def test_public_register_rejects_explicit_student_id_binding(client: TestClient, monkeypatch):
    import uuid

    from apps.backend.courseeval_backend.db.database import SessionLocal
    from apps.backend.courseeval_backend.db.models import Class, Gender, Student

    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    from apps.backend.courseeval_backend.core.config import settings

    monkeypatch.setattr(settings, "ALLOW_PUBLIC_REGISTRATION", True)

    db = SessionLocal()
    try:
        klass = Class(name=f"PublicBindGuard_{uuid.uuid4().hex[:8]}", grade=2026)
        db.add(klass)
        db.flush()
        student = Student(name="Existing", student_no=f"existing_{uuid.uuid4().hex[:8]}", gender=Gender.MALE, class_id=klass.id)
        db.add(student)
        db.flush()
        class_id = klass.id
        student_id = student.id
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/auth/register",
        json={
            "username": f"public_bind_attempt_{uuid.uuid4().hex[:8]}",
            "password": "ValidPass9!",
            "real_name": "attacker",
            "role": "student",
            "class_id": class_id,
            "student_id": student_id,
        },
    )

    assert r.status_code == 403
    assert "bind" in (r.json().get("detail") or "").lower()
