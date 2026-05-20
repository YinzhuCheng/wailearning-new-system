"""Roster <-> user sync and safe queries when no accessible classes."""

from __future__ import annotations

from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.domains.courses.access import (
    prepare_student_course_context,
)
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Class, CourseEnrollment, Student, Subject, SubjectClassLink, User, UserRole
from apps.backend.courseeval_backend.domains.roster.sync import (
    reconcile_student_users_and_roster,
)
from fastapi.testclient import TestClient


def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()


def test_students_list_returns_empty_when_teacher_has_no_classes_not_500():
    """Previously Student.class_id.in_([]) caused SQL errors."""
    _reset_db()
    db = SessionLocal()
    try:
        c = Class(name="孤儿班", grade=2026)
        db.add(c)
        db.flush()
        db.add(
            Student(name="无名", student_no="orphan1", class_id=c.id),
        )
        u = User(
            username="solo_teacher",
            hashed_password=get_password_hash("pass"),
            real_name="Solo",
            role=UserRole.TEACHER.value,
        )
        db.add(u)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    r = client.post(
        "/api/auth/login",
        data={"username": "solo_teacher", "password": "pass"},
    )
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    st = client.get("/api/students?page=1&page_size=20", headers=h)
    assert st.status_code == 200, st.text
    assert st.json()["total"] == 0


def test_reconcile_creates_user_from_roster_only():
    """Roster-first deployment: Student row gets matching User without manual load."""
    _reset_db()
    db = SessionLocal()
    try:
        c = Class(name="仅花名册班", grade=2026)
        db.add(c)
        db.flush()
        db.add(Student(name="仅花名册", student_no="roster_only_1", class_id=c.id))
        db.commit()
        reconcile_student_users_and_roster(db)
        db.commit()
        u = db.query(User).filter(User.username == "roster_only_1").first()
        assert u is not None
        assert u.role == UserRole.STUDENT.value
        assert u.class_id == c.id
    finally:
        db.close()


def test_prepare_student_course_context_reuses_pending_enrollment_rows():
    _reset_db()
    db = SessionLocal()
    try:
        klass = Class(name="sync-class", grade=2026)
        db.add(klass)
        db.flush()
        user = User(
            username="sync_stu",
            hashed_password=get_password_hash("pass"),
            real_name="Sync Stu",
            role=UserRole.STUDENT.value,
            class_id=klass.id,
        )
        db.add(user)
        db.flush()
        student = Student(name="Sync Stu", student_no="sync_stu", class_id=klass.id)
        db.add(student)
        db.flush()
        course_a = Subject(name="required-a", class_id=klass.id, course_type="required")
        course_b = Subject(name="required-b", class_id=klass.id, course_type="required")
        db.add_all([course_a, course_b])
        db.flush()
        db.add_all(
            [
                SubjectClassLink(subject_id=course_a.id, class_id=klass.id, enrollment_mode="all_in_class"),
                SubjectClassLink(subject_id=course_b.id, class_id=klass.id, enrollment_mode="all_in_class"),
            ]
        )
        db.flush()

        prepare_student_course_context(user, db)
        prepare_student_course_context(user, db)
        db.flush()

        rows = db.query(CourseEnrollment).filter(CourseEnrollment.student_id == student.id).all()
        assert len(rows) == 2
        assert len({row.subject_id for row in rows}) == 2
    finally:
        db.close()
