"""High-value API smoke: health, auth envelope, object-level homework access, submission payload shape.

These complement domain-heavy suites under ``tests/backend/homework`` by locking generic HTTP contracts
that regress easily when routers or dependencies shift.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.models import CourseEnrollment, Homework, Score, Student, Subject, User, UserRole
from apps.backend.courseeval_backend.main import app
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework


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


def test_api_health_and_root_payload(client: TestClient):
    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json().get("status") == "healthy"
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "running"
    assert "message" in body


def test_lifespan_seeds_initial_admin_without_demo_data():
    from apps.backend.courseeval_backend.core.config import settings

    old_values = (
        settings.INIT_DEFAULT_DATA,
        settings.INIT_ADMIN_USERNAME,
        settings.INIT_ADMIN_PASSWORD,
        settings.INIT_ADMIN_REAL_NAME,
        settings.ENABLE_LLM_GRADING_WORKER,
        settings.LLM_GRADING_WORKER_LEADER,
    )
    settings.INIT_DEFAULT_DATA = False
    settings.INIT_ADMIN_USERNAME = "bootstrap_admin"
    settings.INIT_ADMIN_PASSWORD = "bootstrap_admin_pass"
    settings.INIT_ADMIN_REAL_NAME = "Bootstrap Admin"
    settings.ENABLE_LLM_GRADING_WORKER = False
    settings.LLM_GRADING_WORKER_LEADER = False
    try:
        with TestClient(app) as startup_client:
            resp = startup_client.post(
                "/api/auth/login",
                data={"username": "bootstrap_admin", "password": "bootstrap_admin_pass"},
            )
            assert resp.status_code == 200, resp.text

        db = SessionLocal()
        try:
            admin = db.query(User).filter(User.username == "bootstrap_admin").first()
            assert admin is not None
            assert admin.role == UserRole.ADMIN.value
            assert db.query(User).filter(User.username == "teacher").first() is None
        finally:
            db.close()
    finally:
        (
            settings.INIT_DEFAULT_DATA,
            settings.INIT_ADMIN_USERNAME,
            settings.INIT_ADMIN_PASSWORD,
            settings.INIT_ADMIN_REAL_NAME,
            settings.ENABLE_LLM_GRADING_WORKER,
            settings.LLM_GRADING_WORKER_LEADER,
        ) = old_values


def test_login_rejects_bad_password_with_401(client: TestClient):
    ensure_admin()
    resp = client.post("/api/auth/login", data={"username": "pytest_admin", "password": "not-the-password"})
    assert resp.status_code == 401


def test_auth_me_requires_bearer(client: TestClient):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_auth_me_returns_profile_for_valid_token(client: TestClient):
    ensure_admin()
    headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["username"] == "pytest_admin"
    assert body["role"] == UserRole.ADMIN.value


def test_users_list_requires_authentication(client: TestClient):
    """Admin-heavy route must not leak without JWT."""
    resp = client.get("/api/users")
    assert resp.status_code == 401


def test_student_get_homework_outside_enrollment_returns_403(client: TestClient):
    """Object-level guard: homework exists but student has no CourseEnrollment for that subject."""
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    hid = ctx["homework_id"]
    teacher_id = ctx["teacher_id"]
    class_id = ctx["class_id"]

    db = SessionLocal()
    try:
        orphan = Subject(name="pytest-orphan-course", teacher_id=teacher_id, class_id=class_id, course_type="elective")
        db.add(orphan)
        db.flush()
        hw2 = Homework(
            title="orphan-hw",
            content="hidden",
            class_id=class_id,
            subject_id=orphan.id,
            max_score=100,
            auto_grading_enabled=False,
            created_by=teacher_id,
        )
        db.add(hw2)
        db.commit()
        orphan_hw_id = hw2.id
    finally:
        db.close()

    stu_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    blocked = client.get(f"/api/homeworks/{orphan_hw_id}", headers=stu_headers)
    assert blocked.status_code == 403, blocked.text


def test_student_lists_homework_only_for_enrolled_course(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    headers = login_api(client, ctx["student_username"], ctx["student_password"])
    resp = client.get(
        "/api/homeworks",
        params={"class_id": ctx["class_id"], "subject_id": ctx["subject_id"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in (resp.json().get("data") or [])}
    assert ctx["homework_id"] in ids


def test_homework_submission_me_includes_effective_score_metadata_keys(client: TestClient):
    """After a minimal submission, payload must expose aggregate-score explanation fields."""
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    hid = ctx["homework_id"]
    headers = login_api(client, ctx["student_username"], ctx["student_password"])
    sub = client.post(f"/api/homeworks/{hid}/submission", headers=headers, json={"content": "hello"})
    assert sub.status_code == 200, sub.text

    me = client.get(f"/api/homeworks/{hid}/submission/me", headers=headers)
    assert me.status_code == 200, me.text
    body = me.json()
    assert "effective_score_note_zh" in body
    assert "effective_score_attempt_seq" in body


def test_teacher_sees_staff_only_rubric_fields(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    hid = ctx["homework_id"]
    db = SessionLocal()
    try:
        hw = db.query(Homework).filter(Homework.id == hid).first()
        hw.rubric_staff_only = "## staff only"
        hw.reference_answer = "## ref"
        db.commit()
    finally:
        db.close()

    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    detail = client.get(f"/api/homeworks/{hid}", headers=th)
    assert detail.status_code == 200, detail.text
    assert detail.json().get("rubric_staff_only") == "## staff only"
    assert detail.json().get("reference_answer") == "## ref"

    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    student_view = client.get(f"/api/homeworks/{hid}", headers=sh)
    assert student_view.status_code == 200, student_view.text
    assert student_view.json().get("rubric_staff_only") is None
    assert student_view.json().get("reference_answer") is None


def test_dashboard_stats_subject_id_counts_enrollments_not_class_roster(client: TestClient):
    """Electives (and course-scoped stats) must use CourseEnrollment, not class-wide Student rows."""
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    db = SessionLocal()
    try:
        u2 = User(
            username=f"pytest_roster_only_{ctx['class_id']}",
            hashed_password=get_password_hash("p2"),
            real_name="Roster Only",
            role=UserRole.STUDENT.value,
            class_id=ctx["class_id"],
        )
        db.add(u2)
        db.flush()
        db.add(Student(name="Roster Only", student_no=u2.username, class_id=ctx["class_id"]))
        db.commit()
    finally:
        db.close()

    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.get("/api/dashboard/stats", headers=th, params={"subject_id": ctx["subject_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["total_students"] == 1


def test_teacher_course_scoped_scores_do_not_require_class_link_visibility(client: TestClient):
    """Course-owned score/dashboard reads must not be reduced to class-id-only access."""
    ensure_admin()
    db = SessionLocal()
    try:
        from apps.backend.courseeval_backend.db.models import Class

        cls = Class(name="pytest-elective-score-class", grade=2026)
        db.add(cls)
        db.flush()
        teacher = User(
            username="pytest_score_teacher",
            hashed_password=get_password_hash("score-pass"),
            real_name="Score Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        student_user = User(
            username="pytest_score_student",
            hashed_password=get_password_hash("student-pass"),
            real_name="Score Student",
            role=UserRole.STUDENT.value,
            class_id=cls.id,
        )
        db.add(student_user)
        db.flush()
        student = Student(name="Score Student", student_no=student_user.username, class_id=cls.id)
        db.add(student)
        db.flush()
        course = Subject(
            name="pytest-score-elective",
            teacher_id=teacher.id,
            class_id=None,
            course_type="elective",
            status="active",
        )
        db.add(course)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=course.id,
                student_id=student.id,
                class_id=cls.id,
                enrollment_type="elective",
                can_remove=True,
            )
        )
        db.add(
            Score(
                student_id=student.id,
                subject_id=course.id,
                class_id=cls.id,
                score=88,
                exam_type="midterm",
                semester="2026-spring",
            )
        )
        db.commit()
        ctx = {"subject_id": course.id, "student_id": student.id}
    finally:
        db.close()

    headers = login_api(client, "pytest_score_teacher", "score-pass")

    scores = client.get("/api/scores", headers=headers, params={"subject_id": ctx["subject_id"]})
    assert scores.status_code == 200, scores.text
    assert scores.json()["total"] == 1

    stats = client.get("/api/dashboard/stats", headers=headers, params={"subject_id": ctx["subject_id"]})
    assert stats.status_code == 200, stats.text
    assert stats.json()["total_scores"] == 1

    ranking = client.get(f"/api/dashboard/rankings/subjects/{ctx['subject_id']}", headers=headers)
    assert ranking.status_code == 200, ranking.text
    assert ranking.json()[0]["student_id"] == ctx["student_id"]


def test_users_list_returns_page_for_admin(client: TestClient):
    ensure_admin()
    headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    resp = client.get("/api/users", params={"page": 1, "page_size": 5}, headers=headers)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert isinstance(payload, list)
    assert any(row.get("username") == "pytest_admin" for row in payload)
