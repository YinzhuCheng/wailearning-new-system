from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import (
    CourseDiscussionEntry,
    DiscussionLLMJob,
    LLMDiscussionTokenUsageLog,
)
from apps.backend.courseeval_backend.domains.llm.runtime import advance_test_clock, set_test_clock
from apps.backend.courseeval_backend.llm_discussion import run_discussion_llm_reply_for_job
from apps.backend.courseeval_backend.main import app
from tests.scenarios.llm_scenario import login_api, make_grading_course_with_homework


def _discussion_llm_response(text: str) -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
    }


def test_discussion_llm_transient_failure_retries_and_bills_only_on_success(monkeypatch):
    client = TestClient(app)
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    set_test_clock(datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc))

    monkeypatch.setattr(
        "apps.backend.courseeval_backend.api.routers.discussions.threading.Thread",
        lambda *args, **kwargs: type("NoopThread", (), {"start": lambda self: None})(),
    )

    payload = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
        "body": "@LLM\n请帮我分析一下这道题",
        "invoke_llm": True,
    }
    created = client.post("/api/discussions", headers=student_h, json=payload)
    assert created.status_code == 200, created.text
    user_entry_id = created.json()["id"]

    db = SessionLocal()
    try:
        job = db.query(DiscussionLLMJob).order_by(DiscussionLLMJob.id.desc()).first()
        assert job is not None
        job_id = job.id
    finally:
        db.close()

    with mock.patch.object(httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(503, json={"error": "upstream"})):
        run_discussion_llm_reply_for_job(job_id)

    db = SessionLocal()
    try:
        job = db.query(DiscussionLLMJob).filter(DiscussionLLMJob.id == job_id).first()
        assert job is not None
        assert job.status == "retry_scheduled"
        assert job.failure_class == "transient"
        assert job.retry_count == 1
        assert job.next_retry_at is not None
        assert job.assistant_entry_id is None
        assert db.query(LLMDiscussionTokenUsageLog).filter(LLMDiscussionTokenUsageLog.job_id == job_id).count() == 0

        entries = (
            db.query(CourseDiscussionEntry)
            .filter(
                CourseDiscussionEntry.target_type == "homework",
                CourseDiscussionEntry.target_id == ctx["homework_id"],
            )
            .order_by(CourseDiscussionEntry.id.asc())
            .all()
        )
        assert [row.id for row in entries] == [user_entry_id]
    finally:
        db.close()

    advance_test_clock(timedelta(seconds=60))
    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=_discussion_llm_response("这是恢复后的智能助教回复。")),
    ):
        run_discussion_llm_reply_for_job(job_id)

    db = SessionLocal()
    try:
        job = db.query(DiscussionLLMJob).filter(DiscussionLLMJob.id == job_id).first()
        assert job is not None
        assert job.status == "success"
        assert job.error_code is None
        assert job.next_retry_at is None
        assert job.assistant_entry_id is not None
        assert db.query(LLMDiscussionTokenUsageLog).filter(LLMDiscussionTokenUsageLog.job_id == job_id).count() == 1

        assistant = db.query(CourseDiscussionEntry).filter(CourseDiscussionEntry.id == job.assistant_entry_id).first()
        assert assistant is not None
        assert assistant.message_kind == "llm_assistant"
        assert "恢复后" in assistant.body
    finally:
        db.close()


def test_discussion_job_claim_is_single_winner_even_when_called_twice(monkeypatch):
    client = TestClient(app)
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])

    monkeypatch.setattr(
        "apps.backend.courseeval_backend.api.routers.discussions.threading.Thread",
        lambda *args, **kwargs: type("NoopThread", (), {"start": lambda self: None})(),
    )

    payload = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
        "body": "@LLM\n请帮我解释一下这道题",
        "invoke_llm": True,
    }
    created = client.post("/api/discussions", headers=student_h, json=payload)
    assert created.status_code == 200, created.text

    db = SessionLocal()
    try:
        job = db.query(DiscussionLLMJob).order_by(DiscussionLLMJob.id.desc()).first()
        assert job is not None
        job_id = job.id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=_discussion_llm_response("单次回复")),
    ):
        run_discussion_llm_reply_for_job(job_id)
        run_discussion_llm_reply_for_job(job_id)

    db = SessionLocal()
    try:
        job = db.query(DiscussionLLMJob).filter(DiscussionLLMJob.id == job_id).first()
        assert job is not None
        assert job.status == "success"
        assert job.assistant_entry_id is not None
        assistant_rows = (
            db.query(CourseDiscussionEntry)
            .filter(
                CourseDiscussionEntry.target_type == "homework",
                CourseDiscussionEntry.target_id == ctx["homework_id"],
                CourseDiscussionEntry.message_kind == "llm_assistant",
            )
            .all()
        )
        assert len(assistant_rows) == 1
        assert db.query(LLMDiscussionTokenUsageLog).filter(LLMDiscussionTokenUsageLog.job_id == job_id).count() == 1
    finally:
        db.close()



def test_discussion_llm_permanent_failure_emits_visible_reply(monkeypatch):
    client = TestClient(app)
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])

    monkeypatch.setattr(
        "apps.backend.courseeval_backend.api.routers.discussions.threading.Thread",
        lambda *args, **kwargs: type("NoopThread", (), {"start": lambda self: None})(),
    )

    payload = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
        "body": "@LLM\nplease explain",
        "invoke_llm": True,
    }
    created = client.post("/api/discussions", headers=student_h, json=payload)
    assert created.status_code == 200, created.text

    db = SessionLocal()
    try:
        job = db.query(DiscussionLLMJob).order_by(DiscussionLLMJob.id.desc()).first()
        assert job is not None
        job_id = job.id
    finally:
        db.close()


def test_discussion_job_transient_failure_past_retry_lifetime_becomes_failed(monkeypatch):
    client = TestClient(app)
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    set_test_clock(datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc))

    monkeypatch.setattr(
        "apps.backend.courseeval_backend.api.routers.discussions.threading.Thread",
        lambda *args, **kwargs: type("NoopThread", (), {"start": lambda self: None})(),
    )

    payload = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
        "body": "@LLM\nplease retry later",
        "invoke_llm": True,
    }
    created = client.post("/api/discussions", headers=student_h, json=payload)
    assert created.status_code == 200, created.text

    db = SessionLocal()
    try:
        job = db.query(DiscussionLLMJob).order_by(DiscussionLLMJob.id.desc()).first()
        assert job is not None
        job.created_at = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    with mock.patch.object(httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(503, json={"error": "upstream"})):
        run_discussion_llm_reply_for_job(job_id)

    db = SessionLocal()
    try:
        job = db.query(DiscussionLLMJob).filter(DiscussionLLMJob.id == job_id).first()
        assert job is not None
        assert job.status == "failed"
        assert job.failure_class == "permanent"
    finally:
        db.close()

    with mock.patch.object(httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(413, json={"error": "too_large"})):
        run_discussion_llm_reply_for_job(job_id)

    db = SessionLocal()
    try:
        job = db.query(DiscussionLLMJob).filter(DiscussionLLMJob.id == job_id).first()
        assert job is not None
        assert job.status == "failed"
        assert job.failure_class == "permanent"
        assert job.assistant_entry_id is not None
        assistant = db.query(CourseDiscussionEntry).filter(CourseDiscussionEntry.id == job.assistant_entry_id).first()
        assert assistant is not None
        assert assistant.message_kind == "llm_assistant"
    finally:
        db.close()
