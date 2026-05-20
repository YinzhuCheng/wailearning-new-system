"""
高难度集成：POST /api/students/batch（与「文件导入」前端同一后端）。

覆盖：
- 混合批次：合法行 + 性别非法 + 文件内重复学号 + 库内已存在学号 → success/failed/duplicate 计数与 errors 形态；
- 管理员导入新班级名 → 自动建班 + created_classes；
- 新学生仅同步必修课选课，不因同班选修课自动入课（与 sync_student_course_enrollments 跳过 elective 一致）；
- 任课教师无权向「课程不可见」的班级导入（accessible_class_ids 边界）。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Class, CourseEnrollment, Gender, Student, Subject, SubjectClassLink, User, UserRole
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


def _admin_headers(client: TestClient) -> dict[str, str]:
    ensure_admin()
    return login_api(client, "pytest_admin", "pytest_admin_pass")


def test_batch_import_mixed_rows_counts_errors_and_duplicate_in_file(client: TestClient):
    """同一 payload：成功 1 条、文件内重复 1、性别错误 1、库内重复 1。"""
    h = _admin_headers(client)
    suf = uuid.uuid4().hex[:8]
    cname = f"导入测试班_{suf}"
    db = SessionLocal()
    try:
        k = Class(name=cname, grade=2026)
        db.add(k)
        db.flush()
        db.add(
            Student(
                name="老生",
                student_no=f"EXIST_{suf}",
                gender=Gender.MALE,
                class_id=k.id,
            )
        )
        db.commit()
        kid = k.id
    finally:
        db.close()

    payload = {
        "students": [
            {"name": "新生甲", "student_no": f"OK_{suf}", "gender": "男", "class_name": cname},
            {"name": "重复行", "student_no": f"DUP_{suf}", "gender": "女", "class_name": cname},
            {"name": "重复行2", "student_no": f"DUP_{suf}", "gender": "女", "class_name": cname},
            {"name": "坏性别", "student_no": f"BADG_{suf}", "gender": "火星人", "class_name": cname},
            {"name": "撞库", "student_no": f"EXIST_{suf}", "gender": "男", "class_name": cname},
        ]
    }
    r = client.post("/api/students/batch", headers=h, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    # OK 行 + 文件内 DUP 的第一行成功；第二行 DUP 记为文件内重复；性别错误；库内学号重复
    assert body["success"] == 2
    assert body["failed"] == 3
    assert body["duplicate"] == 2
    assert any("导入文件中重复" in e for e in body.get("errors", []))
    assert any("性别" in e for e in body.get("errors", []))
    assert any("已存在" in e for e in body.get("errors", []))

    db = SessionLocal()
    try:
        assert db.query(Student).filter(Student.student_no == f"OK_{suf}").first() is not None
    finally:
        db.close()


def test_admin_batch_import_creates_unknown_class_and_returns_created_classes(client: TestClient):
    h = _admin_headers(client)
    suf = uuid.uuid4().hex[:8]
    new_name = f"自动建班_{suf}"
    db = SessionLocal()
    try:
        assert db.query(Class).filter(Class.name == new_name).first() is None
    finally:
        db.close()

    r = client.post(
        "/api/students/batch",
        headers=h,
        json={"students": [{"name": "首生", "student_no": f"AUTO_{suf}", "gender": "男", "class_name": new_name}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["success"] == 1
    assert new_name in (r.json().get("created_classes") or [])

    db = SessionLocal()
    try:
        assert db.query(Class).filter(Class.name == new_name).first() is not None
    finally:
        db.close()


def test_new_student_batch_only_enrolls_required_courses_not_electives(client: TestClient):
    """同班同时有必修、选修时，批量新增学生只应有必修课 enrollment。"""
    h = _admin_headers(client)
    suf = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        k = Class(name=f"双课班_{suf}", grade=2026)
        db.add(k)
        db.flush()
        t = User(
            username=f"t_batch_{suf}",
            hashed_password=get_password_hash("tp"),
            real_name="老师",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        req = Subject(
            name=f"必修_{suf}",
            teacher_id=t.id,
            class_id=k.id,
            course_type="required",
            status="active",
        )
        el = Subject(
            name=f"选修_{suf}",
            teacher_id=t.id,
            class_id=k.id,
            course_type="elective",
            status="active",
        )
        db.add_all([req, el])
        db.flush()
        db.add(
            SubjectClassLink(
                subject_id=req.id,
                class_id=k.id,
                enrollment_mode="all_in_class",
            )
        )
        db.flush()
        rid, eid, kid = req.id, el.id, k.id
        db.commit()
    finally:
        db.close()

    sid = f"ONLYREQ_{suf}"
    r = client.post(
        "/api/students/batch",
        headers=h,
        json={"students": [{"name": "同步生", "student_no": sid, "gender": "女", "class_id": kid}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["success"] == 1

    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.student_no == sid).first()
        assert st is not None
        subs = {row.subject_id for row in db.query(CourseEnrollment).filter(CourseEnrollment.student_id == st.id).all()}
        assert rid in subs
        assert eid not in subs
    finally:
        db.close()


def test_teacher_cannot_batch_import_into_class_without_course_access(client: TestClient):
    """教师仅对「自己课程所属班级」有 accessible_class_ids；另一班级同名导入应整批权限失败。"""
    suf = uuid.uuid4().hex[:8]
    t_username = f"t_iso_{suf}"
    db = SessionLocal()
    try:
        k_own = Class(name=f"教师班_{suf}", grade=2026)
        k_other = Class(name=f"外班_{suf}", grade=2026)
        db.add_all([k_own, k_other])
        db.flush()
        t = User(
            username=t_username,
            hashed_password=get_password_hash("tp"),
            real_name="任课",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        db.add(
            Subject(
                name=f"唯一课_{suf}",
                teacher_id=t.id,
                class_id=k_own.id,
                course_type="required",
                status="active",
            )
        )
        db.commit()
        other_name = k_other.name
    finally:
        db.close()

    th = login_api(client, t_username, "tp")
    r = client.post(
        "/api/students/batch",
        headers=th,
        json={
            "students": [
                {"name": "非法", "student_no": f"X_{suf}", "gender": "男", "class_name": other_name},
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] == 0
    assert body["failed"] == 1
    assert any("无权" in e or "不存在" in e for e in body.get("errors", []))
