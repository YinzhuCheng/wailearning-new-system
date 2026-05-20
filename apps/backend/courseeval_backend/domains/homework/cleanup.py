from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.attachments import delete_attachment_file
from apps.backend.courseeval_backend.db.models import (
    Homework,
    HomeworkAttempt,
    HomeworkGradeAppeal,
    HomeworkGradingTask,
    HomeworkScoreCandidate,
    HomeworkSubmission,
    CourseMaterialHomeworkLink,
    LLMQuotaReservation,
    LLMTokenUsageLog,
)


def delete_attachment_if_unreferenced(
    db: Session,
    attachment_url: Optional[str],
) -> None:
    from apps.backend.courseeval_backend.attachments import attachment_is_referenced

    if not attachment_url:
        return
    if attachment_is_referenced(db, attachment_url):
        return
    delete_attachment_file(attachment_url)


def purge_homework_row(db: Session, homework: Homework) -> None:
    """Remove a homework row and dependent rows for internal/admin delete flows."""
    db.query(CourseMaterialHomeworkLink).filter(CourseMaterialHomeworkLink.homework_id == homework.id).delete(
        synchronize_session=False
    )

    db.query(HomeworkGradeAppeal).filter(HomeworkGradeAppeal.homework_id == homework.id).delete(
        synchronize_session=False
    )

    attachment_urls: set[str] = set()

    db.query(HomeworkSubmission).filter(HomeworkSubmission.homework_id == homework.id).update(
        {HomeworkSubmission.latest_attempt_id: None},
        synchronize_session=False,
    )
    db.query(HomeworkAttempt).filter(HomeworkAttempt.homework_id == homework.id).update(
        {HomeworkAttempt.submission_summary_id: None},
        synchronize_session=False,
    )
    db.flush()

    attempts = db.query(HomeworkAttempt).filter(HomeworkAttempt.homework_id == homework.id).all()
    for attempt in attempts:
        if attempt.attachment_url:
            attachment_urls.add(attempt.attachment_url)
        db.query(HomeworkScoreCandidate).filter(HomeworkScoreCandidate.attempt_id == attempt.id).delete()
        task_ids = [
            item[0]
            for item in db.query(HomeworkGradingTask.id)
            .filter(HomeworkGradingTask.attempt_id == attempt.id)
            .all()
        ]
        if task_ids:
            db.query(LLMQuotaReservation).filter(LLMQuotaReservation.task_id.in_(task_ids)).delete(
                synchronize_session=False
            )
            db.query(LLMTokenUsageLog).filter(LLMTokenUsageLog.task_id.in_(task_ids)).delete(
                synchronize_session=False
            )
        db.query(HomeworkGradingTask).filter(HomeworkGradingTask.attempt_id == attempt.id).delete()
        db.delete(attempt)

    for submission in list(homework.submissions):
        if submission.attachment_url:
            attachment_urls.add(submission.attachment_url)
        db.delete(submission)

    if homework.attachment_url:
        delete_attachment_if_unreferenced(
            db,
            homework.attachment_url,
        )

    for attachment_url in attachment_urls:
        delete_attachment_if_unreferenced(db, attachment_url)

    db.delete(homework)
