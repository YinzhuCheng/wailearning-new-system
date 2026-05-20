from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import HomeworkGradingTask, LLMTokenUsageLog
from apps.backend.courseeval_backend.domains.llm.runtime import (
    RetryPolicy,
    advance_test_clock,
    compute_retry_delay_seconds,
    retry_window_exhausted,
    set_test_clock,
)
from apps.backend.courseeval_backend.llm_grading import claim_grading_tasks_batch, process_grading_task
from apps.backend.courseeval_backend.main import app
from tests.scenarios.llm_scenario import json_llm_response, login_api, make_grading_course_with_homework


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    yield
    SessionLocal().close()


def test_grading_task_transient_failure_becomes_retry_scheduled_then_succeeds(client: TestClient):
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    set_test_clock(datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc))

    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_h,
        json={"content": "retry later"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()


def test_retry_policy_delay_caps_at_twenty_minutes():
    policy = RetryPolicy()
    assert compute_retry_delay_seconds(retry_count=0, policy=policy) == 60
    assert compute_retry_delay_seconds(retry_count=10, policy=policy) == 20 * 60


def test_retry_window_exhausted_after_seven_days():
    created = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    not_yet = created + timedelta(days=6, hours=23, minutes=59)
    exhausted = created + timedelta(days=7)
    assert retry_window_exhausted(created_at=created, current_time=not_yet) is False
    assert retry_window_exhausted(created_at=created, current_time=exhausted) is True


def test_grading_task_transient_failure_past_retry_lifetime_becomes_failed(client: TestClient):
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    set_test_clock(datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc))

    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_h,
        json={"content": "expire later"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first()
        assert task is not None
        task.created_at = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        db.commit()
        tid = task.id
    finally:
        db.close()

    with mock.patch.object(httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(503, json={"error": "upstream"})):
        process_grading_task(tid)

    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).first()
        assert task is not None
        assert task.status == "failed"
        assert task.failure_class == "permanent"
    finally:
        db.close()
