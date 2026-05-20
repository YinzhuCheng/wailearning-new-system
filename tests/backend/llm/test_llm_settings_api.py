"""
HTTP API tests for /api/llm-settings: presets, validate (mocked connectivity), course config.
"""

from __future__ import annotations

from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.llm_grading import VISION_TEST_IMAGE_DATA_URL
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    LLMEndpointPreset,
    Student,
    Subject,
    User,
    UserRole,
)


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


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    db = SessionLocal()
    try:
        db.add(
            User(
                username="t_admin",
                hashed_password=get_password_hash("t_admin_pass"),
                real_name="Admin",
                role=UserRole.ADMIN.value,
            )
        )
        db.commit()
    finally:
        db.close()
    return _login(client, "t_admin", "t_admin_pass")


def _tiny_test_png() -> bytes:
    import base64

    b64 = VISION_TEST_IMAGE_DATA_URL.split("base64,", 1)[1]
    return base64.b64decode(b64)


@pytest.fixture
def teacher_course_context(client: TestClient) -> dict:
    db = SessionLocal()
    try:
        klass = Class(name="TClass", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username="t_teacher",
            hashed_password=get_password_hash("t_teacher_pass"),
            real_name="T Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        course = Subject(name="TCourse", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.commit()
        return {"subject_id": course.id, "teacher_user": "t_teacher", "teacher_pass": "t_teacher_pass"}
    finally:
        db.close()


@pytest.fixture
def teacher_headers(client: TestClient, teacher_course_context: dict) -> dict[str, str]:
    return _login(
        client,
        teacher_course_context["teacher_user"],
        teacher_course_context["teacher_pass"],
    )


def test_teachers_can_list_presets(client: TestClient, admin_headers, teacher_headers):
    r = client.get("/api/llm-settings/presets", headers=teacher_headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Schema bootstrap may insert a default validated preset; teachers still get a readable list.


def test_non_admin_cannot_create_preset(client: TestClient, teacher_headers):
    r = client.post(
        "/api/llm-settings/presets",
        headers=teacher_headers,
        json={
            "name": "n1",
            "base_url": "https://a.test/v1/",
            "api_key": "k",
            "model_name": "m",
        },
    )
    assert r.status_code == 403


def test_duplicate_preset_name_400(client: TestClient, admin_headers):
    body = {
        "name": "unique-p1",
        "base_url": "https://a.test/v1/",
        "api_key": "k",
        "model_name": "m",
    }
    assert client.post("/api/llm-settings/presets", headers=admin_headers, json=body).status_code == 200
    r2 = client.post("/api/llm-settings/presets", headers=admin_headers, json=body)
    assert r2.status_code == 400
    assert "exists" in r2.json().get("detail", "")


@mock.patch(
    "apps.backend.courseeval_backend.api.routers.llm_settings.validate_vision_connectivity",
    return_value=(True, "vision ok"),
)
@mock.patch(
    "apps.backend.courseeval_backend.api.routers.llm_settings.validate_text_connectivity",
    return_value=(True, "text ok"),
)
def test_validate_marks_validated(mock_txt, mock_vis, client: TestClient, admin_headers):
    c = client.post(
        "/api/llm-settings/presets",
        headers=admin_headers,
        json={"name": "p-val", "base_url": "https://a.test/v1/", "api_key": "k", "model_name": "m"},
    )
    pid = c.json()["id"]
    v = client.post(
        f"/api/llm-settings/presets/{pid}/validate",
        headers=admin_headers,
        files={"image": ("t.png", _tiny_test_png(), "image/png")},
    )
    assert v.status_code == 200
    d = v.json()
    assert d["validation_status"] == "validated"
    assert d["text_validation_status"] == "passed"
    assert d["vision_validation_status"] == "passed"
    assert d["supports_vision"] is True
    assert mock_txt.called
    assert mock_vis.called


@mock.patch(
    "apps.backend.courseeval_backend.api.routers.llm_settings.validate_vision_connectivity",
    return_value=(True, "vision ok"),
)
@mock.patch(
    "apps.backend.courseeval_backend.api.routers.llm_settings.validate_text_connectivity",
    return_value=(True, "text ok"),
)
def test_get_put_course_config(_, __, client: TestClient, admin_headers, teacher_headers, teacher_course_context):
    c = client.post(
        "/api/llm-settings/presets",
        headers=admin_headers,
        json={"name": "p-course", "base_url": "https://a.test/v1/", "api_key": "k", "model_name": "m"},
    )
    pid = c.json()["id"]
    client.post(
        f"/api/llm-settings/presets/{pid}/validate",
        headers=admin_headers,
        files={"image": ("t.png", _tiny_test_png(), "image/png")},
    )

    sid = teacher_course_context["subject_id"]
    payload = {
        "is_enabled": True,
        "response_language": "zh",
        "quota_timezone": "UTC",
        "estimated_chars_per_token": 4.0,
        "estimated_image_tokens": 850,
        "max_input_tokens": 8000,
        "max_output_tokens": 1000,
        "endpoints": [{"preset_id": pid, "priority": 1}],
    }
    put = client.put(f"/api/llm-settings/courses/{sid}", headers=teacher_headers, json=payload)
    assert put.status_code == 200, put.text
    g = client.get(f"/api/llm-settings/courses/{sid}", headers=teacher_headers)
    assert g.status_code == 200
    data = g.json()
    assert data["is_enabled"] is True
    assert "quota_timezone" not in data
    assert "estimated_chars_per_token" not in data
    assert "estimated_image_tokens" not in data
    assert len(data["endpoints"]) == 1
    assert "visual_validation_notice" in data and len(data["visual_validation_notice"]) > 0


def test_cannot_bind_unvalidated_preset(client: TestClient, admin_headers, teacher_headers, teacher_course_context):
    c = client.post(
        "/api/llm-settings/presets",
        headers=admin_headers,
        json={"name": "p-pending", "base_url": "https://a.test/v1/", "api_key": "k", "model_name": "m"},
    )
    pid = c.json()["id"]
    sid = teacher_course_context["subject_id"]
    r = client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=teacher_headers,
        json={
            "is_enabled": False,
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 4.0,
            "estimated_image_tokens": 850,
            "max_input_tokens": 16000,
            "max_output_tokens": 1200,
            "endpoints": [{"preset_id": pid, "priority": 1}],
        },
    )
    assert r.status_code == 400
    assert "vision" in r.json().get("detail", "").lower()


def test_course_config_accepts_null_max_output_tokens(client: TestClient, teacher_headers, teacher_course_context):
    sid = teacher_course_context["subject_id"]
    r = client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=teacher_headers,
        json={
            "is_enabled": False,
            "max_input_tokens": 16000,
            "max_output_tokens": None,
            "endpoints": [],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["max_output_tokens"] is None


def test_student_403_on_llm_routes(client: TestClient, teacher_course_context: dict):
    """Students must not list presets or read course LLM (API returns 403)."""
    db = SessionLocal()
    try:
        subj = db.query(Subject).filter(Subject.id == teacher_course_context["subject_id"]).first()
        su = User(
            username="t_student",
            hashed_password=get_password_hash("t_student_pass"),
            real_name="Stu",
            role=UserRole.STUDENT.value,
            class_id=subj.class_id,
        )
        db.add(su)
        db.flush()
        st = Student(name="Stu", student_no="t_student", class_id=subj.class_id)
        db.add(st)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=subj.id,
                student_id=st.id,
                class_id=subj.class_id,
                enrollment_type="required",
            )
        )
        db.commit()
    finally:
        db.close()

    h = _login(client, "t_student", "t_student_pass")
    r = client.get("/api/llm-settings/presets", headers=h)
    assert r.status_code == 403
    r2 = client.get(f"/api/llm-settings/courses/{teacher_course_context['subject_id']}", headers=h)
    assert r2.status_code == 403
