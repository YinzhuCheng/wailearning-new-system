"""Course LLM config: flat PUT must not wipe existing group routing unless forced."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    LLMEndpointPreset,
    LLMGroup,
    Subject,
    User,
    UserRole,
)
from tests.scenarios.llm_scenario import ensure_admin, login_api


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


def test_put_flat_preserves_group_routing_when_config_has_groups(client: TestClient):
    ensure_admin()
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    db = SessionLocal()
    try:
        k = Class(name="merge-class", grade=2026)
        db.add(k)
        db.flush()
        t = User(
            username="merge_t",
            hashed_password=get_password_hash("t"),
            real_name="T",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        s = Subject(name="merge-subj", teacher_id=t.id, class_id=k.id)
        db.add(s)
        db.flush()
        a = LLMEndpointPreset(
            name="mga",
            base_url="https://a.mg/v1/",
            api_key="a",
            model_name="a",
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        b = LLMEndpointPreset(
            name="mgb",
            base_url="https://b.mg/v1/",
            api_key="b",
            model_name="b",
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        db.add_all([a, b])
        db.flush()
        cfg = CourseLLMConfig(subject_id=s.id, is_enabled=True, max_input_tokens=4000, max_output_tokens=500)
        db.add(cfg)
        db.flush()
        g1 = LLMGroup(config_id=cfg.id, priority=1, name="G1")
        db.add(g1)
        db.flush()
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, group_id=g1.id, preset_id=a.id, priority=1))
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, group_id=g1.id, preset_id=b.id, priority=2))
        db.commit()
        sid, pid_a, pid_b = s.id, a.id, b.id
    finally:
        db.close()
    th = login_api(client, "merge_t", "t")
    r = client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=th,
        json={
            "is_enabled": False,
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 4.0,
            "estimated_image_tokens": 100,
            "max_input_tokens": 4000,
            "max_output_tokens": 500,
            "endpoints": [{"preset_id": pid_a, "priority": 1}],
        },
    )
    assert r.status_code == 200, r.text
    g = client.get(f"/api/llm-settings/courses/{sid}", headers=th).json()["groups"]
    assert len(g) == 1
    m_ids = [m["preset_id"] for m in g[0]["members"]]
    assert set(m_ids) == {pid_a, pid_b}


def test_put_replace_flag_drops_groups(client: TestClient):
    ensure_admin()
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    db = SessionLocal()
    try:
        k = Class(name="merge2-class", grade=2026)
        db.add(k)
        db.flush()
        t = User(
            username="merge2_t",
            hashed_password=get_password_hash("t2"),
            real_name="T2",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        s = Subject(name="merge2-subj", teacher_id=t.id, class_id=k.id)
        db.add(s)
        db.flush()
        a = LLMEndpointPreset(
            name="m2a",
            base_url="https://a2.mg/v1/",
            api_key="a",
            model_name="a",
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        b = LLMEndpointPreset(
            name="m2b",
            base_url="https://b2.mg/v1/",
            api_key="b",
            model_name="b",
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        db.add_all([a, b])
        db.flush()
        cfg = CourseLLMConfig(subject_id=s.id, is_enabled=True, max_input_tokens=4000, max_output_tokens=500)
        db.add(cfg)
        db.flush()
        g1 = LLMGroup(config_id=cfg.id, priority=1, name="G1")
        db.add(g1)
        db.flush()
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, group_id=g1.id, preset_id=a.id, priority=1))
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, group_id=g1.id, preset_id=b.id, priority=2))
        db.commit()
        sid, pid_a = s.id, a.id
    finally:
        db.close()
    th = login_api(client, "merge2_t", "t2")
    r = client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=th,
        json={
            "is_enabled": True,
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 4.0,
            "estimated_image_tokens": 100,
            "max_input_tokens": 4000,
            "max_output_tokens": 500,
            "endpoints": [{"preset_id": pid_a, "priority": 1}],
            "replace_group_routing_with_flat_endpoints": True,
        },
    )
    assert r.status_code == 200, r.text
    g = client.get(f"/api/llm-settings/courses/{sid}", headers=th).json()["groups"]
    assert len(g) == 0
