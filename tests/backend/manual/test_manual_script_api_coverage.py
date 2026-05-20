"""
Migrated from root-level manual scripts: smoke coverage for admin APIs via TestClient.

Replaces former requests-to-localhost:8001 scripts so CI exercises the same routes in-process.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.bootstrap import seed_default_system_settings
from apps.backend.courseeval_backend.db.models import Class, SystemSetting, User, UserRole
from tests.scenarios.llm_scenario import ensure_admin, login_api


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    db = SessionLocal()
    try:
        if db.query(SystemSetting).count() == 0:
            seed_default_system_settings(db)
    finally:
        db.close()
    yield
    SessionLocal().close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    ensure_admin()
    return login_api(client, "pytest_admin", "pytest_admin_pass")


def test_login_classes_users_smoke(client: TestClient, admin_headers: dict[str, str]):
    r = client.get("/api/classes", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []

    suffix = uuid.uuid4().hex[:8]
    r2 = client.post(
        "/api/classes",
        headers=admin_headers,
        json={"name": f"SmokeClass_{suffix}", "grade": 2026},
    )
    assert r2.status_code == 200, r2.text
    cid = r2.json()["id"]

    r3 = client.get("/api/classes", headers=admin_headers)
    assert r3.status_code == 200
    assert len(r3.json()) == 1
    assert r3.json()[0]["id"] == cid

    r4 = client.get("/api/users", headers=admin_headers)
    assert r4.status_code == 200
    usernames = {u["username"] for u in r4.json()}
    assert "pytest_admin" in usernames


def test_semesters_and_dashboard_stats(client: TestClient, admin_headers: dict[str, str]):
    r = client.get("/api/semesters", headers=admin_headers)
    assert r.status_code == 200, r.text
    semesters = r.json()
    assert isinstance(semesters, list)

    r2 = client.get("/api/dashboard/stats", headers=admin_headers)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    for key in ("total_students", "total_classes", "total_scores", "avg_score", "attendance_rate"):
        assert key in body

    if semesters:
        name = semesters[0].get("name") or ""
        r3 = client.get("/api/dashboard/stats", headers=admin_headers, params={"semester": name})
        assert r3.status_code == 200, r3.text


def test_users_create_teacher_and_class_teacher(client: TestClient, admin_headers: dict[str, str]):
    suffix = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/classes",
        headers=admin_headers,
        json={"name": f"UserFlow_{suffix}", "grade": 2026},
    )
    assert r.status_code == 200, r.text
    cid = r.json()["id"]

    r1 = client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "username": f"smoke_teacher_{suffix}",
            "password": "Test123456!",
            "real_name": "Smoke Teacher",
            "role": "teacher",
            "class_id": None,
        },
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["username"] == f"smoke_teacher_{suffix}"

    r2 = client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "username": f"smoke_ct_{suffix}",
            "password": "Test123456!",
            "real_name": "Smoke Class Teacher",
            "role": "class_teacher",
            "class_id": cid,
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["class_id"] == cid

    r3 = client.get("/api/users", headers=admin_headers)
    assert r3.status_code == 200
    names = {u["username"] for u in r3.json()}
    assert f"smoke_teacher_{suffix}" in names
    assert f"smoke_ct_{suffix}" in names


def test_logs_list_summary_and_filter(client: TestClient, admin_headers: dict[str, str]):
    r = client.get("/api/logs", headers=admin_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "total" in data and "data" in data

    r2 = client.get("/api/logs/stats/summary", headers=admin_headers)
    assert r2.status_code == 200, r.text
    assert "total" in r2.json()

    r3 = client.get("/api/logs", headers=admin_headers, params={"action": "登录"})
    assert r3.status_code == 200, r.text


def test_points_stats_rules_items_ranking(client: TestClient, admin_headers: dict[str, str]):
    r = client.get("/api/points/stats", headers=admin_headers)
    assert r.status_code == 200, r.text
    for key in ("total_students", "active_students", "total_points_distributed", "total_points_exchanged"):
        assert key in r.json()

    r2 = client.get("/api/points/rules", headers=admin_headers)
    assert r2.status_code == 200
    assert isinstance(r2.json(), list)

    r3 = client.get("/api/points/items", headers=admin_headers)
    assert r3.status_code == 200
    assert isinstance(r3.json(), list)

    r4 = client.get("/api/points/ranking", headers=admin_headers, params={"limit": 5})
    assert r4.status_code == 200
    assert isinstance(r4.json(), list)


def test_settings_public_and_all(client: TestClient, admin_headers: dict[str, str]):
    r = client.get("/api/settings/public")
    assert r.status_code == 200, r.text
    pub = r.json()
    for key in ("system_name", "system_intro", "system_logo", "login_background", "copyright"):
        assert key in pub

    r2 = client.get("/api/settings/all", headers=admin_headers)
    assert r2.status_code == 200, r2.text
    assert isinstance(r2.json(), list)
    assert len(r2.json()) >= 1


def test_dashboard_stats_direct_router_call():
    """Covers former test_dashboard.py DB + router call path (no HTTP)."""
    from apps.backend.courseeval_backend.domains.courses.class_scope import get_accessible_class_ids
    from apps.backend.courseeval_backend.api.routers.dashboard import get_dashboard_stats

    ensure_admin()
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "pytest_admin").first()
        assert admin is not None
        class_ids = get_accessible_class_ids(admin, db)
        assert isinstance(class_ids, list)
        stats = get_dashboard_stats(semester="", db=db, current_user=admin)
        assert stats.total_students >= 0
        assert stats.total_classes >= 0
    finally:
        db.close()
