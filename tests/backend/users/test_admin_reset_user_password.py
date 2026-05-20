"""Admin POST /api/users/{id}/reset-password behavior."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.core.auth import verify_password
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import Class, User, UserRole
from apps.backend.courseeval_backend.main import app
from tests.scenarios.llm_scenario import ensure_admin, login_api


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _class_id() -> int:
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        k = Class(name=f"rst_cls_{uid}", grade=2026)
        db.add(k)
        db.commit()
        db.refresh(k)
        return int(k.id)
    finally:
        db.close()


def test_admin_reset_student_defaults_to_username(client: TestClient):
    ensure_admin()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    uid = uuid.uuid4().hex[:8]
    cid = _class_id()
    created = client.post(
        "/api/users",
        headers=ah,
        json={
            "username": f"stu_rst_{uid}",
            "password": "initial",
            "real_name": "S",
            "role": "student",
            "class_id": cid,
        },
    )
    assert created.status_code == 200, created.text
    user_id = created.json()["id"]

    r = client.post(f"/api/users/{user_id}/reset-password", headers=ah, json={})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        assert u is not None
        assert verify_password(f"stu_rst_{uid}", u.hashed_password)
    finally:
        db.close()


def test_admin_reset_teacher_defaults_to_111111(client: TestClient):
    ensure_admin()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    uid = uuid.uuid4().hex[:8]
    created = client.post(
        "/api/users",
        headers=ah,
        json={
            "username": f"t_rst_{uid}",
            "password": "initial",
            "real_name": "T",
            "role": "teacher",
        },
    )
    assert created.status_code == 200, created.text
    user_id = created.json()["id"]

    r = client.post(f"/api/users/{user_id}/reset-password", headers=ah, json={})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        assert verify_password("111111", u.hashed_password)
    finally:
        db.close()


def test_admin_reset_admin_requires_explicit_password(client: TestClient):
    ensure_admin()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    uid = uuid.uuid4().hex[:8]
    created = client.post(
        "/api/users",
        headers=ah,
        json={
            "username": f"adm2_{uid}",
            "password": "InitialAdm9!",
            "real_name": "A2",
            "role": "admin",
        },
    )
    assert created.status_code == 200, created.text
    user_id = created.json()["id"]

    r0 = client.post(f"/api/users/{user_id}/reset-password", headers=ah, json={})
    assert r0.status_code == 400

    r1 = client.post(f"/api/users/{user_id}/reset-password", headers=ah, json={"new_password": "NewAdmPwd9!"})
    assert r1.status_code == 200, r1.text

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        assert verify_password("NewAdmPwd9!", u.hashed_password)
    finally:
        db.close()
