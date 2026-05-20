"""A1–A5: Admin global LLM quota policy and bulk overrides (HTTP API)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import LLMStudentTokenOverride
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework


def test_a1_quota_policy_get_matches_defaults(client: TestClient) -> None:
    ensure_admin()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    r = client.get("/api/llm-settings/admin/quota-policy", headers=ah)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_daily_student_tokens"] >= 1
    assert body["quota_timezone"]
    assert 1 <= body["max_parallel_grading_tasks"] <= 64


def test_a2_change_default_student_cap_visible_on_student_quota(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    st = login_api(client, ctx["student_username"], ctx["student_password"])

    client.put(
        "/api/llm-settings/admin/quota-policy",
        headers=ah,
        json={"default_daily_student_tokens": 88_888},
    )
    sq = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    assert sq["daily_student_token_limit"] == 88_888
    assert sq["global_default_daily_student_tokens"] == 88_888


def test_a3_global_timezone_change_reflects_in_student_quota_calendar(client: TestClient) -> None:
    """Student quota snapshots follow LLMGlobalQuotaPolicy only (no per-course quota calendar)."""
    ensure_admin()
    ctx = make_grading_course_with_homework()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    st = login_api(client, ctx["student_username"], ctx["student_password"])

    client.put("/api/llm-settings/admin/quota-policy", headers=ah, json={"quota_timezone": "UTC"})
    u1 = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    assert u1["quota_timezone"] == "UTC"

    client.put(
        "/api/llm-settings/admin/quota-policy",
        headers=ah,
        json={"quota_timezone": "Asia/Shanghai"},
    )
    u2 = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    assert u2["quota_timezone"] == "Asia/Shanghai"


def test_a4_parallel_policy_persists(client: TestClient) -> None:
    ensure_admin()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    r = client.put(
        "/api/llm-settings/admin/quota-policy",
        headers=ah,
        json={"max_parallel_grading_tasks": 2},
    )
    assert r.status_code == 200, r.text
    assert r.json()["max_parallel_grading_tasks"] == 2
    r2 = client.get("/api/llm-settings/admin/quota-policy", headers=ah)
    assert r2.json()["max_parallel_grading_tasks"] == 2


def test_a5_bulk_override_then_clear(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    st = login_api(client, ctx["student_username"], ctx["student_password"])

    r_bulk = client.post(
        "/api/llm-settings/admin/quota-overrides/bulk",
        headers=ah,
        json={"scope": "subject", "subject_id": ctx["subject_id"], "daily_tokens": 77_777},
    )
    assert r_bulk.status_code == 200, r_bulk.text
    assert r_bulk.json()["affected_students"] >= 1

    sq = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    assert sq["daily_student_token_limit"] == 77_777
    assert sq["uses_personal_override"] is True

    r_clear = client.post(
        "/api/llm-settings/admin/quota-overrides/bulk",
        headers=ah,
        json={"scope": "subject", "subject_id": ctx["subject_id"], "clear_override": True},
    )
    assert r_clear.status_code == 200, r_clear.text

    db = SessionLocal()
    try:
        assert (
            db.query(LLMStudentTokenOverride).filter(LLMStudentTokenOverride.student_id == ctx["student_id"]).first()
            is None
        )
    finally:
        db.close()

    sq2 = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    assert sq2["uses_personal_override"] is False
