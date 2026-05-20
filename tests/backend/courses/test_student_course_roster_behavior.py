"""
行为测试：花名册 / 选课 / 作业提交 / 教师端人数 的一致性。

反思（为何「能看课却不能交作业」曾不易暴露）：
1. 测试数据常为「理想全套」，缺少只满足账号或只满足花名册其一的状态。
2. 若课程列表用「班级内全部课程」并集、而提交用「选课表」，两套规则分叉时仍可能 HTTP 200。
3. 教师端 student_count 与名单接口若未对账，人数为 0 或不一致也不易发现。
4. 学生端列表与详情都走「选课 + 花名册同班」时，单测若只断言列表为空，仍漏掉「详情 403 / 提交 404」等路径。
5. 退选后若仅删 CourseEnrollment 而不记 block，prepare 会在下次登录把人选回去，问题看起来像「偶发又能交了」。
6. 教师用「同步选课」把花名册与选课表对齐是运维上的合法恢复手段，应对 CourseEnrollmentBlock 清掉并允许再次提交。

以下用例覆盖运营顺序、学号与用户名不一致、跨班作业、教师移除选课后不得被登录同步悄悄恢复、同步选课后的有意恢复、同班重复学号等场景。
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
    HomeworkSubmission,
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
    _ensure_admin()
    yield
    SessionLocal().close()


def _ensure_admin():
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


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _teacher_and_class(client: TestClient) -> dict:
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        klass = Class(name=f"行为班_{suffix}", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username=f"tchr_{suffix}",
            hashed_password=get_password_hash("tp"),
            real_name="任课教师",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        course = Subject(
            name=f"行为课_{suffix}",
            teacher_id=teacher.id,
            class_id=klass.id,
            course_type="required",
            status="active",
        )
        db.add(course)
        db.flush()
        db.add(
            SubjectClassLink(
                subject_id=course.id,
                class_id=klass.id,
                enrollment_mode="all_in_class",
            )
        )
        db.commit()
        return {
            "suffix": suffix,
            "class_id": klass.id,
            "teacher_username": teacher.username,
            "teacher_password": "tp",
            "course_id": course.id,
        }
    finally:
        db.close()


def test_student_sees_course_only_when_rules_satisfied(client: TestClient):
    """Student login repairs same-class roster drift and exposes required courses."""
    ctx = _teacher_and_class(client)
    db = SessionLocal()
    try:
        stu = User(
            username=f"stu_vis_{ctx['suffix']}",
            hashed_password=get_password_hash("sp"),
            real_name="无花名册学生",
            role=UserRole.STUDENT.value,
            class_id=ctx["class_id"],
        )
        db.add(stu)
        db.commit()
        stu_username = stu.username
    finally:
        db.close()

    h = login_api(client, stu_username, "sp")
    r = client.get("/api/subjects", headers=h)
    assert r.status_code == 200
    assert ctx["course_id"] in {item["id"] for item in r.json()}

    r2 = client.get(f"/api/subjects/{ctx['course_id']}", headers=h)
    assert r2.status_code == 200

    db = SessionLocal()
    try:
        roster = (
            db.query(Student)
            .filter(Student.student_no == stu_username, Student.class_id == ctx["class_id"])
            .first()
        )
        assert roster is not None
        assert (
            db.query(CourseEnrollment)
            .filter(
                CourseEnrollment.student_id == roster.id,
                CourseEnrollment.subject_id == ctx["course_id"],
            )
            .first()
            is not None
        )
    finally:
        db.close()


def test_homework_submit_after_course_created_then_roster_added(client: TestClient):
    """先有课程与账号，后补花名册：提交前应自动具备 CourseEnrollment。"""
    ctx = _teacher_and_class(client)
    stu_no = f"stu_roster_{ctx['suffix']}"
    db = SessionLocal()
    try:
        stu_user = User(
            username=stu_no,
            hashed_password=get_password_hash("sp"),
            real_name="后补花名册",
            role=UserRole.STUDENT.value,
            class_id=ctx["class_id"],
        )
        db.add(stu_user)
        db.flush()
        hw = Homework(
            title="行为作业",
            content="x",
            class_id=ctx["class_id"],
            subject_id=ctx["course_id"],
            max_score=100,
            grade_precision="integer",
            auto_grading_enabled=False,
            allow_late_submission=True,
            late_submission_affects_score=False,
            created_by=db.query(User).filter(User.username == ctx["teacher_username"]).first().id,
        )
        db.add(hw)
        db.commit()
        hw_id = hw.id
    finally:
        db.close()

    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r_roster = client.post(
        "/api/students",
        headers=th,
        json={
            "name": "后补花名册",
            "student_no": stu_no,
            "gender": "male",
            "class_id": ctx["class_id"],
        },
    )
    assert r_roster.status_code == 200, r_roster.text

    sh = login_api(client, stu_no, "sp")
    r_sub = client.post(
        f"/api/homeworks/{hw_id}/submission",
        headers=sh,
        json={"content": "answer"},
    )
    assert r_sub.status_code == 200, r_sub.text


def test_teacher_student_count_matches_course_enrollment_rows(client: TestClient):
    """GET /api/subjects 的 student_count 与 GET /api/subjects/{id}/students 条数一致。"""
    ctx = _teacher_and_class(client)
    db = SessionLocal()
    try:
        st = Student(
            name="名单一人",
            student_no=f"sn_{ctx['suffix']}",
            gender=Gender.MALE,
            class_id=ctx["class_id"],
        )
        db.add(st)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=ctx["course_id"],
                student_id=st.id,
                class_id=ctx["class_id"],
                enrollment_type="required",
                can_remove=False,
            )
        )
        db.commit()
    finally:
        db.close()

    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r_list = client.get("/api/subjects", headers=th)
    assert r_list.status_code == 200
    row = next(item for item in r_list.json() if item["id"] == ctx["course_id"])
    r_students = client.get(f"/api/subjects/{ctx['course_id']}/students", headers=th)
    assert r_students.status_code == 200
    assert row["student_count"] == len(r_students.json())


def test_student_username_mismatch_uses_explicit_student_binding_for_submission(client: TestClient):
    """A student account no longer needs username == student_no when it is bound to Student."""
    ctx = _teacher_and_class(client)
    db = SessionLocal()
    try:
        st = Student(
            name="王五",
            student_no=f"roster_no_{ctx['suffix']}",
            gender=Gender.MALE,
            class_id=ctx["class_id"],
        )
        db.add(st)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=ctx["course_id"],
                student_id=st.id,
                class_id=ctx["class_id"],
                enrollment_type="required",
                can_remove=False,
            )
        )
        stu_user = User(
            username=f"login_mismatch_{ctx['suffix']}",
            hashed_password=get_password_hash("sp"),
            real_name="王五",
            role=UserRole.STUDENT.value,
            class_id=ctx["class_id"],
            student_id=st.id,
        )
        db.add(stu_user)
        db.flush()
        hw = Homework(
            title="作业",
            content="c",
            class_id=ctx["class_id"],
            subject_id=ctx["course_id"],
            max_score=100,
            grade_precision="integer",
            auto_grading_enabled=False,
            allow_late_submission=True,
            late_submission_affects_score=False,
            created_by=db.query(User).filter(User.username == ctx["teacher_username"]).first().id,
        )
        db.add(hw)
        db.commit()
        hw_id = hw.id
        login_username = stu_user.username
    finally:
        db.close()

    h = login_api(client, login_username, "sp")
    r = client.post(f"/api/homeworks/{hw_id}/submission", headers=h, json={"content": "x"})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        original_roster = (
            db.query(Student)
            .filter(Student.student_no == f"roster_no_{ctx['suffix']}", Student.class_id == ctx["class_id"])
            .first()
        )
        assert original_roster is not None
        assert db.query(Student).filter(Student.student_no == login_username).count() == 0
        assert (
            db.query(HomeworkSubmission)
            .filter(HomeworkSubmission.homework_id == hw_id, HomeworkSubmission.student_id == original_roster.id)
            .first()
            is not None
        )
    finally:
        db.close()


def test_student_user_class_set_but_no_roster_row(client: TestClient):
    """A student user with class_id but no roster row is repaired on login."""
    ctx = _teacher_and_class(client)
    db = SessionLocal()
    try:
        stu = User(
            username=f"no_roster_{ctx['suffix']}",
            hashed_password=get_password_hash("sp"),
            real_name="无花名册",
            role=UserRole.STUDENT.value,
            class_id=ctx["class_id"],
        )
        db.add(stu)
        db.commit()
        no_roster_username = stu.username
    finally:
        db.close()

    h = login_api(client, no_roster_username, "sp")
    r = client.get("/api/subjects", headers=h)
    assert r.status_code == 200
    assert ctx["course_id"] in {item["id"] for item in r.json()}

    db = SessionLocal()
    try:
        roster = (
            db.query(Student)
            .filter(Student.student_no == no_roster_username, Student.class_id == ctx["class_id"])
            .first()
        )
        assert roster is not None
        assert (
            db.query(CourseEnrollment)
            .filter(
                CourseEnrollment.student_id == roster.id,
                CourseEnrollment.subject_id == ctx["course_id"],
            )
            .first()
            is not None
        )
    finally:
        db.close()


def test_duplicate_student_no_across_classes_prepare_does_not_move_roster(client: TestClient):
    """同一学号两条花名册不同班：prepare 不得误迁（ambiguous，不移动）。"""
    from apps.backend.courseeval_backend.domains.courses.access import (
        prepare_student_course_context,
    )

    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        ka = Class(name=f"dupA_{suffix}", grade=1)
        kb = Class(name=f"dupB_{suffix}", grade=1)
        db.add_all([ka, kb])
        db.flush()
        shared_no = f"dup_{suffix}"
        st_a = Student(name="甲", student_no=shared_no, gender=Gender.MALE, class_id=ka.id)
        st_b = Student(name="乙", student_no=shared_no, gender=Gender.MALE, class_id=kb.id)
        db.add_all([st_a, st_b])
        course_a = Subject(name=f"课A_{suffix}", class_id=ka.id, course_type="required", status="active")
        db.add(course_a)
        db.flush()
        db.add(
            SubjectClassLink(
                subject_id=course_a.id,
                class_id=ka.id,
                enrollment_mode="all_in_class",
            )
        )
        user = User(
            username=shared_no,
            hashed_password="x",
            real_name="甲",
            role=UserRole.STUDENT.value,
            class_id=ka.id,
        )
        db.add(user)
        db.commit()
        prepare_student_course_context(user, db)
        db.commit()
        db.refresh(st_a)
        db.refresh(st_b)
        assert st_a.class_id == ka.id
        assert st_b.class_id == kb.id
    finally:
        db.close()


def test_homework_class_id_differs_from_student_roster_class(client: TestClient):
    """作业挂在班级 A，花名册在班 B：提交失败且提示与班级一致。"""
    ctx = _teacher_and_class(client)
    db = SessionLocal()
    try:
        klass_b = Class(name=f"另一班_{ctx['suffix']}", grade=2026)
        db.add(klass_b)
        db.flush()
        st = Student(
            name="跨班",
            student_no=f"cross_{ctx['suffix']}",
            gender=Gender.MALE,
            class_id=klass_b.id,
        )
        db.add(st)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=ctx["course_id"],
                student_id=st.id,
                class_id=ctx["class_id"],
                enrollment_type="required",
                can_remove=False,
            )
        )
        stu = User(
            username=st.student_no,
            hashed_password=get_password_hash("sp"),
            real_name="跨班",
            role=UserRole.STUDENT.value,
            class_id=klass_b.id,
        )
        db.add(stu)
        db.flush()
        tid = db.query(User).filter(User.username == ctx["teacher_username"]).first().id
        hw = Homework(
            title="跨班作业",
            content="c",
            class_id=ctx["class_id"],
            subject_id=ctx["course_id"],
            max_score=100,
            grade_precision="integer",
            auto_grading_enabled=False,
            allow_late_submission=True,
            late_submission_affects_score=False,
            created_by=tid,
        )
        db.add(hw)
        db.commit()
        hw_id = hw.id
        cross_student_no = st.student_no
    finally:
        db.close()

    h = login_api(client, cross_student_no, "sp")
    r = client.post(f"/api/homeworks/{hw_id}/submission", headers=h, json={"content": "x"})
    assert r.status_code == 404
    assert "班级" in r.json().get("detail", "")


def test_admin_user_class_change_triggers_enrollment_sync(client: TestClient):
    """管理员修改学生 class_id 后，新课程班级下应出现选课。"""
    ctx = _teacher_and_class(client)
    db = SessionLocal()
    try:
        klass2 = Class(name=f"二班_{ctx['suffix']}", grade=2026)
        db.add(klass2)
        db.flush()
        st = Student(
            name="调班生",
            student_no=f"move_adm_{ctx['suffix']}",
            gender=Gender.MALE,
            class_id=ctx["class_id"],
        )
        db.add(st)
        db.flush()
        course2 = Subject(
            name=f"二班课_{ctx['suffix']}",
            teacher_id=db.query(User).filter(User.username == ctx["teacher_username"]).first().id,
            class_id=klass2.id,
            course_type="required",
            status="active",
        )
        db.add(course2)
        db.flush()
        db.add(
            SubjectClassLink(
                subject_id=course2.id,
                class_id=klass2.id,
                enrollment_mode="all_in_class",
            )
        )
        stu = User(
            username=st.student_no,
            hashed_password=get_password_hash("sp"),
            real_name="调班生",
            role=UserRole.STUDENT.value,
            class_id=ctx["class_id"],
        )
        db.add(stu)
        db.commit()
        stu_id = stu.id
        roster_student_id = st.id
        c2_id = course2.id
        klass2_id = klass2.id
    finally:
        db.close()

    ah = login_api(client, "adm", "a")
    r = client.put(f"/api/users/{stu_id}", headers=ah, json={"class_id": klass2_id})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        enr = (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.student_id == roster_student_id, CourseEnrollment.subject_id == c2_id)
            .first()
        )
        assert enr is not None
    finally:
        db.close()


def test_student_removed_from_course_enrollment_cannot_submit_and_stays_removed(client: TestClient):
    """教师移除选课后不能再提交；学生再次登录也不得被自动同步加回。"""
    ctx = _teacher_and_class(client)
    db = SessionLocal()
    try:
        st = Student(
            name="被退选",
            student_no=f"drop_{ctx['suffix']}",
            gender=Gender.MALE,
            class_id=ctx["class_id"],
        )
        db.add(st)
        db.flush()
        enr = CourseEnrollment(
            subject_id=ctx["course_id"],
            student_id=st.id,
            class_id=ctx["class_id"],
            enrollment_type="required",
            can_remove=False,
        )
        db.add(enr)
        stu = User(
            username=st.student_no,
            hashed_password=get_password_hash("sp"),
            real_name="被退选",
            role=UserRole.STUDENT.value,
            class_id=ctx["class_id"],
        )
        db.add(stu)
        db.flush()
        tid = db.query(User).filter(User.username == ctx["teacher_username"]).first().id
        hw = Homework(
            title="退选作业",
            content="c",
            class_id=ctx["class_id"],
            subject_id=ctx["course_id"],
            max_score=100,
            grade_precision="integer",
            auto_grading_enabled=False,
            allow_late_submission=True,
            late_submission_affects_score=False,
            created_by=tid,
        )
        db.add(hw)
        db.commit()
        hw_id = hw.id
        st_id = st.id
        drop_student_no = st.student_no
    finally:
        db.close()

    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r_del = client.delete(f"/api/subjects/{ctx['course_id']}/students/{st_id}", headers=th)
    assert r_del.status_code == 200, r_del.text

    sh = login_api(client, drop_student_no, "sp")
    r_sub = client.post(f"/api/homeworks/{hw_id}/submission", headers=sh, json={"content": "x"})
    assert r_sub.status_code == 403

    client.post("/api/auth/login", data={"username": drop_student_no, "password": "sp"})
    db = SessionLocal()
    try:
        again = (
            db.query(CourseEnrollment)
            .filter(
                CourseEnrollment.subject_id == ctx["course_id"],
                CourseEnrollment.student_id == st_id,
            )
            .first()
        )
        assert again is None
    finally:
        db.close()


def test_batch_import_students_existing_course_all_get_enrollment(client: TestClient):
    """课已存在时批量导入进班：每人生成 CourseEnrollment。"""
    ctx = _teacher_and_class(client)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.post(
        "/api/students/batch",
        headers=th,
        json={
            "students": [
                {
                    "name": "导入一",
                    "student_no": f"imp1_{ctx['suffix']}",
                    "gender": "male",
                    "class_name": None,
                    "class_id": ctx["class_id"],
                },
                {
                    "name": "导入二",
                    "student_no": f"imp2_{ctx['suffix']}",
                    "gender": "female",
                    "class_id": ctx["class_id"],
                },
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["success"] == 2

    db = SessionLocal()
    try:
        for no in (f"imp1_{ctx['suffix']}", f"imp2_{ctx['suffix']}"):
            st = db.query(Student).filter(Student.student_no == no).first()
            assert st is not None
            enr = (
                db.query(CourseEnrollment)
                .filter(CourseEnrollment.student_id == st.id, CourseEnrollment.subject_id == ctx["course_id"])
                .first()
            )
            assert enr is not None
    finally:
        db.close()


def test_public_register_student_immediately_gets_roster_enrollments_and_quota(client: TestClient, monkeypatch):
    """公开注册学生后，无需再补学生管理花名册，也应直接获得本班课程上下文与额度视图。"""
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    from apps.backend.courseeval_backend.core.config import settings

    monkeypatch.setattr(settings, "ALLOW_PUBLIC_REGISTRATION", True)

    ctx = _teacher_and_class(client)
    reg_no = f"reg_{ctx['suffix']}"
    r = client.post(
        "/api/auth/register",
        json={
            "username": reg_no,
            "password": "rp",
            "real_name": "自注册",
            "role": "student",
            "class_id": ctx["class_id"],
        },
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.student_no == reg_no, Student.class_id == ctx["class_id"]).first()
        assert st is not None
    finally:
        db.close()

    sh = login_api(client, reg_no, "rp")
    r_list = client.get("/api/subjects", headers=sh)
    assert r_list.status_code == 200
    assert ctx["course_id"] in {item["id"] for item in r_list.json()}
    quota = client.get("/api/llm-settings/courses/student-quotas", headers=sh)
    assert quota.status_code == 200, quota.text
    assert quota.json().get("daily_student_token_limit") is not None


def test_get_homework_list_for_student_submission_map_consistent(client: TestClient):
    """学生作业列表仅包含有权限的班级作业；提交映射与花名册一致时才可交。"""
    ctx = _teacher_and_class(client)
    db = SessionLocal()
    try:
        klass_b = Class(name=f"列表班B_{ctx['suffix']}", grade=2026)
        db.add(klass_b)
        db.flush()
        st = Student(
            name="列表生",
            student_no=f"liststu_{ctx['suffix']}",
            gender=Gender.MALE,
            class_id=ctx["class_id"],
        )
        db.add(st)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=ctx["course_id"],
                student_id=st.id,
                class_id=ctx["class_id"],
                enrollment_type="required",
                can_remove=False,
            )
        )
        stu = User(
            username=st.student_no,
            hashed_password=get_password_hash("sp"),
            real_name="列表生",
            role=UserRole.STUDENT.value,
            class_id=ctx["class_id"],
        )
        db.add(stu)
        tid = db.query(User).filter(User.username == ctx["teacher_username"]).first().id
        hw_ok = Homework(
            title="本班作业",
            content="c",
            class_id=ctx["class_id"],
            subject_id=ctx["course_id"],
            max_score=100,
            grade_precision="integer",
            auto_grading_enabled=False,
            allow_late_submission=True,
            late_submission_affects_score=False,
            created_by=tid,
        )
        course_b = Subject(
            name=f"另一门课_{ctx['suffix']}",
            teacher_id=tid,
            class_id=klass_b.id,
            course_type="required",
            status="active",
        )
        db.add_all([hw_ok, course_b])
        db.flush()
        db.add(
            SubjectClassLink(
                subject_id=course_b.id,
                class_id=klass_b.id,
                enrollment_mode="all_in_class",
            )
        )
        hw_other = Homework(
            title="他班作业",
            content="c",
            class_id=klass_b.id,
            subject_id=course_b.id,
            max_score=100,
            grade_precision="integer",
            auto_grading_enabled=False,
            allow_late_submission=True,
            late_submission_affects_score=False,
            created_by=tid,
        )
        db.add(hw_other)
        db.commit()
        hw_ok_id = hw_ok.id
        hw_other_id = hw_other.id
        list_student_no = st.student_no
    finally:
        db.close()

    sh = login_api(client, list_student_no, "sp")
    r_hw = client.get("/api/homeworks", headers=sh)
    assert r_hw.status_code == 200
    ids = {item["id"] for item in r_hw.json()["data"]}
    assert hw_ok_id in ids
    assert hw_other_id not in ids

    r_ok = client.post(f"/api/homeworks/{hw_ok_id}/submission", headers=sh, json={"content": "ok"})
    assert r_ok.status_code == 200, r_ok.text

    r_bad = client.post(f"/api/homeworks/{hw_other_id}/submission", headers=sh, json={"content": "no"})
    assert r_bad.status_code in (403, 404)


def test_teacher_sync_enrollments_after_drop_clears_block_and_allows_submit(client: TestClient):
    """教师从课程退选后 block 生效；教师「同步选课」应清 block 并恢复选课，学生可再次提交。"""
    ctx = _teacher_and_class(client)
    db = SessionLocal()
    try:
        st = Student(
            name="同步恢复",
            student_no=f"sync_{ctx['suffix']}",
            gender=Gender.MALE,
            class_id=ctx["class_id"],
        )
        db.add(st)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=ctx["course_id"],
                student_id=st.id,
                class_id=ctx["class_id"],
                enrollment_type="required",
                can_remove=False,
            )
        )
        stu = User(
            username=st.student_no,
            hashed_password=get_password_hash("sp"),
            real_name="同步恢复",
            role=UserRole.STUDENT.value,
            class_id=ctx["class_id"],
        )
        db.add(stu)
        db.flush()
        tid = db.query(User).filter(User.username == ctx["teacher_username"]).first().id
        hw = Homework(
            title="同步作业",
            content="c",
            class_id=ctx["class_id"],
            subject_id=ctx["course_id"],
            max_score=100,
            grade_precision="integer",
            auto_grading_enabled=False,
            allow_late_submission=True,
            late_submission_affects_score=False,
            created_by=tid,
        )
        db.add(hw)
        db.commit()
        hw_id = hw.id
        st_id = st.id
        sync_no = st.student_no
    finally:
        db.close()

    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    assert client.delete(f"/api/subjects/{ctx['course_id']}/students/{st_id}", headers=th).status_code == 200

    db = SessionLocal()
    try:
        assert (
            db.query(CourseEnrollmentBlock)
            .filter(
                CourseEnrollmentBlock.subject_id == ctx["course_id"],
                CourseEnrollmentBlock.student_id == st_id,
            )
            .first()
            is not None
        )
    finally:
        db.close()

    r_sync = client.post(f"/api/subjects/{ctx['course_id']}/sync-enrollments", headers=th)
    assert r_sync.status_code == 200, r_sync.text

    db = SessionLocal()
    try:
        assert (
            db.query(CourseEnrollmentBlock)
            .filter(
                CourseEnrollmentBlock.subject_id == ctx["course_id"],
                CourseEnrollmentBlock.student_id == st_id,
            )
            .first()
            is None
        )
        assert (
            db.query(CourseEnrollment)
            .filter(
                CourseEnrollment.subject_id == ctx["course_id"],
                CourseEnrollment.student_id == st_id,
            )
            .first()
            is not None
        )
    finally:
        db.close()

    sh = login_api(client, sync_no, "sp")
    r_sub = client.post(f"/api/homeworks/{hw_id}/submission", headers=sh, json={"content": "after sync"})
    assert r_sub.status_code == 200, r_sub.text


def test_create_student_duplicate_student_no_same_class_returns_400(client: TestClient):
    """同班学号唯一：第二次 POST /api/students 应 400，不产生第二条花名册。"""
    ctx = _teacher_and_class(client)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    shared_no = f"dup_cls_{ctx['suffix']}"
    body = {"name": "甲", "student_no": shared_no, "gender": "male", "class_id": ctx["class_id"]}
    assert client.post("/api/students", headers=th, json=body).status_code == 200
    r2 = client.post("/api/students", headers=th, json={**body, "name": "乙"})
    assert r2.status_code == 400
    db = SessionLocal()
    try:
        n = db.query(Student).filter(Student.student_no == shared_no, Student.class_id == ctx["class_id"]).count()
        assert n == 1
    finally:
        db.close()
