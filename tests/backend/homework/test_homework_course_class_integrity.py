"""Homework row integrity: subject.class_id must align with homework.class_id for access checks."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Class, Homework, Student, Subject, User, UserRole


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


def test_homework_mismatched_subject_class_returns_403(client: TestClient):
    """P1 audit: corrupt homework.class_id vs subject.class_id must not yield misleading 404 from course access."""
    uid = uuid.uuid4().hex[:10]
    db = SessionLocal()
    try:
        c_a = Class(name=f"int_a_{uid}", grade=2026)
        c_b = Class(name=f"int_b_{uid}", grade=2026)
        db.add_all([c_a, c_b])
        db.flush()
        teacher = User(
            username=f"h_int_t_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="T",
            role=UserRole.TEACHER.value,
        )
        admin = User(
            username=f"h_int_ad_{uid}",
            hashed_password=get_password_hash("ap"),
            real_name="A",
            role=UserRole.ADMIN.value,
        )
        db.add_all([teacher, admin])
        db.flush()
        course_b = Subject(name=f"course_b_{uid}", teacher_id=teacher.id, class_id=c_b.id)
        db.add(course_b)
        db.flush()
        hw = Homework(
            title="bad alignment",
            content="x",
            class_id=c_a.id,
            subject_id=course_b.id,
            max_score=100,
            auto_grading_enabled=False,
            created_by=teacher.id,
        )
        db.add(hw)
        db.commit()
        hw_id = hw.id
        login = client.post("/api/auth/login", data={"username": admin.username, "password": "ap"})
        assert login.status_code == 200
        token = login.json()["access_token"]
    finally:
        db.close()

    r = client.get(f"/api/homeworks/{hw_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    detail = (r.json().get("detail") or "").lower()
    assert "integrity" in detail or "course class" in detail


def test_student_blocked_when_homework_subject_class_mismatched(client: TestClient):
    uid = uuid.uuid4().hex[:10]
    db = SessionLocal()
    try:
        c_a = Class(name=f"stu_a_{uid}", grade=2026)
        c_b = Class(name=f"stu_b_{uid}", grade=2026)
        db.add_all([c_a, c_b])
        db.flush()
        teacher = User(
            username=f"h_st_t_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="T",
            role=UserRole.TEACHER.value,
        )
        stu_user = User(
            username=f"h_st_s_{uid}",
            hashed_password=get_password_hash("sp"),
            real_name="S",
            role=UserRole.STUDENT.value,
            class_id=c_a.id,
        )
        db.add_all([teacher, stu_user])
        db.flush()
        st_row = Student(name="S", student_no=stu_user.username, class_id=c_a.id)
        db.add(st_row)
        db.flush()
        course_b = Subject(name=f"course_sb_{uid}", teacher_id=teacher.id, class_id=c_b.id)
        db.add(course_b)
        db.flush()
        hw = Homework(
            title="misaligned student path",
            content="x",
            class_id=c_a.id,
            subject_id=course_b.id,
            max_score=100,
            auto_grading_enabled=False,
            created_by=teacher.id,
        )
        db.add(hw)
        db.commit()
        hw_id = hw.id
        login = client.post("/api/auth/login", data={"username": stu_user.username, "password": "sp"})
        assert login.status_code == 200
        token = login.json()["access_token"]
    finally:
        db.close()

    r = client.get(f"/api/homeworks/{hw_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
