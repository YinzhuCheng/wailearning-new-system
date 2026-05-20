"""T1–T3: Teacher course LLM API (legacy fields ignored, timezone, auto-grading interleave)."""

from __future__ import annotations

from unittest import mock

import httpx
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.llm_grading import process_grading_task
from apps.backend.courseeval_backend.db.models import HomeworkGradingTask
from tests.scenarios.llm_scenario import ensure_admin, json_llm_response, login_api, make_grading_course_with_homework


def test_t1_teacher_save_with_legacy_course_token_fields_ignored(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    body = {
        "is_enabled": True,
        "daily_course_token_limit": 999999,
        "estimated_chars_per_token": 4.0,
        "endpoints": [{"preset_id": ctx["preset_id"], "priority": 1}],
    }
    r = client.put(f"/api/llm-settings/courses/{ctx['subject_id']}", headers=th, json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "daily_course_token_limit" not in data
    assert "daily_student_token_limit" not in data
    assert data["is_enabled"] is True


def test_t2_course_quota_timezone_ignored_for_student_quota_calendar(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    client.put(
        "/api/llm-settings/admin/quota-policy",
        headers=ah,
        json={"quota_timezone": "Asia/Shanghai"},
    )
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.put(
        f"/api/llm-settings/courses/{ctx['subject_id']}",
        headers=th,
        json={
            "is_enabled": True,
            "quota_timezone": "UTC",
            "endpoints": [{"preset_id": ctx["preset_id"], "priority": 1}],
        },
    )
    assert r.status_code == 200, r.text
    assert "quota_timezone" not in r.json()

    st = login_api(client, ctx["student_username"], ctx["student_password"])
    sq = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    assert sq["quota_timezone"] == "Asia/Shanghai"


def test_t3_toggle_auto_grading_while_submissions_in_flight(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    st = login_api(client, ctx["student_username"], ctx["student_password"])

    r_sub = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=st,
        json={"content": "in flight"},
    )
    assert r_sub.status_code == 200, r_sub.text
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    client.put(
        f"/api/homeworks/{ctx['homework_id']}",
        headers=th,
        json={"auto_grading_enabled": False},
    )

    process_grading_task(tid)
    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).first()
        assert task.status == "failed"
        assert task.error_code == "auto_grading_disabled"
        assert "quota_exceeded_course" not in (task.error_code or "")
    finally:
        db.close()

    r2 = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=st,
        json={"content": "after off"},
    )
    assert r2.status_code == 200, r2.text
    db = SessionLocal()
    try:
        assert db.query(HomeworkGradingTask).filter(HomeworkGradingTask.homework_id == ctx["homework_id"]).count() == 1
    finally:
        db.close()

    client.put(
        f"/api/homeworks/{ctx['homework_id']}",
        headers=th,
        json={"auto_grading_enabled": True},
    )
    r3 = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=st,
        json={"content": "back on"},
    )
    assert r3.status_code == 200, r3.text
    db = SessionLocal()
    try:
        tid2 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()
    with mock.patch.object(
        httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(70.0, "ok"))
    ):
        process_grading_task(tid2)
    db = SessionLocal()
    try:
        t2 = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid2).first()
        assert t2.status == "success"
    finally:
        db.close()
