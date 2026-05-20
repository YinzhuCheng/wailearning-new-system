"""POST /api/files/upload: format allow-list and content compliance."""

from __future__ import annotations

import io
import zipfile

import fitz
import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.main import app
from tests.scenarios.llm_scenario import ensure_admin, login_api


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


def _tiny_pdf_bytes() -> bytes:
    doc = fitz.open()
    doc.new_page()
    out = doc.tobytes()
    doc.close()
    return out


def test_upload_rejects_disallowed_extension(client: TestClient):
    ensure_admin()
    h = login_api(client, "pytest_admin", "pytest_admin_pass")
    r = client.post(
        "/api/files/upload",
        headers=h,
        files={"file": ("slide.pptx", b"not a real pptx", "application/octet-stream")},
    )
    assert r.status_code == 400
    assert "允许列表" in (r.json().get("detail") or "")


def test_upload_rejects_zip_without_allowed_inner(client: TestClient):
    ensure_admin()
    h = login_api(client, "pytest_admin", "pytest_admin_pass")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.bin", b"no")
    r = client.post(
        "/api/files/upload",
        headers=h,
        files={"file": ("bundle.zip", buf.getvalue(), "application/zip")},
    )
    assert r.status_code == 400
    assert "压缩包" in (r.json().get("detail") or "")


def test_upload_accepts_zip_with_pdf_inside(client: TestClient):
    ensure_admin()
    h = login_api(client, "pytest_admin", "pytest_admin_pass")
    pdf = _tiny_pdf_bytes()
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("work/hw.pdf", pdf)
    r = client.post(
        "/api/files/upload",
        headers=h,
        files={"file": ("submit.zip", zbuf.getvalue(), "application/zip")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("attachment_url")
    assert body.get("attachment_name") == "submit.zip"


def test_upload_rejects_non_utf8_text_extension(client: TestClient):
    ensure_admin()
    h = login_api(client, "pytest_admin", "pytest_admin_pass")
    r = client.post(
        "/api/files/upload",
        headers=h,
        files={"file": ("notes.md", b"\xff\xfe\x00\x00", "text/plain")},
    )
    assert r.status_code == 400
    assert "UTF-8" in (r.json().get("detail") or "")
