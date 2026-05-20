from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.db.models import DiscussionLLMJob
from apps.backend.courseeval_backend.domains.llm.runtime import (
    RetryPolicy,
    classify_llm_error_code,
    compute_next_retry_at,
    ensure_utc_datetime,
    now_utc,
    retry_window_exhausted,
)


DISCUSSION_RETRY_POLICY = RetryPolicy()


def schedule_discussion_retry(
    db: Session,
    job: DiscussionLLMJob,
    *,
    error_code: str,
    error_message: str,
) -> str:
    failure_class = classify_llm_error_code(error_code=error_code, error_message=error_message)
    if failure_class == "transient" and retry_window_exhausted(
        created_at=job.created_at,
        policy=DISCUSSION_RETRY_POLICY,
        current_time=now_utc(),
    ):
        failure_class = "permanent"
    job.error_code = error_code
    job.error_message = error_message
    job.last_error_at = now_utc()
    job.retry_count = int(job.retry_count or 0) + 1
    job.failure_class = failure_class
    if failure_class == "transient":
        job.status = "retry_scheduled"
        job.next_retry_at = compute_next_retry_at(
            retry_count=max(0, int(job.retry_count or 1) - 1),
            policy=DISCUSSION_RETRY_POLICY,
            base_time=job.last_error_at,
        )
        job.finished_at = None
    else:
        job.status = "failed"
        job.next_retry_at = None
        job.finished_at = job.last_error_at
    db.flush()
    return failure_class


def promote_due_discussion_job(db: Session, job: DiscussionLLMJob) -> bool:
    if job.status != "retry_scheduled":
        return False
    next_retry_at = ensure_utc_datetime(job.next_retry_at)
    if next_retry_at and next_retry_at > now_utc():
        return False
    job.status = "pending"
    job.next_retry_at = None
    job.finished_at = None
    db.flush()
    return True
