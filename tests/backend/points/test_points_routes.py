"""Regressions: /api/points/my uses student_no match, not wrong teacher_id."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    Student,
    StudentPoint,
    Subject,
    User,
    UserRole,
)
from tests.scenarios.llm_scenario import login_api


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


def test_get_my_points_matches_by_student_no_not_teacher_id(client: TestClient):
    db = SessionLocal()
    try:
        k = Class(name="pc", grade=2026)
        db.add(k)
        db.flush()
        t = User(
            username="some_teacher",
            hashed_password=get_password_hash("t"),
            real_name="T",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        su = User(
            username="stu2026",
            hashed_password=get_password_hash("s"),
            real_name="Wrong Name",
            role=UserRole.STUDENT.value,
            class_id=k.id,
        )
        db.add(su)
        db.flush()
        st = Student(name="Student A", student_no="stu2026", class_id=k.id, teacher_id=t.id)
        db.add(st)
        db.flush()
        course = Subject(name="C", teacher_id=t.id, class_id=k.id)
        db.add(course)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=course.id,
                student_id=st.id,
                class_id=k.id,
                enrollment_type="required",
            )
        )
        db.add(StudentPoint(student_id=st.id, total_points=5, available_points=5, total_earned=5, total_spent=0))
        db.commit()
        st_id = st.id
    finally:
        db.close()
    h = login_api(client, "stu2026", "s")
    r = client.get("/api/points/my", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["total_points"] == 5
    assert r.json()["student_id"] == st_id


def test_get_my_points_non_student_400(client: TestClient):
    db = SessionLocal()
    try:
        t = User(
            username="onlyt",
            hashed_password=get_password_hash("x"),
            real_name="T2",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.commit()
    finally:
        db.close()
    h = login_api(client, "onlyt", "x")
    r = client.get("/api/points/my", headers=h)
    assert r.status_code == 400
