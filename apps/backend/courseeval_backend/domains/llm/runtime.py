from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


TRANSIENT_LLM_ERROR_CODES = frozenset(
    {
        "llm_call_failed",
        "unexpected_error",
        "transient_upstream_failure",
        "discussion_call_failed",
    }
)

PERMANENT_LLM_ERROR_CODES = frozenset(
    {
        "attempt_not_found",
        "homework_not_found",
        "auto_grading_disabled",
        "course_missing",
        "llm_config_disabled",
        "endpoint_missing",
        "no_usable_content",
        "quota_exceeded_student",
        "discussion_target_missing",
        "discussion_course_missing",
        "discussion_student_binding_missing",
        "discussion_system_user_missing",
        "discussion_permanent_failure",
    }
)

TERMINAL_HTTP_STATUS_CODES = frozenset({401, 403, 404, 413})

DEFAULT_RETRY_INITIAL_SECONDS = 60
DEFAULT_RETRY_MAX_SECONDS = 20 * 60
DEFAULT_RETRY_MAX_LIFETIME_SECONDS = 7 * 24 * 60 * 60
DEFAULT_RETRY_MULTIPLIER = 2.0

PERMANENT_ERROR_MESSAGE_SNIPPETS = frozenset(
    {
        "invalid_api_key",
        "authentication",
        "permission denied",
        "forbidden",
        "unauthorized",
        "model_not_found",
        "model not found",
        "context_length",
        "context length",
        "max_tokens",
        "max token",
        "request too large",
        "input too large",
        "unsupported_parameter",
        "unsupported parameter",
    }
)

TRANSIENT_ERROR_MESSAGE_SNIPPETS = frozenset(
    {
        "rate_limit",
        "rate limit",
        "too many requests",
        "rpm",
        "tpm",
        "slow down",
        "temporarily unavailable",
        "service unavailable",
        "timeout",
        "timed out",
        "connection reset",
        "connection refused",
        "connection aborted",
        "overloaded",
        "capacity",
        "upstream",
    }
)

_test_clock_lock = threading.Lock()
_test_clock_now: Optional[datetime] = None


@dataclass(frozen=True)
class RetryPolicy:
    initial_delay_seconds: int = DEFAULT_RETRY_INITIAL_SECONDS
    max_delay_seconds: int = DEFAULT_RETRY_MAX_SECONDS
    max_lifetime_seconds: int = DEFAULT_RETRY_MAX_LIFETIME_SECONDS
    multiplier: float = DEFAULT_RETRY_MULTIPLIER


def now_utc() -> datetime:
    with _test_clock_lock:
        if _test_clock_now is not None:
            return _test_clock_now
    return datetime.now(timezone.utc)


def ensure_utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def set_test_clock(now: Optional[datetime]) -> None:
    with _test_clock_lock:
        global _test_clock_now
        _test_clock_now = now


def advance_test_clock(delta: timedelta) -> datetime:
    with _test_clock_lock:
        global _test_clock_now
        base = _test_clock_now or datetime.now(timezone.utc)
        _test_clock_now = base + delta
        return _test_clock_now


def sleep_with_test_scaling(seconds: float) -> None:
    if seconds <= 0:
        return
    scale_raw = os.environ.get("COURSEEVAL_TEST_TIME_SCALE")
    if scale_raw:
        try:
            scale = float(scale_raw)
        except ValueError:
            scale = 1.0
        if scale > 0:
            time.sleep(seconds / scale)
            return
    if os.environ.get("LLM_GRADING_TEST_SKIP_BACKOFF") == "1":
        return
    time.sleep(seconds)


def classify_llm_error_code(
    *,
    error_code: str,
    error_message: str,
) -> str:
    code = (error_code or "").strip()
    message = (error_message or "").strip()
    message_lower = message.lower()
    if code in PERMANENT_LLM_ERROR_CODES:
        return "permanent"
    if any(f"HTTP {status}" in message for status in TERMINAL_HTTP_STATUS_CODES):
        return "permanent"
    if any(snippet in message_lower for snippet in PERMANENT_ERROR_MESSAGE_SNIPPETS):
        return "permanent"
    if code in TRANSIENT_LLM_ERROR_CODES:
        return "transient"
    if any(snippet in message_lower for snippet in TRANSIENT_ERROR_MESSAGE_SNIPPETS):
        return "transient"
    return "transient"


def compute_retry_delay_seconds(
    *,
    retry_count: int,
    policy: RetryPolicy | None = None,
) -> int:
    pol = policy or RetryPolicy()
    retry_index = max(0, int(retry_count))
    delay = float(pol.initial_delay_seconds) * (pol.multiplier ** retry_index)
    return int(min(max(1.0, delay), float(pol.max_delay_seconds)))


def compute_next_retry_at(
    *,
    retry_count: int,
    policy: RetryPolicy | None = None,
    base_time: Optional[datetime] = None,
) -> datetime:
    base = ensure_utc_datetime(base_time) or now_utc()
    return base + timedelta(seconds=compute_retry_delay_seconds(retry_count=retry_count, policy=policy))


def retry_window_exhausted(
    *,
    created_at: Optional[datetime],
    policy: RetryPolicy | None = None,
    current_time: Optional[datetime] = None,
) -> bool:
    created = ensure_utc_datetime(created_at)
    if created is None:
        return False
    pol = policy or RetryPolicy()
    now_value = ensure_utc_datetime(current_time) or now_utc()
    return (now_value - created).total_seconds() >= int(pol.max_lifetime_seconds or DEFAULT_RETRY_MAX_LIFETIME_SECONDS)
