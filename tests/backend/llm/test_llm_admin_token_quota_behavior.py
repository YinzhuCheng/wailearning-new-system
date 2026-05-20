"""Behavior tests: admin-managed global LLM per-student daily cap and student quota API sync."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseLLMConfig,
    Gender,
    LLMStudentTokenOverride,
    Student,
    Subject,
    User,
    UserRole,
)
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework
from tests.backend.llm.test_llm_token_quota_behavior import _tiny_png_bytes


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


def _seed_student_course_and_config(client: TestClient):
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        k = Class(name=f"admq_{uid}", grade=2026)
        db.add(k)
        db.flush()
        su = User(
            username=f"stu_admq_{uid}",
            hashed_password=get_password_hash("p1"),
            real_name="S",
            role=UserRole.STUDENT.value,
            class_id=k.id,
        )
        db.add(su)
        db.flush()
        st = Student(name="S", student_no=su.username, gender=Gender.MALE, class_id=k.id)
        db.add(st)
        db.flush()
        t = User(
            username=f"t_admq_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="T",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        course = Subject(name=f"C_{uid}", teacher_id=t.id, class_id=k.id)
        db.add(course)
        db.flush()
        db.add(
            CourseEnrollment(subject_id=course.id, student_id=st.id, class_id=k.id, enrollment_type="required")
        )
        cfg = CourseLLMConfig(subject_id=course.id, is_enabled=False)
        db.add(cfg)
        db.commit()
        return {
            "student_headers": login_api(client, su.username, "p1"),
            "admin_headers": None,
            "subject_id": course.id,
            "class_id": k.id,
            "student_id": st.id,
            "teacher_username": t.username,
            "teacher_password": "tp",
        }
    finally:
        db.close()


def test_student_quota_reflects_default_policy_and_admin_update(client: TestClient):
    ensure_admin()
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    ctx = _seed_student_course_and_config(client)
    ctx["admin_headers"] = admin_h

    r0 = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=ctx["student_headers"])
    assert r0.status_code == 200, r0.text
    b0 = r0.json()
    assert b0["daily_student_token_limit"] == 100_000
    assert b0["uses_personal_override"] is False
    assert b0["global_default_daily_student_tokens"] == 100_000
    assert b0["student_remaining_tokens_today"] == 100_000

    r_put = client.put(
        "/api/llm-settings/admin/quota-policy",
        headers=admin_h,
        json={"default_daily_student_tokens": 50_000, "quota_timezone": "UTC"},
    )
    assert r_put.status_code == 200, r_put.text

    r1 = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=ctx["student_headers"])
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["daily_student_token_limit"] == 50_000
    assert b1["global_default_daily_student_tokens"] == 50_000
    assert b1["student_remaining_tokens_today"] == 50_000


def test_admin_single_student_override_visible_in_quota_api(client: TestClient):
    ensure_admin()
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    ctx = _seed_student_course_and_config(client)

    r_put = client.put(
        f"/api/llm-settings/admin/students/{ctx['student_id']}/quota-override",
        headers=admin_h,
        json={"daily_tokens": 12_345},
    )
    assert r_put.status_code == 200, r_put.text

    r = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=ctx["student_headers"])
    assert r.status_code == 200
    b = r.json()
    assert b["daily_student_token_limit"] == 12_345
    assert b["uses_personal_override"] is True
    assert b["student_remaining_tokens_today"] == 12_345

    r_clear = client.put(
        f"/api/llm-settings/admin/students/{ctx['student_id']}/quota-override",
        headers=admin_h,
        json={"clear_override": True},
    )
    assert r_clear.status_code == 200, r_clear.text

    r2 = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=ctx["student_headers"])
    b2 = r2.json()
    assert b2["uses_personal_override"] is False
    db = SessionLocal()
    try:
        from apps.backend.courseeval_backend.db.models import LLMGlobalQuotaPolicy

        pol = db.query(LLMGlobalQuotaPolicy).filter(LLMGlobalQuotaPolicy.id == 1).one()
        assert b2["daily_student_token_limit"] == int(pol.default_daily_student_tokens)
    finally:
        db.close()


def test_bulk_class_scope_updates_all_students_in_class(client: TestClient):
    ensure_admin()
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        k = Class(name=f"bulk_{uid}", grade=2026)
        db.add(k)
        db.flush()
        for i in range(2):
            u = User(
                username=f"bstu_{uid}_{i}",
                hashed_password=get_password_hash("p"),
                real_name=f"N{i}",
                role=UserRole.STUDENT.value,
                class_id=k.id,
            )
            db.add(u)
            db.flush()
            st = Student(name=f"N{i}", student_no=f"bstu_{uid}_{i}", class_id=k.id)
            db.add(st)
            db.flush()
        db.commit()
        class_id = k.id
        s0 = db.query(Student).filter(Student.student_no == f"bstu_{uid}_0").first()
        s1 = db.query(Student).filter(Student.student_no == f"bstu_{uid}_1").first()
        sid0, sid1 = s0.id, s1.id
    finally:
        db.close()

    r = client.post(
        "/api/llm-settings/admin/quota-overrides/bulk",
        headers=admin_h,
        json={"scope": "class", "class_id": class_id, "daily_tokens": 77_777},
    )
    assert r.status_code == 200, r.text
    assert r.json()["affected_students"] == 2

    db = SessionLocal()
    try:
        assert db.query(LLMStudentTokenOverride).filter(LLMStudentTokenOverride.student_id == sid0).one().daily_tokens == 77_777
        assert db.query(LLMStudentTokenOverride).filter(LLMStudentTokenOverride.student_id == sid1).one().daily_tokens == 77_777
    finally:
        db.close()


def test_teacher_course_config_response_omits_student_limit_field(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(daily_student_token_limit=99)
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    pid = ctx["preset_id"]
    sid = ctx["subject_id"]
    client.post(
        f"/api/llm-settings/presets/{pid}/validate",
        headers=admin_h,
        files={"image": ("t.png", _tiny_png_bytes(), "image/png")},
    )
    client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=teacher_h,
        json={
            "is_enabled": True,
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 4.0,
            "estimated_image_tokens": 850,
            "max_input_tokens": 8000,
            "max_output_tokens": 1000,
            "endpoints": [{"preset_id": pid, "priority": 1}],
        },
    )
    g = client.get(f"/api/llm-settings/courses/{sid}", headers=teacher_h)
    assert g.status_code == 200
    assert g.json().get("daily_student_token_limit") is None


def test_global_quota_policy_includes_max_parallel_grading_tasks(client: TestClient):
    ensure_admin()
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    r = client.get("/api/llm-settings/admin/quota-policy", headers=admin_h)
    assert r.status_code == 200
    assert r.json().get("max_parallel_grading_tasks") == 3
    r2 = client.put(
        "/api/llm-settings/admin/quota-policy",
        headers=admin_h,
        json={"max_parallel_grading_tasks": 5},
    )
    assert r2.status_code == 200
    assert r2.json()["max_parallel_grading_tasks"] == 5


def test_non_admin_cannot_change_global_policy(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.put(
        "/api/llm-settings/admin/quota-policy",
        headers=teacher_h,
        json={"default_daily_student_tokens": 1},
    )
    assert r.status_code == 403
