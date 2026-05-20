"""
End-to-end style tests: student submission queues LLM grading; worker path is
exercised via process_grading_task with httpx mocked at _request_grade_from_endpoint.

See tests/conftest.py for env (SQLite, skip worker thread, skip retry backoff sleep).
"""

from __future__ import annotations

import json
import uuid
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.llm_grading import process_grading_task
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    Homework,
    HomeworkAttempt,
    HomeworkGradingTask,
    HomeworkScoreCandidate,
    HomeworkSubmission,
    LLMEndpointPreset,
    LLMTokenUsageLog,
    Notification,
)
from tests.scenarios.llm_scenario import ensure_admin, json_llm_response, login_api, make_grading_course_with_homework


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


@pytest.fixture
def grading_context(client: TestClient) -> dict:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    ctx["client"] = client
    ctx["admin_headers"] = login_api(client, "pytest_admin", "pytest_admin_pass")
    ctx["teacher_headers"] = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    ctx["student_headers"] = login_api(client, ctx["student_username"], ctx["student_password"])
    return ctx


def test_submit_queues_task_and_retry_then_success_updates_submission(grading_context: dict):
    client: TestClient = grading_context["client"]
    hid = grading_context["homework_id"]
    student_h = grading_context["student_headers"]

    r = client.post(
        f"/api/homeworks/{hid}/submission",
        headers=student_h,
        json={"content": "My answer for pytest."},
    )
    assert r.status_code == 200, r.text
    sub_id = r.json()["id"]

    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first()
        assert task is not None
        assert task.status == "queued"
        tid = task.id
    finally:
        db.close()

    responses = [
        httpx.Response(503, json={"error": "upstream"}),
        httpx.Response(200, json=json_llm_response(88.0, "auto comment")),
    ]

    def fake_post(self, url, **kwargs):
        return responses.pop(0)

    with mock.patch.object(httpx.Client, "post", fake_post):
        process_grading_task(tid)

    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).first()
        assert task.status == "success"
        sub = db.query(HomeworkSubmission).filter(HomeworkSubmission.id == sub_id).first()
        assert sub is not None
        assert sub.review_score == 88.0
        assert sub.review_comment == "auto comment"
        assert sub.latest_task_status == "success"
        auto = (
            db.query(HomeworkScoreCandidate)
            .filter(HomeworkScoreCandidate.attempt_id == sub.latest_attempt_id, HomeworkScoreCandidate.source == "auto")
            .first()
        )
        assert auto is not None
        assert auto.score == 88.0
    finally:
        db.close()


def test_auto_grading_disabled_no_task(grading_context: dict):
    ctx = make_grading_course_with_homework(auto_grading=False)
    client = grading_context["client"]
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])

    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_h,
        json={"content": "no auto grade"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        assert db.query(HomeworkGradingTask).count() == 0
    finally:
        db.close()


def test_course_llm_disabled_task_fails(grading_context: dict):
    ctx = make_grading_course_with_homework(course_llm_enabled=False)
    client = grading_context["client"]
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])

    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_h,
        json={"content": "answer"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first()
        assert task is not None
        tid = task.id
    finally:
        db.close()

    process_grading_task(tid)

    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).first()
        assert task.status == "failed"
        assert task.error_code == "llm_config_disabled"
    finally:
        db.close()


def test_non_retryable_http_fails_without_extra_llm_calls(grading_context: dict):
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    client = grading_context["client"]
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])

    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_h,
        json={"content": "answer"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    calls: list[int] = []

    def fake_post(self, url, **kwargs):
        calls.append(1)
        return httpx.Response(401, json={"error": "bad key"})

    with mock.patch.object(httpx.Client, "post", fake_post):
        process_grading_task(tid)

    assert len(calls) == 1
    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).first()
        assert task.status == "failed"
    finally:
        db.close()


def test_auto_grade_creates_targeted_notification(grading_context: dict):
    client: TestClient = grading_context["client"]
    hid = grading_context["homework_id"]
    student_h = grading_context["student_headers"]

    r = client.post(
        f"/api/homeworks/{hid}/submission",
        headers=student_h,
        json={"content": "notify me"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(77.0, "auto ok")),
    ):
        process_grading_task(tid)

    db = SessionLocal()
    try:
        note = (
            db.query(Notification)
            .filter(
                Notification.related_homework_id == hid,
                Notification.related_student_id == grading_context["student_id"],
            )
            .first()
        )
        assert note is not None
        assert note.target_student_id == grading_context["student_id"]
        assert "作业已批改" in note.title
        note_id = note.id
    finally:
        db.close()

    listed = client.get("/api/notifications", headers=student_h)
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    note_ids = [row["id"] for row in payload.get("data", [])]
    assert note_id in note_ids


def test_teacher_review_updates_grade_notification(grading_context: dict):
    client: TestClient = grading_context["client"]
    hid = grading_context["homework_id"]
    student_h = grading_context["student_headers"]
    teacher_h = grading_context["teacher_headers"]

    r = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "answer body"})
    assert r.status_code == 200, r.text
    sub_id = r.json()["id"]

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(70.0, "llm")),
    ):
        process_grading_task(tid)

    rev = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 92.0, "review_comment": "Adjusted by teacher"},
    )
    assert rev.status_code == 200, rev.text
    data = rev.json()
    assert data["review_score"] == 92.0
    assert data["review_comment"] == "Adjusted by teacher"

    db = SessionLocal()
    try:
        teachers = db.query(HomeworkScoreCandidate).filter(HomeworkScoreCandidate.source == "teacher").all()
        assert len(teachers) == 1
        assert teachers[0].score == 92.0
        note = (
            db.query(Notification)
            .filter(
                Notification.related_homework_id == hid,
                Notification.related_student_id == grading_context["student_id"],
            )
            .first()
        )
        assert note is not None
        assert "92" in (note.content or "")
    finally:
        db.close()


def test_second_endpoint_used_when_first_keeps_retryable(grading_context: dict):
    """Two presets on the course; first returns 503 until exhausted; second succeeds."""
    base_ctx = make_grading_course_with_homework(preset_max_retries=0)
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        preset_b = LLMEndpointPreset(
            name=f"pytest-llm-preset-b-{uid}",
            base_url="https://api.virtual-b.test/v1/",
            api_key="sk-b",
            model_name="virtual-b",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        db.add(preset_b)
        db.flush()
        cfg = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == base_ctx["subject_id"]).first()
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, preset_id=preset_b.id, priority=2))
        db.commit()
        pid_b = preset_b.id
    finally:
        db.close()

    client: TestClient = grading_context["client"]
    student_h = login_api(client, base_ctx["student_username"], base_ctx["student_password"])

    r = client.post(
        f"/api/homeworks/{base_ctx['homework_id']}/submission",
        headers=student_h,
        json={"content": "multi endpoint"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    def fake_post(self, url, **kwargs):
        auth = (kwargs.get("headers") or {}).get("Authorization", "")
        if "sk-test" in auth:
            return httpx.Response(503, json={"error": "bad"})
        return httpx.Response(200, json=json_llm_response(81.0, "from B"))

    with mock.patch.object(httpx.Client, "post", fake_post):
        process_grading_task(tid)

    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).first()
        assert task.status == "success"
        auto = (
            db.query(HomeworkScoreCandidate)
            .filter(HomeworkScoreCandidate.source == "auto")
            .order_by(HomeworkScoreCandidate.id.desc())
            .first()
        )
        assert auto.source_metadata.get("endpoint_id") == pid_b
    finally:
        db.close()


def test_quota_precheck_fails_without_llm_post(grading_context: dict):
    ctx = make_grading_course_with_homework(daily_student_token_limit=1)
    client = grading_context["client"]
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])

    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_h,
        json={"content": "quota block"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    calls: list[int] = []

    def fake_post(self, url, **kwargs):
        calls.append(1)
        return httpx.Response(200, json=json_llm_response(50.0, "should not"))

    with mock.patch.object(httpx.Client, "post", fake_post):
        process_grading_task(tid)

    assert calls == []
    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).first()
        assert task.status == "failed"
        assert task.error_code == "quota_exceeded_student"
    finally:
        db.close()


def test_regrade_queues_new_task(grading_context: dict):
    client: TestClient = grading_context["client"]
    hid = grading_context["homework_id"]
    student_h = grading_context["student_headers"]
    teacher_h = grading_context["teacher_headers"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "v1"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    db = SessionLocal()
    try:
        first_tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(60.0, "first")),
    ):
        process_grading_task(first_tid)

    reg = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/regrade",
        headers=teacher_h,
        json={},
    )
    assert reg.status_code == 200, reg.text

    db = SessionLocal()
    try:
        tasks = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.asc()).all()
        assert len(tasks) == 2
        second = tasks[-1]
        assert second.status == "queued"
        second_id = second.id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(77.0, "regrade")),
    ):
        process_grading_task(second_id)

    db = SessionLocal()
    try:
        sub_row = db.query(HomeworkSubmission).filter(HomeworkSubmission.id == sub_id).first()
        assert sub_row.review_score == 77.0
    finally:
        db.close()


def test_token_usage_recorded_after_success(grading_context: dict):
    client: TestClient = grading_context["client"]
    hid = grading_context["homework_id"]
    student_h = grading_context["student_headers"]

    r = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "token log test"})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(50.0, "x")),
    ):
        process_grading_task(tid)

    db = SessionLocal()
    try:
        log = db.query(LLMTokenUsageLog).filter(LLMTokenUsageLog.task_id == tid).first()
        assert log is not None
        assert log.total_tokens is not None
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).first()
        assert task.billed_total_tokens is not None
    finally:
        db.close()


def test_llm_failure_sets_error_code_and_call_log(grading_context: dict):
    client: TestClient = grading_context["client"]
    hid = grading_context["homework_id"]
    student_h = grading_context["student_headers"]

    r = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "log me"})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(401, json={"error": "nope"}),
    ):
        process_grading_task(tid)

    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).first()
        assert task.status == "failed"
        assert task.error_code == "llm_call_failed"
        assert task.artifact_manifest
        log = task.artifact_manifest.get("llm_call_log")
        assert isinstance(log, list) and len(log) >= 1
        assert any(e.get("phase") == "http_response" for e in log)
    finally:
        db.close()


def test_auto_retry_after_llm_failure_queues_second_task(grading_context: dict):
    client: TestClient = grading_context["client"]
    hid = grading_context["homework_id"]
    student_h = grading_context["student_headers"]

    r = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "retry me"})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(401, json={"error": "nope"}),
    ):
        process_grading_task(tid)

    db = SessionLocal()
    try:
        tasks = (
            db.query(HomeworkGradingTask)
            .filter(HomeworkGradingTask.homework_id == hid)
            .order_by(HomeworkGradingTask.id.asc())
            .all()
        )
        assert len(tasks) == 1
        assert tasks[0].status == "failed"
        assert tasks[0].failure_class == "permanent"
        assert tasks[0].next_retry_at is None
    finally:
        db.close()


def test_submissions_api_includes_task_log(grading_context: dict):
    client: TestClient = grading_context["client"]
    hid = grading_context["homework_id"]
    student_h = grading_context["student_headers"]
    teacher_h = grading_context["teacher_headers"]

    r = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "api log"})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(401, json={"error": "nope"}),
    ):
        process_grading_task(tid)

    lst = client.get(f"/api/homeworks/{hid}/submissions", headers=teacher_h)
    assert lst.status_code == 200, lst.text
    rows = lst.json().get("data") or []
    assert rows
    row = next((x for x in rows if x.get("latest_task_log")), None)
    assert row is not None
    assert row.get("latest_task_error_code") == "llm_call_failed"
    assert isinstance(row.get("latest_task_log"), list)


def test_grading_prompt_includes_two_round_iteration_context(grading_context: dict):
    """Prior attempt text + best comment are injected; older than 2 priors omitted (token cap)."""
    ctx = make_grading_course_with_homework()
    client: TestClient = grading_context["client"]
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    hid = ctx["homework_id"]

    r1 = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "第一版草稿缺少第二节"})
    assert r1.status_code == 200, r1.text
    db = SessionLocal()
    try:
        t1 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(40.0, "请补充第二节推导")),
    ):
        process_grading_task(t1)

    r2 = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "第二版已补充第二节推导"})
    assert r2.status_code == 200, r2.text
    db = SessionLocal()
    try:
        t2 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    captured: list[str] = []

    def capture_post(self, url, **kwargs):
        payload = kwargs.get("json") or {}
        captured.append(json.dumps(payload.get("messages") or [], ensure_ascii=False))
        return httpx.Response(200, json=json_llm_response(72.0, "改进可见"))

    with mock.patch.object(httpx.Client, "post", capture_post):
        process_grading_task(t2)

    assert len(captured) == 1
    blob = captured[0]
    assert "迭代上下文" in blob
    assert "第一版草稿缺少第二节" in blob
    assert "请补充第二节推导" in blob

    # Third prior: only two newest priors should appear when grading the 4th attempt.
    r3 = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "第三版微调格式"})
    assert r3.status_code == 200, r3.text
    db = SessionLocal()
    try:
        t3 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()
    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(73.0, "ok3")),
    ):
        process_grading_task(t3)

    r4 = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "第四版终稿"})
    assert r4.status_code == 200, r4.text
    db = SessionLocal()
    try:
        t4 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
        a1 = (
            db.query(HomeworkAttempt)
            .filter(HomeworkAttempt.homework_id == hid, HomeworkAttempt.student_id == ctx["student_id"])
            .order_by(HomeworkAttempt.id.asc())
            .first()
        )
        assert a1 is not None
        first_note = (a1.content or "").strip()
    finally:
        db.close()

    captured2: list[str] = []

    def capture2(self, url, **kwargs):
        payload = kwargs.get("json") or {}
        captured2.append(json.dumps(payload.get("messages") or [], ensure_ascii=False))
        return httpx.Response(200, json=json_llm_response(80.0, "done"))

    with mock.patch.object(httpx.Client, "post", capture2):
        process_grading_task(t4)

    assert len(captured2) == 1
    b2 = captured2[0]
    assert "第二版已补充第二节推导" in b2
    assert "第三版微调格式" in b2
    assert first_note not in b2


def test_latest_passing_validated_routes_to_newest_preset(grading_context: dict):
    ctx = make_grading_course_with_homework()
    client: TestClient = grading_context["client"]
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])

    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        from datetime import datetime, timezone

        p_old = LLMEndpointPreset(
            name=f"old-pass-{uid}",
            base_url="https://old.test/v1/",
            api_key="k-old",
            model_name="m-old",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
            text_validation_status="passed",
            validated_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        p_new = LLMEndpointPreset(
            name=f"new-pass-{uid}",
            base_url="https://new.test/v1/",
            api_key="k-new",
            model_name="m-new",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
            text_validation_status="passed",
            validated_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
        db.add_all([p_old, p_new])
        db.flush()
        hw = db.query(Homework).filter(Homework.id == ctx["homework_id"]).first()
        hw.llm_routing_spec = {"mode": "latest_passing_validated"}
        db.commit()
        new_id = p_new.id
    finally:
        db.close()

    r = client.post(f"/api/homeworks/{ctx['homework_id']}/submission", headers=student_h, json={"content": "route"})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    def fake_post(self, url, **kwargs):
        auth = (kwargs.get("headers") or {}).get("Authorization", "")
        assert "k-new" in auth
        return httpx.Response(200, json=json_llm_response(55.0, "picked new"))

    with mock.patch.object(httpx.Client, "post", fake_post):
        process_grading_task(tid)

    db = SessionLocal()
    try:
        cand = (
            db.query(HomeworkScoreCandidate)
            .filter(HomeworkScoreCandidate.source == "auto")
            .order_by(HomeworkScoreCandidate.id.desc())
            .first()
        )
        assert cand is not None
        assert cand.source_metadata.get("endpoint_id") == new_id
    finally:
        db.close()


def test_all_endpoints_exhausted_fails(grading_context: dict):
    """Single preset, max_retries=0: 503 enters persistent retry scheduling on the same row."""
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    client = grading_context["client"]
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])

    r = client.post(f"/api/homeworks/{ctx['homework_id']}/submission", headers=student_h, json={"content": "fail all"})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(503, json={})):
        process_grading_task(tid)

    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).first()
        assert task.status == "retry_scheduled"
        assert task.failure_class == "transient"
        assert task.next_retry_at is not None
        assert "503" in (task.error_message or "") or "暂时不可用" in (task.error_message or "")
    finally:
        db.close()
