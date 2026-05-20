"""Batch homework operations: late submission policy + LLM regrade queue."""

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
    Student,
    Subject,
    User,
    UserRole,
)


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


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def course_with_two_homeworks(client: TestClient) -> dict:
    db = SessionLocal()
    try:
        klass = Class(name="BatchClass", grade=2026)
        db.add(klass)
        db.flush()
        t = User(
            username="batch_t",
            hashed_password=get_password_hash("p"),
            real_name="Batch T",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        subj = Subject(name="BatchCourse", teacher_id=t.id, class_id=klass.id)
        db.add(subj)
        db.flush()
        h1 = Homework(
            title="H1",
            content="c",
            class_id=klass.id,
            subject_id=subj.id,
            max_score=100,
            grade_precision="integer",
            auto_grading_enabled=False,
            allow_late_submission=False,
            late_submission_affects_score=True,
            created_by=t.id,
        )
        h2 = Homework(
            title="H2",
            content="c",
            class_id=klass.id,
            subject_id=subj.id,
            max_score=100,
            grade_precision="integer",
            auto_grading_enabled=False,
            allow_late_submission=False,
            late_submission_affects_score=True,
            created_by=t.id,
        )
        db.add_all([h1, h2])
        db.commit()
        return {
            "teacher_headers": _login(client, "batch_t", "p"),
            "h1": h1.id,
            "h2": h2.id,
        }
    finally:
        db.close()


def test_batch_late_submission_updates_homeworks(client: TestClient, course_with_two_homeworks: dict):
    h = course_with_two_homeworks["teacher_headers"]
    r = client.post(
        "/api/homeworks/batch-late-submission",
        headers=h,
        json={
            "homework_ids": [course_with_two_homeworks["h1"], course_with_two_homeworks["h2"]],
            "allow_late_submission": True,
            "late_submission_affects_score": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 2
    assert body["missing_ids"] == []
    assert body["forbidden_ids"] == []

    db = SessionLocal()
    try:
        for hid in (course_with_two_homeworks["h1"], course_with_two_homeworks["h2"]):
            hw = db.query(Homework).filter(Homework.id == hid).one()
            assert hw.allow_late_submission is True
            assert hw.late_submission_affects_score is False
    finally:
        db.close()


def test_batch_regrade_queues_for_submissions_with_attempts(client: TestClient, course_with_two_homeworks: dict):
    """Two students, one homework with auto_grad on; batch-regrade both submissions."""
    h = course_with_two_homeworks["teacher_headers"]
    hid = course_with_two_homeworks["h1"]
    db = SessionLocal()
    try:
        hw = db.query(Homework).filter(Homework.id == hid).one()
        hw.auto_grading_enabled = True
        klass_id = hw.class_id
        subj_id = hw.subject_id
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        s1 = Student(name="S1", student_no="batch_s1", class_id=klass_id)
        s2 = Student(name="S2", student_no="batch_s2", class_id=klass_id)
        db.add_all([s1, s2])
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=subj_id,
                student_id=s1.id,
                class_id=klass_id,
                enrollment_type="required",
            )
        )
        db.add(
            CourseEnrollment(
                subject_id=subj_id,
                student_id=s2.id,
                class_id=klass_id,
                enrollment_type="required",
            )
        )
        db.flush()
        sub1 = HomeworkSubmission(homework_id=hid, student_id=s1.id, subject_id=subj_id, class_id=klass_id)
        sub2 = HomeworkSubmission(homework_id=hid, student_id=s2.id, subject_id=subj_id, class_id=klass_id)
        db.add_all([sub1, sub2])
        db.flush()
        a1 = HomeworkAttempt(
            homework_id=hid,
            student_id=s1.id,
            subject_id=subj_id,
            class_id=klass_id,
            submission_summary_id=sub1.id,
            content="a1",
            is_late=False,
            counts_toward_final_score=True,
        )
        a2 = HomeworkAttempt(
            homework_id=hid,
            student_id=s2.id,
            subject_id=subj_id,
            class_id=klass_id,
            submission_summary_id=sub2.id,
            content="a2",
            is_late=False,
            counts_toward_final_score=True,
        )
        db.add_all([a1, a2])
        db.flush()
        sub1.latest_attempt_id = a1.id
        sub2.latest_attempt_id = a2.id
        sid1, sid2 = sub1.id, sub2.id
        db.commit()
    finally:
        db.close()

    r = client.post(
        f"/api/homeworks/{hid}/submissions/batch-regrade",
        headers=h,
        json={"submission_ids": [sid1, sid2], "only_latest_attempt": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["queued"] == 2
    assert data["skipped"] == 0
    assert len(data["results"]) == 2

    db = SessionLocal()
    try:
        tasks = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.homework_id == hid).all()
        assert len(tasks) == 2
    finally:
        db.close()


def test_batch_regrade_skips_empty_submission(client: TestClient, course_with_two_homeworks: dict):
    h = course_with_two_homeworks["teacher_headers"]
    hid = course_with_two_homeworks["h1"]
    db = SessionLocal()
    try:
        hw = db.query(Homework).filter(Homework.id == hid).one()
        hw.auto_grading_enabled = True
        klass_id = hw.class_id
        subj_id = hw.subject_id
        s1 = Student(name="E1", student_no="batch_e1", class_id=klass_id)
        db.add(s1)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=subj_id,
                student_id=s1.id,
                class_id=klass_id,
                enrollment_type="required",
            )
        )
        sub_empty = HomeworkSubmission(homework_id=hid, student_id=s1.id, subject_id=subj_id, class_id=klass_id)
        db.add(sub_empty)
        db.flush()
        sid = sub_empty.id
        db.commit()
    finally:
        db.close()

    r = client.post(
        f"/api/homeworks/{hid}/submissions/batch-regrade",
        headers=h,
        json={"submission_ids": [sid], "only_latest_attempt": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["queued"] == 0
    assert r.json()["skipped"] == 1
    assert r.json()["results"][0]["status"] == "skipped"
