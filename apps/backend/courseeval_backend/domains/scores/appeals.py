"""Teacher notifications for course score (composition) appeals."""

from __future__ import annotations

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.domains.appeal_notifications import sync_appeal_notification_projection
from apps.backend.courseeval_backend.domains.courses.access import subject_teacher_user_ids
from apps.backend.courseeval_backend.db.models import Homework, Notification, ScoreGradeAppeal, Subject


def notify_teachers_score_grade_appeal(
    db: Session,
    *,
    appeal: ScoreGradeAppeal,
    student_name: str,
    creator_user_id: int,
    related_homework_id: int | None = None,
) -> list[Notification]:
    course = db.query(Subject).filter(Subject.id == appeal.subject_id).first()
    class_id = course.class_id if course else None
    teacher_ids = subject_teacher_user_ids(db, int(appeal.subject_id))
    created: list[Notification] = []
    homework = db.query(Homework).filter(Homework.id == related_homework_id).first() if related_homework_id else None
    title = f"成绩构成申诉：{homework.title}" if homework else "成绩构成申诉"
    excerpt = (appeal.reason_text or "").strip()
    if len(excerpt) > 500:
        excerpt = excerpt[:500] + "..."
    target_label = f"作业《{homework.title}》" if homework else appeal.target_component
    content = "\n".join(
        [
            f"学生 {student_name} 提交了成绩申诉。",
            f"申诉编号：{appeal.id}",
            f"学期：{appeal.semester}",
            f"申诉对象：{target_label}",
            "申诉理由：",
            excerpt or "（无）",
            "",
            "请在对应页面中查看并处理。",
        ]
    )

    for uid in teacher_ids:
        existing = (
            db.query(Notification)
            .filter(
                Notification.related_score_appeal_id == appeal.id,
                Notification.target_user_id == uid,
                Notification.notification_kind == "score_grade_appeal",
            )
            .first()
        )
        if existing:
            existing.class_id = class_id
            existing.subject_id = appeal.subject_id
            existing.related_homework_id = related_homework_id
            existing.related_student_id = appeal.student_id
            existing.created_by = creator_user_id
            sync_appeal_notification_projection(existing, status=appeal.status, content=content)
            created.append(existing)
            continue

        notification = Notification(
            title=title,
            content=content,
            priority="important",
            is_pinned=False,
            class_id=class_id,
            subject_id=appeal.subject_id,
            target_student_id=None,
            target_user_id=uid,
            related_homework_id=related_homework_id,
            related_student_id=appeal.student_id,
            related_appeal_id=None,
            related_score_appeal_id=appeal.id,
            notification_kind="score_grade_appeal",
            created_by=creator_user_id,
        )
        sync_appeal_notification_projection(notification, status=appeal.status, content=content)
        db.add(notification)
        created.append(notification)

    return created


def mark_score_appeal_notifications_handled(db: Session, appeal_id: int, status: str) -> None:
    rows = db.query(Notification).filter(Notification.related_score_appeal_id == appeal_id).all()
    for notification in rows:
        if notification.notification_kind == "score_grade_appeal":
            sync_appeal_notification_projection(notification, status=status)
