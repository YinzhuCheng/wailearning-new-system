"""S1–S3: Student quota API (My Courses card data) vs submission-driven usage."""

from __future__ import annotations

from unittest import mock

import httpx
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.llm_grading import process_grading_task
from apps.backend.courseeval_backend.db.models import HomeworkGradingTask, LLMStudentTokenOverride, LLMTokenUsageLog
from tests.scenarios.llm_scenario import ensure_admin, json_llm_response, login_api, make_grading_course_with_homework


def test_s0_student_quotas_summary_lists_enrolled_course(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.get("/api/llm-settings/courses/student-quotas", headers=st)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "courses" in body
    ids = {c["subject_id"] for c in body["courses"]}
    assert ctx["subject_id"] in ids
    row = next(c for c in body["courses"] if c["subject_id"] == ctx["subject_id"])
    assert row.get("subject_name")
    assert "usage_date" in row and "quota_timezone" in row


def test_s1_student_quota_loaded_vs_not_enrolled(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r_ok = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st)
    assert r_ok.status_code == 200, r_ok.text
    body = r_ok.json()
    assert body["subject_id"] == ctx["subject_id"]
    assert body["daily_student_token_limit"] is not None
    assert body["student_used_tokens_today"] is not None
    assert body["student_remaining_tokens_today"] is not None
    assert "usage_date" in body and "quota_timezone" in body

    r404 = client.get("/api/llm-settings/courses/student-quota/999999", headers=st)
    assert r404.status_code == 404


def test_s2_submission_increments_usage_counters(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(daily_student_token_limit=500_000)
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    before = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    used_before = int(before["student_used_tokens_today"] or 0)

    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=st,
        json={"content": "answer for usage"},
    )
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(77.0, "graded"))
    ):
        process_grading_task(tid)

    after = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    used_after = int(after["student_used_tokens_today"] or 0)
    assert used_after >= used_before + 10

    db = SessionLocal()
    try:
        log = db.query(LLMTokenUsageLog).filter(LLMTokenUsageLog.task_id == tid).first()
        assert log is not None
        assert int(log.input_tokens or 0) == 10
        assert int(log.total_tokens or 0) == 15
    finally:
        db.close()


def test_s3_second_submit_fails_when_student_daily_cap_hit(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(daily_student_token_limit=50_000)
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r1 = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=st,
        json={"content": "first"},
    )
    assert r1.status_code == 200, r1.text
    db = SessionLocal()
    try:
        tid1 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(60.0, "ok")),
    ):
        process_grading_task(tid1)

    db = SessionLocal()
    try:
        db.query(LLMStudentTokenOverride).filter(LLMStudentTokenOverride.student_id == ctx["student_id"]).delete()
        db.merge(LLMStudentTokenOverride(student_id=ctx["student_id"], daily_tokens=20))
        db.commit()
    finally:
        db.close()

    r2 = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=st,
        json={"content": "second should hit cap"},
    )
    assert r2.status_code == 200, r2.text
    db = SessionLocal()
    try:
        tid2 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    process_grading_task(tid2)
    db = SessionLocal()
    try:
        t2 = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid2).first()
        assert t2.status == "failed"
        assert t2.error_code == "quota_exceeded_student"
    finally:
        db.close()
