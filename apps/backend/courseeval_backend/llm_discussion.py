"""Synchronous LLM replies for course discussions (same endpoint routing + quota as grading)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import os
import time

import httpx
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.llm_grading import (
    GroupRoutingContext,
    _collect_grading_endpoints_for_config,
    _preset_eligible_for_grading,
    ensure_course_llm_config,
)
from apps.backend.courseeval_backend.domains.llm.errors import NonRetryableLLMError, RetryableLLMError
from apps.backend.courseeval_backend.domains.llm.protocol import (
    NON_RETRYABLE_STATUS_CODES,
    RETRYABLE_STATUS_CODES,
    build_chat_completion_url as _build_chat_completion_url,
)
from apps.backend.courseeval_backend.domains.llm.discussion_ui import strip_llm_ui_prefix
from apps.backend.courseeval_backend.domains.text_content_format import body_text_for_grading_llm, normalize_content_format
from apps.backend.courseeval_backend.domains.courses.access import get_student_profile_for_user, prepare_student_course_context
from apps.backend.courseeval_backend.domains.llm.quota import (
    record_discussion_usage_if_needed,
    release_discussion_quota_reservation,
    reserve_discussion_quota_tokens,
)
from apps.backend.courseeval_backend.domains.llm.discussion_retry import (
    promote_due_discussion_job,
    schedule_discussion_retry,
)
from apps.backend.courseeval_backend.domains.llm.runtime import now_utc, sleep_with_test_scaling
from apps.backend.courseeval_backend.db.models import (
    CourseDiscussionEntry,
    CourseLLMConfig,
    CourseMaterial,
    DiscussionLLMJob,
    Homework,
    HomeworkAttempt,
    HomeworkSubmission,
    LLMEndpointPreset,
    Student,
    Subject,
    User,
    UserRole,
)

def resolve_student_for_discussion_llm(db: Session, user: User, *, class_id: int) -> Student:
    """Student roster row for quota billing, using the same account<->roster repair path as the rest of the app."""
    prepare_student_course_context(user, db)
    row = get_student_profile_for_user(user, db)
    if not row or row.class_id is None or int(row.class_id) != int(class_id):
        raise ValueError("no_linked_student")
    return row


def discussion_llm_user_is_quota_exempt(user: User) -> bool:
    return (user.role or "").strip() in {
        UserRole.ADMIN.value,
        UserRole.TEACHER.value,
        UserRole.CLASS_TEACHER.value,
    }


def _strip_for_context(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 20] + "\n…（已截断）"


def _homework_context_blocks(db: Session, hw: Homework, *, student_id: Optional[int]) -> list[str]:
    parts: list[str] = []
    parts.append(f"【作业标题】\n{hw.title}")
    ctx_hw = _strip_for_context(hw.content or '', 12000)
    if normalize_content_format(getattr(hw, "content_format", None)) == "plain":
        ctx_hw = _strip_for_context(body_text_for_grading_llm(content=hw.content or "", content_format="plain"), 12000)
    parts.append(f"【作业说明】\n{ctx_hw}")
    if (hw.rubric_text or "").strip():
        parts.append(f"【评分要点（学生可见）】\n{_strip_for_context(hw.rubric_text, 8000)}")
    if student_id is None:
        parts.append("【当前提问者身份】当前提问者不是学生账号，未附带个人提交记录。")
        return parts
    sub = (
        db.query(HomeworkSubmission)
        .filter(HomeworkSubmission.homework_id == hw.id, HomeworkSubmission.student_id == student_id)
        .first()
    )
    if sub:
        attempt = None
        if sub.latest_attempt_id:
            attempt = db.query(HomeworkAttempt).filter(HomeworkAttempt.id == sub.latest_attempt_id).first()
        if not attempt:
            attempt = (
                db.query(HomeworkAttempt)
                .filter(HomeworkAttempt.homework_id == hw.id, HomeworkAttempt.student_id == student_id)
                .order_by(HomeworkAttempt.submitted_at.desc(), HomeworkAttempt.id.desc())
                .first()
            )
        if attempt:
            att_body = attempt.content or ""
            if normalize_content_format(getattr(attempt, "content_format", None)) == "plain":
                att_body = body_text_for_grading_llm(content=att_body, content_format="plain")
            parts.append(
                "【该生本人最近一次提交概要】\n"
                f"说明/正文：\n{_strip_for_context(att_body, 8000)}\n"
                f"附件：{(attempt.attachment_name or '无').strip()}"
            )
        else:
            parts.append("【该生本人提交】暂无提交记录。")
    else:
        parts.append("【该生本人提交】暂无提交记录。")
    return parts


def _material_context_blocks(mat: CourseMaterial) -> list[str]:
    body = mat.content or ""
    if normalize_content_format(getattr(mat, "content_format", None)) == "plain":
        body = body_text_for_grading_llm(content=body, content_format="plain")
    return [
        f"【资料标题】\n{mat.title}",
        f"【资料正文】\n{_strip_for_context(body, 16000)}",
        f"附件：{(mat.attachment_name or '无').strip()}",
    ]


def _discussion_thread_text(
    db: Session,
    *,
    target_type: str,
    target_id: int,
    subject_id: int,
    class_id: int,
    max_messages: int = 200,
) -> str:
    rows = (
        db.query(CourseDiscussionEntry, User)
        .join(User, User.id == CourseDiscussionEntry.author_user_id)
        .filter(
            CourseDiscussionEntry.target_type == target_type,
            CourseDiscussionEntry.target_id == target_id,
            CourseDiscussionEntry.subject_id == subject_id,
            CourseDiscussionEntry.class_id == class_id,
        )
        .order_by(CourseDiscussionEntry.created_at.asc(), CourseDiscussionEntry.id.asc())
        .limit(max_messages)
        .all()
    )
    lines: list[str] = []
    for entry, author in rows:
        who = author.real_name or author.username
        kind = "（智能助教）" if entry.message_kind == "llm_assistant" else ""
        inv = " [调用LLM]" if entry.llm_invocation else ""
        body_line = entry.body
        if normalize_content_format(getattr(entry, "body_format", None)) == "plain":
            body_line = body_text_for_grading_llm(content=body_line, content_format="plain")
        lines.append(f"- {who}{kind}{inv}: {body_line}")
    return "\n".join(lines) if lines else "（尚无留言）"


def _estimate_discussion_prompt_tokens(messages: list[dict[str, Any]], max_output_tokens: int) -> int:
    """Rough prompt size + configured max output for reservation."""
    enc = __import__("tiktoken").get_encoding("o200k_base")
    n = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            n += len(enc.encode(c))
        elif isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and part.get("type") == "text":
                    n += len(enc.encode(part.get("text") or ""))
    return int(n + max(256, int(max_output_tokens or 0)))


def _build_discussion_messages(
    *,
    context_text: str,
    thread_text: str,
    user_message: str,
    response_language: Optional[str],
) -> list[dict[str, Any]]:
    lang = (response_language or "zh").strip()
    system = (
        "你是智能教学辅助系统中的「智能助教」，仅根据下方提供的课程材料、作业说明与讨论区公开留言作答。\n"
        "规则：\n"
        "1) 只使用给定上下文；若信息不足请明确说明，不要编造。\n"
        "2) 讨论区为公开实名讨论；回答应专业、友善、面向学习辅导。\n"
        "3) 若上下文含「该生本人提交」，那是当前提问学生自己的作业，可引用；不要臆测其他同学提交。\n"
        f"4) 主要使用语言：{lang}。\n"
        "5) 直接给出助教回复正文，不要使用 JSON 或代码围栏包裹全篇。"
    )
    user_block = (
        "【课程/条目上下文】\n"
        f"{context_text}\n\n"
        "【讨论区留言（按时间顺序）】\n"
        f"{thread_text}\n\n"
        "【当前学生的新留言】\n"
        f"{user_message}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_block},
    ]


def _request_discussion_completion(
    *,
    preset: LLMEndpointPreset,
    messages: list[dict[str, Any]],
    max_output_tokens: int | None,
    job: DiscussionLLMJob,
) -> dict[str, Any]:
    timeout = httpx.Timeout(
        connect=preset.connect_timeout_seconds or 10,
        read=preset.read_timeout_seconds or 120,
        write=preset.read_timeout_seconds or 120,
        pool=preset.connect_timeout_seconds or 10,
    )
    payload = {
        "model": preset.model_name,
        "messages": messages,
        "temperature": 0.4,
    }
    if max_output_tokens:
        payload["max_tokens"] = int(max_output_tokens)
    endpoint_url = _build_chat_completion_url(preset.base_url)
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
        raise RetryableLLMError(f"请求超时：{exc}") from exc
    except httpx.HTTPError as exc:
        raise RetryableLLMError(f"网络请求失败：{exc}") from exc

    if response.status_code in NON_RETRYABLE_STATUS_CODES:
        raise NonRetryableLLMError(f"鉴权或权限失败：HTTP {response.status_code}")
    if response.status_code == 413:
        raise NonRetryableLLMError("??????????????HTTP 413")
    if response.status_code in RETRYABLE_STATUS_CODES:
        raise RetryableLLMError(f"端点暂时不可用：HTTP {response.status_code}")
    if response.status_code >= 400:
        raise NonRetryableLLMError(f"端点请求失败：HTTP {response.status_code} {response.text[:300]}")

    try:
        data = response.json()
    except ValueError as exc:
        raise RetryableLLMError("模型返回的不是合法 JSON 响应。") from exc

    choices = data.get("choices") or []
    raw = ""
    if choices:
        msg = (choices[0] or {}).get("message") or {}
        raw = msg.get("content") or ""
    if not str(raw).strip():
        raise RetryableLLMError("模型返回空内容。")
    usage = data.get("usage") or {}
    return {
        "text": str(raw).strip(),
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
    }


def _call_discussion_with_routing(
    *,
    db: Session,
    config: CourseLLMConfig,
    messages: list[dict[str, Any]],
    max_output_tokens: int | None,
    job: DiscussionLLMJob,
) -> dict[str, Any]:
    """Reuse group + flat endpoint routing like grading (text-only; vision not required)."""
    group_rows, flat_endpoints = _collect_grading_endpoints_for_config(config)
    need_vision = False

    if group_rows:
        routing = GroupRoutingContext.from_config(group_rows, task_id=job.id)
        last_error: Optional[str] = None
        for group_state in routing.group_states:
            group_state.apply_round_robin_start(job.id)
            while group_state.current_order:
                link = group_state.current_order[0]
                preset: LLMEndpointPreset = link.preset
                ok, reason = _preset_eligible_for_grading(preset, need_vision=need_vision)
                if not ok:
                    last_error = reason
                    group_state.remove_member(link)
                    continue
                attempt_limit = max(1, int(preset.max_retries or 0) + 1)
                for request_attempt in range(1, attempt_limit + 1):
                    try:
                        return _request_discussion_completion(
                            preset=preset,
                            messages=messages,
                            max_output_tokens=max_output_tokens,
                            job=job,
                        )
                    except RetryableLLMError as exc:
                        last_error = str(exc)
                        routing.note_failure(group_state, link, exc)
                        if request_attempt >= attempt_limit:
                            group_state.remove_member(link)
                            break
                        wait_seconds = min(
                            int(preset.initial_backoff_seconds or 2) * (2 ** (request_attempt - 1)),
                            120,
                        )
                        sleep_with_test_scaling(wait_seconds)
                    except NonRetryableLLMError as exc:
                        last_error = str(exc)
                        routing.note_failure(group_state, link, exc)
                        group_state.remove_member(link)
                        break
        raise NonRetryableLLMError(last_error or "所有组内端点都调用失败。")

    last_error_flat: Optional[str] = None
    for link in sorted(flat_endpoints, key=lambda row: (row.priority, row.id)):
        preset = link.preset
        ok, reason = _preset_eligible_for_grading(preset, need_vision=need_vision)
        if not ok:
            last_error_flat = reason
            continue
        attempt_limit = max(1, int(preset.max_retries or 0) + 1)
        for request_attempt in range(1, attempt_limit + 1):
            try:
                return _request_discussion_completion(
                    preset=preset,
                    messages=messages,
                    max_output_tokens=max_output_tokens,
                    job=job,
                )
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
    raise NonRetryableLLMError(last_error_flat or "所有端点都调用失败。")


def _claim_discussion_job_for_execution(db: Session, job_id: int) -> Optional[DiscussionLLMJob]:
    updated = (
        db.query(DiscussionLLMJob)
        .filter(
            DiscussionLLMJob.id == job_id,
            DiscussionLLMJob.status.in_(("pending", "retry_scheduled")),
        )
        .update(
            {
                DiscussionLLMJob.status: "processing",
                DiscussionLLMJob.next_retry_at: None,
                DiscussionLLMJob.finished_at: None,
                DiscussionLLMJob.error_code: None,
                DiscussionLLMJob.error_message: None,
                DiscussionLLMJob.failure_class: None,
                DiscussionLLMJob.last_error_at: None,
            },
            synchronize_session=False,
        )
    )
    if not updated:
        db.rollback()
        return None
    db.commit()
    return db.query(DiscussionLLMJob).filter(DiscussionLLMJob.id == job_id).first()


def run_discussion_llm_reply_for_job(job_id: int) -> None:
    """Load job in a new session and complete LLM reply (commits internally)."""
    db = SessionLocal()
    try:
        job = db.query(DiscussionLLMJob).filter(DiscussionLLMJob.id == job_id).first()
        if not job or job.status not in ("pending", "retry_scheduled"):
            return
        if not promote_due_discussion_job(db, job) and job.status == "retry_scheduled":
            db.commit()
            return
        job = _claim_discussion_job_for_execution(db, job_id)
        if not job:
            return
        user_entry = db.query(CourseDiscussionEntry).filter(CourseDiscussionEntry.id == job.user_entry_id).first()
        user = db.query(User).filter(User.id == job.requester_user_id).first()
        if not user_entry or not user:
            job.status = "failed"
            job.error_message = "内部错误：找不到讨论或用户。"
            job.finished_at = now_utc()
            db.commit()
            return
        _run_discussion_llm_reply_unlocked(
            db,
            job=job,
            user=user,
            user_body=user_entry.body,
            target_type=job.target_type,
            target_id=job.target_id,
            subject_id=job.subject_id,
            class_id=job.class_id,
        )
    finally:
        db.close()


def _run_discussion_llm_reply_unlocked(
    db: Session,
    *,
    job: DiscussionLLMJob,
    user: User,
    user_body: str,
    target_type: str,
    target_id: int,
    subject_id: int,
    class_id: int,
) -> None:
    def _schedule_failure(msg: str, *, release_reservation: bool, error_code: str) -> str:
        if release_reservation:
            release_discussion_quota_reservation(db, job.id)
        return schedule_discussion_retry(
            db,
            job,
            error_code=error_code,
            error_message=msg,
        )

    def _emit_failure_message(msg: str) -> None:
        sys_user = db.query(User).filter(User.username == "__system_llm_assistant__").first()
        if sys_user:
            assistant_entry = CourseDiscussionEntry(
                target_type=target_type,
                target_id=target_id,
                subject_id=subject_id,
                class_id=class_id,
                author_user_id=sys_user.id,
                body=f"【智能助教】暂无法回复：{msg}",
                body_format="markdown",
                linked_targets=[],
                message_kind="llm_assistant",
                llm_invocation=False,
            )
            db.add(assistant_entry)
            db.flush()
            job.assistant_entry_id = assistant_entry.id

    def _fail_visible(
        msg: str,
        *,
        release_reservation: bool,
        error_code: str,
        visible: bool = True,
    ) -> None:
        failure_class = _schedule_failure(
            msg,
            release_reservation=release_reservation,
            error_code=error_code,
        )
        if visible or failure_class != "transient":
            _emit_failure_message(msg)
        db.commit()

    hw: Optional[Homework] = None
    mat: Optional[CourseMaterial] = None
    if target_type == "homework":
        hw = db.query(Homework).filter(Homework.id == target_id).first()
        if not hw:
            _fail_visible("作业不存在。", release_reservation=False, error_code="discussion_target_missing", visible=True)
            return
    else:
        mat = db.query(CourseMaterial).filter(CourseMaterial.id == target_id).first()
        if not mat:
            _fail_visible("资料不存在。", release_reservation=False, error_code="discussion_target_missing", visible=True)
            return

    course = db.query(Subject).filter(Subject.id == subject_id).first()
    if not course:
        _fail_visible("课程不存在。", release_reservation=False, error_code="discussion_course_missing", visible=True)
        return

    student: Optional[Student] = None
    quota_exempt = discussion_llm_user_is_quota_exempt(user)
    if not quota_exempt:
        try:
            student = resolve_student_for_discussion_llm(db, user, class_id=class_id)
        except ValueError:
            _fail_visible("当前账号无法计费：请使用已绑定学籍的学生账号发起智能助教。", release_reservation=False, error_code="discussion_student_binding_missing", visible=True)
            return

    config = ensure_course_llm_config(db, subject_id, user_id=user.id)
    if not config.is_enabled:
        _fail_visible("当前课程未启用 LLM 配置。", release_reservation=False, error_code="llm_config_disabled", visible=True)
        return
    if not (config.groups or []) and not (config.endpoints or []):
        _fail_visible("当前课程未配置可用端点。", release_reservation=False, error_code="endpoint_missing", visible=True)
        return

    max_out = int(config.max_output_tokens) if config.max_output_tokens else None
    context_parts: list[str] = []
    if hw:
        context_parts.extend(_homework_context_blocks(db, hw, student_id=student.id if student else None))
    elif mat:
        context_parts.extend(_material_context_blocks(mat))
    context_text = "\n\n".join(context_parts)
    thread_text = _discussion_thread_text(
        db,
        target_type=target_type,
        target_id=target_id,
        subject_id=subject_id,
        class_id=class_id,
    )
    user_visible = strip_llm_ui_prefix(user_body)
    if not user_visible:
        user_visible = (user_body or "").strip()
    messages = _build_discussion_messages(
        context_text=context_text,
        thread_text=thread_text,
        user_message=user_visible,
        response_language=config.response_language,
    )
    est = _estimate_discussion_prompt_tokens(messages, max_out or 0)
    job.requester_student_id = student.id if student else None
    db.flush()

    if not quota_exempt:
        allowed, err = reserve_discussion_quota_tokens(
            db,
            job,
            config,
            student_id=student.id,
            subject_id=subject_id,
            estimated_tokens=est,
        )
        if not allowed:
            msg = {
                "quota_exceeded_student": "已达到本日学生 token 上限，智能助教未执行。",
            }.get(err or "", "今日额度已用尽，智能助教未执行。")
            _fail_visible(msg, release_reservation=False, error_code=err or "quota_exceeded_student", visible=True)
            return

    try:
        result = _call_discussion_with_routing(
            db=db,
            config=config,
            messages=messages,
            max_output_tokens=max_out,
            job=job,
        )
    except NonRetryableLLMError as exc:
        _fail_visible(str(exc) or "LLM 调用失败。", release_reservation=True, error_code="discussion_call_failed", visible=False)
        return
    except Exception as exc:
        _fail_visible(f"LLM 调用异常：{exc}", release_reservation=True, error_code="discussion_call_failed", visible=False)
        return

    sys_user = db.query(User).filter(User.username == "__system_llm_assistant__").first()
    if not sys_user:
        _fail_visible("系统未初始化智能助教账号，请联系管理员。", release_reservation=True, error_code="discussion_system_user_missing", visible=True)
        return

    reply_body = result["text"]
    usage = result.get("usage") or {}
    assistant_entry = CourseDiscussionEntry(
        target_type=target_type,
        target_id=target_id,
        subject_id=subject_id,
        class_id=class_id,
        author_user_id=sys_user.id,
        body=reply_body,
        body_format="markdown",
        linked_targets=[],
        message_kind="llm_assistant",
        llm_invocation=False,
    )
    db.add(assistant_entry)
    db.flush()
    job.assistant_entry_id = assistant_entry.id
    job.status = "success"
    job.error_message = None
    job.error_code = None
    job.failure_class = None
    job.next_retry_at = None
    job.finished_at = now_utc()
    if not quota_exempt and student is not None:
        record_discussion_usage_if_needed(db, job, config, student.id, subject_id, usage)
    db.commit()
