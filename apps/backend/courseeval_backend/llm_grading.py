from __future__ import annotations

import logging
import os
import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
import tiktoken
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from apps.backend.courseeval_backend.domains.homework.notifications import notify_student_homework_graded
from apps.backend.courseeval_backend.domains.homework.appeals import mark_appeal_notifications_resolved
from apps.backend.courseeval_backend.domains.text_content_format import body_text_for_grading_llm
from apps.backend.courseeval_backend.markdown_llm import append_markdown_with_dataurl_images_to_parts
from apps.backend.courseeval_backend.domains.llm.attachments import (
    ITERATION_CONTEXT_MAX_PRIOR_ATTEMPTS,
    ITERATION_PRIOR_COMMENT_CHAR_MAX,
    ITERATION_PRIOR_NOTE_CHAR_MAX,
    MAX_ZIP_DEPTH,
    MAX_ZIP_FILES,
    MAX_ZIP_TOTAL_BYTES,
    MaterialBlock,
    VISION_TEST_IMAGE_DATA_URL,
    _classify_and_extract,
    _collect_attachment_blocks,
    _truncate_text,
    _walk_rar_bytes,
    _walk_zip_bytes,
    build_png_data_url_from_image_bytes,
)


from apps.backend.courseeval_backend.domains.llm.protocol import (
    NON_RETRYABLE_STATUS_CODES,
    RETRYABLE_STATUS_CODES,
    build_chat_completion_url as _build_chat_completion_url,
    extract_message_content as _extract_message_content,
    parse_scoring_json as _parse_scoring_json,
    redact_endpoint_host as _redact_endpoint_host,
)
from apps.backend.courseeval_backend.domains.llm.quota import (
    get_quota_usage_snapshot,
    get_student_quota_usage_snapshot,
    get_used_tokens_for_scope as _get_used_tokens_for_scope,
    precheck_quota,
    record_usage_if_needed,
    release_quota_reservation,
    reserve_quota_tokens,
)
from apps.backend.courseeval_backend.domains.llm.grading_prompt import (
    SECTION_ASSIGNMENT,
    SECTION_ATTACHMENT,
    SECTION_IMAGES,
    SECTION_NOTES,
    SECTION_PRIOR_SUBMISSION,
    SECTION_STUDENT_BODY,
    comment_format_system_suffix,
    expand_homework_field_for_llm,
    llm_assist_assignment_addendum,
)
from apps.backend.courseeval_backend.domains.llm.grading_result import (
    attempt_eligible_for_effective_score_aggregate,
    get_best_score_candidate,
    normalize_score_for_homework,
    pick_best_candidate_for_attempt,
    resolve_effective_submission_score,
)
from apps.backend.courseeval_backend.domains.llm.token_quota import (
    quota_calendar_for_timezone,
    resolve_effective_daily_student_tokens,
    resolve_global_estimated_chars_per_token,
    resolve_global_estimated_image_tokens,
    resolve_max_parallel_grading_tasks,
)
from apps.backend.courseeval_backend.domains.llm.runtime import (
    RetryPolicy,
    classify_llm_error_code,
    compute_next_retry_at,
    ensure_utc_datetime,
    now_utc,
    retry_window_exhausted,
    sleep_with_test_scaling,
)


from sqlalchemy.orm import Session, joinedload

from apps.backend.courseeval_backend.core.config import settings
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.domains.llm.routing import GroupRoutingContext
from apps.backend.courseeval_backend.db.models import (
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    DiscussionLLMJob,
    Homework,
    HomeworkAttempt,
    HomeworkGradeAppeal,
    HomeworkGradingTask,
    HomeworkScoreCandidate,
    HomeworkSubmission,
    LLMEndpointPreset,
    LLMGroup,
)

_LLM_CALL_LOG_MAX_EVENTS = 60
UNLIMITED_OUTPUT_TOKEN_SENTINEL = 32768
_LLM_TASK_RETRY_POLICY = RetryPolicy()
_CLAIM_FAIRNESS_WINDOW_SECONDS = 1.0


from apps.backend.courseeval_backend.domains.llm.errors import NonRetryableLLMError, RetryableLLMError


logger = logging.getLogger(__name__)


class _WorkerManager:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._executor_workers: int = 0

    def start(self) -> None:
        if not settings.ENABLE_LLM_GRADING_WORKER:
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="llm-grading-worker", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        with self._lock:
            if self._executor:
                self._executor.shutdown(wait=False)
                self._executor = None
                self._executor_workers = 0
            self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=1.0)

    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive() and not self._stop_event.is_set())

    def _ensure_executor(self, workers: int) -> ThreadPoolExecutor:
        w = max(1, int(workers))
        if self._executor is not None and self._executor_workers == w:
            return self._executor
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
        self._executor = ThreadPoolExecutor(max_workers=w, thread_name_prefix="llm-grade")
        self._executor_workers = w
        return self._executor

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                db = SessionLocal()
                try:
                    cap = resolve_max_parallel_grading_tasks(db)
                finally:
                    db.close()
                claimed = claim_grading_tasks_batch(cap)
                _drain_due_discussion_jobs(cap)
                if not claimed:
                    self._stop_event.wait(settings.LLM_GRADING_WORKER_POLL_SECONDS)
                    continue
                ex = self._ensure_executor(cap)
                futs = [ex.submit(process_grading_task, tid) for tid in claimed]
                wait(futs)
                for tid, fut in zip(claimed, futs):
                    try:
                        fut.result()
                    except Exception as exc:
                        logger.exception("LLM grading task error task_id=%s", tid)
                        _mark_task_failed_from_worker_executor(tid, exc)
            except Exception as exc:
                logger.exception("LLM grading worker loop error")
                self._stop_event.wait(settings.LLM_GRADING_WORKER_POLL_SECONDS)


worker_manager = _WorkerManager()

# Serialize grading for a single task id in-process (duplicate worker wakeups / tests).
_task_grading_locks: dict[int, threading.Lock] = {}
_task_grading_locks_mutex = threading.Lock()


def _grading_lock_for_task(task_id: int) -> threading.Lock:
    with _task_grading_locks_mutex:
        if task_id not in _task_grading_locks:
            _task_grading_locks[task_id] = threading.Lock()
        return _task_grading_locks[task_id]


def start_grading_worker() -> None:
    worker_manager.start()


def _now_utc() -> datetime:
    return now_utc()


def effective_score_display_zh(homework: Homework, seq: Optional[int]) -> str:
    """Student/teacher facing explanation for the aggregate homework score rule."""
    late_line = (
        "若启用「迟交影响评分」，迟交提交不参与「有效成绩」比较（仍会保留批改与记录）；"
        "若关闭该选项，迟交与准时提交一并参与比较。"
    )
    core = (
        "「有效成绩」：在作业截止时间或之前提交的尝试，以及虽已迟交但仍计入总评的尝试（见课程设置）之中，取得分最高者作为列表与汇总中显示的分数。"
    )
    if seq is None:
        return core + late_line + " 当前尚无符合条件的得分记录。"
    return (
        core
        + late_line
        + f" 当前显示的分数来自第 {seq} 次提交；下方正文与附件仍为最近一次上传的内容。"
    )


def refresh_submission_summary(db: Session, summary: HomeworkSubmission) -> HomeworkSubmission:
    homework = db.query(Homework).filter(Homework.id == summary.homework_id).first()
    best_candidate: Optional[HomeworkScoreCandidate] = None
    win_attempt_id: Optional[int] = None
    win_seq: Optional[int] = None
    if homework:
        best_candidate, win_attempt_id, win_seq = resolve_effective_submission_score(db, homework, summary)
    summary.review_score = best_candidate.score if best_candidate else None
    summary.review_comment = (best_candidate.comment or None) if best_candidate else None
    setattr(summary, "_effective_win_attempt_id", win_attempt_id)
    setattr(summary, "_effective_win_attempt_seq", win_seq)

    if summary.latest_attempt_id:
        latest_attempt = (
            db.query(HomeworkAttempt)
            .filter(HomeworkAttempt.id == summary.latest_attempt_id)
            .first()
        )
        if latest_attempt:
            summary.content = latest_attempt.content
            summary.content_format = getattr(latest_attempt, "content_format", None) or "markdown"
            summary.attachment_name = latest_attempt.attachment_name
            summary.attachment_url = latest_attempt.attachment_url
            summary.submitted_at = latest_attempt.submitted_at
            latest_task = (
                db.query(HomeworkGradingTask)
                .filter(HomeworkGradingTask.attempt_id == latest_attempt.id)
                .order_by(HomeworkGradingTask.created_at.desc(), HomeworkGradingTask.id.desc())
                .first()
            )
            summary.latest_task_status = latest_task.status if latest_task else None
            err_task = latest_task
            if latest_task and latest_task.status in ("queued", "processing"):
                prev_failed = (
                    db.query(HomeworkGradingTask)
                    .filter(
                        HomeworkGradingTask.attempt_id == latest_attempt.id,
                        HomeworkGradingTask.status == "failed",
                        HomeworkGradingTask.id < latest_task.id,
                    )
                    .order_by(HomeworkGradingTask.id.desc())
                    .first()
                )
                if prev_failed:
                    err_task = prev_failed
            summary.latest_task_error = err_task.error_message if err_task else None
    return summary


def _course_has_any_endpoint_row(db: Session, config_id: int) -> bool:
    return (
        db.query(CourseLLMConfigEndpoint.id)
        .filter(CourseLLMConfigEndpoint.config_id == config_id)
        .first()
        is not None
    )


def _pick_latest_validated_course_llm_template(
    db: Session, *, exclude_subject_id: Optional[int] = None
) -> Optional[CourseLLMConfig]:
    """Another course's LLM row with at least one vision-validated active endpoint, most recently updated first."""
    subq = (
        db.query(CourseLLMConfigEndpoint.config_id)
        .join(LLMEndpointPreset, LLMEndpointPreset.id == CourseLLMConfigEndpoint.preset_id)
        .filter(
            LLMEndpointPreset.is_active.is_(True),
            LLMEndpointPreset.validation_status == "validated",
            LLMEndpointPreset.supports_vision.is_(True),
        )
    )
    ok_ids = [int(r[0]) for r in subq.distinct().all() if r[0] is not None]
    if not ok_ids:
        return None
    q = (
        db.query(CourseLLMConfig)
        .options(
            joinedload(CourseLLMConfig.groups).joinedload(LLMGroup.members),
            joinedload(CourseLLMConfig.endpoints),
        )
        .filter(CourseLLMConfig.id.in_(ok_ids))
    )
    if exclude_subject_id is not None:
        q = q.filter(CourseLLMConfig.subject_id != exclude_subject_id)
    return q.order_by(CourseLLMConfig.updated_at.desc().nullslast(), CourseLLMConfig.id.desc()).first()


def _copy_course_llm_from_template(db: Session, target: CourseLLMConfig, template: CourseLLMConfig) -> None:
    """Replace target endpoints/groups with template's validated routing and course-owned tuning fields."""
    target.is_enabled = bool(template.is_enabled)
    target.response_language = template.response_language
    target.max_input_tokens = template.max_input_tokens
    target.max_output_tokens = template.max_output_tokens
    target.system_prompt = template.system_prompt
    target.teacher_prompt = template.teacher_prompt

    db.query(CourseLLMConfigEndpoint).filter(CourseLLMConfigEndpoint.config_id == target.id).delete(
        synchronize_session=False
    )
    db.query(LLMGroup).filter(LLMGroup.config_id == target.id).delete(synchronize_session=False)
    db.flush()

    template = (
        db.query(CourseLLMConfig)
        .options(
            joinedload(CourseLLMConfig.groups).joinedload(LLMGroup.members).joinedload(CourseLLMConfigEndpoint.preset),
            joinedload(CourseLLMConfig.endpoints).joinedload(CourseLLMConfigEndpoint.preset),
        )
        .filter(CourseLLMConfig.id == template.id)
        .first()
    )
    if not template:
        return

    group_rows = sorted([g for g in (template.groups or []) if g is not None], key=lambda row: (row.priority, row.id))
    if group_rows and any((g.members or []) for g in group_rows):
        for gi, g_src in enumerate(group_rows):
            g_new = LLMGroup(config_id=target.id, priority=gi + 1, name=(g_src.name or "").strip() or f"group {gi + 1}")
            db.add(g_new)
            db.flush()
            for mj, m_src in enumerate(sorted(g_src.members or [], key=lambda row: (row.priority, row.id))):
                pr = m_src.preset
                if not pr:
                    continue
                ok, _ = _preset_eligible_for_grading(pr, need_vision=True)
                if not ok:
                    continue
                db.add(
                    CourseLLMConfigEndpoint(
                        config_id=target.id,
                        group_id=g_new.id,
                        preset_id=m_src.preset_id,
                        priority=mj + 1,
                    )
                )
        db.flush()
        if _course_has_any_endpoint_row(db, target.id):
            return
        db.query(CourseLLMConfigEndpoint).filter(CourseLLMConfigEndpoint.config_id == target.id).delete(
            synchronize_session=False
        )
        db.query(LLMGroup).filter(LLMGroup.config_id == target.id).delete(synchronize_session=False)
        db.flush()

    for item in sorted(template.endpoints or [], key=lambda row: (row.priority, row.id)):
        pr = item.preset
        if not pr:
            continue
        ok, _ = _preset_eligible_for_grading(pr, need_vision=True)
        if not ok:
            continue
        db.add(
            CourseLLMConfigEndpoint(
                config_id=target.id,
                group_id=None,
                preset_id=item.preset_id,
                priority=item.priority,
            )
        )
    db.flush()


def sync_latest_validated_course_llm_template(db: Session, target: CourseLLMConfig) -> bool:
    """If target has no endpoints, clone from the latest validated peer course config. Returns True if cloned."""
    if _course_has_any_endpoint_row(db, target.id):
        return False
    tmpl = _pick_latest_validated_course_llm_template(db, exclude_subject_id=target.subject_id)
    if not tmpl or tmpl.id == target.id:
        return False
    _copy_course_llm_from_template(db, target, tmpl)
    return _course_has_any_endpoint_row(db, target.id)


def purge_invalid_course_llm_endpoints(db: Session, config: CourseLLMConfig) -> int:
    """
    Remove course endpoint rows whose preset is missing or no longer passes course eligibility (vision).
    Returns count of removed endpoint rows.
    """
    removed = 0
    for ep in (
        db.query(CourseLLMConfigEndpoint)
        .filter(CourseLLMConfigEndpoint.config_id == config.id)
        .all()
    ):
        pr = ep.preset
        if not pr:
            db.delete(ep)
            removed += 1
            continue
        ok, _ = _preset_eligible_for_grading(pr, need_vision=True)
        if not ok:
            db.delete(ep)
            removed += 1
    if removed:
        db.flush()
        for g in db.query(LLMGroup).filter(LLMGroup.config_id == config.id).all():
            if not db.query(CourseLLMConfigEndpoint).filter(CourseLLMConfigEndpoint.group_id == g.id).first():
                db.delete(g)
        db.flush()
    return removed


def purge_invalid_course_llm_endpoints_for_preset(db: Session, preset_id: int) -> None:
    """After a preset fails validation or is deactivated, strip it from all course configs."""
    config_ids = [
        int(r[0])
        for r in db.query(CourseLLMConfigEndpoint.config_id)
        .filter(CourseLLMConfigEndpoint.preset_id == preset_id)
        .distinct()
        .all()
        if r[0] is not None
    ]
    for cid in config_ids:
        cfg = db.query(CourseLLMConfig).filter(CourseLLMConfig.id == cid).first()
        if cfg:
            purge_invalid_course_llm_endpoints(db, cfg)


def _find_session_course_llm_config(db: Session, subject_id: int) -> Optional[CourseLLMConfig]:
    for obj in tuple(db.identity_map.values()) + tuple(db.new):
        if isinstance(obj, CourseLLMConfig) and getattr(obj, "subject_id", None) == subject_id:
            return obj
    return None


def ensure_course_llm_config(db: Session, subject_id: int, user_id: Optional[int] = None) -> CourseLLMConfig:
    config = _find_session_course_llm_config(db, subject_id)
    if not config:
        config = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == subject_id).first()
    created = False
    if not config:
        try:
            with db.begin_nested():
                config = CourseLLMConfig(
                    subject_id=subject_id,
                    created_by=user_id,
                    updated_by=user_id,
                    max_output_tokens=UNLIMITED_OUTPUT_TOKEN_SENTINEL,
                )
                db.add(config)
                db.flush()
                created = True
        except IntegrityError:
            config = _find_session_course_llm_config(db, subject_id)
            if not config:
                config = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == subject_id).first()
        if not config:
            raise RuntimeError(f"Failed to initialize course LLM config for subject {subject_id}.")
    if created or not _course_has_any_endpoint_row(db, config.id):
        sync_latest_validated_course_llm_template(db, config)
    purge_invalid_course_llm_endpoints(db, config)
    if not _course_has_any_endpoint_row(db, config.id):
        sync_latest_validated_course_llm_template(db, config)
    for g in db.query(LLMGroup).filter(LLMGroup.config_id == config.id).all():
        if not db.query(CourseLLMConfigEndpoint).filter(CourseLLMConfigEndpoint.group_id == g.id).first():
            db.delete(g)
    db.flush()
    return config


def build_task_summary(task: HomeworkGradingTask) -> str:
    status_map = {
        "queued": "排队中",
        "processing": "处理中",
        "success": "成功",
        "failed": "失败",
    }
    status_label = status_map.get(task.status, task.status)
    if task.error_message:
        return f"{status_label}: {task.error_message}"
    return status_label


def _reclaim_stale_processing_tasks(db: Session) -> int:
    stale_before = _now_utc() - timedelta(seconds=max(60, int(settings.LLM_GRADING_TASK_STALE_SECONDS or 600)))
    stale_tasks = (
        db.query(HomeworkGradingTask)
        .filter(
            HomeworkGradingTask.status == "processing",
            HomeworkGradingTask.updated_at.isnot(None),
            HomeworkGradingTask.updated_at < stale_before,
        )
        .all()
    )
    reclaimed = 0
    for task in stale_tasks:
        task.status = "queued"
        task.error_code = None
        task.error_message = None
        task.failure_class = None
        task.queue_reason = "reclaimed_stale_processing"
        task.task_summary = "已回收超时任务，等待重试"
        task.started_at = None
        task.finished_at = None
        task.next_retry_at = None
        task.updated_at = _now_utc()
        reclaimed += 1
    if reclaimed:
        db.commit()
    return reclaimed


def queue_grading_task(
    db: Session,
    attempt: HomeworkAttempt,
    queue_reason: str = "new_submission",
    billed_user_id: int | None = None,
) -> HomeworkGradingTask:
    def _sync_submission_summary(task: HomeworkGradingTask, *, force_queued: bool = False) -> None:
        summary = (
            db.query(HomeworkSubmission)
            .filter(
                HomeworkSubmission.homework_id == attempt.homework_id,
                HomeworkSubmission.student_id == attempt.student_id,
            )
            .first()
        )
        if summary:
            summary.latest_task_status = "queued" if force_queued else task.status
            summary.latest_task_error = task.error_message
            refresh_submission_summary(db, summary)

    existing_task = (
        db.query(HomeworkGradingTask)
        .filter(
            HomeworkGradingTask.attempt_id == attempt.id,
            HomeworkGradingTask.status.in_(("queued", "processing", "retry_scheduled")),
        )
        .order_by(HomeworkGradingTask.created_at.desc(), HomeworkGradingTask.id.desc())
        .first()
    )
    if existing_task:
        existing_billed_user_id = getattr(existing_task, "billed_user_id", None)
        allow_billing_owner_reuse = existing_task.status in ("queued", "retry_scheduled")
        if billed_user_id is not None:
            if existing_billed_user_id is not None and int(existing_billed_user_id) != int(billed_user_id):
                existing_task = None
            elif existing_billed_user_id is None and queue_reason != "new_submission" and not allow_billing_owner_reuse:
                existing_task = None
        if existing_task is not None:
            if allow_billing_owner_reuse and billed_user_id is not None and (
                existing_billed_user_id is None or int(existing_billed_user_id) != int(billed_user_id)
            ):
                existing_task.billed_user_id = billed_user_id
                existing_task.updated_at = _now_utc()
            if existing_task.status == "retry_scheduled":
                existing_task.status = "queued"
                existing_task.queue_reason = queue_reason
                existing_task.next_retry_at = None
                existing_task.error_code = None
                existing_task.error_message = None
                existing_task.failure_class = None
                existing_task.finished_at = None
                existing_task.updated_at = _now_utc()
            _sync_submission_summary(existing_task, force_queued=existing_task.status == "queued")
            return existing_task

    task = HomeworkGradingTask(
        attempt_id=attempt.id,
        homework_id=attempt.homework_id,
        student_id=attempt.student_id,
        subject_id=attempt.subject_id,
        billed_user_id=billed_user_id,
        status="queued",
        queue_reason=queue_reason,
    )
    db.add(task)
    db.flush()
    _sync_submission_summary(task, force_queued=True)
    return task


def _append_llm_call_log(task: HomeworkGradingTask, event: dict[str, Any]) -> None:
    if not isinstance(task.artifact_manifest, dict):
        task.artifact_manifest = {}
    log = task.artifact_manifest.get("llm_call_log")
    if not isinstance(log, list):
        log = []
    event = {**event, "ts": _now_utc().isoformat()}
    log.append(event)
    if len(log) > _LLM_CALL_LOG_MAX_EVENTS:
        log = log[-_LLM_CALL_LOG_MAX_EVENTS :]
    task.artifact_manifest["llm_call_log"] = log
    flag_modified(task, "artifact_manifest")


def _flag_artifact_manifest_modified(task: HomeworkGradingTask) -> None:
    """JSON columns need explicit dirty flag when mutating nested dicts in place."""
    flag_modified(task, "artifact_manifest")


def _material_needs_vision(material: dict[str, Any]) -> bool:
    for block in material.get("student_blocks") or []:
        if getattr(block, "block_type", None) == "image":
            return True
    return False


def _preset_text_ready(preset: Optional[LLMEndpointPreset]) -> bool:
    if not preset or not preset.is_active:
        return False
    if preset.validation_status != "validated":
        return False
    ts = getattr(preset, "text_validation_status", None)
    if ts == "failed":
        return False
    # Legacy rows may only set validation_status; treat unknown as OK if overall validated.
    return ts in (None, "passed", "skipped")


def _preset_eligible_for_grading(preset: Optional[LLMEndpointPreset], *, need_vision: bool) -> tuple[bool, str]:
    if not preset:
        return False, "端点预设不存在。"
    if not preset.is_active:
        return False, f"端点「{preset.name}」已停用。"
    if preset.validation_status != "validated":
        return False, f"端点「{preset.name}」未通过整体校验（状态：{preset.validation_status}）。"
    if not _preset_text_ready(preset):
        msg = getattr(preset, "text_validation_message", None) or "未通过纯文本连通性测试"
        return False, f"端点「{preset.name}」{msg}。"
    if need_vision:
        if not preset.supports_vision:
            return False, f"端点「{preset.name}」未声明支持视觉，无法处理含图片/PDF 的提交。"
        vs = getattr(preset, "vision_validation_status", None)
        if vs == "failed":
            vm = getattr(preset, "vision_validation_message", None) or "视觉连通性未通过"
            return False, f"端点「{preset.name}」{vm}。"
        if vs not in (None, "passed", "skipped"):
            vm = getattr(preset, "vision_validation_message", None) or "视觉连通性未通过"
            return False, f"端点「{preset.name}」{vm}。"
    return True, ""


def _homework_routing_warnings(db: Session, homework: Homework, config: CourseLLMConfig) -> list[str]:
    """Return user-facing warnings when homework.llm_routing_spec may diverge from course defaults."""
    spec = homework.llm_routing_spec
    if not spec or not isinstance(spec, dict):
        return []
    mode = spec.get("mode")
    warnings: list[str] = []
    if mode == "latest_passing_validated":
        preset = (
            db.query(LLMEndpointPreset)
            .filter(
                LLMEndpointPreset.is_active.is_(True),
                LLMEndpointPreset.validation_status == "validated",
                LLMEndpointPreset.text_validation_status == "passed",
            )
            .order_by(LLMEndpointPreset.validated_at.desc().nullslast(), LLMEndpointPreset.id.desc())
            .first()
        )
        if not preset:
            warnings.append("作业要求使用「最新纯文本测试通过」的端点，但系统中没有符合条件的预设，已按课程设置路由。")
            return warnings
        bound_ids = {m.preset_id for g in (config.groups or []) for m in (g.members or [])}
        bound_ids |= {e.preset_id for e in (config.endpoints or [])}
        if preset.id not in bound_ids:
            warnings.append(
                f"作业要求优先使用「{preset.name}」，但该预设未加入本课程的 LLM 配置，调用仍可能失败。"
            )
    if mode == "limit_to_preset_ids":
        raw_ids = spec.get("preset_ids")
        if isinstance(raw_ids, list) and raw_ids:
            id_set: set[int] = set()
            for x in raw_ids:
                try:
                    id_set.add(int(x))
                except (TypeError, ValueError):
                    continue
            if id_set:
                any_hit = any(
                    m.preset_id in id_set for g in (config.groups or []) for m in (g.members or [])
                ) or any(e.preset_id in id_set for e in (config.endpoints or []))
                if not any_hit:
                    warnings.append("作业限制了端点预设，但与课程设置无交集，已回退为课程完整路由。")
    return warnings


def _filter_course_links_for_homework(
    homework: Homework,
    group_rows: list[LLMGroup],
    flat_endpoints: list[CourseLLMConfigEndpoint],
) -> tuple[list[Any], list[CourseLLMConfigEndpoint], list[str]]:
    """Apply homework.llm_routing_spec (preset subset) without mutating ORM collections."""
    from types import SimpleNamespace

    spec = homework.llm_routing_spec
    notes: list[str] = []
    if not spec or not isinstance(spec, dict):
        return group_rows, flat_endpoints, notes

    mode = spec.get("mode")
    if mode != "limit_to_preset_ids":
        return group_rows, flat_endpoints, notes

    raw_ids = spec.get("preset_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        return group_rows, flat_endpoints, notes
    id_set: set[int] = set()
    for x in raw_ids:
        try:
            id_set.add(int(x))
        except (TypeError, ValueError):
            continue
    if not id_set:
        return group_rows, flat_endpoints, notes

    ephemeral_groups: list[Any] = []
    for g in sorted(group_rows, key=lambda x: (x.priority, x.id)):
        members = [m for m in (g.members or []) if m.preset_id in id_set]
        if members:
            ephemeral_groups.append(
                SimpleNamespace(id=g.id, priority=g.priority, name=getattr(g, "name", None), members=members)
            )
    new_flat = [e for e in flat_endpoints if e.preset_id in id_set]
    if ephemeral_groups:
        notes.append("routing_mode:limit_to_preset_ids(groups)")
        return ephemeral_groups, [], notes
    if new_flat:
        notes.append("routing_mode:limit_to_preset_ids(flat)")
        return [], new_flat, notes
    notes.append("routing_mode:limit_to_preset_ids_miss")
    return group_rows, flat_endpoints, notes


def validate_text_connectivity(
    base_url: str,
    api_key: str,
    model_name: str,
    connect_timeout_seconds: int,
    read_timeout_seconds: int,
) -> tuple[bool, str]:
    """OpenAI-style chat: text-only smoke test before multimodal check."""
    timeout = httpx.Timeout(connect=connect_timeout_seconds, read=read_timeout_seconds, write=read_timeout_seconds, pool=connect_timeout_seconds)
    messages = [
        {
            "role": "user",
            "content": "Please reply with the single word: OK",
        }
    ]
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 8,
    }
    endpoint_url = _build_chat_completion_url(base_url)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                endpoint_url,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        return False, f"纯文本连通性校验失败：{exc}"

    if response.status_code >= 400:
        return False, f"纯文本连通性校验失败：HTTP {response.status_code} {response.text[:300]}"

    try:
        data = response.json()
    except ValueError:
        return False, "纯文本连通性校验失败：返回内容不是 JSON。"

    content = _extract_message_content(data)
    if not content.strip():
        return False, "纯文本连通性校验失败：模型未返回可读文本。"

    return True, "纯文本请求校验通过。"


def validate_vision_connectivity(
    base_url: str,
    api_key: str,
    model_name: str,
    connect_timeout_seconds: int,
    read_timeout_seconds: int,
    image_data_url: Optional[str] = None,
) -> tuple[bool, str]:
    if image_data_url and not (image_data_url.startswith("data:image/") and "base64," in image_data_url):
        return False, "视觉能力校验失败：图片数据格式无效（需为 data:image/...;base64,...）。"
    data_url = image_data_url or VISION_TEST_IMAGE_DATA_URL
    timeout = httpx.Timeout(connect=connect_timeout_seconds, read=read_timeout_seconds, write=read_timeout_seconds, pool=connect_timeout_seconds)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Please reply with OK."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 5,
    }

    endpoint_url = _build_chat_completion_url(base_url)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                endpoint_url,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        return False, f"视觉能力校验失败：{exc}"

    if response.status_code >= 400:
        return False, f"视觉能力校验失败：HTTP {response.status_code} {response.text[:300]}"

    try:
        data = response.json()
    except ValueError:
        return False, "视觉能力校验失败：返回内容不是 JSON。"

    content = _extract_message_content(data)
    if not content.strip():
        return False, "视觉能力校验失败：模型未返回可读文本。"

    return True, "多模态（图像）输入校验通过。"


def validate_endpoint_connectivity(
    base_url: str,
    api_key: str,
    model_name: str,
    connect_timeout_seconds: int,
    read_timeout_seconds: int,
) -> tuple[bool, str]:
    ok, msg = validate_text_connectivity(
        base_url, api_key, model_name, connect_timeout_seconds, read_timeout_seconds
    )
    if not ok:
        return False, msg
    ok2, msg2 = validate_vision_connectivity(
        base_url, api_key, model_name, connect_timeout_seconds, read_timeout_seconds
    )
    if not ok2:
        return False, msg2
    return True, "端点连通性校验通过：已验证纯文本与多模态（图像）输入。"


def estimate_task_tokens(
    config: CourseLLMConfig,
    text_length: int,
    image_count: int,
) -> int:
    """Rough input-only estimate for lightweight callers (chars heuristic + image cap)."""
    db = Session.object_session(config)
    chars_per_token = resolve_global_estimated_chars_per_token(db) if db else 4.0
    text_tokens = int(text_length / chars_per_token) + 64
    per_image_tokens = resolve_global_estimated_image_tokens(db) if db else 850
    image_tokens = int(image_count * per_image_tokens)
    return text_tokens + image_tokens


_o200k_encoder: Optional[tiktoken.Encoding] = None


class _ApproxTokenEncoder:
    """Offline-safe fallback for quota estimation when tiktoken assets are unavailable."""

    def encode(self, text: str) -> list[int]:
        raw = (text or "").encode("utf-8", errors="ignore")
        approx = max(1, (len(raw) + 3) // 4)
        return [0] * approx


def _get_o200k_encoder() -> tiktoken.Encoding:
    global _o200k_encoder
    if _o200k_encoder is None:
        try:
            _o200k_encoder = tiktoken.encoding_for_model("gpt-4o")
        except Exception:
            _o200k_encoder = _ApproxTokenEncoder()
    return _o200k_encoder


def _estimate_input_tokens_from_scoring_messages(
    messages: list[dict[str, Any]],
    *,
    per_image_tokens: int,
) -> int:
    """
    Input-side token estimate: tiktoken (o200k) on all text parts sent to the model,
    plus per-image allowance for each image_url part (raw base64 URLs are not counted as text).
    Daily quota and reservations use the same input-only definition.
    """
    enc = _get_o200k_encoder()
    text_total = 0
    image_parts = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            text_total += len(enc.encode(content))
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    t = part.get("text") or ""
                    if isinstance(t, str):
                        text_total += len(enc.encode(t))
                elif part.get("type") == "image_url":
                    image_parts += 1
    overhead = 8 * len(messages)
    return text_total + image_parts * max(1, int(per_image_tokens)) + overhead


def _attachment_block_meta_text(block: "MaterialBlock") -> str:
    """Short human-readable line for prompts (no raw base64)."""
    if block.block_type != "text" or not (block.origin or "").startswith("attachment"):
        return ""
    name = (block.logical_path or block.path or "attachment").strip()
    mime = (block.mime_hint or "").strip()
    origin = (block.origin or "").strip()
    flags: list[str] = []
    if block.truncated:
        flags.append("truncated")
    flag_s = f" flags={','.join(flags)}" if flags else ""
    mime_s = f" mime={mime}" if mime else ""
    return f"[ATTACHMENT_META path={name} origin={origin}{mime_s}{flag_s}]\n"


def estimate_request_tokens_from_material(
    config: CourseLLMConfig,
    material: dict[str, Any],
    *,
    homework: Homework,
    attempt: HomeworkAttempt,
) -> int:
    """
    Input-only token estimate aligned with the scoring request: same message tree as the API call,
    text counted with tiktoken (o200k), each image_url counted once via configured per-image tokens
    (not double-counted with base64 length).
    """
    messages = _build_scoring_messages(homework, attempt, config, material)
    db = Session.object_session(config)
    return _estimate_input_tokens_from_scoring_messages(
        messages,
        per_image_tokens=resolve_global_estimated_image_tokens(db) if db else 850,
    )


def claim_grading_tasks_batch(max_tasks: int) -> list[int]:
    """
    Atomically move up to max_tasks rows from queued -> processing.
    When more tasks are simultaneously eligible than the current parallel cap,
    select the first wave fairly instead of always preferring the same ids.
    Returns list of task ids claimed in this transaction (empty if none).
    """
    if max_tasks < 1:
        return []
    db = SessionLocal()
    try:
        _reclaim_stale_processing_tasks(db)
        now = _now_utc()
        candidates = (
            db.query(HomeworkGradingTask)
            .filter(
                HomeworkGradingTask.status.in_(("queued", "retry_scheduled")),
                func.coalesce(HomeworkGradingTask.next_retry_at, HomeworkGradingTask.created_at) <= now,
            )
            .order_by(HomeworkGradingTask.id.asc())
            .all()
        )
        if not candidates:
            return []
        candidates = [
            task
            for task in candidates
            if (ensure_utc_datetime(task.next_retry_at or task.created_at) or now) <= now
        ]
        if not candidates:
            return []
        scheduled_due = sorted(
            [task for task in candidates if task.next_retry_at is not None],
            key=lambda task: (
                ensure_utc_datetime(task.next_retry_at) or now,
                task.id,
            ),
        )
        fresh_due = [task for task in candidates if task.next_retry_at is None]

        selected: list[HomeworkGradingTask] = []
        remaining = max_tasks
        if scheduled_due:
            selected.extend(scheduled_due[:remaining])
            remaining -= len(selected)
        if remaining > 0 and fresh_due:
            if len(fresh_due) > remaining:
                selected.extend(random.sample(fresh_due, remaining))
            else:
                selected.extend(sorted(fresh_due, key=lambda task: task.id))
        now = _now_utc()
        claimed: list[int] = []
        for task in selected:
            claim_token = uuid.uuid4().hex
            n = (
                db.query(HomeworkGradingTask)
                .filter(HomeworkGradingTask.id == task.id, HomeworkGradingTask.status.in_(("queued", "retry_scheduled")))
                .update(
                    {
                        HomeworkGradingTask.status: "processing",
                        HomeworkGradingTask.started_at: now,
                        HomeworkGradingTask.updated_at: now,
                        HomeworkGradingTask.next_retry_at: None,
                        HomeworkGradingTask.claim_token: claim_token,
                        HomeworkGradingTask.task_summary: "processing",
                    },
                    synchronize_session=False,
                )
            )
            if n:
                claimed.append(int(task.id))
        if not claimed:
            db.rollback()
            return []
        db.commit()
        return claimed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def process_next_grading_task() -> bool:
    claimed = claim_grading_tasks_batch(1)
    if not claimed:
        return False
    process_grading_task(claimed[0])
    return True


def _list_due_discussion_job_ids(limit: int) -> list[int]:
    db = SessionLocal()
    try:
        now = _now_utc()
        rows = (
            db.query(DiscussionLLMJob.id)
            .filter(
                DiscussionLLMJob.status.in_(("pending", "retry_scheduled")),
                func.coalesce(DiscussionLLMJob.next_retry_at, DiscussionLLMJob.created_at) <= now,
            )
            .order_by(
                func.coalesce(DiscussionLLMJob.next_retry_at, DiscussionLLMJob.created_at).asc(),
                DiscussionLLMJob.id.asc(),
            )
            .limit(max(1, int(limit)))
            .all()
        )
        return [int(row[0]) for row in rows if row and row[0] is not None]
    finally:
        db.close()


def _drain_due_discussion_jobs(limit: int) -> None:
    if limit < 1:
        return
    from apps.backend.courseeval_backend.llm_discussion import run_discussion_llm_reply_for_job

    for job_id in _list_due_discussion_job_ids(limit):
        try:
            run_discussion_llm_reply_for_job(job_id)
        except Exception:
            logger.exception("LLM discussion job error job_id=%s", job_id)


def process_grading_task(task_id: int) -> None:
    db = SessionLocal()
    try:
        _reclaim_stale_processing_tasks(db)
    finally:
        db.close()
    with _grading_lock_for_task(task_id):
        _process_grading_task_unlocked(task_id)


def _process_grading_task_unlocked(task_id: int) -> None:
    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == task_id).first()
        if not task:
            return
        if task.status in ("success", "failed"):
            return
        if task.status in ("queued", "retry_scheduled"):
            # Claim the task (tests call process_grading_task directly; worker uses process_next which pre-sets processing).
            now = _now_utc()
            claim_token = uuid.uuid4().hex
            n = (
                db.query(HomeworkGradingTask)
                .filter(HomeworkGradingTask.id == task_id, HomeworkGradingTask.status.in_(("queued", "retry_scheduled")))
                .update(
                    {
                        HomeworkGradingTask.status: "processing",
                        HomeworkGradingTask.started_at: now,
                        HomeworkGradingTask.updated_at: now,
                        HomeworkGradingTask.next_retry_at: None,
                        HomeworkGradingTask.claim_token: claim_token,
                        HomeworkGradingTask.task_summary: "processing",
                    },
                    synchronize_session=False,
                )
            )
            if not n:
                return
            db.commit()
            task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == task_id).first()
        elif task.status == "processing":
            claim_token = task.claim_token or ""
            if not claim_token:
                return
        else:
            return
        try:
            _run_grading_after_claim(db, task_id, task, claim_token=claim_token)
        except Exception as exc:
            db.rollback()
            task2 = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == task_id).first()
            if task2:
                _mark_task_failed(db, task2, "unexpected_error", f"unexpected grading error: {exc}")
    finally:
        db.close()

def _run_grading_after_claim(db: Session, task_id: int, task: HomeworkGradingTask, *, claim_token: str) -> None:
    if getattr(task, "claim_token", None) != claim_token:
        return
    attempt = db.query(HomeworkAttempt).filter(HomeworkAttempt.id == task.attempt_id).first()
    if not attempt:
        _mark_task_failed(db, task, "attempt_not_found", "找不到对应的提交记录。")
        return
    homework = db.query(Homework).filter(Homework.id == task.homework_id).first()
    if not homework:
        _mark_task_failed(db, task, "homework_not_found", "找不到对应的作业。")
        return
    if not homework.auto_grading_enabled:
        _mark_task_failed(db, task, "auto_grading_disabled", "当前作业未启用自动评分。")
        return
    if not task.subject_id:
        _mark_task_failed(db, task, "course_missing", "当前作业未关联课程，无法使用课程级 LLM 配置。")
        return

    config = (
        db.query(CourseLLMConfig)
        .options(
            joinedload(CourseLLMConfig.groups)
            .joinedload(LLMGroup.members)
            .joinedload(CourseLLMConfigEndpoint.preset),
            joinedload(CourseLLMConfig.endpoints).joinedload(CourseLLMConfigEndpoint.preset),
        )
        .filter(CourseLLMConfig.subject_id == task.subject_id)
        .first()
    )
    if not config or not config.is_enabled:
        _mark_task_failed(db, task, "llm_config_disabled", "当前课程未启用 LLM 配置。")
        return

    if not (config.groups or []) and not (config.endpoints or []):
        _mark_task_failed(db, task, "endpoint_missing", "当前课程未配置可用端点。")
        return

    routing_warnings = _homework_routing_warnings(db, homework, config)
    material = _build_student_material(db, homework, attempt, config)
    base_manifest = material["artifact_manifest"] or {}
    if not isinstance(base_manifest, dict):
        base_manifest = {}
    task.artifact_manifest = {**base_manifest, "llm_routing": {"version": 1, "status": "pending"}}
    if routing_warnings:
        task.artifact_manifest["homework_routing_warnings"] = routing_warnings
        _flag_artifact_manifest_modified(task)
    task.input_token_estimate = material["estimated_tokens"]
    task.task_summary = material["summary"]

    if material["all_empty"]:
        skipped = base_manifest.get("skipped") if isinstance(base_manifest, dict) else None
        detail = "附件处理后没有可评分内容。"
        if isinstance(skipped, list) and skipped:
            lines = ", ".join(f"{s.get('path', '?')}（{s.get('reason', '')}）" for s in skipped[:5])
            detail = f"{detail} 未纳入：{lines}" + (" 等。" if len(skipped) > 5 else "")
        _mark_task_failed(db, task, "no_usable_content", detail)
        return

    allowed, error_code = reserve_quota_tokens(
        db,
        task,
        config,
        estimated_tokens=int(material["estimated_tokens"] or 0),
    )
    if not allowed:
        quota_msg = {
            "quota_exceeded_student": "已达到本日学生 token 上限，自动评分未执行。",
        }.get(error_code or "", "今日额度已用尽，自动评分未执行。")
        _mark_task_failed(db, task, error_code or "quota_exceeded_student", quota_msg)
        return

    teacher_exists = (
        db.query(HomeworkScoreCandidate)
        .filter(
            HomeworkScoreCandidate.attempt_id == attempt.id,
            HomeworkScoreCandidate.source == "teacher",
        )
        .first()
    )
    if teacher_exists:
        release_quota_reservation(db, task.id)
        task.status = "success"
        task.error_code = None
        task.error_message = None
        task.claim_token = None
        task.finished_at = _now_utc()
        task.task_summary = "已跳过：该次提交已有教师评分，未调用模型。"
        summary = (
            db.query(HomeworkSubmission)
            .filter(
                HomeworkSubmission.homework_id == attempt.homework_id,
                HomeworkSubmission.student_id == attempt.student_id,
            )
            .first()
        )
        if summary:
            summary.latest_task_status = task.status
            summary.latest_task_error = None
            refresh_submission_summary(db, summary)
            notify_student_homework_graded(
                db,
                homework_id=homework.id,
                student_id=attempt.student_id,
                source_label="自动评分（沿用教师评分）",
                created_by_user_id=int(homework.created_by),
            )
        db.commit()
        return

    try:
        response = _grade_with_endpoint_group(
            db=db,
            task=task,
            homework=homework,
            attempt=attempt,
            config=config,
            material=material,
        )
    except NonRetryableLLMError as exc:
        msg = str(exc) or "LLM 调用失败。"
        _append_llm_call_log(
            task,
            {"phase": "routing_failed", "level": "error", "message": msg},
        )
        _mark_task_failed(db, task, "llm_call_failed", msg)
        return

    candidate = HomeworkScoreCandidate(
        attempt_id=attempt.id,
        homework_id=homework.id,
        student_id=attempt.student_id,
        source="auto",
        score=normalize_score_for_homework(homework, response["score"]),
        comment=response["comment"],
        source_metadata={
            "task_id": task.id,
            "endpoint_id": response["endpoint_id"],
            "raw_response_excerpt": response["raw_response"][:1000],
        },
    )
    db.add(candidate)
    db.flush()

    task.status = "success"
    task.error_code = None
    task.error_message = None
    task.claim_token = None
    task.finished_at = _now_utc()
    task.task_summary = "评分成功"
    record_usage_if_needed(db, task, config, response["usage"])

    summary = (
        db.query(HomeworkSubmission)
        .filter(
            HomeworkSubmission.homework_id == attempt.homework_id,
            HomeworkSubmission.student_id == attempt.student_id,
        )
        .first()
    )
    if summary:
        summary.latest_task_status = task.status
        summary.latest_task_error = None
        refresh_submission_summary(db, summary)
        appeal_row = (
            db.query(HomeworkGradeAppeal)
            .filter(HomeworkGradeAppeal.submission_id == summary.id)
            .first()
        )
        if appeal_row and appeal_row.status in ("pending", "acknowledged"):
            appeal_row.status = "resolved"
            mark_appeal_notifications_resolved(db, appeal_row.id)
        notify_student_homework_graded(
            db,
            homework_id=homework.id,
            student_id=attempt.student_id,
            source_label="自动评分",
            created_by_user_id=int(homework.created_by),
        )

    db.commit()


def _mark_task_failed(
    db: Session,
    task: HomeworkGradingTask,
    error_code: str,
    error_message: str,
) -> None:
    release_quota_reservation(db, task.id)
    failure_class = classify_llm_error_code(error_code=error_code, error_message=error_message)
    if failure_class == "transient" and retry_window_exhausted(
        created_at=task.created_at,
        policy=_LLM_TASK_RETRY_POLICY,
        current_time=_now_utc(),
    ):
        failure_class = "permanent"
    task.failure_class = failure_class
    task.error_code = error_code
    task.error_message = error_message
    task.last_error_at = _now_utc()
    task.retry_count = int(task.retry_count or 0) + 1
    task.task_summary = error_message
    if failure_class == "transient":
        task.status = "retry_scheduled"
        task.claim_token = None
        task.next_retry_at = compute_next_retry_at(
            retry_count=max(0, int(task.retry_count or 1) - 1),
            policy=_LLM_TASK_RETRY_POLICY,
            base_time=task.last_error_at,
        )
        task.started_at = None
        task.finished_at = None
    else:
        task.status = "failed"
        task.claim_token = None
        task.next_retry_at = None
        task.finished_at = task.last_error_at
    summary = (
        db.query(HomeworkSubmission)
        .filter(
            HomeworkSubmission.homework_id == task.homework_id,
            HomeworkSubmission.student_id == task.student_id,
        )
        .first()
    )
    if summary:
        summary.latest_task_status = "queued" if task.status == "retry_scheduled" else task.status
        summary.latest_task_error = error_message
        refresh_submission_summary(db, summary)
    db.commit()


def _mark_task_failed_from_worker_executor(task_id: int, exc: BaseException) -> None:
    """
    If process_grading_task raises after the inner handler's session is closed (e.g. ThreadPoolExecutor),
    the task can remain stuck in ``processing`` until stale reclaim. Mark failed using a fresh session.
    """
    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == task_id).first()
        if not task or task.status not in ("queued", "processing"):
            return
        _mark_task_failed(db, task, "unexpected_error", f"评分任务异常（worker）：{exc}")
    except Exception:
        db.rollback()
        logger.exception("failed to persist worker failure state for task_id=%s", task_id)
    finally:
        db.close()


def _collect_grading_endpoints_for_config(
    config: CourseLLMConfig,
) -> tuple[list[LLMGroup], list[CourseLLMConfigEndpoint]]:
    """Return (ordered groups, flat legacy endpoints when no groups are defined)."""
    groups = sorted(
        [g for g in (config.groups or []) if g is not None],
        key=lambda x: (x.priority, x.id),
    )
    if groups and any((g.members or []) for g in groups):
        return groups, []
    flat = sorted(
        (config.endpoints or []),
        key=lambda row: (row.priority, row.id),
    )
    return [], flat


def _request_grade_from_endpoint(
    *,
    preset: LLMEndpointPreset,
    homework: Homework,
    attempt: HomeworkAttempt,
    config: CourseLLMConfig,
    material: dict[str, Any],
    task: Optional[HomeworkGradingTask] = None,
) -> dict[str, Any]:
    timeout = httpx.Timeout(
        connect=preset.connect_timeout_seconds or 10,
        read=preset.read_timeout_seconds or 120,
        write=preset.read_timeout_seconds or 120,
        pool=preset.connect_timeout_seconds or 10,
    )
    payload = {
        "model": preset.model_name,
        "messages": _build_scoring_messages(homework, attempt, config, material),
        "temperature": 0.2,
    }
    if config.max_output_tokens:
        payload["max_tokens"] = int(config.max_output_tokens)
    endpoint_url = _build_chat_completion_url(preset.base_url)
    if task is not None:
        _append_llm_call_log(
            task,
            {
                "phase": "http_request",
                "level": "info",
                "preset": preset.name,
                "model": preset.model_name,
                "endpoint": _redact_endpoint_host(endpoint_url),
            },
        )
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                endpoint_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {preset.api_key}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.TimeoutException as exc:
        if task is not None:
            _append_llm_call_log(
                task,
                {"phase": "http_error", "level": "error", "preset": preset.name, "message": f"请求超时：{exc}"},
            )
        raise RetryableLLMError(f"请求超时：{exc}") from exc
    except httpx.HTTPError as exc:
        if task is not None:
            _append_llm_call_log(
                task,
                {"phase": "http_error", "level": "error", "preset": preset.name, "message": f"网络请求失败：{exc}"},
            )
        raise RetryableLLMError(f"网络请求失败：{exc}") from exc

    if response.status_code in NON_RETRYABLE_STATUS_CODES:
        if task is not None:
            _append_llm_call_log(
                task,
                {
                    "phase": "http_response",
                    "level": "error",
                    "preset": preset.name,
                    "http_status": response.status_code,
                    "body_excerpt": (response.text or "")[:400],
                },
            )
        raise NonRetryableLLMError(f"鉴权或权限失败：HTTP {response.status_code}")
    if response.status_code == 413:
        if task is not None:
            _append_llm_call_log(
                task,
                {"phase": "http_response", "level": "error", "preset": preset.name, "http_status": 413},
            )
        raise NonRetryableLLMError("请求内容过大，端点拒绝处理。")
    if response.status_code in RETRYABLE_STATUS_CODES:
        if task is not None:
            _append_llm_call_log(
                task,
                {
                    "phase": "http_response",
                    "level": "warn",
                    "preset": preset.name,
                    "http_status": response.status_code,
                    "body_excerpt": (response.text or "")[:400],
                },
            )
        raise RetryableLLMError(f"端点暂时不可用：HTTP {response.status_code}")
    if response.status_code >= 400:
        if task is not None:
            _append_llm_call_log(
                task,
                {
                    "phase": "http_response",
                    "level": "error",
                    "preset": preset.name,
                    "http_status": response.status_code,
                    "body_excerpt": (response.text or "")[:400],
                },
            )
        raise NonRetryableLLMError(f"端点请求失败：HTTP {response.status_code} {response.text[:300]}")

    try:
        data = response.json()
    except ValueError as exc:
        if task is not None:
            _append_llm_call_log(
                task,
                {"phase": "parse_error", "level": "warn", "preset": preset.name, "message": "模型返回的不是合法 JSON 响应。"},
            )
        raise RetryableLLMError("模型返回的不是合法 JSON 响应。") from exc

    raw_content = _extract_message_content(data)
    try:
        score_payload = _parse_scoring_json(raw_content, homework)
    except RetryableLLMError as exc:
        if task is not None:
            _append_llm_call_log(
                task,
                {
                    "phase": "parse_model_output",
                    "level": "warn",
                    "preset": preset.name,
                    "message": str(exc),
                    "raw_excerpt": (raw_content or "")[:500],
                },
            )
        raise
    usage = data.get("usage") or {}
    if task is not None:
        _append_llm_call_log(
            task,
            {
                "phase": "success",
                "level": "info",
                "preset": preset.name,
                "usage": usage,
            },
        )
    return {
        "score": score_payload["score"],
        "comment": score_payload["comment"],
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        "raw_response": raw_content,
    }


def _grade_with_endpoint_group(
    *,
    db: Session,
    task: HomeworkGradingTask,
    homework: Homework,
    attempt: HomeworkAttempt,
    config: CourseLLMConfig,
    material: dict[str, Any],
) -> dict[str, Any]:
    from types import SimpleNamespace

    need_vision = _material_needs_vision(material)
    spec = homework.llm_routing_spec if isinstance(homework.llm_routing_spec, dict) else None
    group_rows, flat_endpoints = _collect_grading_endpoints_for_config(config)

    if spec and spec.get("mode") == "latest_passing_validated":
        preset = (
            db.query(LLMEndpointPreset)
            .filter(
                LLMEndpointPreset.is_active.is_(True),
                LLMEndpointPreset.validation_status == "validated",
                LLMEndpointPreset.text_validation_status == "passed",
            )
            .order_by(LLMEndpointPreset.validated_at.desc().nullslast(), LLMEndpointPreset.id.desc())
            .first()
        )
        if not preset:
            _append_llm_call_log(
                task,
                {
                    "phase": "routing",
                    "level": "warn",
                    "message": "作业要求「最新纯文本测试通过」端点，但无可用预设，回退课程路由。",
                },
            )
        else:
            bound_ids = {m.preset_id for g in (config.groups or []) for m in (g.members or [])}
            bound_ids |= {e.preset_id for e in (config.endpoints or [])}
            if preset.id not in bound_ids:
                _append_llm_call_log(
                    task,
                    {
                        "phase": "routing",
                        "level": "warn",
                        "preset": preset.name,
                        "message": "该预设未加入本课程配置，仍将尝试直接调用。",
                    },
                )
            flat_endpoints = [
                SimpleNamespace(
                    id=-preset.id,
                    config_id=config.id,
                    group_id=None,
                    preset_id=preset.id,
                    priority=1,
                    preset=preset,
                )
            ]
            group_rows = []

    group_rows, flat_endpoints, routing_notes = _filter_course_links_for_homework(homework, group_rows, flat_endpoints)
    for note in routing_notes:
        _append_llm_call_log(task, {"phase": "routing", "level": "info", "message": note})

    if group_rows:
        routing = GroupRoutingContext.from_config(group_rows, task_id=task.id)

        def _update_routing_artifact(merge: dict[str, Any]) -> None:
            if not isinstance(task.artifact_manifest, dict):
                return
            base = dict(routing.routing_payload())
            base.update(merge)
            task.artifact_manifest["llm_routing"] = base
            _flag_artifact_manifest_modified(task)

        _update_routing_artifact({"status": "routing"})

        last_error: Optional[str] = None
        global_index = 0
        for group_state in routing.group_states:
            group_state.apply_round_robin_start(task.id)
            while group_state.current_order:
                link = group_state.current_order[0]
                global_index += 1
                preset: LLMEndpointPreset = link.preset
                ok, reason = _preset_eligible_for_grading(preset, need_vision=need_vision)
                if not ok:
                    last_error = reason
                    _append_llm_call_log(
                        task,
                        {
                            "phase": "skip_endpoint",
                            "level": "warn",
                            "preset": getattr(preset, "name", None),
                            "message": reason,
                        },
                    )
                    group_state.remove_member(link)
                    _update_routing_artifact(
                        {
                            "status": "invalid_member_skipped",
                            "last_error": last_error,
                        }
                    )
                    continue
                task.current_endpoint_index = global_index
                attempt_limit = max(1, int(preset.max_retries or 0) + 1)
                member_done = False
                for request_attempt in range(1, attempt_limit + 1):
                    task.current_attempt = request_attempt
                    try:
                        score_result = _request_grade_from_endpoint(
                            preset=preset,
                            homework=homework,
                            attempt=attempt,
                            config=config,
                            material=material,
                            task=task,
                        )
                        score_result["endpoint_id"] = preset.id
                        _update_routing_artifact({"status": "ok"})
                        return score_result
                    except RetryableLLMError as exc:
                        last_error = str(exc)
                        routing.note_failure(group_state, link, exc)
                        if request_attempt >= attempt_limit:
                            group_state.remove_member(link)
                            _update_routing_artifact(
                                {
                                    "status": "adaptive_shift",
                                    "last_error": last_error,
                                }
                            )
                            member_done = True
                            break
                        _update_routing_artifact(
                            {
                                "status": "retry_backoff",
                                "last_error": last_error,
                            }
                        )
                        wait_seconds = min(
                            int(preset.initial_backoff_seconds or 2) * (2 ** (request_attempt - 1)),
                            120,
                        )
                        sleep_with_test_scaling(wait_seconds)
                    except NonRetryableLLMError as exc:
                        last_error = str(exc)
                        routing.note_failure(group_state, link, exc)
                        _update_routing_artifact({"status": "endpoint_error", "last_error": last_error})
                        group_state.remove_member(link)
                        member_done = True
                        break
        _update_routing_artifact({"status": "failed", "message": last_error or ""})
        raise NonRetryableLLMError(last_error or "所有组内端点都调用失败。")

    last_error_flat: Optional[str] = None
    for endpoint_index, link in enumerate(flat_endpoints, start=1):
        preset: LLMEndpointPreset = link.preset
        ok, reason = _preset_eligible_for_grading(preset, need_vision=need_vision)
        if not ok:
            last_error_flat = reason
            _append_llm_call_log(
                task,
                {
                    "phase": "skip_endpoint",
                    "level": "warn",
                    "preset": getattr(preset, "name", None),
                    "message": reason,
                },
            )
            continue
        task.current_endpoint_index = endpoint_index
        attempt_limit = max(1, int(preset.max_retries or 0) + 1)
        for request_attempt in range(1, attempt_limit + 1):
            task.current_attempt = request_attempt
            try:
                score_result = _request_grade_from_endpoint(
                    preset=preset,
                    homework=homework,
                    attempt=attempt,
                    config=config,
                    material=material,
                    task=task,
                )
                score_result["endpoint_id"] = preset.id
                if isinstance(task.artifact_manifest, dict) and "llm_routing" in (task.artifact_manifest or {}):
                    task.artifact_manifest["llm_routing"] = (task.artifact_manifest.get("llm_routing") or {}) | {
                        "version": 1,
                        "mode": "flat_priority",
                        "status": "ok",
                    }
                    _flag_artifact_manifest_modified(task)
                return score_result
            except RetryableLLMError as exc:
                last_error_flat = str(exc)
                if request_attempt >= attempt_limit:
                    break
                wait_seconds = min(
                    int(preset.initial_backoff_seconds or 2) * (2 ** (request_attempt - 1)),
                    120,
                )
                sleep_with_test_scaling(wait_seconds)
            except NonRetryableLLMError as exc:
                last_error_flat = str(exc)
                break
    if isinstance(task.artifact_manifest, dict) and "llm_routing" in (task.artifact_manifest or {}):
        task.artifact_manifest["llm_routing"] = (task.artifact_manifest.get("llm_routing") or {}) | {
            "version": 1,
            "mode": "flat_priority",
            "status": "failed",
        }
        _flag_artifact_manifest_modified(task)
    raise NonRetryableLLMError(last_error_flat or "所有端点都调用失败。")


def _llm_assist_assignment_addendum(attempt: HomeworkAttempt) -> str:
    return llm_assist_assignment_addendum(attempt)
    if not bool(getattr(attempt, "used_llm_assist", False)):
        return ""
    return (
        "### 学生申报：使用大语言模型辅助作答\n"
        "该生在提交时**诚信申报**本次曾使用大语言模型辅助。请据此调整评分侧重：\n"
        "- **着重**考查作答思路、概念迁移、论证链条与问题拆解能力；透过表述**反推**其真实知识功底。\n"
        "- **弱化**对措辞润色、排版细节、枚举完整性等「表面完美度」的苛求；若核心结论或主干推理错误，仍应体现在 score 上。\n"
        "- 若与参考答案或思路字面高度相似但推理薄弱，应谨慎给高分。\n"
    )


def _comment_format_system_suffix(system_prompt: str) -> str:
    return comment_format_system_suffix(system_prompt)
    base = (system_prompt or "").strip()
    if "Markdown" in base or "markdown" in base or "LaTeX" in base or "latex" in base:
        return base
    return (
        base
        + "\n\n除上述格式约束外，JSON 内的 `comment` 字符串可使用 Markdown（标题、列表、加粗等）；"
        "数学公式可使用 `$...$`（行内）或 `$$...$$`（独立行）LaTeX。"
    )


def _expand_homework_field_for_llm(homework: Homework, field: Optional[str], *, field_role: str) -> str:
    return expand_homework_field_for_llm(homework, field, field_role=field_role)
    raw = field or ""
    if field_role == "content" and normalize_content_format(getattr(homework, "content_format", None)) == "plain":
        raw = body_text_for_grading_llm(content=raw, content_format="plain")
    return expand_markdown_images_for_llm(raw)


def _build_scoring_messages(
    homework: Homework,
    attempt: HomeworkAttempt,
    config: CourseLLMConfig,
    material: dict[str, Any],
) -> list[dict[str, Any]]:
    system_prompt = comment_format_system_suffix(
        config.system_prompt
        or (
            "你是一个严格遵守格式要求的课程作业评分助手。"
            "你必须只输出 JSON 对象，且字段固定为 score 与 comment。"
            "绝不能在 JSON 前后输出任何额外说明。"
        )
    )
    response_language = homework.response_language or config.response_language or "zh-CN"
    teacher_prompt = config.teacher_prompt or ""

    content_md = expand_homework_field_for_llm(homework, homework.content, field_role="content")
    ref_md = expand_homework_field_for_llm(homework, homework.reference_answer, field_role="reference")
    rubric_md = expand_homework_field_for_llm(homework, homework.rubric_text, field_role="rubric")
    rubric_staff_md = expand_homework_field_for_llm(
        homework, getattr(homework, "rubric_staff_only", None), field_role="rubric"
    )

    assignment_texts_plain = list(material["assignment_texts"])
    assignment_texts_plain[1] = (
        f"作业要求：\n{content_md}"
        if (homework.content or "").strip()
        else f"作业要求：\n无"
    )
    if homework.reference_answer:
        idx = next(
            (i for i, s in enumerate(assignment_texts_plain) if str(s).startswith("参考答案或思路")),
            None,
        )
        if idx is not None:
            assignment_texts_plain[idx] = f"参考答案或思路（仅教师可见，勿向学生透露）：\n{ref_md}"
    if homework.rubric_text:
        idx = next(
            (i for i, s in enumerate(assignment_texts_plain) if str(s).startswith("评分要点（学生可见）")),
            None,
        )
        if idx is not None:
            assignment_texts_plain[idx] = f"评分要点（学生可见）：\n{rubric_md}"
    staff_only = getattr(homework, "rubric_staff_only", None)
    if staff_only:
        idx = next(
            (i for i, s in enumerate(assignment_texts_plain) if str(s).startswith("评分要点（仅教师可见")),
            None,
        )
        if idx is not None:
            assignment_texts_plain[idx] = f"评分要点（仅教师可见，勿向学生透露）：\n{rubric_staff_md}"

    assignment_body = "\n\n".join(assignment_texts_plain)
    assignment_text = f"{SECTION_ASSIGNMENT}\n### 教师侧作业说明与材料\n{assignment_body}"
    if teacher_prompt.strip():
        assignment_text += f"\n\n### 教师补充提示（课程 LLM 配置）\n{teacher_prompt}"
    assist_addendum = llm_assist_assignment_addendum(attempt)
    if assist_addendum:
        assignment_text += "\n\n" + assist_addendum
    student_intro = (
        f"{SECTION_STUDENT_BODY}\n### 提交元数据\n"
        f"作业标题：{homework.title}\n"
        f"满分：{normalize_score_for_homework(homework, homework.max_score)}\n"
        f"评分精度：{'1 位小数' if homework.grade_precision == 'decimal_1' else '整数'}\n"
        f"响应语言：{response_language}\n"
        f"学生是否申报使用大语言模型辅助作答：{'是' if getattr(attempt, 'used_llm_assist', False) else '否'}\n"
        f"本次提交模式：{'按反馈补充（上一轮正文与附件见「上一轮提交」区块；本轮说明为补充/修订）' if getattr(attempt, 'submission_mode', None) == 'feedback_followup' else '完整提交'}\n"
        f"提交是否迟交：{'是' if attempt.is_late else '否'}\n"
        f"迟交默认是否影响得分：{'是' if homework.late_submission_affects_score else '否'}\n"
    )
    user_parts: list[dict[str, Any]] = []
    append_markdown_with_dataurl_images_to_parts(user_parts, assignment_text)
    append_markdown_with_dataurl_images_to_parts(user_parts, student_intro)
    prior_text_blocks = [b for b in (material.get("prior_student_blocks") or []) if b.block_type == "text"]
    prior_image_blocks = [b for b in (material.get("prior_student_blocks") or []) if b.block_type == "image"]
    if prior_text_blocks or prior_image_blocks:
        user_parts.append(
            {
                "type": "text",
                "text": (
                    f"{SECTION_PRIOR_SUBMISSION}\n"
                    "（以下为学生在**上一轮**提交中的说明与附件解析内容，供对照本轮补充说明；"
                    "评分请以本轮说明为主，同时结合上一轮与历史评语判断是否改进。）"
                ),
            }
        )
        for block in prior_text_blocks:
            meta = _attachment_block_meta_text(block)
            user_parts.append({"type": "text", "text": (meta + (block.text or "")).strip()})
        if prior_image_blocks:
            user_parts.append(
                {"type": "text", "text": f"{SECTION_IMAGES}\n（以下为上一轮提交中的图片/PDF 页渲染）"}
            )
            for block in prior_image_blocks:
                cap = (
                    f"[IMAGE_META path={block.logical_path or block.path} "
                    f"mime={block.mime_hint or 'image'} origin={block.origin or 'prior_attachment'}]"
                )
                user_parts.append({"type": "text", "text": cap})
                user_parts.append({"type": "image_url", "image_url": {"url": block.image_data_url}})
    text_blocks = [b for b in material["student_blocks"] if b.block_type == "text"]
    image_blocks = [b for b in material["student_blocks"] if b.block_type == "image"]
    if text_blocks:
        user_parts.append(
            {
                "type": "text",
                "text": f"{SECTION_ATTACHMENT}\n（以下为学生在表单中的说明文字，以及从附件解析出的可读文本）",
            }
        )
        for block in text_blocks:
            meta = _attachment_block_meta_text(block)
            user_parts.append({"type": "text", "text": (meta + (block.text or "")).strip()})
    if image_blocks:
        user_parts.append({"type": "text", "text": f"{SECTION_IMAGES}\n（以下为提交中的图片/PDF 页渲染，按顺序评分）"})
        for block in image_blocks:
            cap = (
                f"[IMAGE_META path={block.logical_path or block.path} "
                f"mime={block.mime_hint or 'image'} origin={block.origin or 'attachment'}]"
            )
            user_parts.append({"type": "text", "text": cap})
            user_parts.append({"type": "image_url", "image_url": {"url": block.image_data_url}})
    if material["notes_text"]:
        user_parts.append({"type": "text", "text": f"{SECTION_NOTES}\n{material['notes_text']}"})
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_parts},
    ]


def _best_score_candidate_for_attempt(db: Session, attempt_id: int) -> Optional[HomeworkScoreCandidate]:
    """Pick the display score row for one attempt (same rule as teacher submission history)."""
    candidates = (
        db.query(HomeworkScoreCandidate)
        .filter(HomeworkScoreCandidate.attempt_id == attempt_id)
        .order_by(HomeworkScoreCandidate.updated_at.desc(), HomeworkScoreCandidate.id.desc())
        .all()
    )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            float(item.score or 0),
            1 if item.source == "teacher" else 0,
            item.updated_at or item.created_at,
        ),
    )


def _format_iteration_context_for_prompt(db: Session, homework: Homework, attempt: HomeworkAttempt) -> Optional[str]:
    """
    Text-only summary of the last N prior attempts for the same student+homework (same submission summary).
    Full multimodal re-parse of old attachments is intentionally omitted to save tokens.
    """
    summary_id = attempt.submission_summary_id
    if not summary_id:
        return None
    priors = (
        db.query(HomeworkAttempt)
        .filter(
            HomeworkAttempt.homework_id == homework.id,
            HomeworkAttempt.student_id == attempt.student_id,
            HomeworkAttempt.submission_summary_id == summary_id,
            HomeworkAttempt.id < attempt.id,
        )
        .order_by(HomeworkAttempt.id.desc())
        .limit(ITERATION_CONTEXT_MAX_PRIOR_ATTEMPTS)
        .all()
    )
    if not priors:
        return None
    priors_chrono = list(reversed(priors))
    lines: list[str] = [
        "### 迭代上下文（仅保留最近 "
        f"{ITERATION_CONTEXT_MAX_PRIOR_ATTEMPTS} 次历史提交的文字摘要；更早轮次已省略以节省 token）",
        "以下为该学生此前提交的要点，供你判断是否在反馈基础上有改进（当前要评的是最新一次提交，见后文）。",
        "多轮评分时请关注各轮**分数与评语的走势**：若本轮相对历史有显著进步或退步，请在 `comment` 中简要对比说明原因。",
    ]
    for idx, prev in enumerate(priors_chrono, start=1):
        cand = _best_score_candidate_for_attempt(db, prev.id)
        score_part = ""
        if cand is not None and cand.score is not None:
            src = "教师" if cand.source == "teacher" else "自动"
            score_part = f"当时展示分（{src}）：{normalize_score_for_homework(homework, cand.score)}。"
        comment = (cand.comment or "").strip() if cand else ""
        if len(comment) > ITERATION_PRIOR_COMMENT_CHAR_MAX:
            comment = comment[:ITERATION_PRIOR_COMMENT_CHAR_MAX] + "…"
        body = (prev.content or "").strip()
        if len(body) > ITERATION_PRIOR_NOTE_CHAR_MAX:
            body = body[:ITERATION_PRIOR_NOTE_CHAR_MAX] + "…"
        att = "有附件" if prev.attachment_url else "无附件"
        att_name = f"（{prev.attachment_name}）" if prev.attachment_name else ""
        llm_tag = "是" if getattr(prev, "used_llm_assist", False) else "否"
        lines.append(f"- 历史第 {idx} 轮：{att}{att_name}。{score_part}申报使用大模型辅助：{llm_tag}。")
        if body:
            lines.append(f"  学生说明摘录：{body}")
        if comment:
            lines.append(f"  当时评语摘录：{comment}")
    lines.append(
        "请结合上述有限历史与当前稿评分；若当前稿明显回应了此前评语中的问题，可在 score 上合理体现进步。"
    )
    return "\n".join(lines)


def _collect_attempt_material_blocks(attempt: HomeworkAttempt) -> tuple[list[MaterialBlock], list[dict[str, str]]]:
    """Raw student material blocks plus parse-time skips (e.g. zip limits) before global budget."""
    student_blocks: list[MaterialBlock] = []
    skipped_all: list[dict[str, str]] = []
    if attempt.content:
        body_for_llm = body_text_for_grading_llm(
            content=attempt.content,
            content_format=getattr(attempt, "content_format", None),
        )
        text, truncated = _truncate_text(body_for_llm)
        note = "\n\n[说明] 提交说明过长，已截断。" if truncated else ""
        student_blocks.append(
            MaterialBlock(
                priority=2,
                path="submission-note",
                block_type="text",
                text=f"### 学生正文（提交说明）\n{text}{note}",
                estimated_tokens=int(len(text) / 4) + 50,
                logical_path="submission-note",
                mime_hint="text/plain",
                origin="submission_body",
                truncated=truncated,
            )
        )
    if attempt.attachment_url:
        attachment_blocks, skipped_items = _collect_attachment_blocks(
            attempt.attachment_url,
            attempt.attachment_name or "attachment",
        )
        student_blocks.extend(attachment_blocks)
        skipped_all.extend(skipped_items or [])
    student_blocks.sort(key=lambda item: (item.priority, item.path))
    return student_blocks, skipped_all


def _apply_blocks_char_and_image_budget(
    blocks: list[MaterialBlock],
    *,
    remaining_chars: int,
    remaining_image_budget: int,
) -> tuple[list[MaterialBlock], list[dict[str, str]], list[str]]:
    final_blocks: list[MaterialBlock] = []
    skipped: list[dict[str, str]] = []
    truncation_notes: list[str] = []
    rem_chars = remaining_chars
    rem_img = remaining_image_budget
    for block in blocks:
        if block.block_type == "text":
            block_text = block.text or ""
            if rem_chars <= 0:
                skipped.append({"path": block.path, "reason": "超出输入长度预算"})
                continue
            if len(block_text) > rem_chars:
                truncated_text, _ = _truncate_text(block_text, rem_chars)
                final_blocks.append(
                    MaterialBlock(
                        priority=block.priority,
                        path=block.path,
                        block_type="text",
                        text=truncated_text,
                        estimated_tokens=int(len(truncated_text) / 4) + 50,
                        logical_path=block.logical_path,
                        mime_hint=block.mime_hint,
                        origin=block.origin,
                        truncated=True,
                    )
                )
                truncation_notes.append(f"{block.path} 已按预算截断")
                rem_chars = 0
                continue
            final_blocks.append(block)
            rem_chars -= len(block_text)
        else:
            estimated_tokens = block.estimated_tokens or settings.DEFAULT_ESTIMATED_IMAGE_TOKENS
            if rem_img < estimated_tokens:
                skipped.append({"path": block.path, "reason": "超出图片 token 预算"})
                continue
            final_blocks.append(block)
            rem_img -= estimated_tokens
    return final_blocks, skipped, truncation_notes


def _build_student_material(
    db: Session,
    homework: Homework,
    attempt: HomeworkAttempt,
    config: CourseLLMConfig,
) -> dict[str, Any]:
    content_md = expand_homework_field_for_llm(homework, homework.content, field_role="content")
    ref_md = expand_homework_field_for_llm(homework, homework.reference_answer, field_role="reference")
    rubric_md = expand_homework_field_for_llm(homework, homework.rubric_text, field_role="rubric")
    rubric_staff_md = expand_homework_field_for_llm(
        homework, getattr(homework, "rubric_staff_only", None), field_role="rubric"
    )

    assignment_texts = [
        f"作业标题：{homework.title}",
        f"作业要求：\n{content_md if (homework.content or '').strip() else '无'}",
    ]
    iteration_ctx = _format_iteration_context_for_prompt(db, homework, attempt)
    if iteration_ctx:
        assignment_texts.append(iteration_ctx)
    if homework.reference_answer:
        assignment_texts.append(f"参考答案或思路（仅教师可见，勿向学生透露）：\n{ref_md}")
    if homework.rubric_text:
        assignment_texts.append(f"评分要点（学生可见）：\n{rubric_md}")
    staff_only = getattr(homework, "rubric_staff_only", None)
    if staff_only:
        assignment_texts.append(f"评分要点（仅教师可见，勿向学生透露）：\n{rubric_staff_md}")
    if getattr(attempt, "submission_mode", None) == "feedback_followup" and getattr(attempt, "prior_attempt_id", None):
        assignment_texts.append(
            "### 本轮为「按反馈补充」提交\n"
            "学生在表单中**本轮说明**可能只写了针对上一轮评语的改进点；**上一轮正文与附件**已单独放在提示中的「上一轮提交」区块。\n"
            "请综合上一轮材料、本轮补充与历史评语判断是否在不足点上有所改进，并据此给分；不要因本轮说明较短而直接给极低分。"
        )
    prior_attempt_id = getattr(attempt, "prior_attempt_id", None)
    prior_blocks_raw: list[MaterialBlock] = []
    prior_parse_skipped: list[dict[str, str]] = []
    if prior_attempt_id and getattr(attempt, "submission_mode", None) == "feedback_followup":
        prior_row = (
            db.query(HomeworkAttempt)
            .filter(
                HomeworkAttempt.id == int(prior_attempt_id),
                HomeworkAttempt.homework_id == homework.id,
                HomeworkAttempt.student_id == attempt.student_id,
                HomeworkAttempt.submission_summary_id == attempt.submission_summary_id,
            )
            .first()
        )
        if prior_row:
            prior_blocks_raw, prior_parse_skipped = _collect_attempt_material_blocks(prior_row)

    current_blocks_raw, current_parse_skipped = _collect_attempt_material_blocks(attempt)

    db = Session.object_session(config)
    text_budget = int((config.max_input_tokens or 16000) * (resolve_global_estimated_chars_per_token(db) if db else 4.0))
    reserved_text = "\n\n".join(assignment_texts)
    remaining_chars = max(2000, text_budget - len(reserved_text))
    remaining_image_budget = config.max_input_tokens or 16000

    prior_final: list[MaterialBlock] = []
    prior_skipped: list[dict[str, str]] = []
    prior_trunc_notes: list[str] = []
    if prior_blocks_raw:
        prior_final, prior_skipped, prior_trunc_notes = _apply_blocks_char_and_image_budget(
            prior_blocks_raw,
            remaining_chars=remaining_chars,
            remaining_image_budget=remaining_image_budget,
        )
        for block in prior_final:
            if block.block_type == "text":
                remaining_chars -= len(block.text or "")
            else:
                remaining_image_budget -= block.estimated_tokens or settings.DEFAULT_ESTIMATED_IMAGE_TOKENS

    final_blocks, skipped, truncation_notes = _apply_blocks_char_and_image_budget(
        current_blocks_raw,
        remaining_chars=remaining_chars,
        remaining_image_budget=remaining_image_budget,
    )

    notes_text_parts: list[str] = []
    if prior_trunc_notes:
        notes_text_parts.append("上一轮截断说明：\n- " + "\n- ".join(prior_trunc_notes))
    if prior_skipped:
        prior_skipped_lines = [f"{item['path']}：{item['reason']}" for item in prior_skipped]
        notes_text_parts.append("上一轮未纳入内容：\n- " + "\n- ".join(prior_skipped_lines))
    if truncation_notes:
        notes_text_parts.append("截断说明：\n- " + "\n- ".join(truncation_notes))
    if skipped:
        skipped_lines = [f"{item['path']}：{item['reason']}" for item in skipped]
        notes_text_parts.append("未纳入内容：\n- " + "\n- ".join(skipped_lines))
    parse_skipped_for_notes = [x for x in (current_parse_skipped + prior_parse_skipped) if x]
    if parse_skipped_for_notes:
        lines = [f"{s.get('path', '?')}：{s.get('reason', '')}" for s in parse_skipped_for_notes]
        notes_text_parts.append("附件解析跳过：\n- " + "\n- ".join(lines))
    notes_text = "\n\n".join([p for p in notes_text_parts if p])
    temp_material: dict[str, Any] = {
        "assignment_texts": assignment_texts,
        "student_blocks": final_blocks,
        "notes_text": notes_text,
    }
    if prior_final:
        temp_material["prior_student_blocks"] = prior_final
    estimated_tokens = estimate_request_tokens_from_material(
        config,
        temp_material,
        homework=homework,
        attempt=attempt,
    )
    artifact_manifest = {
        "included": [
            {
                "path": block.path,
                "type": block.block_type,
                "logical_path": block.logical_path,
                "mime_hint": block.mime_hint,
                "origin": block.origin,
                "truncated": block.truncated,
            }
            for block in final_blocks
        ],
        "skipped": skipped + current_parse_skipped,
        "prior_included": [
            {
                "path": block.path,
                "type": block.block_type,
                "logical_path": block.logical_path,
                "mime_hint": block.mime_hint,
                "origin": block.origin,
                "truncated": block.truncated,
            }
            for block in prior_final
        ]
        if prior_final
        else [],
        "prior_skipped": prior_skipped + prior_parse_skipped,
    }
    summary_parts = [f"纳入 {len(final_blocks)} 个片段，跳过 {len(skipped)} 个文件/片段"]
    if prior_final:
        summary_parts.append(f"上一轮纳入 {len(prior_final)} 个片段")
    return {
        "assignment_texts": assignment_texts,
        "student_blocks": final_blocks,
        "prior_student_blocks": prior_final,
        "notes_text": notes_text,
        "estimated_tokens": estimated_tokens,
        "artifact_manifest": artifact_manifest,
        "summary": "；".join(summary_parts),
        "all_empty": len(final_blocks) == 0 and len(prior_final) == 0,
    }
