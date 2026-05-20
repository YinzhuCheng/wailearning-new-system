"""Regression tests for ``subject_class_links`` (multi-class required courses + elective decoupling)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates, seed_default_system_settings
from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import Class, CourseEnrollment, Student, Subject, SubjectClassLink, User, UserRole
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


def _seed_admin(username: str, password: str) -> None:
    db = SessionLocal()
    try:
        db.add(
            User(
                username=username,
                hashed_password=get_password_hash(password),
                real_name=username,
                role=UserRole.ADMIN.value,
            )
        )
        db.commit()
    finally:
        db.close()


def test_required_course_two_classes_auto_enrolls_each_class_roster(client: TestClient):
    suffix = uuid.uuid4().hex[:10]
    admin_user = f"adm_mc_{suffix}"
    _seed_admin(admin_user, "pw123456")
    h = _login(client, admin_user, "pw123456")

    c1 = client.post("/api/classes", headers=h, json={"name": f"A-{suffix}", "grade": 1})
    assert c1.status_code == 200, c1.text
    id1 = c1.json()["id"]
    c2 = client.post("/api/classes", headers=h, json={"name": f"B-{suffix}", "grade": 1})
    assert c2.status_code == 200, c2.text
    id2 = c2.json()["id"]

    for cid, no in ((id1, "s1"), (id2, "s2")):
        r = client.post(
            "/api/students",
            headers=h,
            json={"name": f"stu-{no}", "student_no": no, "gender": "male", "class_id": cid},
        )
        assert r.status_code == 200, r.text

    title = f"Math-{suffix}"
    created = client.post(
        "/api/subjects",
        headers=h,
        json={
            "name": title,
            "course_type": "required",
            "status": "active",
            "class_links": [
                {"class_id": id1, "enrollment_mode": "all_in_class"},
                {"class_id": id2, "enrollment_mode": "all_in_class"},
            ],
            "course_times": [],
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]
    links = created.json().get("class_links") or []
    assert len(links) == 2

    db = SessionLocal()
    try:
        subs = db.query(Student).filter(Student.student_no.in_(["s1", "s2"])).all()
        assert len(subs) == 2
        enroll_rows = db.query(CourseEnrollment).filter(CourseEnrollment.subject_id == subject_id).all()
        assert len(enroll_rows) == 2
        class_ids = {e.class_id for e in enroll_rows}
        assert class_ids == {id1, id2}
    finally:
        db.close()


def test_delete_class_rejects_non_primary_subject_class_link(client: TestClient):
    suffix = uuid.uuid4().hex[:10]
    admin_user = f"adm_del_{suffix}"
    _seed_admin(admin_user, "pw123456")
    h = _login(client, admin_user, "pw123456")

    c1 = client.post("/api/classes", headers=h, json={"name": f"DelA-{suffix}", "grade": 1})
    c2 = client.post("/api/classes", headers=h, json={"name": f"DelB-{suffix}", "grade": 1})
    assert c1.status_code == c2.status_code == 200
    id1 = c1.json()["id"]
    id2 = c2.json()["id"]

    created = client.post(
        "/api/subjects",
        headers=h,
        json={
            "name": f"DeleteGuard-{suffix}",
            "course_type": "required",
            "status": "active",
            "class_links": [
                {"class_id": id1, "enrollment_mode": "all_in_class"},
                {"class_id": id2, "enrollment_mode": "roster_subset"},
            ],
            "course_times": [],
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["class_id"] == id1

    deleted = client.delete(f"/api/classes/{id2}", headers=h)
    assert deleted.status_code == 400
    assert "courses assigned" in deleted.json().get("detail", "")


def test_elective_create_rejects_class_binding(client: TestClient):
    suffix = uuid.uuid4().hex[:10]
    admin_user = f"adm_el_{suffix}"
    _seed_admin(admin_user, "pw123456")
    h = _login(client, admin_user, "pw123456")

    c1 = client.post("/api/classes", headers=h, json={"name": f"C-{suffix}", "grade": 1})
    assert c1.status_code == 200, c1.text
    cid = c1.json()["id"]

    bad = client.post(
        "/api/subjects",
        headers=h,
        json={
            "name": f"Elective-{suffix}",
            "course_type": "elective",
            "status": "active",
            "class_id": cid,
            "course_times": [],
        },
    )
    assert bad.status_code == 400


def test_roster_subset_link_does_not_auto_sync_whole_class(client: TestClient):
    suffix = uuid.uuid4().hex[:10]
    admin_user = f"adm_rs_{suffix}"
    _seed_admin(admin_user, "pw123456")
    h = _login(client, admin_user, "pw123456")

    c1 = client.post("/api/classes", headers=h, json={"name": f"D-{suffix}", "grade": 1})
    assert c1.status_code == 200, c1.text
    cid = c1.json()["id"]

    r = client.post(
        "/api/students",
        headers=h,
        json={"name": "solo", "student_no": "solo1", "gender": "male", "class_id": cid},
    )
    assert r.status_code == 200, r.text

    title = f"Physics-{suffix}"
    created = client.post(
        "/api/subjects",
        headers=h,
        json={
            "name": title,
            "course_type": "required",
            "status": "active",
            "class_links": [{"class_id": cid, "enrollment_mode": "roster_subset"}],
            "course_times": [],
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]

    db = SessionLocal()
    try:
        cnt = db.query(CourseEnrollment).filter(CourseEnrollment.subject_id == subject_id).count()
        assert cnt == 0
        row = db.query(SubjectClassLink).filter(SubjectClassLink.subject_id == subject_id).first()
        assert row is not None
        assert row.enrollment_mode == "roster_subset"
    finally:
        db.close()


def test_required_roster_enroll_skips_student_outside_linked_classes(client: TestClient):
    """必修课绑定 A+B 班时，C 班学生在 roster-enroll 中应计入 skipped_not_in_class_roster。"""
    suffix = uuid.uuid4().hex[:10]
    admin_user = f"adm_re_{suffix}"
    _seed_admin(admin_user, "pw123456")
    h = _login(client, admin_user, "pw123456")

    ca = client.post("/api/classes", headers=h, json={"name": f"RA-{suffix}", "grade": 1})
    cb = client.post("/api/classes", headers=h, json={"name": f"RB-{suffix}", "grade": 1})
    cc = client.post("/api/classes", headers=h, json={"name": f"RC-{suffix}", "grade": 1})
    assert ca.status_code == cb.status_code == cc.status_code == 200
    ida, idb, idc = ca.json()["id"], cb.json()["id"], cc.json()["id"]

    sr = client.post(
        "/api/students",
        headers=h,
        json={"name": "outsider", "student_no": f"out_{suffix}", "gender": "male", "class_id": idc},
    )
    assert sr.status_code == 200, sr.text
    sid = sr.json()["id"]

    title = f"Chem-{suffix}"
    cr = client.post(
        "/api/subjects",
        headers=h,
        json={
            "name": title,
            "course_type": "required",
            "status": "active",
            "class_links": [
                {"class_id": ida, "enrollment_mode": "all_in_class"},
                {"class_id": idb, "enrollment_mode": "roster_subset"},
            ],
            "course_times": [],
        },
    )
    assert cr.status_code == 200, cr.text
    sub_id = cr.json()["id"]

    rr = client.post(
        f"/api/subjects/{sub_id}/roster-enroll",
        headers=h,
        json={"student_ids": [sid]},
    )
    assert rr.status_code == 200, rr.text
    body = rr.json()
    assert body.get("created", 0) == 0
    assert body.get("skipped_not_in_class_roster", 0) >= 1


def test_get_subject_serializes_elective_class_placeholder(client: TestClient):
    """选修课序列化：班级展示占位「-」，且无 class_links。"""
    suffix = uuid.uuid4().hex[:10]
    admin_user = f"adm_g_{suffix}"
    _seed_admin(admin_user, "pw123456")
    h = _login(client, admin_user, "pw123456")

    cr = client.post(
        "/api/subjects",
        headers=h,
        json={
            "name": f"FreeElective-{suffix}",
            "course_type": "elective",
            "status": "active",
            "course_times": [],
        },
    )
    assert cr.status_code == 200, cr.text
    sub_id = cr.json()["id"]
    assert cr.json().get("class_name") == "-"
    assert cr.json().get("class_links") == []

    gr = client.get(f"/api/subjects/{sub_id}", headers=h)
    assert gr.status_code == 200, gr.text
    row = gr.json()
    assert row.get("class_name") == "-"
    assert row.get("class_id") is None
    assert row.get("class_links") == []
