"""Effective homework score = max over eligible attempts (on-time or counts toward final score)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import Homework, HomeworkAttempt, HomeworkGradingTask
from apps.backend.courseeval_backend.llm_grading import process_grading_task
from apps.backend.courseeval_backend.main import app
from tests.scenarios.llm_scenario import ensure_admin, json_llm_response, login_api, make_grading_course_with_homework, patch_httpx_post


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


def _submit(client: TestClient, hid: int, headers: dict, content: str) -> int:
    r = client.post(f"/api/homeworks/{hid}/submission", headers=headers, json={"content": content})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_effective_score_is_max_score_among_eligible_attempts(client: TestClient):
    """Earlier high-scoring attempt must dominate when a later attempt scores lower."""
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h, sth = ctx["homework_id"], login_api(client, ctx["student_username"], ctx["student_password"])
    _submit(client, h, sth, "attempt-one")
    db = SessionLocal()
    try:
        tid1 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.asc()).first().id
    finally:
        db.close()
    with patch_httpx_post(lambda self, u, **k: httpx.Response(200, json=json_llm_response(92.0, "first"))):
        process_grading_task(tid1)

    _submit(client, h, sth, "attempt-two")
    db = SessionLocal()
    try:
        tid2 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()
    with patch_httpx_post(lambda self, u, **k: httpx.Response(200, json=json_llm_response(61.0, "second"))):
        process_grading_task(tid2)

    r = client.get(f"/api/homeworks/{h}/submission/me", headers=sth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["review_score"] == 92.0
    assert body.get("effective_score_attempt_seq") == 1
    assert "有效成绩" in (body.get("effective_score_note_zh") or "")


def test_late_attempt_excluded_from_aggregate_when_late_affects_score(client: TestClient):
    """Higher score on a non-counting late attempt must not replace an on-time score."""
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h, sth = ctx["homework_id"], login_api(client, ctx["student_username"], ctx["student_password"])
    due = datetime.now(timezone.utc) + timedelta(days=3)

    db = SessionLocal()
    try:
        hw = db.query(Homework).filter(Homework.id == h).first()
        hw.due_date = due
        hw.allow_late_submission = True
        hw.late_submission_affects_score = True
        db.commit()
    finally:
        db.close()

    _submit(client, h, sth, "on-time-body")
    db = SessionLocal()
    try:
        tid1 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.asc()).first().id
        att1 = db.query(HomeworkAttempt).order_by(HomeworkAttempt.id.asc()).first()
        att1.submitted_at = due - timedelta(hours=2)
        att1.is_late = False
        att1.counts_toward_final_score = True
        db.commit()
    finally:
        db.close()

    with patch_httpx_post(lambda self, u, **k: httpx.Response(200, json=json_llm_response(70.0, "ot"))):
        process_grading_task(tid1)

    _submit(client, h, sth, "late-body")
    db = SessionLocal()
    try:
        tid2 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
        att2 = db.query(HomeworkAttempt).order_by(HomeworkAttempt.id.desc()).first()
        att2.submitted_at = due + timedelta(hours=1)
        att2.is_late = True
        att2.counts_toward_final_score = False
        db.commit()
    finally:
        db.close()

    with patch_httpx_post(lambda self, u, **k: httpx.Response(200, json=json_llm_response(99.0, "late"))):
        process_grading_task(tid2)

    r = client.get(f"/api/homeworks/{h}/submission/me", headers=sth)
    assert r.status_code == 200, r.text
    assert r.json()["review_score"] == 70.0
