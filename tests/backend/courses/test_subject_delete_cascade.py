"""Regression: admin delete course must succeed with dependent homework + LLM rows."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    Homework,
    HomeworkAttempt,
    HomeworkGradingTask,
    HomeworkSubmission,
    LLMQuotaReservation,
    Notification,
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
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_admin_delete_subject_cascades_homework_llm_quota(client: TestClient):
    uid = "delcascade01"
    db = SessionLocal()
    try:
        klass = Class(name=f"c-{uid}", grade=2026)
        db.add(klass)
        db.flush()

        admin = User(
            username=f"adm_{uid}",
            hashed_password=get_password_hash("ap"),
            real_name="Admin",
            role=UserRole.ADMIN.value,
        )
        teacher = User(
            username=f"t_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add_all([admin, teacher])
        db.flush()

        stu_user = User(
            username=f"s_{uid}",
            hashed_password=get_password_hash("sp"),
            real_name="Stu",
            role=UserRole.STUDENT.value,
            class_id=klass.id,
        )
        db.add(stu_user)
        db.flush()
        student = Student(name="Stu", student_no=f"s_{uid}", class_id=klass.id)
        db.add(student)
        db.flush()

        course = Subject(
            name=f"Course-{uid}",
            teacher_id=teacher.id,
            class_id=klass.id,
            course_type="required",
            status="active",
        )
        db.add(course)
        db.flush()

        db.add(
            CourseEnrollment(
                subject_id=course.id,
                student_id=student.id,
                class_id=klass.id,
                enrollment_type="required",
            )
        )

        hw = Homework(
            title="hw",
            content="x",
            class_id=klass.id,
            subject_id=course.id,
            max_score=100,
            created_by=teacher.id,
        )
        db.add(hw)
        db.flush()

        sub = HomeworkSubmission(
            homework_id=hw.id,
            student_id=student.id,
            subject_id=course.id,
            class_id=klass.id,
        )
        db.add(sub)
        db.flush()

        att = HomeworkAttempt(
            homework_id=hw.id,
            student_id=student.id,
            subject_id=course.id,
            class_id=klass.id,
            submission_summary_id=sub.id,
            content="a",
        )
        db.add(att)
        db.flush()

        task = HomeworkGradingTask(
            attempt_id=att.id,
            homework_id=hw.id,
            student_id=student.id,
            subject_id=course.id,
            status="queued",
        )
        db.add(task)
        db.flush()

        db.add(
            LLMQuotaReservation(
                task_id=task.id,
                student_id=student.id,
                subject_id=course.id,
                usage_date="2026-05-02",
                timezone="UTC",
                reserved_tokens=100,
            )
        )

        db.add(
            Notification(
                title="n",
                content="c",
                subject_id=course.id,
                class_id=klass.id,
                related_homework_id=hw.id,
                notification_kind="general",
                created_by=teacher.id,
            )
        )

        db.commit()
        subject_id = course.id
    finally:
        db.close()

    ah = login_api(client, f"adm_{uid}", "ap")
    r = client.delete(f"/api/subjects/{subject_id}", headers=ah)
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        assert db.query(Subject).filter(Subject.id == subject_id).first() is None
    finally:
        db.close()
