"""
学生端「全校课程目录」与必修/选修入课策略的集成测试。

难度设计：
- 多班级、多课程交叉：目录对在读「进行中」课程全校可见；选修课 **不按行政班绑定**，未选课学生均可自主选课（前提：学生账号有对应花名册与 class_id）；
- 教师 sync-enrollments 与选修隔离：选修不得被全班同步批量写入；
- 花名册点名进选修：与自主选课 UI 字段（can_self_enroll / is_enrolled）的交互；
- CourseEnrollmentBlock：被挡的必修课不会自动补选，目录与「我的课程」一致；
- 边界：已结束课程不出现在目录。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseEnrollmentBlock,
    Gender,
    Student,
    Subject,
    SubjectClassLink,
    User,
    UserRole,
)
from tests.scenarios.llm_scenario import login_api


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "adm").first():
            db.add(
                User(
                    username="adm",
                    hashed_password=get_password_hash("a"),
                    real_name="Admin",
                    role=UserRole.ADMIN.value,
                )
            )
            db.commit()
    finally:
        db.close()
    yield
    SessionLocal().close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _admin_headers(client: TestClient) -> dict[str, str]:
    return login_api(client, "adm", "a")


def _seed_catalog_matrix(client: TestClient) -> dict:
    """
    班级甲、乙；甲班学生；课程：甲班必修、甲班选修、乙班选修、甲班已结束选修。
    """
    suf = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        ca = Class(name=f"甲班_{suf}", grade=1)
        cb = Class(name=f"乙班_{suf}", grade=1)
        db.add_all([ca, cb])
        db.flush()

        stu = User(
            username=f"stu_cat_{suf}",
            hashed_password=get_password_hash("p1"),
            real_name="甲生",
            role=UserRole.STUDENT.value,
            class_id=ca.id,
        )
        db.add(stu)
        db.flush()
        roster = Student(
            name="甲生",
            student_no=f"stu_cat_{suf}",
            gender=Gender.MALE,
            class_id=ca.id,
        )
        db.add(roster)
        db.flush()

        req = Subject(
            name=f"甲必修_{suf}",
            class_id=ca.id,
            course_type="required",
            status="active",
        )
        el_same = Subject(
            name=f"甲选修_{suf}",
            class_id=ca.id,
            course_type="elective",
            status="active",
        )
        el_other = Subject(
            name=f"乙选修_{suf}",
            class_id=cb.id,
            course_type="elective",
            status="active",
        )
        el_done = Subject(
            name=f"甲选修已结_{suf}",
            class_id=ca.id,
            course_type="elective",
            status="completed",
        )
        el_noclass = Subject(
            name=f"全校选修无班_{suf}",
            class_id=None,
            course_type="elective",
            status="active",
        )
        db.add_all([req, el_same, el_other, el_done, el_noclass])
        db.flush()

        # 甲生已在必修花名册（模拟教师已同步）
        db.add(
            CourseEnrollment(
                subject_id=req.id,
                student_id=roster.id,
                class_id=ca.id,
                enrollment_type="required",
                can_remove=False,
            )
        )
        db.commit()

        return {
            "headers": login_api(client, f"stu_cat_{suf}", "p1"),
            "req_id": req.id,
            "el_same_id": el_same.id,
            "el_other_id": el_other.id,
            "el_done_id": el_done.id,
            "el_noclass_id": el_noclass.id,
        }
    finally:
        db.close()


def test_course_catalog_matrix_visibility_and_elective_flags(client: TestClient):
    """目录应含外班与无班选修；选修未修均可自主选课；必修提示与 can_self_enroll 矩阵正确；已结束课程不出现。"""
    ctx = _seed_catalog_matrix(client)
    r = client.get("/api/subjects/course-catalog", headers=ctx["headers"])
    assert r.status_code == 200, r.text
    by_id = {row["id"]: row for row in r.json()}

    assert ctx["el_done_id"] not in by_id

    row_req = by_id[ctx["req_id"]]
    assert row_req["course_type"] == "required"
    assert row_req["is_enrolled"] is True
    assert row_req["can_self_enroll_elective"] is False
    assert "花名册" in (row_req.get("enrollment_hint") or "")

    row_same = by_id[ctx["el_same_id"]]
    assert row_same["course_type"] == "elective"
    assert row_same["is_enrolled"] is False
    assert row_same["can_self_enroll_elective"] is True
    assert "选修" in (row_same.get("enrollment_hint") or "") or "选课" in (row_same.get("enrollment_hint") or "")

    row_other = by_id[ctx["el_other_id"]]
    assert row_other["course_type"] == "elective"
    assert row_other["can_self_enroll_elective"] is True
    assert "选修" in (row_other.get("enrollment_hint") or "") or "选课" in (row_other.get("enrollment_hint") or "")

    row_nc = by_id[ctx["el_noclass_id"]]
    assert row_nc["course_type"] == "elective"
    assert row_nc["can_self_enroll_elective"] is True


def test_course_catalog_updates_after_self_enroll_and_drop(client: TestClient):
    """选课/退选后目录字段应翻转（同一会话、同一学生）。"""
    ctx = _seed_catalog_matrix(client)
    h = ctx["headers"]
    eid = ctx["el_same_id"]

    r0 = client.get("/api/subjects/course-catalog", headers=h)
    assert r0.json()
    assert next(x for x in r0.json() if x["id"] == eid)["is_enrolled"] is False

    assert client.post(f"/api/subjects/{eid}/student-self-enroll", headers=h).status_code == 200

    r1 = client.get("/api/subjects/course-catalog", headers=h)
    row = next(x for x in r1.json() if x["id"] == eid)
    assert row["is_enrolled"] is True
    assert row["can_self_enroll_elective"] is False
    assert "已选修" in (row.get("enrollment_hint") or "")

    assert client.post(f"/api/subjects/{eid}/student-self-drop", headers=h).status_code == 200

    r2 = client.get("/api/subjects/course-catalog", headers=h)
    row2 = next(x for x in r2.json() if x["id"] == eid)
    assert row2["is_enrolled"] is False
    assert row2["can_self_enroll_elective"] is True


def test_elective_excluded_from_teacher_bulk_sync_enrollments(client: TestClient):
    """教师 sync-enrollments 只批量加入必修课，不得把全班写入选修课。"""
    suf = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        klass = Class(name=f"同步班_{suf}", grade=2026)
        db.add(klass)
        db.flush()
        t = User(
            username=f"t_sync_{suf}",
            hashed_password=get_password_hash("tp"),
            real_name="同步老师",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        s1 = Student(name="生1", student_no=f"sn1_{suf}", gender=Gender.MALE, class_id=klass.id)
        s2 = Student(name="生2", student_no=f"sn2_{suf}", gender=Gender.FEMALE, class_id=klass.id)
        db.add_all([s1, s2])
        db.flush()
        req = Subject(
            name=f"同步必修_{suf}",
            teacher_id=t.id,
            class_id=klass.id,
            course_type="required",
            status="active",
        )
        el = Subject(
            name=f"同步选修_{suf}",
            teacher_id=t.id,
            class_id=klass.id,
            course_type="elective",
            status="active",
        )
        db.add_all([req, el])
        db.flush()
        db.add(
            SubjectClassLink(
                subject_id=req.id,
                class_id=klass.id,
                enrollment_mode="all_in_class",
            )
        )
        rid, eid, tid = req.id, el.id, t.id
        sid1, sid2 = s1.id, s2.id
        db.commit()
    finally:
        db.close()

    th = login_api(client, f"t_sync_{suf}", "tp")
    r = client.post(f"/api/subjects/{rid}/sync-enrollments", headers=th)
    assert r.status_code == 200, r.text
    assert r.json().get("created", 0) >= 2

    db = SessionLocal()
    try:
        n_req = (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.subject_id == rid, CourseEnrollment.student_id.in_((sid1, sid2)))
            .count()
        )
        n_el = (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.subject_id == eid, CourseEnrollment.student_id.in_((sid1, sid2)))
            .count()
        )
        assert n_req == 2
        assert n_el == 0
    finally:
        db.close()


def test_roster_enroll_one_student_elective_others_still_self_enrollable(client: TestClient):
    """教师花名册进选修：仅被选学生 is_enrolled；同班另一人仍可自主选课。"""
    suf = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        klass = Class(name=f"花名册选修班_{suf}", grade=2026)
        db.add(klass)
        db.flush()
        t = User(
            username=f"t_re_{suf}",
            hashed_password=get_password_hash("tp"),
            real_name="花老师",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        s1 = Student(name="A", student_no=f"sA_{suf}", class_id=klass.id)
        s2 = Student(name="B", student_no=f"sB_{suf}", class_id=klass.id)
        db.add_all([s1, s2])
        db.flush()
        u1 = User(
            username=f"sA_{suf}",
            hashed_password=get_password_hash("p"),
            real_name="A",
            role=UserRole.STUDENT.value,
            class_id=klass.id,
        )
        u2 = User(
            username=f"sB_{suf}",
            hashed_password=get_password_hash("p"),
            real_name="B",
            role=UserRole.STUDENT.value,
            class_id=klass.id,
        )
        db.add_all([u1, u2])
        db.flush()
        el = Subject(
            name=f"点名选修_{suf}",
            teacher_id=t.id,
            class_id=klass.id,
            course_type="elective",
            status="active",
        )
        db.add(el)
        db.flush()
        eid, tid = el.id, t.id
        db.commit()
    finally:
        db.close()

    th = login_api(client, f"t_re_{suf}", "tp")
    db = SessionLocal()
    try:
        sid1 = db.query(Student).filter(Student.student_no == f"sA_{suf}").first().id
    finally:
        db.close()

    r = client.post(
        f"/api/subjects/{eid}/roster-enroll",
        headers=th,
        json={"student_ids": [sid1]},
    )
    assert r.status_code == 200, r.json().get("created") == 1

    h1 = login_api(client, f"sA_{suf}", "p")
    h2 = login_api(client, f"sB_{suf}", "p")

    cat1 = {row["id"]: row for row in client.get("/api/subjects/course-catalog", headers=h1).json()}
    cat2 = {row["id"]: row for row in client.get("/api/subjects/course-catalog", headers=h2).json()}
    assert cat1[eid]["is_enrolled"] is True
    assert cat1[eid]["can_self_enroll_elective"] is False
    assert cat2[eid]["is_enrolled"] is False
    assert cat2[eid]["can_self_enroll_elective"] is True


def test_enrollment_block_prevents_required_auto_rejoin_and_self_enroll_fails(client: TestClient):
    """必修课被 block 后：登录同步不会偷偷加回；目录显示未在课；自主选必修仍拒绝。"""
    suf = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        klass = Class(name=f"挡课班_{suf}", grade=2026)
        db.add(klass)
        db.flush()
        stu_u = User(
            username=f"stu_blk_{suf}",
            hashed_password=get_password_hash("p"),
            real_name="被挡生",
            role=UserRole.STUDENT.value,
            class_id=klass.id,
        )
        db.add(stu_u)
        db.flush()
        roster = Student(name="被挡生", student_no=f"stu_blk_{suf}", class_id=klass.id)
        db.add(roster)
        db.flush()
        req = Subject(name=f"挡课必修_{suf}", class_id=klass.id, course_type="required", status="active")
        db.add(req)
        db.flush()
        rid = req.id
        db.add(CourseEnrollmentBlock(subject_id=rid, student_id=roster.id))
        db.commit()
    finally:
        db.close()

    h = login_api(client, f"stu_blk_{suf}", "p")
    cat = {row["id"]: row for row in client.get("/api/subjects/course-catalog", headers=h).json()}
    assert cat[rid]["is_enrolled"] is False
    assert "不可在此自主选课" in (cat[rid].get("enrollment_hint") or "")

    mine = client.get("/api/subjects", headers=h)
    assert mine.status_code == 200
    assert rid not in {c["id"] for c in mine.json()}

    assert client.post(f"/api/subjects/{rid}/student-self-enroll", headers=h).status_code == 400


def test_course_catalog_forbidden_for_non_student(client: TestClient):
    _seed_catalog_matrix(client)
    assert client.get("/api/subjects/course-catalog", headers=_admin_headers(client)).status_code == 403


def test_cross_class_elective_self_enroll_allowed_under_schoolwide_policy(client: TestClient):
    """选修课不按行政班绑定：目录可见「乙班名义」开设的选修，甲班学生仍可成功自主选课。"""
    ctx = _seed_catalog_matrix(client)
    oid = ctx["el_other_id"]
    assert oid in {row["id"] for row in client.get("/api/subjects/course-catalog", headers=ctx["headers"]).json()}
    r = client.post(f"/api/subjects/{oid}/student-self-enroll", headers=ctx["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("subject_id") == oid
    assert body.get("already_enrolled") is False
    assert body.get("created") is True
