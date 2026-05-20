from __future__ import annotations

import pytest

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseLLMConfig,
    Homework,
    HomeworkAttempt,
    HomeworkSubmission,
    HomeworkGradingTask,
    LLMQuotaReservation,
    LLMTokenUsageLog,
    Student,
    Subject,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.llm.quota import get_used_tokens_for_scope, record_usage_if_needed
from apps.backend.courseeval_backend.domains.llm.token_quota import resolve_global_quota_calendar
from apps.backend.courseeval_backend.llm_grading import queue_grading_task


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    yield
    SessionLocal().close()


def test_teacher_regrade_is_not_counted_against_student_quota():
    db = SessionLocal()
    try:
        usage_date, timezone_name = resolve_global_quota_calendar(db)
        klass = Class(name="billing_class", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username="billing_teacher",
            hashed_password="x",
            real_name="Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        student = Student(name="Student", student_no="billing_student", class_id=klass.id)
        db.add(student)
        db.flush()
        course = Subject(name="Billing Course", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.flush()
        config = CourseLLMConfig(subject_id=course.id, is_enabled=True, max_input_tokens=16000, max_output_tokens=None)
        db.add(config)
        db.flush()
        homework = Homework(
            title="Billing Homework",
            content="content",
            class_id=klass.id,
            subject_id=course.id,
            max_score=100,
            auto_grading_enabled=True,
            created_by=teacher.id,
        )
        db.add(homework)
        db.flush()
        attempt = HomeworkAttempt(
            homework_id=homework.id,
            student_id=student.id,
            subject_id=course.id,
            class_id=klass.id,
            content="submission",
        )
        db.add(attempt)
        db.flush()

        submission_task = queue_grading_task(db, attempt, "new_submission", billed_user_id=None)
        original_submission_task_id = submission_task.id
        db.flush()
        submission_task.status = "success"
        db.flush()
        regrade_task = queue_grading_task(db, attempt, "regrade", billed_user_id=teacher.id)
        db.flush()

        assert submission_task.billed_user_id is None
        assert regrade_task.id != original_submission_task_id
        assert regrade_task.billed_user_id == teacher.id

        db.add(
            LLMQuotaReservation(
                task_id=original_submission_task_id,
                student_id=student.id,
                subject_id=course.id,
                billed_user_id=None,
                usage_date=usage_date,
                timezone=timezone_name,
                reserved_tokens=120,
            )
        )
        db.add(
            LLMQuotaReservation(
                task_id=regrade_task.id,
                student_id=student.id,
                subject_id=course.id,
                billed_user_id=teacher.id,
                usage_date=usage_date,
                timezone=timezone_name,
                reserved_tokens=220,
            )
        )
        db.flush()

        used_before = get_used_tokens_for_scope(
            db,
            usage_date=usage_date,
            timezone_name=timezone_name,
            student_id=student.id,
        )
        assert used_before == 0

        record_usage_if_needed(
            db,
            db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == original_submission_task_id).one(),
            config,
            {"prompt_tokens": 120, "completion_tokens": 900, "total_tokens": 1020},
        )
        record_usage_if_needed(
            db,
            regrade_task,
            config,
            {"prompt_tokens": 220, "completion_tokens": 1800, "total_tokens": 2020},
        )
        db.flush()

        student_used = get_used_tokens_for_scope(
            db,
            usage_date=usage_date,
            timezone_name=timezone_name,
            student_id=student.id,
        )
        assert student_used == 120

        usage_rows = db.query(LLMTokenUsageLog).order_by(LLMTokenUsageLog.task_id.asc()).all()
        assert len(usage_rows) == 2
        assert usage_rows[0].input_tokens == 120
        assert usage_rows[0].output_tokens == 900
        assert usage_rows[0].total_tokens == 1020
        assert usage_rows[1].billed_user_id == teacher.id
        assert usage_rows[1].output_tokens == 1800
        assert usage_rows[1].total_tokens == 2020
    finally:
        db.close()


def test_student_submission_auto_grading_still_counts_against_student_quota():
    db = SessionLocal()
    try:
        usage_date, timezone_name = resolve_global_quota_calendar(db)
        klass = Class(name="student_billing_class", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username="student_billing_teacher",
            hashed_password="x",
            real_name="Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        student = Student(name="Student", student_no="student_billing_student", class_id=klass.id)
        db.add(student)
        db.flush()
        course = Subject(name="Student Billing Course", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.flush()
        config = CourseLLMConfig(subject_id=course.id, is_enabled=True, max_input_tokens=16000, max_output_tokens=None)
        db.add(config)
        db.flush()
        homework = Homework(
            title="Student Billing Homework",
            content="content",
            class_id=klass.id,
            subject_id=course.id,
            max_score=100,
            auto_grading_enabled=True,
            created_by=teacher.id,
        )
        db.add(homework)
        db.flush()
        attempt = HomeworkAttempt(
            homework_id=homework.id,
            student_id=student.id,
            subject_id=course.id,
            class_id=klass.id,
            content="submission",
        )
        db.add(attempt)
        db.flush()

        task = queue_grading_task(db, attempt, "new_submission", billed_user_id=None)
        db.add(
            LLMQuotaReservation(
                task_id=task.id,
                student_id=student.id,
                subject_id=course.id,
                billed_user_id=None,
                usage_date=usage_date,
                timezone=timezone_name,
                reserved_tokens=150,
            )
        )
        db.flush()

        record_usage_if_needed(
            db,
            task,
            config,
            {"prompt_tokens": 150, "completion_tokens": 1000, "total_tokens": 1150},
        )
        db.flush()

        student_used = get_used_tokens_for_scope(
            db,
            usage_date=usage_date,
            timezone_name=timezone_name,
            student_id=student.id,
        )
        assert student_used == 150
    finally:
        db.close()


def test_teacher_regrade_does_not_create_a_new_submission_attempt():
    db = SessionLocal()
    try:
        klass = Class(name="regrade_count_class", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username="regrade_count_teacher",
            hashed_password="x",
            real_name="Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        student = Student(name="Student", student_no="regrade_count_student", class_id=klass.id)
        db.add(student)
        db.flush()
        course = Subject(name="Regrade Count Course", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.flush()
        config = CourseLLMConfig(subject_id=course.id, is_enabled=True, max_input_tokens=16000, max_output_tokens=None)
        db.add(config)
        db.flush()
        homework = Homework(
          title="Regrade Count Homework",
          content="content",
          class_id=klass.id,
          subject_id=course.id,
          max_score=100,
          auto_grading_enabled=True,
          created_by=teacher.id,
        )
        db.add(homework)
        db.flush()
        submission = HomeworkSubmission(homework_id=homework.id, student_id=student.id, subject_id=course.id, class_id=klass.id)
        db.add(submission)
        db.flush()
        attempt = HomeworkAttempt(
            homework_id=homework.id,
            student_id=student.id,
            subject_id=course.id,
            class_id=klass.id,
            submission_summary_id=submission.id,
            content="first submission",
        )
        db.add(attempt)
        db.flush()
        submission.latest_attempt_id = attempt.id
        db.flush()

        before_count = len(submission.attempts)
        queue_grading_task(db, attempt, "regrade", billed_user_id=teacher.id)
        db.flush()
        db.refresh(submission)
        after_count = len(submission.attempts)

        assert before_count == 1
        assert after_count == 1
        assert db.query(HomeworkAttempt).filter(HomeworkAttempt.submission_summary_id == submission.id).count() == 1
    finally:
        db.close()


def test_teacher_regrade_reuses_queued_task_and_updates_billing_owner():
    db = SessionLocal()
    try:
        klass = Class(name="regrade_reuse_class", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username="regrade_reuse_teacher",
            hashed_password="x",
            real_name="Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        student = Student(name="Student", student_no="regrade_reuse_student", class_id=klass.id)
        db.add(student)
        db.flush()
        course = Subject(name="Regrade Reuse Course", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.flush()
        config = CourseLLMConfig(subject_id=course.id, is_enabled=True, max_input_tokens=16000, max_output_tokens=None)
        db.add(config)
        db.flush()
        homework = Homework(
            title="Regrade Reuse Homework",
            content="content",
            class_id=klass.id,
            subject_id=course.id,
            max_score=100,
            auto_grading_enabled=True,
            created_by=teacher.id,
        )
        db.add(homework)
        db.flush()
        attempt = HomeworkAttempt(
            homework_id=homework.id,
            student_id=student.id,
            subject_id=course.id,
            class_id=klass.id,
            content="submission",
        )
        db.add(attempt)
        db.flush()

        original_task = queue_grading_task(db, attempt, "new_submission", billed_user_id=None)
        db.flush()
        reused_task = queue_grading_task(db, attempt, "regrade", billed_user_id=teacher.id)
        db.flush()

        assert reused_task.id == original_task.id
        assert reused_task.status == "queued"
        assert reused_task.queue_reason == "new_submission"
        assert reused_task.billed_user_id == teacher.id
    finally:
        db.close()
