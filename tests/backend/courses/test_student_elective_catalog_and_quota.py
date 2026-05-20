"""Student elective catalog, self-enroll/drop, and read-only LLM quota API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseLLMConfig,
    Gender,
    LLMStudentTokenOverride,
    Student,
    Subject,
    SubjectClassLink,
    User,
    UserRole,
)


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


def _seed_student_and_elective(client: TestClient):
    db = SessionLocal()
    try:
        k = Class(name="高一甲", grade=1)
        db.add(k)
        db.flush()
        kid = k.id
        stu_user = User(
            username="stu_e1",
            hashed_password=get_password_hash("p"),
            real_name="学生一",
            role=UserRole.STUDENT.value,
            class_id=kid,
        )
        db.add(stu_user)
        db.flush()
        roster = Student(
            name="学生一",
            student_no="stu_e1",
            gender=Gender.MALE,
            class_id=kid,
        )
        db.add(roster)
        db.flush()
        other_class = Class(name="高一乙", grade=1)
        db.add(other_class)
        db.flush()
        el_same = Subject(
            name="机器人选修",
            class_id=kid,
            course_type="elective",
            status="active",
        )
        el_other = Subject(
            name="外班选修",
            class_id=other_class.id,
            course_type="elective",
            status="active",
        )
        req = Subject(
            name="语文必修",
            class_id=kid,
            course_type="required",
            status="active",
        )
        db.add_all([el_same, el_other, req])
        db.flush()
        db.add(
            SubjectClassLink(
                subject_id=req.id,
                class_id=kid,
                enrollment_mode="all_in_class",
            )
        )
        eid, oid, rid = el_same.id, el_other.id, req.id
        db.commit()
    finally:
        db.close()
    return _login(client, "stu_e1", "p"), kid, eid, oid, rid


def test_elective_catalog_lists_active_electives_schoolwide(client: TestClient):
    sh, kid, eid, oid, rid = _seed_student_and_elective(client)
    r = client.get("/api/subjects/elective-catalog", headers=sh)
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()}
    assert eid in ids
    assert oid in ids
    assert rid not in ids


@pytest.mark.parametrize(
    ("target_subject_key", "case_label"),
    [
        ("rid", "required_course"),
    ],
)
def test_student_cannot_self_enroll_forbidden_course_types(
    client: TestClient, target_subject_key: str, case_label: str
):
    sh, kid, eid, oid, rid = _seed_student_and_elective(client)
    subject_ids = {"eid": eid, "oid": oid, "rid": rid}
    r = client.post(f"/api/subjects/{subject_ids[target_subject_key]}/student-self-enroll", headers=sh)
    assert r.status_code == 400, case_label


def test_student_self_enroll_elective_other_class_offering_succeeds(client: TestClient):
    """「外班选修」仅表示种子数据里的行政班字段遗留展示；学生仍可全校自主选课。"""
    sh, kid, eid, oid, rid = _seed_student_and_elective(client)
    r = client.post(f"/api/subjects/{oid}/student-self-enroll", headers=sh)
    assert r.status_code == 200, r.text
    assert r.json().get("created") is True


def test_student_self_enroll_then_list_my_courses(client: TestClient):
    sh, kid, eid, oid, rid = _seed_student_and_elective(client)
    r = client.post(f"/api/subjects/{eid}/student-self-enroll", headers=sh)
    assert r.status_code == 200, r.json() == {"subject_id": eid, "created": True, "already_enrolled": False}

    r2 = client.post(f"/api/subjects/{eid}/student-self-enroll", headers=sh)
    assert r2.status_code == 200
    assert r2.json()["already_enrolled"] is True

    mine = client.get("/api/subjects", headers=sh)
    assert mine.status_code == 200
    mine_ids = {c["id"] for c in mine.json()}
    assert eid in mine_ids


def test_student_self_drop_elective(client: TestClient):
    sh, kid, eid, oid, rid = _seed_student_and_elective(client)
    assert client.post(f"/api/subjects/{eid}/student-self-enroll", headers=sh).status_code == 200
    r = client.post(f"/api/subjects/{eid}/student-self-drop", headers=sh)
    assert r.status_code == 200
    assert r.json() == {"subject_id": eid, "removed": True}

    mine = client.get("/api/subjects", headers=sh)
    mine_ids = {c["id"] for c in mine.json()}
    assert eid not in mine_ids


def test_student_quota_endpoint(client: TestClient):
    sh, kid, eid, oid, rid = _seed_student_and_elective(client)
    assert client.post(f"/api/subjects/{eid}/student-self-enroll", headers=sh).status_code == 200

    db = SessionLocal()
    try:
        stu_row = db.query(Student).filter(Student.student_no == "stu_e1").first()
        assert stu_row is not None
        cfg = CourseLLMConfig(
            subject_id=eid,
            is_enabled=True,
        )
        db.add(cfg)
        db.add(LLMStudentTokenOverride(student_id=stu_row.id, daily_tokens=1000))
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/llm-settings/courses/student-quota/{eid}", headers=sh)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subject_id"] == eid
    assert body["daily_student_token_limit"] == 1000
    assert body["student_remaining_tokens_today"] == 1000


def test_student_quota_forbidden_for_teacher(client: TestClient):
    sh, kid, eid, oid, rid = _seed_student_and_elective(client)
    db = SessionLocal()
    try:
        t = User(
            username="t_quota",
            hashed_password=get_password_hash("tp"),
            real_name="老师",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        course = Subject(name="老师课", teacher_id=t.id, class_id=kid, course_type="required", status="active")
        db.add(course)
        db.flush()
        tid = t.id
        cid = course.id
        db.commit()
    finally:
        db.close()
    th = _login(client, "t_quota", "tp")
    r = client.get(f"/api/llm-settings/courses/student-quota/{cid}", headers=th)
    assert r.status_code == 403


def test_elective_catalog_forbidden_for_teacher(client: TestClient):
    _seed_student_and_elective(client)
    db = SessionLocal()
    try:
        t = User(
            username="t_cat",
            hashed_password=get_password_hash("tp"),
            real_name="老师2",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.commit()
    finally:
        db.close()
    th = _login(client, "t_cat", "tp")
    r = client.get("/api/subjects/elective-catalog", headers=th)
    assert r.status_code == 403


def test_student_course_catalog_lists_required_and_elective_with_hints(client: TestClient):
    sh, kid, eid, oid, rid = _seed_student_and_elective(client)
    r = client.get("/api/subjects/course-catalog", headers=sh)
    assert r.status_code == 200, r.text
    rows = r.json()
    by_id = {row["id"]: row for row in rows}
    assert rid in by_id and eid in by_id and oid in by_id
    assert by_id[rid]["course_type"] == "required"
    assert by_id[rid]["is_enrolled"] is True
    hint_req = by_id[rid].get("enrollment_hint") or ""
    assert "花名册" in hint_req or "教师" in hint_req
    assert by_id[eid]["course_type"] == "elective"
    assert by_id[eid]["can_self_enroll_elective"] is True
    assert by_id[oid]["course_type"] == "elective"
    assert by_id[oid]["can_self_enroll_elective"] is True
