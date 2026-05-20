"""Homework grading completion notices for students (notification center)."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.db.models import Homework, HomeworkSubmission, Notification, Student


def _format_score_line(score: Optional[float], homework: Homework) -> str:
    if score is None:
        return "得分：（暂无分数）"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "得分：（暂无分数）"
    if (homework.grade_precision or "integer") == "decimal_1":
        return f"得分：{s:.1f} / {homework.max_score:g}"
    return f"得分：{int(round(s))} / {int(round(homework.max_score))}"


def upsert_homework_grade_notification(
    db: Session,
    *,
    homework: Homework,
    student: Student,
    score: Optional[float],
    comment: Optional[str],
    source_label: str,
    created_by_user_id: int,
) -> Optional[Notification]:
    """
    Create or update a single per-(homework, student) notification when grading completes.
    Visible only to that student (target_student_id) plus admins.
    """
    title = f"作业已批改：{homework.title}"
    lines = [
        f"课程作业「{homework.title}」已完成批改（{source_label}）。",
        _format_score_line(score, homework),
    ]
    if comment and str(comment).strip():
        excerpt = str(comment).strip()
        if len(excerpt) > 400:
            excerpt = excerpt[:400] + "…"
        lines.append(f"评语摘要：{excerpt}")
    lines.append("请在「作业提交」页面查看最高分及完整评语。")
    content = "\n".join(lines)

    existing = (
        db.query(Notification)
        .filter(
            Notification.related_homework_id == homework.id,
            Notification.related_student_id == student.id,
        )
        .first()
    )
    if existing:
        existing.title = title
        existing.content = content
        existing.priority = "normal"
        existing.class_id = homework.class_id
        existing.subject_id = homework.subject_id
        existing.target_student_id = student.id
        existing.notification_kind = "grade_complete"
        existing.target_user_id = None
        existing.related_appeal_id = None
        existing.created_by = created_by_user_id
        return existing

    notification = Notification(
        title=title,
        content=content,
        priority="normal",
        is_pinned=False,
        class_id=homework.class_id,
        subject_id=homework.subject_id,
        target_student_id=student.id,
        related_homework_id=homework.id,
        related_student_id=student.id,
        notification_kind="grade_complete",
        created_by=created_by_user_id,
    )
    db.add(notification)
    return notification


def notify_student_homework_graded(
    db: Session,
    *,
    homework_id: int,
    student_id: int,
    source_label: str,
    created_by_user_id: int,
) -> Optional[Notification]:
    homework = db.query(Homework).filter(Homework.id == homework_id).first()
    student = db.query(Student).filter(Student.id == student_id).first()
    if not homework or not student:
        return None
    submission = (
        db.query(HomeworkSubmission)
        .filter(
            HomeworkSubmission.homework_id == homework_id,
            HomeworkSubmission.student_id == student_id,
        )
        .first()
    )
    if not submission:
        return None
    return upsert_homework_grade_notification(
        db,
        homework=homework,
        student=student,
        score=submission.review_score,
        comment=submission.review_comment,
        source_label=source_label,
        created_by_user_id=created_by_user_id,
    )
