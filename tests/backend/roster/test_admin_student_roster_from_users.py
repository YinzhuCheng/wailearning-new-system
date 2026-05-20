"""Admin POST /api/users/student-roster/from-users — sync student accounts into Student roster."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Class, Gender, Student, User, UserRole


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


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _admin_headers(client: TestClient) -> dict[str, str]:
    r = client.post("/api/auth/login", data={"username": "adm", "password": "a"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_sync_from_users_creates_roster_and_matches_login(client: TestClient):
    db = SessionLocal()
    try:
        k = Class(name="同步班", grade=3)
        db.add(k)
        db.flush()
        kid = k.id
        u = User(
            username="stu_roster_1",
            hashed_password=get_password_hash("x"),
            real_name="花名册一号",
            role=UserRole.STUDENT.value,
            class_id=kid,
        )
        db.add(u)
        db.flush()
        uid = u.id
        db.commit()
    finally:
        db.close()

    ah = _admin_headers(client)
    r = client.post("/api/users/student-roster/from-users", headers=ah, json={"user_ids": [uid]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1
    assert body["updated"] == 0
    assert body["skipped"] == 0
    assert body["errors"] == []

    db = SessionLocal()
    try:
        st = (
            db.query(Student)
            .filter(Student.student_no == "stu_roster_1", Student.class_id == kid)
            .first()
        )
        assert st is not None
        assert st.name == "花名册一号"
        u = db.query(User).filter(User.id == uid).one()
        assert u.student_id == st.id
    finally:
        db.close()

    r2 = client.post("/api/users/student-roster/from-users", headers=ah, json={"user_ids": [uid]})
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["created"] == 0
    assert body2["skipped"] == 1


def test_sync_from_users_updates_display_name(client: TestClient):
    db = SessionLocal()
    try:
        k = Class(name="改名班", grade=4)
        db.add(k)
        db.flush()
        kid = k.id
        u = User(
            username="stu_roster_2",
            hashed_password=get_password_hash("x"),
            real_name="新显示名",
            role=UserRole.STUDENT.value,
            class_id=kid,
        )
        db.add(u)
        db.flush()
        uid = u.id
        db.add(
            Student(
                name="旧名",
                student_no="stu_roster_2",
                gender=Gender.MALE,
                class_id=kid,
            )
        )
        db.commit()
    finally:
        db.close()

    ah = _admin_headers(client)
    r = client.post("/api/users/student-roster/from-users", headers=ah, json={"user_ids": [uid]})
    assert r.status_code == 200
    assert r.json()["updated"] == 1

    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.student_no == "stu_roster_2").one()
        assert st.name == "新显示名"
    finally:
        db.close()


def test_sync_from_users_reuses_explicit_student_binding_when_username_differs(client: TestClient):
    db = SessionLocal()
    try:
        k = Class(name="BoundClass", grade=4)
        db.add(k)
        db.flush()
        st = Student(
            name="Old Name",
            student_no="real_student_no",
            gender=Gender.MALE,
            class_id=k.id,
        )
        db.add(st)
        db.flush()
        u = User(
            username="login_account_only",
            hashed_password=get_password_hash("x"),
            real_name="Bound Display",
            role=UserRole.STUDENT.value,
            class_id=k.id,
            student_id=st.id,
        )
        db.add(u)
        db.flush()
        uid = u.id
        sid = st.id
        db.commit()
    finally:
        db.close()

    ah = _admin_headers(client)
    r = client.post("/api/users/student-roster/from-users", headers=ah, json={"user_ids": [uid]})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 1
    assert r.json()["created"] == 0

    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.id == sid).one()
        assert st.name == "Bound Display"
        assert st.student_no == "login_account_only"
        assert db.query(Student).filter(Student.student_no == "real_student_no").count() == 0
    finally:
        db.close()


def test_sync_from_users_conflict_other_class(client: TestClient):
    db = SessionLocal()
    try:
        k1 = Class(name="一班", grade=1)
        k2 = Class(name="二班", grade=1)
        db.add_all([k1, k2])
        db.flush()
        db.add(
            Student(
                name="占用",
                student_no="dup_no",
                gender=Gender.MALE,
                class_id=k1.id,
            )
        )
        u = User(
            username="dup_no",
            hashed_password=get_password_hash("x"),
            real_name="另一班学生",
            role=UserRole.STUDENT.value,
            class_id=k2.id,
        )
        db.add(u)
        db.flush()
        uid = u.id
        db.commit()
    finally:
        db.close()

    ah = _admin_headers(client)
    r = client.post("/api/users/student-roster/from-users", headers=ah, json={"user_ids": [uid]})
    assert r.status_code == 200
    err = r.json()["errors"]
    assert len(err) == 1
    assert "其他班级" in err[0]["reason"]


def test_sync_from_users_rejects_non_student(client: TestClient):
    db = SessionLocal()
    try:
        k = Class(name="教师班", grade=2)
        db.add(k)
        db.flush()
        t = User(
            username="t_only",
            hashed_password=get_password_hash("x"),
            real_name="老师",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        tid = t.id
        db.commit()
    finally:
        db.close()

    ah = _admin_headers(client)
    r = client.post("/api/users/student-roster/from-users", headers=ah, json={"user_ids": [tid]})
    assert r.status_code == 200
    assert r.json()["errors"][0]["reason"] == "仅支持学生角色账号"


def test_sync_from_users_forbidden_for_teacher(client: TestClient):
    db = SessionLocal()
    try:
        k = Class(name="T班", grade=1)
        db.add(k)
        db.flush()
        t = User(
            username="t_act",
            hashed_password=get_password_hash("tp"),
            real_name="任课",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        s = User(
            username="s_act",
            hashed_password=get_password_hash("sp"),
            real_name="学生",
            role=UserRole.STUDENT.value,
            class_id=k.id,
        )
        db.add(s)
        db.flush()
        sid = s.id
        db.commit()
    finally:
        db.close()

    th = {"Authorization": f"Bearer {client.post('/api/auth/login', data={'username': 't_act', 'password': 'tp'}).json()['access_token']}"}
    r = client.post("/api/users/student-roster/from-users", headers=th, json={"user_ids": [sid]})
    assert r.status_code == 403
