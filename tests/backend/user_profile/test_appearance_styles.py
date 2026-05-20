from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates, seed_default_system_settings
from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import User, UserRole
from apps.backend.courseeval_backend.main import app


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    ensure_schema_updates()
    db = SessionLocal()
    try:
        seed_default_system_settings(db)
    finally:
        db.close()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return _headers(r.json()["access_token"])


def _seed_user(*, username: str, password: str, role: str = UserRole.TEACHER.value) -> None:
    db = SessionLocal()
    try:
        db.add(
            User(
                username=username,
                hashed_password=get_password_hash(password),
                real_name=username,
                role=role,
            )
        )
        db.commit()
    finally:
        db.close()


def test_public_settings_expose_default_appearance_preset(client: TestClient):
    r = client.get("/api/settings/public")
    assert r.status_code == 200, r.text
    assert r.json()["appearance_default_preset"] == "professional-blue"


def test_user_can_save_select_and_clear_personal_appearance_style(client: TestClient):
    suffix = uuid.uuid4().hex[:10]
    username = f"theme_{suffix}"
    _seed_user(username=username, password="pw123456")
    h = _login(client, username, "pw123456")

    initial = client.get("/api/appearance/me", headers=h)
    assert initial.status_code == 200, initial.text
    assert initial.json()["selected_style"] is None
    assert initial.json()["system_default_preset"] == "professional-blue"

    create = client.post(
        "/api/appearance/me/styles",
        headers=h,
        json={
            "name": "My Study Style",
            "source": "custom",
            "preset_key": "fresh-green",
            "config": {
                "primary": "green",
                "accent": "blue",
                "shadow": "medium",
                "transparency": "glass",
                "radius": "soft",
                "density": "comfortable",
                "font_family": "system",
                "font_scale": "medium",
            },
            "select_after_save": True,
        },
    )
    assert create.status_code == 200, create.text
    style = create.json()
    assert style["is_selected"] is True
    assert style["config"]["primary"] == "green"

    state = client.get("/api/appearance/me", headers=h).json()
    assert state["selected_style"]["id"] == style["id"]
    assert len(state["saved_styles"]) == 1

    clear = client.post("/api/appearance/me/use-system", headers=h)
    assert clear.status_code == 200, clear.text
    assert clear.json()["selected_style"] is None
    assert clear.json()["saved_styles"][0]["is_selected"] is False


def test_personal_appearance_style_names_are_user_scoped(client: TestClient):
    suffix = uuid.uuid4().hex[:10]
    user_a = f"style_a_{suffix}"
    user_b = f"style_b_{suffix}"
    _seed_user(username=user_a, password="pw123456")
    _seed_user(username=user_b, password="pw123456")
    h_a = _login(client, user_a, "pw123456")
    h_b = _login(client, user_b, "pw123456")

    payload = {
        "name": "Shared Name",
        "source": "custom",
        "preset_key": None,
        "config": {
            "primary": "blue",
            "accent": "cyan",
            "shadow": "soft",
            "transparency": "balanced",
            "radius": "balanced",
            "density": "comfortable",
            "font_family": "system",
            "font_scale": "medium",
        },
        "select_after_save": True,
    }

    assert client.post("/api/appearance/me/styles", headers=h_a, json=payload).status_code == 200
    assert client.post("/api/appearance/me/styles", headers=h_b, json=payload).status_code == 200

    duplicate = client.post("/api/appearance/me/styles", headers=h_a, json=payload)
    assert duplicate.status_code == 409
