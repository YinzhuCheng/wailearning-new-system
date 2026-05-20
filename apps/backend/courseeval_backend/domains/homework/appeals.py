"""Teacher notifications for student homework grade appeals."""

from __future__ import annotations

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.domains.appeal_notifications import (
    APPEAL_STATUS_ACKNOWLEDGED,
    APPEAL_STATUS_PENDING,
    APPEAL_STATUS_REJECTED,
    APPEAL_STATUS_RESOLVED,
    sync_appeal_notification_projection,
)
from apps.backend.courseeval_backend.domains.courses.access import subject_teacher_user_ids
from apps.backend.courseeval_backend.db.models import Homework, HomeworkGradeAppeal, Notification


def notify_teachers_grade_appeal(
    db: Session,
    *,
    appeal: HomeworkGradeAppeal,
    homework: Homework,
    student_name: str,
    creator_user_id: int,
) -> list[Notification]:
    """Create one teacher-targeted notification per course teacher + class teacher."""
    if not homework.subject_id:
        return []

    teacher_ids = subject_teacher_user_ids(db, int(homework.subject_id))
    created: list[Notification] = []
    title = f"成绩申诉：{homework.title}"
    excerpt = (appeal.reason_text or "").strip()
    if len(excerpt) > 500:
        excerpt = excerpt[:500] + "..."
    content = "\n".join(
        [
            f"学生 {student_name} 对作业《{homework.title}》提交了成绩申诉。",
            f"申诉编号：{appeal.id}",
            "申诉理由：",
            excerpt or "（无）",
            "",
            "请在“作业 -> 学生提交”中打开对应学生，查看详情并调整分数。",
        ]
    )

    for uid in teacher_ids:
        existing = (
            db.query(Notification)
            .filter(
                Notification.related_appeal_id == appeal.id,
                Notification.target_user_id == uid,
                Notification.notification_kind == "grade_appeal",
            )
            .first()
        )
        if existing:
            existing.class_id = homework.class_id
            existing.subject_id = homework.subject_id
            existing.related_homework_id = homework.id
            existing.related_student_id = appeal.student_id
            existing.created_by = creator_user_id
            sync_appeal_notification_projection(existing, status=APPEAL_STATUS_PENDING, content=content)
            created.append(existing)
            continue

        row = Notification(
            title=title,
            content=content,
            priority="important",
            is_pinned=False,
            class_id=homework.class_id,
            subject_id=homework.subject_id,
            target_student_id=None,
            target_user_id=uid,
            related_homework_id=homework.id,
            related_student_id=appeal.student_id,
            related_appeal_id=appeal.id,
            notification_kind="grade_appeal",
            created_by=creator_user_id,
        )
        sync_appeal_notification_projection(row, status=APPEAL_STATUS_PENDING, content=content)
        db.add(row)
        created.append(row)

    return created


def mark_appeal_notifications_acknowledged(db: Session, appeal_id: int) -> None:
    """Project acknowledged status without implying the appeal is resolved."""
    rows = db.query(Notification).filter(Notification.related_appeal_id == appeal_id).all()
    for row in rows:
        if row.notification_kind == "grade_appeal":
            sync_appeal_notification_projection(row, status=APPEAL_STATUS_ACKNOWLEDGED)


def mark_appeal_notifications_resolved(db: Session, appeal_id: int) -> None:
    """Project resolved status after the appeal is actually handled."""
    rows = db.query(Notification).filter(Notification.related_appeal_id == appeal_id).all()
    for row in rows:
        if row.notification_kind == "grade_appeal":
            sync_appeal_notification_projection(row, status=APPEAL_STATUS_RESOLVED)


def mark_appeal_notifications_handled(db: Session, appeal_id: int, status: str) -> None:
    rows = db.query(Notification).filter(Notification.related_appeal_id == appeal_id).all()
    for row in rows:
        if row.notification_kind == "grade_appeal":
            projected_status = status if status in (APPEAL_STATUS_ACKNOWLEDGED, APPEAL_STATUS_RESOLVED, APPEAL_STATUS_REJECTED) else APPEAL_STATUS_PENDING
            sync_appeal_notification_projection(row, status=projected_status)
