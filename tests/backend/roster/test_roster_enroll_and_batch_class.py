"""
花名册进课（POST /api/subjects/{id}/roster-enroll）与管理员批量调班（POST /api/users/batch-set-class）。

覆盖：R1–R6（权限、退选恢复+作业提交、选修类型、无班级 400、空列表）与 B1–B5（权限、混合 ID、无效班级、幂等、花名册对齐）。
UI 全链路见 frontend/e2e/roster-and-users.spec.js + app/routers/e2e_dev.py。
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
    Homework,
    Student,
    Subject,
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


def _seed_teacher_course(client: TestClient):
    suffix = "re_batch"
    db = SessionLocal()
    try:
        klass = Class(name=f"花名册班_{suffix}", grade=2026)
        db.add(klass)
        db.flush()
        t = User(
            username=f"t_{suffix}",
            hashed_password=get_password_hash("tp"),
            real_name="任课",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        s1 = Student(
            name="甲",
            student_no=f"sn1_{suffix}",
            gender=Gender.MALE,
            class_id=klass.id,
        )
        s2 = Student(
            name="乙",
            student_no=f"sn2_{suffix}",
            gender=Gender.FEMALE,
            class_id=klass.id,
        )
        other = Class(name=f"外班_{suffix}", grade=2026)
        db.add(other)
        db.flush()
        s_other = Student(
            name="外班生",
            student_no=f"snx_{suffix}",
            gender=Gender.MALE,
            class_id=other.id,
        )
        db.add_all([s1, s2, s_other])
        db.flush()
        course = Subject(
            name=f"课_{suffix}",
            teacher_id=t.id,
            class_id=klass.id,
            course_type="required",
            status="active",
        )
        db.add(course)
        db.flush()
        cid = course.id
        ids = (s1.id, s2.id, s_other.id, klass.id, t.username)
        db.commit()
    finally:
        db.close()
    th = {"Authorization": f"Bearer {client.post('/api/auth/login', data={'username': ids[4], 'password': 'tp'}).json()['access_token']}"}
    return {"th": th, "course_id": cid, "s1": ids[0], "s2": ids[1], "s_other": ids[2]}


def test_roster_enroll_only_class_roster(client: TestClient):
    ctx = _seed_teacher_course(client)
    r = client.post(
        f"/api/subjects/{ctx['course_id']}/roster-enroll",
        headers=ctx["th"],
        json={"student_ids": [ctx["s1"], ctx["s_other"], 999999]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1
    assert body["skipped_not_in_class_roster"] == 1
    assert body["skipped_not_found"] == 1

    r2 = client.post(
        f"/api/subjects/{ctx['course_id']}/roster-enroll",
        headers=ctx["th"],
        json={"student_ids": [ctx["s1"], ctx["s2"]]},
    )
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["skipped_already_enrolled"] == 1
    assert b2["created"] == 1

    db = SessionLocal()
    try:
        n = (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.subject_id == ctx["course_id"])
            .count()
        )
        assert n == 2
    finally:
        db.close()


def test_admin_batch_set_class_syncs_student_user(client: TestClient):
    suffix = "adm_bc"
    db = SessionLocal()
    try:
        k1 = Class(name=f"A_{suffix}", grade=1)
        k2 = Class(name=f"B_{suffix}", grade=1)
        db.add_all([k1, k2])
        db.flush()
        st = Student(
            name="调",
            student_no=f"u_{suffix}",
            gender=Gender.MALE,
            class_id=k1.id,
        )
        db.add(st)
        db.flush()
        u = User(
            username=st.student_no,
            hashed_password=get_password_hash("p"),
            real_name="调",
            role=UserRole.STUDENT.value,
            class_id=k1.id,
        )
        db.add(u)
        db.flush()
        uid = u.id
        k2_id = k2.id
        db.commit()
    finally:
        db.close()

    ah = login_api(client, "adm", "a")
    r = client.post(
        "/api/users/batch-set-class",
        headers=ah,
        json={"user_ids": [uid], "class_id": k2_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 1
    assert not r.json()["errors"]

    db = SessionLocal()
    try:
        u2 = db.query(User).filter(User.id == uid).first()
        st2 = db.query(Student).filter(Student.student_no == f"u_{suffix}").first()
        assert u2.class_id == k2_id
        assert st2.class_id == k2_id
    finally:
        db.close()


def test_admin_batch_set_class_moves_bound_student_when_username_differs(client: TestClient):
    suffix = "adm_bound"
    db = SessionLocal()
    try:
        k1 = Class(name=f"A_{suffix}", grade=1)
        k2 = Class(name=f"B_{suffix}", grade=1)
        db.add_all([k1, k2])
        db.flush()
        st = Student(
            name="Bound Move",
            student_no=f"real_{suffix}",
            gender=Gender.MALE,
            class_id=k1.id,
        )
        db.add(st)
        db.flush()
        u = User(
            username=f"login_{suffix}",
            hashed_password=get_password_hash("p"),
            real_name="Bound Move",
            role=UserRole.STUDENT.value,
            class_id=k1.id,
            student_id=st.id,
        )
        db.add(u)
        db.flush()
        uid = u.id
        sid = st.id
        k2_id = k2.id
        db.commit()
    finally:
        db.close()

    ah = login_api(client, "adm", "a")
    r = client.post(
        "/api/users/batch-set-class",
        headers=ah,
        json={"user_ids": [uid], "class_id": k2_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 1
    assert not r.json()["errors"]

    db = SessionLocal()
    try:
        u2 = db.query(User).filter(User.id == uid).one()
        st2 = db.query(Student).filter(Student.id == sid).one()
        assert u2.student_id == sid
        assert u2.class_id == k2_id
        assert st2.class_id == k2_id
        assert db.query(Student).filter(Student.student_no == f"login_{suffix}").count() == 1
    finally:
        db.close()


def test_roster_enroll_forbidden_for_student(client: TestClient):
    ctx = _seed_teacher_course(client)
    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.id == ctx["s1"]).first()
        u = User(
            username=f"stu_r1_{uuid.uuid4().hex[:8]}",
            hashed_password=get_password_hash("sp"),
            real_name="学生",
            role=UserRole.STUDENT.value,
            class_id=st.class_id,
        )
        db.add(u)
        db.commit()
        uname = u.username
    finally:
        db.close()
    sh = login_api(client, uname, "sp")
    r = client.post(
        f"/api/subjects/{ctx['course_id']}/roster-enroll",
        headers=sh,
        json={"student_ids": [ctx["s1"]]},
    )
    assert r.status_code == 403


def test_roster_enroll_forbidden_for_unrelated_teacher(client: TestClient):
    ctx = _seed_teacher_course(client)
    db = SessionLocal()
    try:
        t2 = User(
            username=f"t2_{uuid.uuid4().hex[:8]}",
            hashed_password=get_password_hash("tp2"),
            real_name="别班老师",
            role=UserRole.TEACHER.value,
        )
        db.add(t2)
        db.commit()
        uname = t2.username
    finally:
        db.close()
    h2 = login_api(client, uname, "tp2")
    r = client.post(
        f"/api/subjects/{ctx['course_id']}/roster-enroll",
        headers=h2,
        json={"student_ids": [ctx["s1"]]},
    )
    assert r.status_code == 403


def test_roster_enroll_after_drop_clears_enrollment_block(client: TestClient):
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        klass = Class(name=f"班R3_{suffix}", grade=2026)
        db.add(klass)
        db.flush()
        t = User(
            username=f"tr3_{suffix}",
            hashed_password=get_password_hash("tp"),
            real_name="教师R3",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        st = Student(
            name="退选恢复",
            student_no=f"sr3_{suffix}",
            gender=Gender.MALE,
            class_id=klass.id,
        )
        db.add(st)
        db.flush()
        course = Subject(
            name=f"课R3_{suffix}",
            teacher_id=t.id,
            class_id=klass.id,
            course_type="required",
            status="active",
        )
        db.add(course)
        db.flush()
        enr = CourseEnrollment(
            subject_id=course.id,
            student_id=st.id,
            class_id=klass.id,
            enrollment_type="required",
            can_remove=False,
        )
        db.add(enr)
        db.flush()
        hw = Homework(
            title="作业R3",
            content="c",
            class_id=klass.id,
            subject_id=course.id,
            max_score=100,
            grade_precision="integer",
            auto_grading_enabled=False,
            allow_late_submission=True,
            late_submission_affects_score=False,
            created_by=t.id,
        )
        db.add(hw)
        db.flush()
        cid, sid, stid, hwid, tuname, klass_id = course.id, st.id, st.id, hw.id, t.username, klass.id
        db.commit()
    finally:
        db.close()

    th = login_api(client, tuname, "tp")
    assert client.delete(f"/api/subjects/{cid}/students/{sid}", headers=th).status_code == 200

    db = SessionLocal()
    try:
        assert db.query(CourseEnrollment).filter(CourseEnrollment.subject_id == cid, CourseEnrollment.student_id == stid).first() is None
        blk = (
            db.query(CourseEnrollmentBlock)
            .filter(CourseEnrollmentBlock.subject_id == cid, CourseEnrollmentBlock.student_id == stid)
            .first()
        )
        assert blk is not None
    finally:
        db.close()

    r = client.post(f"/api/subjects/{cid}/roster-enroll", headers=th, json={"student_ids": [stid]})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1

    db = SessionLocal()
    try:
        en = db.query(CourseEnrollment).filter(CourseEnrollment.subject_id == cid, CourseEnrollment.student_id == stid).first()
        assert en is not None
        blk2 = (
            db.query(CourseEnrollmentBlock)
            .filter(CourseEnrollmentBlock.subject_id == cid, CourseEnrollmentBlock.student_id == stid)
            .first()
        )
        assert blk2 is None
    finally:
        db.close()

    stu = User(
        username=f"sr3_{suffix}",
        hashed_password=get_password_hash("sp"),
        real_name="退选恢复",
        role=UserRole.STUDENT.value,
        class_id=klass_id,
    )
    db = SessionLocal()
    try:
        db.add(stu)
        db.commit()
    finally:
        db.close()
    sh = login_api(client, f"sr3_{suffix}", "sp")
    r_sub = client.post(f"/api/homeworks/{hwid}/submission", headers=sh, json={"content": "ok"})
    assert r_sub.status_code == 200, r_sub.text


def test_roster_enroll_elective_course_sets_enrollment_flags(client: TestClient):
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        klass = Class(name=f"班R4_{suffix}", grade=2026)
        db.add(klass)
        db.flush()
        t = User(
            username=f"tr4_{suffix}",
            hashed_password=get_password_hash("tp"),
            real_name="教师R4",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        st = Student(
            name="选修生",
            student_no=f"sr4_{suffix}",
            gender=Gender.FEMALE,
            class_id=klass.id,
        )
        db.add(st)
        db.flush()
        course = Subject(
            name=f"选修课_{suffix}",
            teacher_id=t.id,
            class_id=klass.id,
            course_type="elective",
            status="active",
        )
        db.add(course)
        db.flush()
        cid, stid, tuname = course.id, st.id, t.username
        db.commit()
    finally:
        db.close()

    th = login_api(client, tuname, "tp")
    r = client.post(f"/api/subjects/{cid}/roster-enroll", headers=th, json={"student_ids": [stid]})
    assert r.status_code == 200
    assert r.json()["created"] == 1

    db = SessionLocal()
    try:
        en = db.query(CourseEnrollment).filter(CourseEnrollment.subject_id == cid, CourseEnrollment.student_id == stid).first()
        assert en.enrollment_type == "elective"
        assert en.can_remove is True
    finally:
        db.close()


def test_roster_enroll_rejects_when_course_has_no_class(client: TestClient):
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        t = User(
            username=f"tnoclass_{suffix}",
            hashed_password=get_password_hash("tp"),
            real_name="教师无班课",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        course = Subject(
            name=f"孤儿课_{suffix}",
            teacher_id=t.id,
            class_id=None,
            course_type="required",
            status="active",
        )
        db.add(course)
        db.flush()
        cid, tuname = course.id, t.username
        db.commit()
    finally:
        db.close()

    th = login_api(client, tuname, "tp")
    r = client.post(f"/api/subjects/{cid}/roster-enroll", headers=th, json={"student_ids": [1]})
    assert r.status_code == 400


def test_roster_enroll_empty_student_ids_is_noop(client: TestClient):
    ctx = _seed_teacher_course(client)
    r = client.post(
        f"/api/subjects/{ctx['course_id']}/roster-enroll",
        headers=ctx["th"],
        json={"student_ids": []},
    )
    assert r.status_code == 200
    b = r.json()
    assert b["created"] == 0
    assert b["skipped_already_enrolled"] == 0
    assert b["skipped_not_in_class_roster"] == 0
    assert b["skipped_not_found"] == 0


def test_batch_set_class_forbidden_for_non_admin(client: TestClient):
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        k = Class(name=f"班B1_{suffix}", grade=1)
        db.add(k)
        db.flush()
        t = User(
            username=f"tb1_{suffix}",
            hashed_password=get_password_hash("tp"),
            real_name="老师",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        st = Student(
            name="S",
            student_no=f"sb1_{suffix}",
            gender=Gender.MALE,
            class_id=k.id,
        )
        db.add(st)
        db.flush()
        u = User(
            username=st.student_no,
            hashed_password=get_password_hash("sp"),
            real_name="S",
            role=UserRole.STUDENT.value,
            class_id=k.id,
        )
        db.add(u)
        db.flush()
        uid, kid = u.id, k.id
        db.commit()
    finally:
        db.close()

    th = login_api(client, f"tb1_{suffix}", "tp")
    r = client.post("/api/users/batch-set-class", headers=th, json={"user_ids": [uid], "class_id": kid})
    assert r.status_code == 403


def test_batch_set_class_mixed_student_and_teacher_ids(client: TestClient):
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        k1 = Class(name=f"K1_{suffix}", grade=1)
        k2 = Class(name=f"K2_{suffix}", grade=1)
        db.add_all([k1, k2])
        db.flush()
        t = User(
            username=f"teacher_b2_{suffix}",
            hashed_password=get_password_hash("tp"),
            real_name="老师B2",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        st = Student(
            name="学生B2",
            student_no=f"sb2_{suffix}",
            gender=Gender.MALE,
            class_id=k1.id,
        )
        db.add(st)
        db.flush()
        u = User(
            username=st.student_no,
            hashed_password=get_password_hash("sp"),
            real_name="学生B2",
            role=UserRole.STUDENT.value,
            class_id=k1.id,
        )
        db.add(u)
        db.flush()
        uid_s, uid_t, k2id = u.id, t.id, k2.id
        db.commit()
    finally:
        db.close()

    ah = login_api(client, "adm", "a")
    r = client.post(
        "/api/users/batch-set-class",
        headers=ah,
        json={"user_ids": [uid_s, uid_t], "class_id": k2id},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["user_id"] == uid_t


def test_batch_set_class_rejects_invalid_class_id(client: TestClient):
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        k = Class(name=f"KB3_{suffix}", grade=1)
        db.add(k)
        db.flush()
        st = Student(
            name="SB3",
            student_no=f"sb3_{suffix}",
            gender=Gender.MALE,
            class_id=k.id,
        )
        db.add(st)
        db.flush()
        u = User(
            username=st.student_no,
            hashed_password=get_password_hash("sp"),
            real_name="SB3",
            role=UserRole.STUDENT.value,
            class_id=k.id,
        )
        db.add(u)
        db.flush()
        uid = u.id
        db.commit()
    finally:
        db.close()

    ah = login_api(client, "adm", "a")
    r = client.post(
        "/api/users/batch-set-class",
        headers=ah,
        json={"user_ids": [uid], "class_id": 999999999},
    )
    assert r.status_code == 400


def test_batch_set_class_idempotent_when_already_in_target_class(client: TestClient):
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        k = Class(name=f"KB4_{suffix}", grade=1)
        db.add(k)
        db.flush()
        st = Student(
            name="SB4",
            student_no=f"sb4_{suffix}",
            gender=Gender.MALE,
            class_id=k.id,
        )
        db.add(st)
        db.flush()
        u = User(
            username=st.student_no,
            hashed_password=get_password_hash("sp"),
            real_name="SB4",
            role=UserRole.STUDENT.value,
            class_id=k.id,
        )
        db.add(u)
        db.flush()
        uid, kid = u.id, k.id
        db.commit()
    finally:
        db.close()

    ah = login_api(client, "adm", "a")
    r = client.post("/api/users/batch-set-class", headers=ah, json={"user_ids": [uid], "class_id": kid})
    assert r.status_code == 200
    assert r.json()["updated"] == 0


def test_batch_set_class_aligns_roster_when_mismatched_with_user(client: TestClient):
    """花名册在 k1，账号误在 k2；批量调到 k1 后二者一致。"""
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        k1 = Class(name=f"KB5a_{suffix}", grade=1)
        k2 = Class(name=f"KB5b_{suffix}", grade=1)
        db.add_all([k1, k2])
        db.flush()
        st = Student(
            name="错位",
            student_no=f"sb5_{suffix}",
            gender=Gender.MALE,
            class_id=k1.id,
        )
        db.add(st)
        db.flush()
        u = User(
            username=st.student_no,
            hashed_password=get_password_hash("sp"),
            real_name="错位",
            role=UserRole.STUDENT.value,
            class_id=k2.id,
        )
        db.add(u)
        db.flush()
        uid, k1id = u.id, k1.id
        db.commit()
    finally:
        db.close()

    ah = login_api(client, "adm", "a")
    assert client.post("/api/users/batch-set-class", headers=ah, json={"user_ids": [uid], "class_id": k1id}).status_code == 200

    db = SessionLocal()
    try:
        st2 = db.query(Student).filter(Student.student_no == f"sb5_{suffix}").first()
        u2 = db.query(User).filter(User.id == uid).first()
        assert st2.class_id == k1id
        assert u2.class_id == k1id
    finally:
        db.close()
