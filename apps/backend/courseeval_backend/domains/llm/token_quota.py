"""Admin-managed LLM daily token caps (per-student limit) and helpers for quota calendars."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.db.models import CourseEnrollment, LLMGlobalQuotaPolicy, LLMStudentTokenOverride, Student

ScopeName = Literal["all", "class", "subject"]


def get_or_create_global_quota_policy(db: Session) -> LLMGlobalQuotaPolicy:
    row = db.query(LLMGlobalQuotaPolicy).filter(LLMGlobalQuotaPolicy.id == 1).first()
    if row:
        return row
    row = LLMGlobalQuotaPolicy(
        id=1,
        default_daily_student_tokens=100_000,
        quota_timezone="Asia/Shanghai",
        estimated_chars_per_token=4.0,
        estimated_image_tokens=850,
        max_parallel_grading_tasks=3,
    )
    db.add(row)
    db.flush()
    return row


def resolve_max_parallel_grading_tasks(db: Session) -> int:
    pol = get_or_create_global_quota_policy(db)
    return max(1, int(getattr(pol, "max_parallel_grading_tasks", None) or 3))


def resolve_global_estimated_chars_per_token(db: Session) -> float:
    pol = get_or_create_global_quota_policy(db)
    try:
        return max(0.1, float(getattr(pol, "estimated_chars_per_token", None) or 4.0))
    except (TypeError, ValueError):
        return 4.0


def resolve_global_estimated_image_tokens(db: Session) -> int:
    pol = get_or_create_global_quota_policy(db)
    try:
        return max(1, int(getattr(pol, "estimated_image_tokens", None) or 850))
    except (TypeError, ValueError):
        return 850


def resolve_global_quota_calendar(db: Session) -> tuple[str, str]:
    pol = get_or_create_global_quota_policy(db)
    return quota_calendar_for_timezone(getattr(pol, "quota_timezone", None) or "Asia/Shanghai")


def quota_calendar_for_timezone(tz_raw: str) -> tuple[str, str]:
    """Calendar day for the system-wide LLM usage pool and course attribution snapshots."""
    tz_name = (tz_raw or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz_name = "UTC"
        tz = ZoneInfo("UTC")
    usage_date = datetime.now(tz).date().isoformat()
    return usage_date, tz_name


def resolve_effective_daily_student_tokens(db: Session, student_id: int) -> int:
    pol = get_or_create_global_quota_policy(db)
    ov = db.query(LLMStudentTokenOverride).filter(LLMStudentTokenOverride.student_id == student_id).first()
    if ov is not None:
        return max(1, int(ov.daily_tokens))
    return max(1, int(pol.default_daily_student_tokens or 100_000))


def resolve_student_ids_for_scope(
    db: Session,
    scope: ScopeName,
    *,
    class_id: Optional[int] = None,
    subject_id: Optional[int] = None,
) -> list[int]:
    if scope == "all":
        return [row[0] for row in db.query(Student.id).order_by(Student.id.asc()).all()]
    if scope == "class":
        if class_id is None:
            return []
        return [row[0] for row in db.query(Student.id).filter(Student.class_id == class_id).order_by(Student.id.asc()).all()]
    if scope == "subject":
        if subject_id is None:
            return []
        q = (
            db.query(CourseEnrollment.student_id)
            .filter(CourseEnrollment.subject_id == subject_id)
            .distinct()
        )
        return sorted({int(r[0]) for r in q.all() if r[0] is not None})
    return []


def apply_student_daily_token_overrides(
    db: Session,
    student_ids: list[int],
    daily_tokens: int,
    *,
    clear_only: bool,
) -> int:
    """
    Set or clear per-student caps. When clear_only, removes overrides for listed students.
    Returns number of students affected (rows deleted + rows upserted).
    """
    if not student_ids:
        return 0
    uniq = sorted(set(int(s) for s in student_ids))
    affected = 0
    for sid in uniq:
        existing = db.query(LLMStudentTokenOverride).filter(LLMStudentTokenOverride.student_id == sid).first()
        if clear_only:
            if existing:
                db.delete(existing)
                affected += 1
            continue
        cap = max(1, int(daily_tokens))
        if existing:
            if int(existing.daily_tokens) != cap:
                existing.daily_tokens = cap
                affected += 1
        else:
            db.add(LLMStudentTokenOverride(student_id=sid, daily_tokens=cap))
            affected += 1
    return affected
