"""
Edge cases: fresh demo seed + default LLM preset, roster/user churn, new enrollments, student-quotas API.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.domains.seed.demo import seed_demo_course_bundle
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    LLMEndpointPreset,
    Student,
    Subject,
    User,
    UserRole,
)


def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()


@pytest.fixture(autouse=True)
def _reset_each():
    _reset_db()
    yield
    SessionLocal().close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_demo_seed_binds_llm_to_required_course_when_validated_preset_exists():
    """Cold install path: ensure_schema seeds default preset; demo seed must attach it to 数据挖掘."""
    db = SessionLocal()
    try:
        seed_demo_course_bundle(db)
        course = db.query(Subject).filter(Subject.name == "数据挖掘").first()
        assert course is not None
        cfg = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == course.id).first()
        assert cfg is not None
        assert cfg.is_enabled is True
        links = db.query(CourseLLMConfigEndpoint).filter(CourseLLMConfigEndpoint.config_id == cfg.id).all()
        assert len(links) >= 1
        pr = db.query(LLMEndpointPreset).filter(LLMEndpointPreset.id == links[0].preset_id).first()
        assert pr is not None
        # With DEFAULT_LLM_API_KEY unset, bootstrap creates the built-in preset as pending; demo seed
        # still links it so local installs have endpoints for UI (see domains/seed/demo.py).
        assert pr.validation_status in ("validated", "pending")
        if pr.validation_status == "pending":
            assert pr.name == "gpt-5.4"
    finally:
        db.close()


def test_demo_seed_ok_when_no_validated_preset_exists():
    """If admins removed every preset, demo bundle must still complete; course LLM stays unbound."""
    db = SessionLocal()
    try:
        for row in db.query(LLMEndpointPreset).all():
            db.delete(row)
        db.commit()
        seed_demo_course_bundle(db)
        course = db.query(Subject).filter(Subject.name == "数据挖掘").first()
        assert course is not None
        cfg = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == course.id).first()
        if cfg:
            n = db.query(CourseLLMConfigEndpoint).filter(CourseLLMConfigEndpoint.config_id == cfg.id).count()
            assert n == 0
    finally:
        db.close()


def test_student_quotas_reflects_course_rename_and_new_enrolled_user(client: TestClient):
    """Subject rename visible to API; newly added student user + enrollment appears in summary."""
    db = SessionLocal()
    try:
        seed_demo_course_bundle(db)
        course = db.query(Subject).filter(Subject.name == "数据挖掘").first()
        assert course
        klass = db.query(Class).filter(Class.name == "人工智能1班").first()
        assert klass
        teacher = db.query(User).filter(User.username == "teacher").first()
        assert teacher
        uid = uuid.uuid4().hex[:10]
        new_uname = f"edge_stu_{uid}"
        db.add(
            User(
                username=new_uname,
                hashed_password=get_password_hash("111111"),
                real_name="边缘新生",
                role=UserRole.STUDENT.value,
                class_id=klass.id,
                is_active=True,
            )
        )
        db.flush()
        new_st = Student(
            name="边缘新生",
            student_no=new_uname,
            class_id=klass.id,
            teacher_id=teacher.id,
        )
        db.add(new_st)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=course.id,
                student_id=new_st.id,
                class_id=klass.id,
                enrollment_type="required",
            )
        )
        course.name = "数据挖掘（演示改名）"
        db.commit()
        sid = course.id
    finally:
        db.close()

    st1 = client.post("/api/auth/login", data={"username": "stu1", "password": "111111"})
    assert st1.status_code == 200, st1.text
    h1 = {"Authorization": f"Bearer {st1.json()['access_token']}"}

    r1 = client.get("/api/llm-settings/courses/student-quotas", headers=h1)
    assert r1.status_code == 200
    by_id = {row["subject_id"]: row for row in r1.json()["courses"]}
    assert by_id[sid]["subject_name"] == "数据挖掘（演示改名）"

    r_new = client.post("/api/auth/login", data={"username": new_uname, "password": "111111"})
    assert r_new.status_code == 200
    h_new = {"Authorization": f"Bearer {r_new.json()['access_token']}"}
    r2 = client.get("/api/llm-settings/courses/student-quotas", headers=h_new)
    assert r2.status_code == 200
    ids_new = {c["subject_id"] for c in r2.json()["courses"]}
    assert sid in ids_new
    row = next(c for c in r2.json()["courses"] if c["subject_id"] == sid)
    assert row["subject_name"] == "数据挖掘（演示改名）"


def test_roster_display_name_change_visible_after_login(client: TestClient):
    """Roster name change syncs to User.real_name; student-quotas still 200 (profile resolves)."""
    db = SessionLocal()
    try:
        seed_demo_course_bundle(db)
        st = db.query(Student).filter(Student.student_no == "stu2").first()
        assert st
        st.name = "花名册已改名二"
        db.commit()
    finally:
        db.close()

    from apps.backend.courseeval_backend.domains.roster.sync import (
        sync_student_user_from_roster_row,
    )

    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.student_no == "stu2").first()
        sync_student_user_from_roster_row(db, st)
        db.commit()
        u = db.query(User).filter(User.username == "stu2").first()
        assert u and "花名册" in (u.real_name or "")
    finally:
        db.close()

    r = client.post("/api/auth/login", data={"username": "stu2", "password": "111111"})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r2 = client.get("/api/llm-settings/courses/student-quotas", headers=h)
    assert r2.status_code == 200
