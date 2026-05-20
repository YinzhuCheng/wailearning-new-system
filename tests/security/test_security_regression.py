"""Twenty security-focused API regression tests (authz boundaries, token handling, IDOR edges).

These are integration-style checks via TestClient against the full app stack.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.scenarios.llm_scenario import (
    ensure_admin,
    login_api,
    make_grading_course_with_homework,
    make_multi_student_scenario,
)


def test_sec01_unauthenticated_users_list_returns_401(client: TestClient):
    r = client.get("/api/users")
    assert r.status_code == 401


def test_sec02_student_list_users_forbidden(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.get("/api/users", headers=st)
    assert r.status_code == 403


def test_sec03_teacher_cannot_create_llm_preset(client: TestClient):
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.post(
        "/api/llm-settings/presets",
        headers={**th, "Content-Type": "application/json"},
        json={
            "name": "sec_preset_should_fail",
            "base_url": "https://x.test/v1/",
            "api_key": "k",
            "model_name": "m",
            "connect_timeout_seconds": 10,
            "read_timeout_seconds": 60,
            "max_retries": 0,
            "initial_backoff_seconds": 1,
            "is_active": True,
        },
    )
    assert r.status_code == 403


def test_sec04_teacher_cannot_update_global_llm_quota_policy(client: TestClient):
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.put(
        "/api/llm-settings/admin/quota-policy",
        headers={**th, "Content-Type": "application/json"},
        json={"default_daily_student_tokens": 999999},
    )
    assert r.status_code == 403


def test_sec05_student_cannot_read_admin_quota_policy(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.get("/api/llm-settings/admin/quota-policy", headers=st)
    assert r.status_code == 403


def test_sec06_student_cannot_generate_parent_code_for_peer(client: TestClient):
    ctx = make_multi_student_scenario(2)
    st_a = ctx["students"][0]
    st_b = ctx["students"][1]
    h_a = login_api(client, st_a["username"], st_a["password"])
    r = client.post(f"/api/parent/students/{st_b['student_id']}/generate-code", headers=h_a)
    assert r.status_code == 403


def test_sec07_unauthenticated_logs_forbidden(client: TestClient):
    r = client.get("/api/logs?page=1&page_size=20")
    assert r.status_code == 401


def test_sec08_student_logs_admin_only(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.get("/api/logs", headers=st)
    assert r.status_code == 403


def test_sec09_student_cannot_list_teacher_homework_submissions_grid(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.get(f"/api/homeworks/{ctx['homework_id']}/submissions?page=1&page_size=20", headers=st)
    assert r.status_code == 403


def test_sec10_cross_teacher_cannot_delete_foreign_homework(client: TestClient):
    ctx_a = make_grading_course_with_homework()
    ctx_b = make_grading_course_with_homework()
    h_b = login_api(client, ctx_b["teacher_username"], ctx_b["teacher_password"])
    r = client.delete(f"/api/homeworks/{ctx_a['homework_id']}", headers=h_b)
    assert r.status_code in (403, 404)


def test_sec11_student_cannot_trigger_batch_regrade(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submissions/batch-regrade",
        headers={**st, "Content-Type": "application/json"},
        json={"only_latest_attempt": True, "submission_ids": []},
    )
    assert r.status_code == 403


def test_sec12_file_upload_requires_auth(client: TestClient):
    r = client.post("/api/files/upload", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 401


def test_sec13_download_nonexistent_stored_name_returns_404_not_stream(client: TestClient):
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.get("/api/files/download/definitely_missing_attachment_xyz.bin", headers=th)
    assert r.status_code == 404


def test_sec14_e2e_seed_disabled_reset_returns_404(client: TestClient):
    r = client.post("/api/e2e/dev/reset-scenario")
    assert r.status_code == 404


def test_sec15_teacher_cannot_read_other_user_profile_by_id(client: TestClient):
    ctx = make_grading_course_with_homework()
    ensure_admin()
    adm = login_api(client, "pytest_admin", "pytest_admin_pass")
    me = client.get("/api/auth/me", headers=adm).json()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.get(f"/api/users/{me['id']}", headers=th)
    assert r.status_code == 403


def test_sec16_student_cannot_read_teacher_user_record(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.get(f"/api/users/{ctx['teacher_id']}", headers=st)
    assert r.status_code == 403


def test_sec17_teacher_cannot_access_student_llm_quota_summary_endpoint(client: TestClient):
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.get("/api/llm-settings/courses/student-quotas", headers=th)
    assert r.status_code == 403


def test_sec18_invalid_bearer_returns_401(client: TestClient):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer totally.invalid.token.here"})
    assert r.status_code == 401


def test_sec19_change_password_requires_authentication(client: TestClient):
    r = client.post(
        "/api/auth/change-password",
        headers={"Content-Type": "application/json"},
        json={"current_password": "x", "new_password": "NewPass123!"},
    )
    assert r.status_code == 401


def test_sec20_notification_subject_id_rejects_non_integer(client: TestClient):
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.get("/api/notifications?subject_id=not-an-int", headers=th)
    assert r.status_code == 422


def test_sec21_teacher_cannot_reset_user_password(client: TestClient):
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.post(f"/api/users/{ctx['student_user_id']}/reset-password", headers=th, json={})
    assert r.status_code == 403


def test_sec22_student_cannot_reset_user_password(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.post(f"/api/users/{ctx['teacher_id']}/reset-password", headers=st, json={"new_password": "x"})
    assert r.status_code == 403
