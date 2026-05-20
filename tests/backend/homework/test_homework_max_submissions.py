"""Homework max_submissions per student: API enforcement and teacher update validation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Homework
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework


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
def cap_ctx(client: TestClient) -> dict:
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    db = SessionLocal()
    try:
        hw = db.query(Homework).filter(Homework.id == ctx["homework_id"]).first()
        assert hw is not None
        hw.max_submissions = 2
        db.commit()
    finally:
        db.close()
    ctx["client"] = client
    ctx["student_headers"] = login_api(client, ctx["student_username"], ctx["student_password"])
    ctx["teacher_headers"] = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    return ctx


def test_submission_blocked_when_max_reached(cap_ctx: dict):
    client = cap_ctx["client"]
    hid = cap_ctx["homework_id"]
    sh = cap_ctx["student_headers"]

    assert client.post(f"/api/homeworks/{hid}/submission", headers=sh, json={"content": "a1"}).status_code == 200
    assert client.post(f"/api/homeworks/{hid}/submission", headers=sh, json={"content": "a2"}).status_code == 200
    r3 = client.post(f"/api/homeworks/{hid}/submission", headers=sh, json={"content": "a3"})
    assert r3.status_code == 400
    assert "最大提交次数" in (r3.json().get("detail") or "")


def test_homework_get_includes_submissions_remaining(cap_ctx: dict):
    client = cap_ctx["client"]
    hid = cap_ctx["homework_id"]
    sh = cap_ctx["student_headers"]

    r0 = client.get(f"/api/homeworks/{hid}", headers=sh)
    assert r0.status_code == 200
    assert r0.json()["submissions_remaining"] == 2

    client.post(f"/api/homeworks/{hid}/submission", headers=sh, json={"content": "once"})
    r1 = client.get(f"/api/homeworks/{hid}", headers=sh)
    assert r1.json()["attempt_count"] == 1
    assert r1.json()["submissions_remaining"] == 1


def test_teacher_cannot_set_max_below_existing_attempts(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    hid = ctx["homework_id"]
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    sh = login_api(client, ctx["student_username"], ctx["student_password"])

    for i in range(3):
        r = client.post(f"/api/homeworks/{hid}/submission", headers=sh, json={"content": f"x{i}"})
        assert r.status_code == 200, r.text

    ok = client.put(f"/api/homeworks/{hid}", headers=th, json={"max_submissions": 3})
    assert ok.status_code == 200

    bad = client.put(f"/api/homeworks/{hid}", headers=th, json={"max_submissions": 2})
    assert bad.status_code == 400
    assert "提交次数上限" in (bad.json().get("detail") or "")
