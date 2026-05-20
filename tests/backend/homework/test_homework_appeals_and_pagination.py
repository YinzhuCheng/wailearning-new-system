"""Homework appeals API and submissions pagination."""

from __future__ import annotations

from sqlalchemy import text

from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.main import app
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework


def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()


def test_submission_status_single_endpoint_matches_list_row():
    """GET /submissions/{id}/status returns same shape as list rows for deep-link review UI."""
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework()
    client = TestClient(app)
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "status-row-body"})
    assert sub.status_code == 200, sub.text
    sid = sub.json()["id"]

    one = client.get(f"/api/homeworks/{hid}/submissions/{sid}/status", headers=teacher_h)
    assert one.status_code == 200, one.text
    body = one.json()
    assert body.get("submission_id") == sid
    assert body.get("content") == "status-row-body"

    paginated = client.get(f"/api/homeworks/{hid}/submissions?page=1&page_size=50", headers=teacher_h)
    assert paginated.status_code == 200, paginated.text
    rows = paginated.json().get("data") or []
    match = next((r for r in rows if r.get("submission_id") == sid), None)
    assert match is not None
    assert match.get("content") == body.get("content")


def test_submissions_endpoint_supports_pagination():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework()
    client = TestClient(app)
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    r = client.get(f"/api/homeworks/{hid}/submissions?page=1&page_size=5", headers=teacher_h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "page" in data and "page_size" in data and "total" in data
    assert data["page"] == 1
    assert data["page_size"] == 5


def test_student_cannot_duplicate_appeal():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework()
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "hello appeal"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    from apps.backend.courseeval_backend.llm_grading import process_grading_task
    from apps.backend.courseeval_backend.db.models import HomeworkGradingTask
    from unittest import mock
    import httpx
    from tests.scenarios.llm_scenario import json_llm_response

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(80.0, "ok")),
    ):
        process_grading_task(tid)

    payload = {"reason_text": "自动评分忽略了第二点推导过程，我认为不合理。"}
    a1 = client.post(f"/api/homeworks/{hid}/submissions/{sub_id}/appeal", headers=student_h, json=payload)
    assert a1.status_code == 200, a1.text

    a2 = client.post(f"/api/homeworks/{hid}/submissions/{sub_id}/appeal", headers=student_h, json=payload)
    assert a2.status_code == 400, a2.text

    note = client.get("/api/notifications", headers=teacher_h)
    assert note.status_code == 200
    titles = [row["title"] for row in note.json().get("data", [])]
    assert any("申诉" in t for t in titles)
