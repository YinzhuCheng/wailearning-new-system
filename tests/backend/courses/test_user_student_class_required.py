"""Admin create/update: student role may be unassigned or class-bound."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Class, Student, User, UserRole
from tests.scenarios.llm_scenario import login_api


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    ensure_admin()
    yield
    SessionLocal().close()


def ensure_admin():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "adm").first():
            db.add(
                User(
                    username="adm",
                    hashed_password=get_password_hash("a"),
                    real_name="A",
                    role=UserRole.ADMIN.value,
                )
            )
            db.commit()
    finally:
        db.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_create_student_without_class_200_for_admin(client: TestClient):
    h = login_api(client, "adm", "a")
    r = client.post(
        "/api/users",
        headers=h,
        json={
            "username": "no_class_stu",
            "password": "p",
            "real_name": "N",
            "role": "student",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["class_id"] is not None
    assert body["student_id"] is not None

    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.id == body["student_id"]).one()
        user = db.query(User).filter(User.username == "no_class_stu").one()
        assert student.student_no == "no_class_stu"
        assert student.class_id is not None
        assert user.student_id == student.id
        assert user.class_id is not None
    finally:
        db.close()


def test_create_student_with_class_200(client: TestClient):
    db = SessionLocal()
    try:
        k = Class(name="K1", grade=2026)
        db.add(k)
        db.commit()
        kid = k.id
    finally:
        db.close()
    h = login_api(client, "adm", "a")
    r = client.post(
        "/api/users",
        headers=h,
        json={
            "username": "has_class_stu",
            "password": "p",
            "real_name": "H",
            "role": "student",
            "class_id": kid,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["class_id"] == kid

    db = SessionLocal()
    try:
        st = (
            db.query(Student)
            .filter(Student.student_no == "has_class_stu", Student.class_id == kid)
            .first()
        )
        assert st is not None
        assert st.name == "H"
    finally:
        db.close()
