from datetime import datetime, timezone
from types import SimpleNamespace

from apps.backend.courseeval_backend.domains.homework.submission_rules import (
    attempt_counts_toward_final_score,
    attempt_is_late,
)


def test_attempt_is_late_handles_missing_and_timezone_mixed_due_dates():
    assert attempt_is_late(SimpleNamespace(due_date=None), datetime(2026, 5, 13, 12, 0)) is False

    aware_due = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)
    assert attempt_is_late(SimpleNamespace(due_date=aware_due), datetime(2026, 5, 13, 12, 1)) is True
    assert attempt_is_late(SimpleNamespace(due_date=aware_due), datetime(2026, 5, 13, 11, 59)) is False


def test_attempt_counts_toward_final_score_follows_late_policy():
    assert attempt_counts_toward_final_score(SimpleNamespace(late_submission_affects_score=True), False) is True
    assert attempt_counts_toward_final_score(SimpleNamespace(late_submission_affects_score=True), True) is False
    assert attempt_counts_toward_final_score(SimpleNamespace(late_submission_affects_score=False), True) is True
