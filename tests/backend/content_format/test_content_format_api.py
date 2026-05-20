"""API persistence for optional Markdown vs plain text flags (content_format / body_format)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.main import app
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_homework_create_and_submit_roundtrip_content_format(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    st = login_api(client, ctx["student_username"], ctx["student_password"])

    r = client.put(
        f"/api/homeworks/{ctx['homework_id']}",
        headers={**th, "Content-Type": "application/json"},
        json={"content": "# Title\n\nHello", "content_format": "plain"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("content_format") == "plain"

    r2 = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers={**st, "Content-Type": "application/json"},
        json={
            "content": "# not a heading",
            "content_format": "plain",
            "used_llm_assist": False,
            "submission_mode": "full",
        },
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body.get("content_format") == "plain"
    assert body.get("content") == "# not a heading"


def test_discussion_create_persists_body_format(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    r = client.post(
        "/api/discussions",
        headers={**th, "Content-Type": "application/json"},
        json={
            "target_type": "homework",
            "target_id": ctx["homework_id"],
            "subject_id": ctx["subject_id"],
            "class_id": ctx["class_id"],
            "body": "* not emphasis *",
            "body_format": "plain",
            "invoke_llm": False,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("body_format") == "plain"

    r2 = client.get(
        "/api/discussions",
        headers=th,
        params={
            "target_type": "homework",
            "target_id": ctx["homework_id"],
            "subject_id": ctx["subject_id"],
            "class_id": ctx["class_id"],
            "page": 1,
            "page_size": 10,
        },
    )
    assert r2.status_code == 200, r2.text
    rows = r2.json().get("data") or []
    assert any(row.get("body_format") == "plain" for row in rows)


def test_notification_create_content_format(client: TestClient):
    ensure_admin()
    adm = login_api(client, "pytest_admin", "pytest_admin_pass")
    ctx = make_grading_course_with_homework(auto_grading=False)

    r = client.post(
        "/api/notifications",
        headers={**adm, "Content-Type": "application/json"},
        json={
            "title": "fmt test",
            "content": "## x",
            "content_format": "plain",
            "class_id": ctx["class_id"],
            "subject_id": ctx["subject_id"],
        },
    )
    assert r.status_code == 200, r.text
    nid = r.json()["id"]
    assert r.json().get("content_format") == "plain"

    r2 = client.get(f"/api/notifications/{nid}", headers=adm)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("content_format") == "plain"
