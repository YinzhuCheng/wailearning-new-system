"""Forgot-password request creates an admin-only notification with reset deep link."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import User, UserRole
from apps.backend.courseeval_backend.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def test_forgot_password_creates_notification_for_teacher(client: TestClient):
    uid = _uid()
    db = SessionLocal()
    try:
        adm = User(
            username=f"adm_fp_{uid}",
            hashed_password=get_password_hash("adm_pass"),
            real_name="Admin FP",
            role=UserRole.ADMIN.value,
        )
        db.add(adm)
        db.flush()
        teach = User(
            username=f"t_fp_{uid}",
            hashed_password=get_password_hash("old"),
            real_name="Teacher FP",
            role=UserRole.TEACHER.value,
        )
        db.add(teach)
        db.commit()
        tid = teach.id
    finally:
        db.close()

    r = client.post("/api/auth/forgot-password", json={"username": f"t_fp_{uid}"})
    assert r.status_code == 200
    assert "管理员" in r.json().get("message", "")

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT notification_kind, content FROM notifications
                WHERE notification_kind = 'password_reset_request'
                  AND content LIKE :pat
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"pat": f"%open_reset_password_user_id={tid}%"},
        ).fetchone()
        assert row is not None
        assert row[0] == "password_reset_request"
        assert "/users?open_reset_password_user_id=" in (row[1] or "")
    finally:
        db.close()


def test_forgot_password_for_unknown_or_admin_is_silent(client: TestClient):
    r1 = client.post("/api/auth/forgot-password", json={"username": "definitely_no_such_user_xyz"})
    assert r1.status_code == 200

    uid = _uid()
    db = SessionLocal()
    try:
        adm = User(
            username=f"onlyadm_{uid}",
            hashed_password=get_password_hash("pw"),
            real_name="Lonely Admin",
            role=UserRole.ADMIN.value,
        )
        db.add(adm)
        db.commit()
    finally:
        db.close()

    r2 = client.post("/api/auth/forgot-password", json={"username": f"onlyadm_{uid}"})
    assert r2.status_code == 200

    db = SessionLocal()
    try:
        n = db.execute(
            text(
                "SELECT COUNT(*) FROM notifications WHERE title LIKE :t"
            ),
            {"t": f"%onlyadm_{uid}%"},
        ).scalar_one()
        assert int(n or 0) == 0
    finally:
        db.close()
