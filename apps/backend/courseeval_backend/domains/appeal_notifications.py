"""Shared appeal status and notification-projection helpers."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.db.models import HomeworkGradeAppeal, Notification, ScoreGradeAppeal

APPEAL_STATUS_PENDING = "pending"
APPEAL_STATUS_ACKNOWLEDGED = "acknowledged"
APPEAL_STATUS_RESOLVED = "resolved"
APPEAL_STATUS_REJECTED = "rejected"

ACTIONABLE_APPEAL_STATUSES = frozenset({APPEAL_STATUS_PENDING, APPEAL_STATUS_ACKNOWLEDGED})
READONLY_APPEAL_STATUSES = frozenset({APPEAL_STATUS_RESOLVED, APPEAL_STATUS_REJECTED})
KNOWN_APPEAL_STATUSES = ACTIONABLE_APPEAL_STATUSES | READONLY_APPEAL_STATUSES

_TITLE_PREFIX_BY_STATUS = {
    APPEAL_STATUS_ACKNOWLEDGED: "【已阅】",
    APPEAL_STATUS_RESOLVED: "【已处理】",
    APPEAL_STATUS_REJECTED: "【已拒绝】",
}

_STATUS_LABEL_ZH = {
    APPEAL_STATUS_PENDING: "待处理",
    APPEAL_STATUS_ACKNOWLEDGED: "已阅/处理中",
    APPEAL_STATUS_RESOLVED: "已处理",
    APPEAL_STATUS_REJECTED: "已拒绝",
}

_STATUS_LINE_PREFIX = "【系统状态】"


def normalize_appeal_status(status: Optional[str]) -> Optional[str]:
    if not isinstance(status, str):
        return None
    normalized = status.strip().lower()
    return normalized or None


def is_actionable_appeal_status(status: Optional[str]) -> bool:
    return normalize_appeal_status(status) in ACTIONABLE_APPEAL_STATUSES


def is_readonly_appeal_status(status: Optional[str]) -> bool:
    return normalize_appeal_status(status) in READONLY_APPEAL_STATUSES


def can_transition_score_appeal_status(
    current_status: Optional[str],
    next_status: Optional[str],
    *,
    has_teacher_response: bool,
) -> tuple[bool, Optional[str]]:
    current = normalize_appeal_status(current_status)
    nxt = normalize_appeal_status(next_status)
    if nxt not in {APPEAL_STATUS_PENDING, APPEAL_STATUS_RESOLVED, APPEAL_STATUS_REJECTED}:
        return False, "invalid_status"
    if is_readonly_appeal_status(current):
        if current == nxt:
            return True, None
        return False, "finalized"
    if nxt == APPEAL_STATUS_PENDING and has_teacher_response:
        return False, "pending_with_response"
    return True, None


def can_transition_homework_appeal_status(
    current_status: Optional[str],
    next_status: Optional[str],
) -> tuple[bool, Optional[str]]:
    current = normalize_appeal_status(current_status)
    nxt = normalize_appeal_status(next_status)
    if nxt not in KNOWN_APPEAL_STATUSES:
        return False, "invalid_status"
    if is_readonly_appeal_status(current):
        if current == nxt:
            return True, None
        return False, "finalized"
    return True, None


def strip_appeal_notification_title_prefix(title: Optional[str]) -> str:
    text = str(title or "")
    for prefix in _TITLE_PREFIX_BY_STATUS.values():
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def appeal_status_label_zh(status: Optional[str]) -> Optional[str]:
    return _STATUS_LABEL_ZH.get(normalize_appeal_status(status))


def render_appeal_notification_title(base_title: Optional[str], status: Optional[str]) -> str:
    clean_title = strip_appeal_notification_title_prefix(base_title)
    prefix = _TITLE_PREFIX_BY_STATUS.get(normalize_appeal_status(status), "")
    return f"{prefix}{clean_title}" if prefix else clean_title


def render_appeal_notification_content(content: Optional[str], status: Optional[str]) -> str:
    label = appeal_status_label_zh(status)
    lines = [line for line in str(content or "").splitlines() if not line.startswith(_STATUS_LINE_PREFIX)]
    if label:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"{_STATUS_LINE_PREFIX}{label}")
    return "\n".join(lines)


def sync_appeal_notification_projection(
    notification: Notification,
    *,
    status: Optional[str],
    content: Optional[str] = None,
) -> None:
    notification.title = render_appeal_notification_title(notification.title, status)
    if content is not None:
        notification.content = content
    notification.content = render_appeal_notification_content(notification.content, status)


def resolve_notification_appeal_status(notification: Notification, db: Session) -> Optional[str]:
    if notification.related_appeal_id is not None:
        appeal_row = (
            db.query(HomeworkGradeAppeal.status)
            .filter(HomeworkGradeAppeal.id == notification.related_appeal_id)
            .first()
        )
        return normalize_appeal_status(appeal_row[0] if appeal_row else None)

    if notification.related_score_appeal_id is not None:
        score_appeal_row = (
            db.query(ScoreGradeAppeal.status)
            .filter(ScoreGradeAppeal.id == notification.related_score_appeal_id)
            .first()
        )
        return normalize_appeal_status(score_appeal_row[0] if score_appeal_row else None)

    return None
