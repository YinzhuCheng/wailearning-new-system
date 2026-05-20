"""Profile PATCH, avatar upload/replace/delete, password change, and download ACL.

Covers cross-user isolation, oversized uploads, orphan cleanup after replace, and login-after-password-change.
"""

from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.attachments import ATTACHMENTS_DIR, get_attachment_file_path
from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import User, UserRole


# Minimal 1x1 PNG (transparent)
MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
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


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return _headers(r.json()["access_token"])


def _seed_user(
    *,
    username: str,
    password: str,
    real_name: str,
    role: str = UserRole.TEACHER.value,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            User(
                username=username,
                hashed_password=get_password_hash(password),
                real_name=real_name,
                role=role,
            )
        )
        db.commit()
    finally:
        db.close()


def test_patch_me_trims_real_name_and_round_trips(client: TestClient):
    uid = uuid.uuid4().hex[:10]
    uname = f"prof_{uid}"
    _seed_user(username=uname, password="pw123456", real_name="Old")

    h = _login(client, uname, "pw123456")
    r = client.patch("/api/auth/me", headers=h, json={"real_name": "  New Display  "})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["real_name"] == "New Display"

    me = client.get("/api/auth/me", headers=h)
    assert me.status_code == 200
    assert me.json()["real_name"] == "New Display"


def test_patch_me_empty_real_name_422(client: TestClient):
    uid = uuid.uuid4().hex[:10]
    uname = f"empty_{uid}"
    _seed_user(username=uname, password="pw123456", real_name="X")

    h = _login(client, uname, "pw123456")
    r = client.patch("/api/auth/me", headers=h, json={"real_name": "   "})
    assert r.status_code == 422


def test_avatar_upload_then_download_owner_only_cross_user_forbidden(client: TestClient):
    uid = uuid.uuid4().hex[:10]
    u_a = f"ava_a_{uid}"
    u_b = f"ava_b_{uid}"
    _seed_user(username=u_a, password="pw123456", real_name="A")
    _seed_user(username=u_b, password="pw123456", real_name="B")

    ha = _login(client, u_a, "pw123456")
    hb = _login(client, u_b, "pw123456")

    files = {"file": ("face.png", io.BytesIO(MINIMAL_PNG), "image/png")}
    up = client.post("/api/auth/me/avatar", headers=ha, files=files)
    assert up.status_code == 200, up.text
    url_a = up.json().get("avatar_url")
    assert url_a

    path_on_disk = get_attachment_file_path(url_a)
    assert path_on_disk is not None
    assert path_on_disk.exists()

    dl_owner = client.get(
        "/api/files/download",
        headers=ha,
        params={"attachment_url": url_a},
    )
    assert dl_owner.status_code == 200
    assert dl_owner.content[:8] == MINIMAL_PNG[:8]

    dl_other = client.get(
        "/api/files/download",
        headers=hb,
        params={"attachment_url": url_a},
    )
    assert dl_other.status_code == 403


def test_avatar_replace_deletes_previous_file_on_disk(client: TestClient):
    uid = uuid.uuid4().hex[:10]
    uname = f"rep_{uid}"
    _seed_user(username=uname, password="pw123456", real_name="R")

    h = _login(client, uname, "pw123456")

    first = client.post(
        "/api/auth/me/avatar",
        headers=h,
        files={"file": ("one.png", io.BytesIO(MINIMAL_PNG), "image/png")},
    )
    assert first.status_code == 200, first.text
    url1 = first.json()["avatar_url"]
    path1 = get_attachment_file_path(url1)
    assert path1 and path1.exists()

    second = client.post(
        "/api/auth/me/avatar",
        headers=h,
        files={"file": ("two.png", io.BytesIO(MINIMAL_PNG), "image/png")},
    )
    assert second.status_code == 200, second.text
    url2 = second.json()["avatar_url"]
    assert url2 != url1

    assert not path1.exists(), "previous avatar file should be removed after replace"
    path2 = get_attachment_file_path(url2)
    assert path2 and path2.exists()


def test_avatar_oversized_rejected_and_orphan_not_left_on_disk(client: TestClient):
    uid = uuid.uuid4().hex[:10]
    uname = f"big_{uid}"
    _seed_user(username=uname, password="pw123456", real_name="B")

    h = _login(client, uname, "pw123456")
    huge = b"\xff" * (2 * 1024 * 1024 + 1)
    r = client.post(
        "/api/auth/me/avatar",
        headers=h,
        files={"file": ("huge.png", io.BytesIO(huge), "image/png")},
    )
    assert r.status_code == 400
    assert "2 MB" in (r.json().get("detail") or "")

    loose = list(ATTACHMENTS_DIR.glob("*.png"))
    over_limit = [p for p in loose if p.stat().st_size > 2 * 1024 * 1024]
    assert not over_limit, "oversized upload should not persist a stored attachment file"


def test_avatar_wrong_extension_rejected(client: TestClient):
    uid = uuid.uuid4().hex[:10]
    uname = f"exe_{uid}"
    _seed_user(username=uname, password="pw123456", real_name="E")

    h = _login(client, uname, "pw123456")
    r = client.post(
        "/api/auth/me/avatar",
        headers=h,
        files={"file": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert r.status_code == 400


def test_delete_avatar_clears_db_and_removes_file(client: TestClient):
    uid = uuid.uuid4().hex[:10]
    uname = f"del_{uid}"
    _seed_user(username=uname, password="pw123456", real_name="D")

    h = _login(client, uname, "pw123456")
    up = client.post(
        "/api/auth/me/avatar",
        headers=h,
        files={"file": ("z.png", io.BytesIO(MINIMAL_PNG), "image/png")},
    )
    assert up.status_code == 200, up.text
    url = up.json()["avatar_url"]
    path = get_attachment_file_path(url)
    assert path and path.exists()

    rm = client.delete("/api/auth/me/avatar", headers=h)
    assert rm.status_code == 200, rm.text
    assert rm.json().get("avatar_url") in (None, "")

    me = client.get("/api/auth/me", headers=h)
    assert me.json().get("avatar_url") in (None, "")

    assert not path.exists()


def test_change_password_then_login_with_new_secret(client: TestClient):
    uid = uuid.uuid4().hex[:10]
    uname = f"pwd_{uid}"
    old_p, new_p = "OldSecret8!", "NewSecret9!"
    _seed_user(username=uname, password=old_p, real_name="P")

    h = _login(client, uname, old_p)
    ch = client.post(
        "/api/auth/change-password",
        headers=h,
        json={
            "current_password": old_p,
            "new_password": new_p,
            "confirm_password": new_p,
        },
    )
    assert ch.status_code == 200, ch.text

    bad = client.post("/api/auth/login", data={"username": uname, "password": old_p})
    assert bad.status_code == 401

    good = client.post("/api/auth/login", data={"username": uname, "password": new_p})
    assert good.status_code == 200
    h2 = _headers(good.json()["access_token"])
    me = client.get("/api/auth/me", headers=h2)
    assert me.status_code == 200
    assert me.json()["username"] == uname


def test_me_includes_avatar_url_after_upload(client: TestClient):
    uid = uuid.uuid4().hex[:10]
    uname = f"me_{uid}"
    _seed_user(username=uname, password="pw123456", real_name="M")

    h = _login(client, uname, "pw123456")
    assert client.get("/api/auth/me", headers=h).json().get("avatar_url") in (None, "")

    client.post(
        "/api/auth/me/avatar",
        headers=h,
        files={"file": ("a.png", io.BytesIO(MINIMAL_PNG), "image/png")},
    )
    me = client.get("/api/auth/me", headers=h).json()
    assert me.get("avatar_url")
