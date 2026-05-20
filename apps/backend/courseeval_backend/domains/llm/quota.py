from __future__ import annotations

import hashlib
import threading
from typing import Any, Optional

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.db.database import engine
from apps.backend.courseeval_backend.db.models import (
    CourseLLMConfig,
    DiscussionLLMJob,
    HomeworkGradingTask,
    LLMDiscussionQuotaReservation,
    LLMDiscussionTokenUsageLog,
    LLMQuotaReservation,
    LLMTokenUsageLog,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.llm.token_quota import (
    resolve_effective_daily_student_tokens,
    resolve_global_quota_calendar,
)


def get_quota_usage_snapshot(db: Session, config: CourseLLMConfig) -> dict[str, Any]:
    usage_date, timezone_name = resolve_global_quota_calendar(db)
    return {
        "usage_date": usage_date,
        "quota_timezone": timezone_name,
    }


def get_student_quota_usage_snapshot(
    db: Session,
    config: Optional[CourseLLMConfig],
    *,
    student_id: int,
    subject_id: Optional[int] = None,
) -> dict[str, Any]:
    """Quota snapshot for a student. Pass ``config`` when a course row exists; otherwise pass ``subject_id`` alone."""
    usage_date, timezone_name = resolve_global_quota_calendar(db)
    lim_stu = resolve_effective_daily_student_tokens(db, student_id)
    if subject_id is not None:
        sid = int(subject_id)
    elif config is not None:
        sid = int(config.subject_id)
    else:
        raise ValueError("subject_id or config with subject_id is required")
    snap: dict[str, Any] = {
        "subject_id": sid,
        "usage_date": usage_date,
        "quota_timezone": timezone_name,
        "daily_student_token_limit": lim_stu,
        "student_used_tokens_today": None,
        "student_remaining_tokens_today": None,
    }
    used_stu = get_used_tokens_for_scope(
        db,
        usage_date=usage_date,
        timezone_name=timezone_name,
        student_id=student_id,
    )
    used_stu += sum_reserved_tokens(
        db,
        usage_date=usage_date,
        timezone_name=timezone_name,
        student_id=student_id,
    )
    snap["student_used_tokens_today"] = used_stu
    snap["student_remaining_tokens_today"] = max(0, lim_stu - used_stu)
    return snap


def homework_grading_user_is_quota_exempt(user: User | None) -> bool:
    if user is None:
        return False
    return (user.role or "").strip() in {
        UserRole.ADMIN.value,
        UserRole.TEACHER.value,
        UserRole.CLASS_TEACHER.value,
    }


def quota_delta_violations(
    db: Session,
    config: CourseLLMConfig,
    *,
    usage_date: str,
    timezone_name: str,
    student_id: int,
    subject_id: Optional[int],
    delta_tokens: int,
) -> list[str]:
    violations: list[str] = []
    lim_stu = resolve_effective_daily_student_tokens(db, student_id)
    used_by_student = get_used_tokens_for_scope(
        db,
        usage_date=usage_date,
        timezone_name=timezone_name,
        student_id=student_id,
        subject_id=subject_id,
    )
    if used_by_student + delta_tokens > lim_stu:
        violations.append("student")
    return violations


def get_used_tokens_for_scope(
    db: Session,
    *,
    usage_date: str,
    timezone_name: str,
    student_id: Optional[int] = None,
    subject_id: Optional[int] = None,
) -> int:
    query = db.query(LLMTokenUsageLog).filter(
        LLMTokenUsageLog.usage_date == usage_date,
        LLMTokenUsageLog.timezone == timezone_name,
    )
    if student_id is not None:
        query = query.filter(
            LLMTokenUsageLog.student_id == student_id,
            func.coalesce(LLMTokenUsageLog.billed_user_id, 0) == 0,
        )
    if subject_id is not None:
        query = query.filter(LLMTokenUsageLog.subject_id == subject_id)
    total = 0
    for item in query.all():
        if item.input_tokens is not None:
            total += int(item.input_tokens)
        elif item.total_tokens is not None:
            total += int(item.total_tokens)
        else:
            total += int(item.output_tokens or 0)
    dq = db.query(LLMDiscussionTokenUsageLog).filter(
        LLMDiscussionTokenUsageLog.usage_date == usage_date,
        LLMDiscussionTokenUsageLog.timezone == timezone_name,
    )
    if student_id is not None:
        dq = dq.filter(LLMDiscussionTokenUsageLog.student_id == student_id)
    if subject_id is not None:
        dq = dq.filter(LLMDiscussionTokenUsageLog.subject_id == subject_id)
    for item in dq.all():
        if item.input_tokens is not None:
            total += int(item.input_tokens)
        elif item.total_tokens is not None:
            total += int(item.total_tokens)
        else:
            total += int(item.output_tokens or 0)
    return total


def sum_reserved_tokens(
    db: Session,
    *,
    usage_date: str,
    timezone_name: str,
    student_id: Optional[int] = None,
    subject_id: Optional[int] = None,
) -> int:
    q = db.query(func.coalesce(func.sum(LLMQuotaReservation.reserved_tokens), 0)).filter(
        LLMQuotaReservation.usage_date == usage_date,
        LLMQuotaReservation.timezone == timezone_name,
    )
    if student_id is not None:
        q = q.filter(
            LLMQuotaReservation.student_id == student_id,
            func.coalesce(LLMQuotaReservation.billed_user_id, 0) == 0,
        )
    if subject_id is not None:
        q = q.filter(LLMQuotaReservation.subject_id == subject_id)
    val = q.scalar()
    total = int(val or 0)
    q2 = db.query(func.coalesce(func.sum(LLMDiscussionQuotaReservation.reserved_tokens), 0)).filter(
        LLMDiscussionQuotaReservation.usage_date == usage_date,
        LLMDiscussionQuotaReservation.timezone == timezone_name,
    )
    if student_id is not None:
        q2 = q2.filter(LLMDiscussionQuotaReservation.student_id == student_id)
    if subject_id is not None:
        q2 = q2.filter(LLMDiscussionQuotaReservation.subject_id == subject_id)
    total += int(q2.scalar() or 0)
    return total


def hash_to_pg_advisory_key(label: str) -> int:
    digest = hashlib.sha256(label.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, "big", signed=False) % (2**62)


def pg_quota_advisory_keys(
    *,
    student_id: int,
    subject_id: int,
    usage_date: str,
    timezone_name: str,
    effective_student_daily_cap: int,
) -> list[int]:
    keys: list[int] = []
    if effective_student_daily_cap and effective_student_daily_cap > 0:
        scope = f"subject|{subject_id}" if subject_id else "system"
        keys.append(
            hash_to_pg_advisory_key(
                f"llm_quota|student|{student_id}|{scope}|{usage_date}|{timezone_name}"
            )
        )
    return sorted(set(keys))


quota_serialization_lock = threading.Lock()


def release_quota_reservation(db: Session, task_id: int) -> None:
    db.query(LLMQuotaReservation).filter(LLMQuotaReservation.task_id == task_id).delete(synchronize_session=False)


def quota_precheck_in_session(
    db: Session,
    config: CourseLLMConfig,
    *,
    student_id: int,
    subject_id: Optional[int],
    estimated_tokens: int,
) -> tuple[bool, Optional[str]]:
    usage_date, timezone_name = resolve_global_quota_calendar(db)
    lim_stu = resolve_effective_daily_student_tokens(db, student_id)
    used_by_student = get_used_tokens_for_scope(
        db,
        usage_date=usage_date,
        timezone_name=timezone_name,
        student_id=student_id,
    )
    used_by_student += sum_reserved_tokens(
        db,
        usage_date=usage_date,
        timezone_name=timezone_name,
        student_id=student_id,
    )
    if used_by_student + estimated_tokens > lim_stu:
        return False, "quota_exceeded_student"
    return True, None


def precheck_quota(
    db: Session,
    config: CourseLLMConfig,
    *,
    student_id: int,
    subject_id: Optional[int],
    estimated_tokens: int,
) -> tuple[bool, Optional[str]]:
    return quota_precheck_in_session(
        db, config, student_id=student_id, subject_id=subject_id or config.subject_id, estimated_tokens=estimated_tokens
    )


def reserve_quota_tokens(
    db: Session,
    task: HomeworkGradingTask,
    config: CourseLLMConfig,
    estimated_tokens: int,
) -> tuple[bool, Optional[str]]:
    usage_date, timezone_name = resolve_global_quota_calendar(db)
    billed_user = None
    if task.billed_user_id:
        billed_user = db.query(User).filter(User.id == task.billed_user_id).first()
    quota_exempt = homework_grading_user_is_quota_exempt(billed_user)

    def _try_insert_reservation(sess: Session) -> tuple[bool, Optional[str]]:
        release_quota_reservation(sess, task.id)
        if not quota_exempt:
            ok, err = quota_precheck_in_session(
                sess,
                config,
                student_id=task.student_id,
                subject_id=task.subject_id,
                estimated_tokens=estimated_tokens,
            )
            if not ok:
                return ok, err
        sess.add(
            LLMQuotaReservation(
                task_id=task.id,
                student_id=task.student_id,
                subject_id=task.subject_id,
                billed_user_id=task.billed_user_id,
                usage_date=usage_date,
                timezone=timezone_name,
                reserved_tokens=int(estimated_tokens),
            )
        )
        sess.flush()
        return True, None

    if quota_exempt:
        return _try_insert_reservation(db)

    if engine.dialect.name == "postgresql":
        keys = pg_quota_advisory_keys(
            student_id=task.student_id,
            subject_id=0,
            usage_date=usage_date,
            timezone_name=timezone_name,
            effective_student_daily_cap=resolve_effective_daily_student_tokens(db, task.student_id),
        )
        with engine.begin() as conn:
            for k in keys:
                conn.execute(text("SELECT pg_advisory_xact_lock(CAST(:k AS BIGINT))"), {"k": k})
            inner = Session(bind=conn, autoflush=False, autocommit=False)
            try:
                ok, err = _try_insert_reservation(inner)
                if not ok:
                    return ok, err
            except IntegrityError:
                return True, None
            finally:
                inner.close()
        return True, None

    with quota_serialization_lock:
        return _try_insert_reservation(db)


def record_usage_if_needed(
    db: Session,
    task: HomeworkGradingTask,
    config: CourseLLMConfig,
    usage: dict[str, Any],
) -> None:
    existing = db.query(LLMTokenUsageLog).filter(LLMTokenUsageLog.task_id == task.id).first()
    if existing:
        return
    release_quota_reservation(db, task.id)
    usage_date, timezone_name = resolve_global_quota_calendar(db)
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    if total_tokens is None:
        total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
    billing_note: Optional[str] = None
    prompt_for_quota = int(prompt_tokens or 0)
    violations = quota_delta_violations(
        db,
        config,
        usage_date=usage_date,
        timezone_name=timezone_name,
        student_id=task.student_id,
        subject_id=None,
        delta_tokens=prompt_for_quota,
    )
    if violations:
        billing_note = "over_daily_limit:" + ",".join(violations)

    db.add(
        LLMTokenUsageLog(
            task_id=task.id,
            subject_id=task.subject_id,
            student_id=task.student_id,
            billed_user_id=task.billed_user_id,
            usage_date=usage_date,
            timezone=timezone_name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=total_tokens,
            billing_note=billing_note,
        )
    )
    task.billed_input_tokens = prompt_tokens
    task.billed_output_tokens = completion_tokens
    task.billed_total_tokens = total_tokens


def release_discussion_quota_reservation(db: Session, job_id: int) -> None:
    db.query(LLMDiscussionQuotaReservation).filter(LLMDiscussionQuotaReservation.job_id == job_id).delete(
        synchronize_session=False
    )


def reserve_discussion_quota_tokens(
    db: Session,
    job: DiscussionLLMJob,
    config: CourseLLMConfig,
    *,
    student_id: int,
    subject_id: int,
    estimated_tokens: int,
) -> tuple[bool, Optional[str]]:
    usage_date, timezone_name = resolve_global_quota_calendar(db)

    def _try_insert(sess: Session) -> tuple[bool, Optional[str]]:
        release_discussion_quota_reservation(sess, job.id)
        ok, err = quota_precheck_in_session(
            sess,
            config,
            student_id=student_id,
            subject_id=subject_id,
            estimated_tokens=estimated_tokens,
        )
        if not ok:
            return ok, err
        sess.add(
            LLMDiscussionQuotaReservation(
                job_id=job.id,
                student_id=student_id,
                subject_id=subject_id,
                usage_date=usage_date,
                timezone=timezone_name,
                reserved_tokens=int(estimated_tokens),
            )
        )
        sess.flush()
        return True, None

    if engine.dialect.name == "postgresql":
        keys = pg_quota_advisory_keys(
            student_id=student_id,
            subject_id=0,
            usage_date=usage_date,
            timezone_name=timezone_name,
            effective_student_daily_cap=resolve_effective_daily_student_tokens(db, student_id),
        )
        with engine.begin() as conn:
            for k in keys:
                conn.execute(text("SELECT pg_advisory_xact_lock(CAST(:k AS BIGINT))"), {"k": k})
            inner = Session(bind=conn, autoflush=False, autocommit=False)
            try:
                ok, err = _try_insert(inner)
                if not ok:
                    return ok, err
            except IntegrityError:
                return True, None
            finally:
                inner.close()
        return True, None

    with quota_serialization_lock:
        return _try_insert(db)


def record_discussion_usage_if_needed(
    db: Session,
    job: DiscussionLLMJob,
    config: CourseLLMConfig,
    student_id: int,
    subject_id: int,
    usage: dict[str, Any],
) -> None:
    existing = db.query(LLMDiscussionTokenUsageLog).filter(LLMDiscussionTokenUsageLog.job_id == job.id).first()
    if existing:
        return
    release_discussion_quota_reservation(db, job.id)
    usage_date, timezone_name = resolve_global_quota_calendar(db)
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    if total_tokens is None:
        total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
    billing_note: Optional[str] = None
    prompt_for_quota = int(prompt_tokens or 0)
    violations = quota_delta_violations(
        db,
        config,
        usage_date=usage_date,
        timezone_name=timezone_name,
        student_id=student_id,
        subject_id=None,
        delta_tokens=prompt_for_quota,
    )
    if violations:
        billing_note = "over_daily_limit:" + ",".join(violations)

    db.add(
        LLMDiscussionTokenUsageLog(
            job_id=job.id,
            subject_id=subject_id,
            student_id=student_id,
            usage_date=usage_date,
            timezone=timezone_name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=total_tokens,
            billing_note=billing_note,
        )
    )
