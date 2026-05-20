"""P1–P3: Admin LLM endpoint presets (create, validate gate, teacher visibility)."""

from __future__ import annotations

import io
import uuid
from unittest import mock

from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import LLMEndpointPreset
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework


def test_p1_create_preset_save_without_api_key(client: TestClient) -> None:
    ensure_admin()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    name = f"behavior-preset-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/llm-settings/presets",
        headers=ah,
        json={
            "name": name,
            "base_url": "https://api.example.com/v1/",
            "api_key": "",
            "model_name": "gpt-test",
        },
    )
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    db = SessionLocal()
    try:
        row = db.query(LLMEndpointPreset).filter(LLMEndpointPreset.id == pid).first()
        assert row is not None
        assert (row.api_key or "") == ""
    finally:
        db.close()


def test_p2_validate_without_image_returns_400(client: TestClient) -> None:
    ensure_admin()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    ctx = make_grading_course_with_homework()
    r = client.post(f"/api/llm-settings/presets/{ctx['preset_id']}/validate", headers=ah)
    assert r.status_code == 400, r.text
    assert "图片" in r.json().get("detail", "") or "image" in (r.text or "").lower()


def test_p3_validate_with_image_then_teacher_sees_preset_in_list(client: TestClient) -> None:
    ensure_admin()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    ctx = make_grading_course_with_homework()
    tiny_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    with mock.patch(
        "apps.backend.courseeval_backend.api.routers.llm_settings.validate_text_connectivity",
        return_value=(True, "ok"),
    ), mock.patch(
        "apps.backend.courseeval_backend.api.routers.llm_settings.validate_vision_connectivity",
        return_value=(True, "vision ok"),
    ):
        r_val = client.post(
            f"/api/llm-settings/presets/{ctx['preset_id']}/validate",
            headers=ah,
            files={"image": ("tiny.png", io.BytesIO(tiny_png), "image/png")},
        )
    assert r_val.status_code == 200, r_val.text
    assert r_val.json().get("validation_status") == "validated"

    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    lst = client.get("/api/llm-settings/presets", headers=th)
    assert lst.status_code == 200, lst.text
    ids = {p["id"] for p in lst.json()}
    assert ctx["preset_id"] in ids
