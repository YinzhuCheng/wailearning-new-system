from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.domains.roster.audit import audit_student_identity
from apps.backend.courseeval_backend.domains.roster.sync import reconcile_student_users_and_roster


BLOCKING_ISSUE_IDS = (
    "multiple_users_for_student",
    "multiple_students_for_user",
    "invalid_user_student_bindings",
)


def _summarize_planned_repairs(report: dict[str, Any]) -> dict[str, int]:
    issues = report["issues"]
    return {
        "bind_legacy_student_users": len(issues["legacy_binding_candidates"]),
        "create_students_from_student_users": len(issues["student_users_without_students"]),
        "create_student_users_from_students": len(issues["students_without_accounts"]),
    }


def _blocking_issues(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    issues = report["issues"]
    return {
        issue_id: issues[issue_id]
        for issue_id in BLOCKING_ISSUE_IDS
        if issues[issue_id]
    }


def repair_student_identity(db: Session, *, apply: bool = False) -> dict[str, Any]:
    """
    Repair new-system/default student identity data.

    This intentionally delegates mutation to the existing reconciliation path and
    blocks on ambiguous audit findings. It is not a general historical migration
    conflict resolver.
    """
    before = audit_student_identity(db)
    blocking = _blocking_issues(before)
    result: dict[str, Any] = {
        "applied": False,
        "blocked": bool(blocking),
        "planned": _summarize_planned_repairs(before),
        "blocking_issues": blocking,
        "before": before["summary"],
        "after": None,
        "reconciliation": None,
    }

    if not apply or blocking:
        return result

    reconciliation = reconcile_student_users_and_roster(db)
    db.flush()
    after = audit_student_identity(db)
    result.update(
        {
            "applied": True,
            "after": after["summary"],
            "reconciliation": reconciliation,
        }
    )
    return result
