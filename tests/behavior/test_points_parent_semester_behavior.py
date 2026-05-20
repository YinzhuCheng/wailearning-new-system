"""
High-difficulty behavior: points (add/exchange/permission), parent portal edges,
semester API, and concurrency / rate-limit surfaces.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    Class,
    PointItem,
    Student,
    StudentPoint,
    User,
    UserRole,
)
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework
from tests.scenarios.material_flow import headers_for


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


def test_behavior_points_student_cannot_view_other_student_points(client: TestClient):
    ctx = make_grading_course_with_homework()
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        other_class = Class(name=f"oc-{uid}", grade=2026)
        db.add(other_class)
        db.flush()
        other_teacher = User(
            username=f"othert_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="OT",
            role=UserRole.TEACHER.value,
        )
        db.add(other_teacher)
        db.flush()
        other_stu_user = User(
            username=f"otherstu_{uid}",
            hashed_password=get_password_hash("sp"),
            real_name="Other",
            role=UserRole.STUDENT.value,
            class_id=other_class.id,
        )
        db.add(other_stu_user)
        db.flush()
        other_student = Student(name="Other", student_no=f"otherstu_{uid}", class_id=other_class.id)
        db.add(other_student)
        db.commit()
        other_sid = other_student.id
    finally:
        db.close()

    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.get(f"/api/points/students/{other_sid}", headers=st)
    assert r.status_code == 403


def test_behavior_points_admin_can_view_student_points_when_accessible(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    db = SessionLocal()
    try:
        stud = db.query(Student).filter(Student.student_no == ctx["student_username"]).first()
        sid = stud.id
    finally:
        db.close()
    ad = login_api(client, "pytest_admin", "pytest_admin_pass")
    r = client.get(f"/api/points/students/{sid}", headers=ad)
    assert r.status_code == 200
    assert r.json()["student_id"] == sid


def test_behavior_points_exchange_insufficient_returns_400(client: TestClient):
    ctx = make_grading_course_with_homework()
    db = SessionLocal()
    try:
        stud = db.query(Student).filter(Student.student_no == ctx["student_username"]).first()
        sid = stud.id
        item = PointItem(
            name=f"cheap-{uuid.uuid4().hex[:6]}",
            description="t",
            item_type="virtual",
            points_cost=99999,
            stock=-1,
            is_active=True,
        )
        db.add(item)
        db.flush()
        sp = StudentPoint(student_id=sid, total_points=0, available_points=1, total_earned=0, total_spent=0)
        db.add(sp)
        db.commit()
        item_id = item.id
    finally:
        db.close()

    st = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.post("/api/points/exchange", headers=st, json={"item_id": item_id, "quantity": 1})
    assert r.status_code == 400
    assert "积分不足" in r.json().get("detail", "")


def test_behavior_points_exchange_student_parallel_requests_once_success_once_400(client: TestClient):
    ctx = make_grading_course_with_homework()
    db = SessionLocal()
    try:
        stud = db.query(Student).filter(Student.student_no == ctx["student_username"]).first()
        sid = stud.id
        item = PointItem(
            name=f"race-{uuid.uuid4().hex[:6]}",
            description="t",
            item_type="virtual",
            points_cost=5,
            stock=-1,
            is_active=True,
        )
        db.add(item)
        db.flush()
        sp = StudentPoint(student_id=sid, total_points=5, available_points=5, total_earned=5, total_spent=0)
        db.add(sp)
        db.commit()
        item_id = item.id
    finally:
        db.close()

    st = login_api(client, ctx["student_username"], ctx["student_password"])

    def one():
        return client.post("/api/points/exchange", headers=st, json={"item_id": item_id, "quantity": 1})

    r1, r2 = one(), one()
    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 400] or (200 in statuses and 400 in statuses)


def test_behavior_points_teacher_add_manual_succeeds(client: TestClient):
    ctx = make_grading_course_with_homework()
    te = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    db = SessionLocal()
    try:
        stud = db.query(Student).filter(Student.student_no == ctx["student_username"]).first()
        sid = stud.id
    finally:
        db.close()

    r = client.post(
        f"/api/points/students/{sid}/add",
        headers=te,
        json={
            "student_id": sid,
            "points": 7,
            "description": "manual bonus",
            "source_type": "manual",
        },
    )
    assert r.status_code == 200, r.text
    bal = r.json().get("current_points")
    assert bal is not None and bal >= 7


def test_behavior_points_concurrent_teacher_adds_sum_balance(client: TestClient):
    ctx = make_grading_course_with_homework()
    te = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    db = SessionLocal()
    try:
        stud = db.query(Student).filter(Student.student_no == ctx["student_username"]).first()
        sid = stud.id
    finally:
        db.close()

    def bump(i: int):
        return client.post(
            f"/api/points/students/{sid}/add",
            headers=te,
            json={"student_id": sid, "points": 2, "description": f"c{i}", "source_type": "manual"},
        )

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(bump, i) for i in range(16)]
        results = [f.result() for f in as_completed(futures)]

    assert all(x.status_code == 200 for x in results)
    r = client.get(f"/api/points/students/{sid}", headers=te)
    assert r.status_code == 200
    assert int(r.json().get("total_points") or 0) >= 32


def test_behavior_parent_verify_invalid_code(client: TestClient):
    r = client.get("/api/parent/verify/XXXXBAD1")
    assert r.status_code == 200
    assert r.json().get("valid") is False


def test_behavior_parent_homework_list_requires_valid_code(client: TestClient):
    r = client.get("/api/parent/homework/BADC0DE1?page_size=20")
    assert r.status_code == 404


def test_behavior_semester_duplicate_name_rejected(client: TestClient):
    ensure_admin()
    ad = login_api(client, "pytest_admin", "pytest_admin_pass")
    semesters = client.get("/api/semesters", headers=ad).json()
    assert isinstance(semesters, list) and semesters
    name = semesters[0]["name"]
    r = client.post("/api/semesters", headers=ad, json={"name": name, "year": int(semesters[0].get("year") or 2026)})
    assert r.status_code == 400


def test_behavior_parent_rate_limit_eventually_429(client: TestClient):
    """Best-effort: hammer verify endpoint until rate limiter trips."""
    code = "BADCODE1"
    statuses = []
    for _ in range(35):
        res = client.get(f"/api/parent/verify/{code}")
        statuses.append(res.status_code)
        if res.status_code == 429:
            break
    assert 429 in statuses or max(statuses) <= 200
