from __future__ import annotations

from datetime import datetime

from apps.backend.courseeval_backend.db.models import Homework


def attempt_is_late(homework: Homework, submitted_at: datetime) -> bool:
    if not homework.due_date:
        return False
    due_date = homework.due_date
    if due_date.tzinfo and not submitted_at.tzinfo:
        submitted_at = submitted_at.replace(tzinfo=due_date.tzinfo)
    elif submitted_at.tzinfo and not due_date.tzinfo:
        due_date = due_date.replace(tzinfo=submitted_at.tzinfo)
    return submitted_at > due_date


def attempt_counts_toward_final_score(homework: Homework, is_late: bool) -> bool:
    return (not is_late) or (not homework.late_submission_affects_score)
