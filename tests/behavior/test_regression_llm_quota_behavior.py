"""R1–R3: Regression guards for removed course-level token pool."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.db.database import SessionLocal, engine
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework


def test_r1_no_quota_exceeded_course_in_app_sources() -> None:
    root = Path(__file__).resolve().parents[2] / "app"
    hits: list[str] = []
    for p in sorted(root.rglob("*.py")):
        try:
            content = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if "quota_exceeded_course" in content:
            hits.append(str(p.relative_to(root.parent)))
    assert not hits, f"quota_exceeded_course still referenced in: {hits}"


def test_r2_course_llm_config_response_shape(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.get(f"/api/llm-settings/courses/{ctx['subject_id']}", headers=th)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "daily_course_token_limit" not in body
    assert "daily_student_token_limit" not in body
    qu = body.get("quota_usage")
    if qu is not None:
        assert set(qu.keys()) <= {"usage_date", "quota_timezone"}


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="information_schema column check is for PostgreSQL")
def test_r3_course_llm_config_columns_no_legacy_token_limits() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'course_llm_configs'
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
