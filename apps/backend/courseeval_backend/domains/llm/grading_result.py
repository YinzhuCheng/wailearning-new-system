from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from apps.backend.courseeval_backend.db.models import (
    Homework,
    HomeworkAttempt,
    HomeworkScoreCandidate,
    HomeworkSubmission,
)


def normalize_score_for_homework(homework: Homework, score: float | int) -> float:
    value = max(0.0, min(float(score), float(homework.max_score or 100)))
    if (homework.grade_precision or "integer") == "decimal_1":
        return round(value, 1)
    return float(round(value))


def _teacher_candidate_sort_key(candidate: HomeworkScoreCandidate) -> tuple[float, datetime]:
    """Higher score first, then newer; used only among teacher rows."""
    ts = candidate.updated_at or candidate.created_at or datetime.min.replace(tzinfo=timezone.utc)
    return (float(candidate.score or 0), ts)


def _auto_candidate_sort_key(candidate: HomeworkScoreCandidate) -> tuple[float, datetime]:
    """Among auto rows: higher score, then newer."""
    ts = candidate.updated_at or candidate.created_at or datetime.min.replace(tzinfo=timezone.utc)
    return (float(candidate.score or 0), ts)


def get_best_score_candidate(
    db: Session,
    homework_id: int,
    student_id: int,
    *,
    latest_attempt_id: Optional[int] = None,
) -> Optional[HomeworkScoreCandidate]:
    """
    Best candidate for a **single** attempt (teacher overrides auto). Signature retained for tests;
    homework_id/student_id are unused but kept for call-site compatibility.
    """
    _ = (homework_id, student_id)
    if latest_attempt_id is None:
        return None
    return pick_best_candidate_for_attempt(db, latest_attempt_id)


def attempt_eligible_for_effective_score_aggregate(homework: Homework, attempt: HomeworkAttempt) -> bool:
    """
    Attempts whose scores participate in the submission summary maximum.

    Union rule (product wording): submitted on/before due **or** ``counts_toward_final_score``.

    Under the default flags, on-time attempts always count; late attempts count only when
    ``late_submission_affects_score`` is false for the homework.
    """
    if getattr(attempt, "counts_toward_final_score", True):
        return True
    due = homework.due_date
    if due is None:
        return True
    sub = attempt.submitted_at
    if sub is None:
        return False
    due_cmp = due
    sub_cmp = sub
    if due_cmp.tzinfo and sub_cmp.tzinfo is None:
        sub_cmp = sub_cmp.replace(tzinfo=due_cmp.tzinfo)
    elif sub_cmp.tzinfo and due_cmp.tzinfo is None:
        due_cmp = due_cmp.replace(tzinfo=sub_cmp.tzinfo)
    return sub_cmp <= due_cmp


def pick_best_candidate_for_attempt(db: Session, attempt_id: int) -> Optional[HomeworkScoreCandidate]:
    """Teacher rows beat auto rows; tie-break higher score then newer ``updated_at``."""
    candidates = (
        db.query(HomeworkScoreCandidate)
        .options(joinedload(HomeworkScoreCandidate.attempt))
        .filter(HomeworkScoreCandidate.attempt_id == attempt_id)
        .all()
    )
    valid_candidates = [c for c in candidates if c.score is not None]
    if not valid_candidates:
        return None
    teacher_rows = [c for c in valid_candidates if c.source == "teacher"]
    if teacher_rows:
        return max(teacher_rows, key=_teacher_candidate_sort_key)
    auto_rows = [c for c in valid_candidates if c.source == "auto"]
    if auto_rows:
        return max(auto_rows, key=_auto_candidate_sort_key)
    return max(valid_candidates, key=_auto_candidate_sort_key)


def _candidate_wins_effective_summary(a: HomeworkScoreCandidate, b: HomeworkScoreCandidate) -> bool:
    """Whether ``a`` should replace ``b`` as the cross-attempt winner."""
    sa, sb = float(a.score or 0), float(b.score or 0)
    if sa != sb:
        return sa > sb
    ta = 1 if a.source == "teacher" else 0
    tb = 1 if b.source == "teacher" else 0
    if ta != tb:
        return ta > tb
    ta_dt = a.updated_at or a.created_at or datetime.min.replace(tzinfo=timezone.utc)
    tb_dt = b.updated_at or b.created_at or datetime.min.replace(tzinfo=timezone.utc)
    return ta_dt > tb_dt


def resolve_effective_submission_score(
    db: Session, homework: Homework, summary: HomeworkSubmission
) -> tuple[Optional[HomeworkScoreCandidate], Optional[int], Optional[int]]:
    """
    Pick the score shown on ``HomeworkSubmission`` as the max over eligible attempts.

    Returns ``(best_candidate, winning_attempt_id, winning_attempt_seq)`` where ``seq`` is 1-based
    ordering among attempts for this submission (by submit time, then id).
    """
    attempts = (
        db.query(HomeworkAttempt)
        .filter(
            HomeworkAttempt.homework_id == summary.homework_id,
            HomeworkAttempt.student_id == summary.student_id,
            HomeworkAttempt.submission_summary_id == summary.id,
        )
        .order_by(HomeworkAttempt.submitted_at.asc(), HomeworkAttempt.id.asc())
        .all()
    )
    ordinal = {att.id: idx + 1 for idx, att in enumerate(attempts)}
    best: Optional[HomeworkScoreCandidate] = None
    best_att_id: Optional[int] = None
    for att in attempts:
        if not attempt_eligible_for_effective_score_aggregate(homework, att):
            continue
        cand = pick_best_candidate_for_attempt(db, att.id)
        if cand is None:
            continue
        if best is None or _candidate_wins_effective_summary(cand, best):
            best = cand
            best_att_id = att.id
    best_seq = ordinal.get(best_att_id) if best_att_id is not None else None
    return best, best_att_id, best_seq
