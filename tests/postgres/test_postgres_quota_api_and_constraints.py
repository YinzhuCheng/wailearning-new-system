"""
Fifteen PostgreSQL-oriented API and constraint checks for LLM global quota, course config,
and enrollment invariants.

These tests intentionally exercise paths that are easy to break when schema or policy
semantics drift (global-only calendar, course attribution, FK uniqueness). They require a
PostgreSQL engine (``TEST_DATABASE_URL``); on SQLite the module is skipped at collection time.

See ``docs/testing/TEST_EXECUTION_PITFALLS.md`` (Pitfall 42: trailing commas in ``IN (...)``)
and the long-form PostgreSQL cloud-agent notes in ``docs/testing/DEVELOPMENT_AND_TESTING.md``.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal, engine
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    Gender,
    Homework,
    LLMEndpointPreset,
    LLMStudentTokenOverride,
    Student,
    Subject,
    User,
    UserRole,
)
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="PostgreSQL-only hazard suite; set TEST_DATABASE_URL",
)


def test_pg_hz_01_duplicate_course_llm_endpoint_preset_raises_integrity_error() -> None:
    uid = uuid.uuid4().hex[:10]
    db = SessionLocal()
    try:
        k = Class(name=f"hz_dup_{uid}", grade=2026)
        db.add(k)
        db.flush()
        t = User(
            username=f"hz_t_{uid}",
            hashed_password=get_password_hash("p"),
            real_name="T",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        sub = Subject(name=f"hz_sub_{uid}", teacher_id=t.id, class_id=k.id, course_type="required", status="active")
        db.add(sub)
        db.flush()
        p = LLMEndpointPreset(
            name=f"hz_pr_{uid}",
            base_url="https://hz.test/v1/",
            api_key="k",
            model_name="m",
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        db.add(p)
        db.flush()
        cfg = CourseLLMConfig(subject_id=sub.id, is_enabled=True)
        db.add(cfg)
        db.flush()
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, preset_id=p.id, priority=1))
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, preset_id=p.id, priority=2))
        with pytest.raises(IntegrityError):
            try:
                db.commit()
            finally:
                db.rollback()
    finally:
        db.close()


def test_pg_hz_02_information_schema_llm_global_quota_policy_has_expected_columns() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'llm_global_quota_policies'
                  AND column_name IN (
                      'default_daily_student_tokens',
                      'quota_timezone',
                      'estimated_chars_per_token',
                      'estimated_image_tokens',
                      'max_parallel_grading_tasks'
                  )
                ORDER BY column_name
                """
            )
        ).fetchall()
        assert [r[0] for r in rows] == [
            "default_daily_student_tokens",
            "estimated_chars_per_token",
            "estimated_image_tokens",
            "max_parallel_grading_tasks",
            "quota_timezone",
        ]
    finally:
        db.close()


def test_pg_hz_03_course_llm_configs_has_no_legacy_quota_columns() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'course_llm_configs'
                  AND column_name IN (
                      'daily_course_token_limit',
                      'daily_student_token_limit',
                      'quota_timezone',
                      'estimated_chars_per_token',
                      'estimated_image_tokens'
                  )
                """
            )
        ).fetchall()
        assert rows == []
    finally:
        db.close()


def test_pg_hz_04_admin_quota_policy_put_parallel_boundary_422(client: TestClient) -> None:
    ensure_admin()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    r = client.put("/api/llm-settings/admin/quota-policy", headers=ah, json={"max_parallel_grading_tasks": 99})
    assert r.status_code == 422


def test_pg_hz_05_admin_quota_policy_put_invalid_estimation_rejected(client: TestClient) -> None:
    """Non-positive estimation knobs must not persist (Pydantic / API validation)."""
    ensure_admin()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    r = client.put(
        "/api/llm-settings/admin/quota-policy",
        headers=ah,
        json={"estimated_chars_per_token": 0},
    )
    assert r.status_code == 422
    r2 = client.put(
        "/api/llm-settings/admin/quota-policy",
        headers=ah,
        json={"estimated_image_tokens": 0},
    )
    assert r2.status_code == 422


def test_pg_hz_06_student_cannot_read_admin_quota_policy(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.get("/api/llm-settings/admin/quota-policy", headers=st)
    assert r.status_code == 403


def test_pg_hz_07_teacher_put_course_llm_with_legacy_keys_still_200(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    cur = client.get(f"/api/llm-settings/courses/{ctx['subject_id']}", headers=th).json()
    r = client.put(
        f"/api/llm-settings/courses/{ctx['subject_id']}",
        headers=th,
        json={
            "is_enabled": bool(cur.get("is_enabled")),
            "response_language": cur.get("response_language"),
            "max_input_tokens": cur.get("max_input_tokens") or 16000,
            "max_output_tokens": cur.get("max_output_tokens") or 1200,
            "system_prompt": cur.get("system_prompt"),
            "teacher_prompt": cur.get("teacher_prompt"),
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 3.0,
            "estimated_image_tokens": 500,
            "daily_course_token_limit": 1_000_000,
            "endpoints": [{"preset_id": ctx["preset_id"], "priority": 1}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "quota_timezone" not in body
    assert "daily_course_token_limit" not in body


def test_pg_hz_08_global_timezone_change_visible_on_student_quota(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    before = client.get("/api/llm-settings/admin/quota-policy", headers=ah).json()
    alt = "UTC" if (before.get("quota_timezone") or "") != "UTC" else "Asia/Shanghai"
    client.put("/api/llm-settings/admin/quota-policy", headers=ah, json={"quota_timezone": alt})
    row = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    assert row.get("quota_timezone") == alt
    client.put(
        "/api/llm-settings/admin/quota-policy",
        headers=ah,
        json={"quota_timezone": before.get("quota_timezone")},
    )


def test_pg_hz_09_bulk_override_subject_scope_then_clear(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    assert (
        client.post(
            "/api/llm-settings/admin/quota-overrides/bulk",
            headers=ah,
            json={"scope": "subject", "subject_id": ctx["subject_id"], "daily_tokens": 44_444},
        ).status_code
        == 200
    )
    q1 = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    assert q1.get("daily_student_token_limit") == 44_444
    assert client.post(
        "/api/llm-settings/admin/quota-overrides/bulk",
        headers=ah,
        json={"scope": "subject", "subject_id": ctx["subject_id"], "clear_override": True},
    ).status_code == 200
    q2 = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    assert q2.get("uses_personal_override") is False


def test_pg_hz_10_student_quotas_summary_has_global_fields(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.get("/api/llm-settings/courses/student-quotas", headers=st)
    assert r.status_code == 200
    body = r.json()
    assert "courses" in body
    assert body.get("quota_timezone") or body.get("usage_date") is not None


def test_pg_hz_11_teacher_other_cannot_get_foreign_course_llm_config(client: TestClient) -> None:
    """A teacher who does not own the course must not read its LLM config."""
    ensure_admin()
    ctx = make_grading_course_with_homework()
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        intruder = User(
            username=f"hz_other_t_{uid}",
            hashed_password=get_password_hash("p2"),
            real_name="Other",
            role=UserRole.TEACHER.value,
            is_active=True,
        )
        db.add(intruder)
        db.flush()
        klass = db.query(Class).filter(Class.id == ctx["class_id"]).first()
        assert klass is not None
        orphan = Subject(
            name=f"hz_orphan_{uid}",
            teacher_id=intruder.id,
            class_id=klass.id,
            course_type="required",
            status="active",
        )
        db.add(orphan)
        db.commit()
    finally:
        db.close()

    h_intruder = login_api(client, f"hz_other_t_{uid}", "p2")
    r = client.get(f"/api/llm-settings/courses/{ctx['subject_id']}", headers=h_intruder)
    assert r.status_code in (403, 404)


def test_pg_hz_12_duplicate_enrollment_integrity(client: TestClient) -> None:
    """Same guard as pg06 but through raw session after API-seeded scenario."""
    ensure_admin()
    ctx = make_grading_course_with_homework()
    db = SessionLocal()
    try:
        dup = CourseEnrollment(
            subject_id=ctx["subject_id"],
            student_id=ctx["student_id"],
            class_id=ctx["class_id"],
            enrollment_type="required",
            can_remove=False,
        )
        db.add(dup)
        with pytest.raises(IntegrityError):
            try:
                db.commit()
            finally:
                db.rollback()
    finally:
        db.close()


def test_pg_hz_13_homework_requires_existing_subject_fk(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    db = SessionLocal()
    try:
        hw = Homework(
            title="orphan_hw",
            content="x",
            class_id=ctx["class_id"],
            subject_id=999_999_999,
            max_score=10,
            auto_grading_enabled=False,
            created_by=ctx["teacher_id"],
        )
        db.add(hw)
        with pytest.raises(IntegrityError):
            try:
                db.commit()
            finally:
                db.rollback()
    finally:
        db.close()


def test_pg_hz_14_student_override_update_in_place(client: TestClient) -> None:
    """Per-student override is one row per student_id; ORM update must not create a second row."""
    ensure_admin()
    ctx = make_grading_course_with_homework()
    db = SessionLocal()
    try:
        db.query(LLMStudentTokenOverride).filter(LLMStudentTokenOverride.student_id == ctx["student_id"]).delete(
            synchronize_session=False
        )
        db.commit()
        db.add(LLMStudentTokenOverride(student_id=ctx["student_id"], daily_tokens=111))
        db.commit()
        row = db.query(LLMStudentTokenOverride).filter(LLMStudentTokenOverride.student_id == ctx["student_id"]).one()
        row.daily_tokens = 222
        db.commit()
        db.refresh(row)
        assert int(row.daily_tokens) == 222
        assert (
            db.query(LLMStudentTokenOverride).filter(LLMStudentTokenOverride.student_id == ctx["student_id"]).count()
            == 1
        )
    finally:
        db.close()


def test_pg_hz_15_llm_token_usage_log_timezone_column_exists() -> None:
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT is_nullable, data_type FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'llm_token_usage_logs'
                  AND column_name = 'timezone'
                """
            )
        ).fetchone()
        assert row is not None
        assert row[0] == "NO"
    finally:
        db.close()
