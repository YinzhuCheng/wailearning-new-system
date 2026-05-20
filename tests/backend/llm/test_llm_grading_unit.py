"""Unit tests for LLM URL building, score JSON parsing, quota precheck, validate (mocked)."""

from __future__ import annotations

from unittest import mock

import httpx
import pytest
from sqlalchemy import text

from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.llm_grading import (
    VISION_TEST_IMAGE_DATA_URL,
    MaterialBlock,
    _build_chat_completion_url,
    _parse_scoring_json,
    build_png_data_url_from_image_bytes,
    ensure_course_llm_config,
    estimate_request_tokens_from_material,
    estimate_task_tokens,
    precheck_quota,
    validate_endpoint_connectivity,
)
import base64
from apps.backend.courseeval_backend.db.models import CourseLLMConfig, Homework, HomeworkAttempt, Subject


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    yield
    SessionLocal().close()


def test_build_png_data_url_from_raster_bytes():
    raw = base64.b64decode(VISION_TEST_IMAGE_DATA_URL.split("base64,", 1)[1])
    d = build_png_data_url_from_image_bytes(raw)
    assert d.startswith("data:image/png;base64,")


def test_build_chat_completion_url():
    assert _build_chat_completion_url("https://api.x/v1") == "https://api.x/v1/chat/completions"
    assert _build_chat_completion_url("https://api.x/v1/chat/completions") == "https://api.x/v1/chat/completions"
    assert _build_chat_completion_url("https://api.x/v1/chat/completions/") == "https://api.x/v1/chat/completions"


def test_parse_scoring_json_valid():
    hw = Homework(max_score=100, grade_precision="integer")
    out = _parse_scoring_json('{"score": 42, "comment": "ok"}', hw)
    assert out["score"] == 42.0
    assert out["comment"] == "ok"


def test_parse_scoring_json_markdown_fence():
    hw = Homework(max_score=10, grade_precision="integer")
    text = '```json\n{"score": 5, "comment": "c"}\n```'
    out = _parse_scoring_json(text, hw)
    assert out["score"] == 5.0


def test_parse_scoring_json_out_of_range():
    from apps.backend.courseeval_backend.llm_grading import RetryableLLMError

    hw = Homework(max_score=10, grade_precision="integer")
    with pytest.raises(RetryableLLMError) as exc:
        _parse_scoring_json('{"score": 99, "comment": "x"}', hw)
    msg = str(exc.value)
    assert "范围" in msg or "超出" in msg or "outside" in msg.lower() or "allowed range" in msg.lower()


def test_estimate_task_tokens():
    cfg = CourseLLMConfig(
        subject_id=1,
        max_input_tokens=8000,
        max_output_tokens=500,
    )
    t = estimate_task_tokens(cfg, text_length=400, image_count=0)
    assert 150 < t < 400


def test_estimate_request_tokens_from_material_uses_tiktoken_not_base64_payload():
    cfg = CourseLLMConfig(
        subject_id=1,
        max_input_tokens=8000,
        max_output_tokens=500,
    )
    tiny_png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAusB9Y9nKXUAAAAASUVORK5CYII="
    )
    material = {
        "assignment_texts": ["作业标题：t", "作业要求：\n无"],
        "student_blocks": [
            MaterialBlock(
                priority=2,
                path="x.png",
                block_type="image",
                image_data_url=f"data:image/png;base64,{tiny_png_b64}",
                estimated_tokens=100,
            )
        ],
        "notes_text": "",
    }
    hw = Homework(title="t", content="c", class_id=1, max_score=100, grade_precision="integer", created_by=1)
    att = HomeworkAttempt(
        homework_id=1,
        student_id=1,
        subject_id=1,
        class_id=1,
        content="",
    )
    t = estimate_request_tokens_from_material(cfg, material, homework=hw, attempt=att)
    assert 200 < t < 2500


def test_precheck_quota_allows_unlimited():
    db = SessionLocal()
    try:
        cfg = CourseLLMConfig(subject_id=1, is_enabled=True)
        with mock.patch(
            "apps.backend.courseeval_backend.domains.llm.quota.resolve_effective_daily_student_tokens",
            return_value=2_000_000_000,
        ):
            ok, code = precheck_quota(db, cfg, student_id=1, subject_id=1, estimated_tokens=999_999_999)
        assert ok is True
        assert code is None
    finally:
        db.close()


def test_precheck_quota_blocks_student_when_mocked_usage_high():
    """precheck uses _get_used_tokens_for_scope; mock to force exceed without heavy DB."""
    db = SessionLocal()
    try:
        cfg = CourseLLMConfig(
            subject_id=1,
            is_enabled=True,
        )
        with mock.patch(
            "apps.backend.courseeval_backend.domains.llm.quota.get_used_tokens_for_scope", return_value=95
        ), mock.patch(
            "apps.backend.courseeval_backend.domains.llm.quota.resolve_effective_daily_student_tokens", return_value=100
        ):
            ok, code = precheck_quota(db, cfg, student_id=1, subject_id=1, estimated_tokens=10)
        assert ok is False
        assert code == "quota_exceeded_student"
    finally:
        db.close()


def test_ensure_course_llm_config_reuses_pending_session_row():
    db = SessionLocal()
    try:
        subject = Subject(name="pending-course")
        db.add(subject)
        db.flush()
        pending = CourseLLMConfig(subject_id=subject.id)
        db.add(pending)

        config = ensure_course_llm_config(db, subject.id)

        assert config is pending
        db.flush()
        assert db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == subject.id).count() == 1
    finally:
        db.close()


def test_validate_endpoint_connectivity_ok():
    def fake_post(self, url, **kwargs):
        return httpx.Response(200, json={"choices": [{"message": {"content": "  ok  "}}]})

    with mock.patch.object(httpx.Client, "post", fake_post):
        ok, msg = validate_endpoint_connectivity("https://x/v1", "k", "m", 5, 10)
    assert ok is True
    assert "通过" in msg


def test_validate_endpoint_connectivity_http_400():
    def fake_post(self, url, **kwargs):
        return httpx.Response(400, text="nope")

    with mock.patch.object(httpx.Client, "post", fake_post):
        ok, msg = validate_endpoint_connectivity("https://x/v1", "k", "m", 5, 10)
    assert ok is False
    assert "400" in msg
