from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.domains.courses.access import (
    ensure_course_access_http,
    get_student_profile_for_user,
    is_course_instructor,
    prepare_student_course_context,
)
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.llm_grading import (
    build_png_data_url_from_image_bytes,
    ensure_course_llm_config,
    get_quota_usage_snapshot,
    get_student_quota_usage_snapshot,
    purge_invalid_course_llm_endpoints_for_preset,
    UNLIMITED_OUTPUT_TOKEN_SENTINEL,
    validate_text_connectivity,
    validate_vision_connectivity,
)
from apps.backend.courseeval_backend.domains.llm.token_quota import (
    apply_student_daily_token_overrides,
    get_or_create_global_quota_policy,
    resolve_effective_daily_student_tokens,
    resolve_global_quota_calendar,
    resolve_student_ids_for_scope,
)
from apps.backend.courseeval_backend.domains.llm.quota import get_used_tokens_for_scope, sum_reserved_tokens
from apps.backend.courseeval_backend.db.models import (
    CourseEnrollment,
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    LLMEndpointPreset,
    LLMGroup,
    LLMStudentTokenOverride,
    Student,
    Subject,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.api.schemas import (
    CourseLLMConfigResponse,
    CourseLLMConfigUpdate,
    CourseLLMConfigEndpointResponse,
    LLMGlobalQuotaPolicyResponse,
    LLMGlobalQuotaPolicyUpdate,
    LLMGroupResponse,
    LLMQuotaBulkOverrideRequest,
    LLMQuotaBulkOverrideResponse,
    LLMStudentQuotaOverrideUpsert,
    LLMEndpointPresetCreate,
    LLMEndpointPresetResponse,
    LLMEndpointPresetUpdate,
    StudentLLMCourseQuotaRow,
    StudentLLMQuotasSummaryResponse,
    StudentLLMQuotaUsageResponse,
)


router = APIRouter(prefix="/api/llm-settings", tags=["LLM 配置"])

VISION_NOTICE = "LLM 连通性验证会同时校验视觉接口。只有通过视觉能力校验的端点，才能被加入课程配置并用于作业自动评分。"


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _can_manage_course_llm(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.CLASS_TEACHER, UserRole.TEACHER]


def _ensure_course_llm_management_access(user: User, course: Subject) -> None:
    if not is_course_instructor(user, course):
        raise HTTPException(status_code=403, detail="Only the assigned course teacher can manage course LLM config.")


def _serialize_preset(preset: LLMEndpointPreset) -> LLMEndpointPresetResponse:
    return LLMEndpointPresetResponse(
        id=preset.id,
        name=preset.name,
        base_url=preset.base_url,
        model_name=preset.model_name,
        connect_timeout_seconds=preset.connect_timeout_seconds,
        read_timeout_seconds=preset.read_timeout_seconds,
        max_retries=preset.max_retries,
        initial_backoff_seconds=preset.initial_backoff_seconds,
        is_active=preset.is_active,
        supports_vision=bool(preset.supports_vision),
        validation_status=preset.validation_status,
        validation_message=preset.validation_message,
        text_validation_status=getattr(preset, "text_validation_status", None),
        text_validation_message=getattr(preset, "text_validation_message", None),
        vision_validation_status=getattr(preset, "vision_validation_status", None),
        vision_validation_message=getattr(preset, "vision_validation_message", None),
        validated_at=preset.validated_at,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


def _serialize_endpoint_item(item: CourseLLMConfigEndpoint) -> CourseLLMConfigEndpointResponse:
    return CourseLLMConfigEndpointResponse(
        id=item.id,
        preset_id=item.preset_id,
        priority=item.priority,
        group_id=getattr(item, "group_id", None),
        preset_name=item.preset.name if item.preset else None,
        model_name=item.preset.model_name if item.preset else None,
        validation_status=item.preset.validation_status if item.preset else None,
        supports_vision=item.preset.supports_vision if item.preset else None,
    )


def _serialize_course_config(config: CourseLLMConfig, db: Optional[Session] = None) -> CourseLLMConfigResponse:
    group_rows = sorted(
        [g for g in (config.groups or []) if g is not None],
        key=lambda row: (row.priority, row.id),
    )
    if group_rows and any((g.members or []) for g in group_rows):
        flat: list[CourseLLMConfigEndpoint] = []
        for g in group_rows:
            for m in sorted(g.members or [], key=lambda row: (row.priority, row.id)):
                flat.append(m)
    else:
        flat = sorted(
            (config.endpoints or []),
            key=lambda row: (row.priority, row.id),
        )

    quota_usage = get_quota_usage_snapshot(db, config) if db is not None else None
    return CourseLLMConfigResponse(
        id=config.id,
        subject_id=config.subject_id,
        is_enabled=bool(config.is_enabled),
        response_language=config.response_language,
        max_input_tokens=config.max_input_tokens,
        max_output_tokens=None if (config.max_output_tokens or 0) >= UNLIMITED_OUTPUT_TOKEN_SENTINEL else config.max_output_tokens,
        system_prompt=config.system_prompt,
        teacher_prompt=config.teacher_prompt,
        endpoints=[_serialize_endpoint_item(item) for item in flat],
        groups=[
            LLMGroupResponse(
                id=g.id,
                priority=g.priority,
                name=g.name,
                members=[_serialize_endpoint_item(m) for m in sorted(g.members or [], key=lambda row: (row.priority, row.id))],
            )
            for g in group_rows
        ],
        visual_validation_notice=VISION_NOTICE,
        quota_usage=quota_usage,
    )


@router.get("/presets", response_model=list[LLMEndpointPresetResponse])
def list_endpoint_presets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _can_manage_course_llm(current_user):
        raise HTTPException(status_code=403, detail="You do not have access to LLM settings.")
    presets = db.query(LLMEndpointPreset).order_by(LLMEndpointPreset.id.asc()).all()
    return [_serialize_preset(item) for item in presets]


@router.post("/presets", response_model=LLMEndpointPresetResponse)
def create_endpoint_preset(
    payload: LLMEndpointPresetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only administrators can manage endpoint presets.")
    existing = db.query(LLMEndpointPreset).filter(LLMEndpointPreset.name == payload.name.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Preset name already exists.")

    preset = LLMEndpointPreset(
        name=payload.name.strip(),
        base_url=payload.base_url.strip(),
        api_key=(payload.api_key or "").strip(),
        model_name=payload.model_name.strip(),
        connect_timeout_seconds=payload.connect_timeout_seconds,
        read_timeout_seconds=payload.read_timeout_seconds,
        max_retries=payload.max_retries,
        initial_backoff_seconds=payload.initial_backoff_seconds,
        is_active=payload.is_active,
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return _serialize_preset(preset)


@router.put("/presets/{preset_id}", response_model=LLMEndpointPresetResponse)
def update_endpoint_preset(
    preset_id: int,
    payload: LLMEndpointPresetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only administrators can manage endpoint presets.")

    preset = db.query(LLMEndpointPreset).filter(LLMEndpointPreset.id == preset_id).first()
    if not preset:
        raise HTTPException(status_code=404, detail="Endpoint preset not found.")

    for field in [
        "name",
        "base_url",
        "api_key",
        "model_name",
        "connect_timeout_seconds",
        "read_timeout_seconds",
        "max_retries",
        "initial_backoff_seconds",
        "is_active",
    ]:
        value = getattr(payload, field)
        if value is not None:
            if isinstance(value, str):
                value = value.strip()
            setattr(preset, field, value)

    db.commit()
    db.refresh(preset)
    purge_invalid_course_llm_endpoints_for_preset(db, preset.id)
    db.commit()
    db.refresh(preset)
    return _serialize_preset(preset)


@router.post("/presets/{preset_id}/validate", response_model=LLMEndpointPresetResponse)
async def validate_preset(
    preset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only administrators can validate endpoint presets.")

    preset = db.query(LLMEndpointPreset).filter(LLMEndpointPreset.id == preset_id).first()
    if not preset:
        raise HTTPException(status_code=404, detail="Endpoint preset not found.")

    image_data_url: Optional[str] = None
    ct = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in ct:
        form = await request.form()
        up = form.get("image")
        if up is not None:
            read_fn = getattr(up, "read", None)
            if read_fn is None or not callable(read_fn):
                raise HTTPException(status_code=400, detail="Field 'image' must be a file upload.")
            body = await read_fn()
            try:
                image_data_url = build_png_data_url_from_image_bytes(body)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Vision step requires a user image (gateways that reject the built-in 1x1 test should use a real file).
    if not image_data_url:
        raise HTTPException(
            status_code=400,
            detail="请在上传图片后再执行视觉校验：选择一张本地图片（JPEG/PNG/WebP 等）作为多模态测试用图。",
        )

    ok_t, msg_t = validate_text_connectivity(
        base_url=preset.base_url,
        api_key=preset.api_key,
        model_name=preset.model_name,
        connect_timeout_seconds=preset.connect_timeout_seconds,
        read_timeout_seconds=preset.read_timeout_seconds,
    )
    preset.text_validation_status = "passed" if ok_t else "failed"
    preset.text_validation_message = msg_t
    if not ok_t:
        preset.validation_status = "failed"
        preset.validation_message = msg_t
        preset.supports_vision = False
        preset.vision_validation_status = "skipped"
        preset.vision_validation_message = "未执行：纯文本未通过。"
    else:
        ok_v, msg_v = validate_vision_connectivity(
            base_url=preset.base_url,
            api_key=preset.api_key,
            model_name=preset.model_name,
            connect_timeout_seconds=preset.connect_timeout_seconds,
            read_timeout_seconds=preset.read_timeout_seconds,
            image_data_url=image_data_url,
        )
        preset.vision_validation_status = "passed" if ok_v else "failed"
        preset.vision_validation_message = msg_v
        ok = ok_v
        message = f"{msg_t} {msg_v}" if ok_v else f"{msg_t} {msg_v}"
        preset.validation_status = "validated" if ok else "failed"
        preset.validation_message = message
        preset.supports_vision = bool(ok_v)
    preset.validated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(preset)
    purge_invalid_course_llm_endpoints_for_preset(db, preset.id)
    db.commit()
    db.refresh(preset)
    return _serialize_preset(preset)


@router.get("/courses/student-quotas", response_model=StudentLLMQuotasSummaryResponse)
def list_student_llm_quotas_for_enrolled_courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """System-wide LLM token budget for the student, with per-course attribution rows."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can view personal LLM quota.")

    prepare_student_course_context(current_user, db)
    db.commit()
    student = get_student_profile_for_user(current_user, db)
    if not student:
        raise HTTPException(status_code=400, detail="未找到与账号匹配的花名册。")

    pol = get_or_create_global_quota_policy(db)
    lim = resolve_effective_daily_student_tokens(db, student.id)
    ov = db.query(LLMStudentTokenOverride).filter(LLMStudentTokenOverride.student_id == student.id).first()
    uses_override = ov is not None
    usage_date, timezone_name = resolve_global_quota_calendar(db)
    total_used = get_used_tokens_for_scope(
        db,
        usage_date=usage_date,
        timezone_name=timezone_name,
        student_id=student.id,
    )
    total_used += sum_reserved_tokens(
        db,
        usage_date=usage_date,
        timezone_name=timezone_name,
        student_id=student.id,
    )

    rows: list[StudentLLMCourseQuotaRow] = []
    enrollments = (
        db.query(CourseEnrollment, Subject)
        .join(Subject, Subject.id == CourseEnrollment.subject_id)
        .filter(CourseEnrollment.student_id == student.id)
        .order_by(Subject.name.asc(), Subject.id.asc())
        .all()
    )
    for _enr, subj in enrollments:
        db.flush()
        course_used = get_used_tokens_for_scope(
            db,
            usage_date=usage_date,
            timezone_name=timezone_name,
            student_id=student.id,
            subject_id=int(subj.id),
        )
        course_used += sum_reserved_tokens(
            db,
            usage_date=usage_date,
            timezone_name=timezone_name,
            student_id=student.id,
            subject_id=int(subj.id),
        )
        snap = {
            "usage_date": usage_date,
            "quota_timezone": timezone_name,
            "daily_student_token_limit": lim,
            "student_used_tokens_today": total_used,
            "student_remaining_tokens_today": max(0, lim - total_used),
        }
        rows.append(
            StudentLLMCourseQuotaRow(
                subject_id=int(subj.id),
                subject_name=subj.name or f"课程 {subj.id}",
                usage_date=str(snap["usage_date"]),
                quota_timezone=str(snap["quota_timezone"]),
                daily_student_token_limit=int(snap["daily_student_token_limit"] or lim),
                student_used_tokens_today=snap.get("student_used_tokens_today"),
                student_remaining_tokens_today=snap.get("student_remaining_tokens_today"),
                course_used_tokens_today=course_used,
                course_usage_ratio=round(course_used / total_used, 4) if total_used > 0 else 0,
            )
        )
    db.commit()
    return StudentLLMQuotasSummaryResponse(
        courses=rows,
        global_default_daily_student_tokens=int(pol.default_daily_student_tokens),
        usage_date=usage_date,
        quota_timezone=timezone_name,
        daily_student_token_limit=lim,
        student_used_tokens_today=total_used,
        student_remaining_tokens_today=max(0, lim - total_used),
        uses_personal_override=uses_override,
    )


@router.get("/courses/student-quota/{subject_id}", response_model=StudentLLMQuotaUsageResponse)
def get_student_llm_quota_for_course(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Token usage vs daily limits for the logged-in student on a course (read-only, no presets)."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can view personal LLM quota.")

    prepare_student_course_context(current_user, db)
    db.commit()
    student = get_student_profile_for_user(current_user, db)
    if not student:
        raise HTTPException(status_code=400, detail="未找到与账号匹配的花名册。")

    ensure_course_access_http(subject_id, current_user, db)

    pol = get_or_create_global_quota_policy(db)
    db.commit()
    lim = resolve_effective_daily_student_tokens(db, student.id)
    ov = db.query(LLMStudentTokenOverride).filter(LLMStudentTokenOverride.student_id == student.id).first()
    uses_override = ov is not None

    snap = get_student_quota_usage_snapshot(db, None, student_id=student.id, subject_id=subject_id)
    course_used = get_used_tokens_for_scope(
        db,
        usage_date=str(snap["usage_date"]),
        timezone_name=str(snap["quota_timezone"]),
        student_id=student.id,
        subject_id=subject_id,
    )
    course_used += sum_reserved_tokens(
        db,
        usage_date=str(snap["usage_date"]),
        timezone_name=str(snap["quota_timezone"]),
        student_id=student.id,
        subject_id=subject_id,
    )
    total_used = int(snap.get("student_used_tokens_today") or 0)
    return StudentLLMQuotaUsageResponse(
        subject_id=subject_id,
        usage_date=snap["usage_date"],
        quota_timezone=snap["quota_timezone"],
        daily_student_token_limit=snap.get("daily_student_token_limit"),
        global_default_daily_student_tokens=int(pol.default_daily_student_tokens),
        uses_personal_override=uses_override,
        student_used_tokens_today=snap.get("student_used_tokens_today"),
        student_remaining_tokens_today=snap.get("student_remaining_tokens_today"),
        course_used_tokens_today=course_used,
        course_usage_ratio=round(course_used / total_used, 4) if total_used > 0 else 0,
    )


@router.get("/admin/quota-policy", response_model=LLMGlobalQuotaPolicyResponse)
def get_llm_global_quota_policy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only administrators can view LLM quota policy.")
    row = get_or_create_global_quota_policy(db)
    db.commit()
    return LLMGlobalQuotaPolicyResponse(
        id=row.id,
        default_daily_student_tokens=int(row.default_daily_student_tokens),
        quota_timezone=row.quota_timezone or "UTC",
        estimated_chars_per_token=float(getattr(row, "estimated_chars_per_token", None) or 4.0),
        estimated_image_tokens=int(getattr(row, "estimated_image_tokens", None) or 850),
        max_parallel_grading_tasks=int(getattr(row, "max_parallel_grading_tasks", None) or 3),
    )


@router.put("/admin/quota-policy", response_model=LLMGlobalQuotaPolicyResponse)
def update_llm_global_quota_policy(
    payload: LLMGlobalQuotaPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only administrators can update LLM quota policy.")
    row = get_or_create_global_quota_policy(db)
    if payload.default_daily_student_tokens is not None:
        row.default_daily_student_tokens = int(payload.default_daily_student_tokens)
    if payload.quota_timezone is not None:
        row.quota_timezone = (payload.quota_timezone or "UTC").strip() or "UTC"
    if payload.estimated_chars_per_token is not None:
        row.estimated_chars_per_token = float(payload.estimated_chars_per_token)
    if payload.estimated_image_tokens is not None:
        row.estimated_image_tokens = int(payload.estimated_image_tokens)
    if payload.max_parallel_grading_tasks is not None:
        row.max_parallel_grading_tasks = int(payload.max_parallel_grading_tasks)
    db.commit()
    db.refresh(row)
    return LLMGlobalQuotaPolicyResponse(
        id=row.id,
        default_daily_student_tokens=int(row.default_daily_student_tokens),
        quota_timezone=row.quota_timezone or "UTC",
        estimated_chars_per_token=float(getattr(row, "estimated_chars_per_token", None) or 4.0),
        estimated_image_tokens=int(getattr(row, "estimated_image_tokens", None) or 850),
        max_parallel_grading_tasks=int(getattr(row, "max_parallel_grading_tasks", None) or 3),
    )


@router.put("/admin/students/{student_id}/quota-override", response_model=LLMQuotaBulkOverrideResponse)
def upsert_one_student_llm_quota_override(
    student_id: int,
    payload: LLMStudentQuotaOverrideUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only administrators can set LLM quota overrides.")
    if not db.query(Student).filter(Student.id == student_id).first():
        raise HTTPException(status_code=404, detail="Student not found.")
    get_or_create_global_quota_policy(db)
    n = apply_student_daily_token_overrides(
        db,
        [student_id],
        int(payload.daily_tokens or 0),
        clear_only=bool(payload.clear_override),
    )
    pol = get_or_create_global_quota_policy(db)
    db.commit()
    return LLMQuotaBulkOverrideResponse(
        affected_students=n,
        default_daily_student_tokens=int(pol.default_daily_student_tokens),
    )


@router.post("/admin/quota-overrides/bulk", response_model=LLMQuotaBulkOverrideResponse)
def bulk_set_llm_student_quota_overrides(
    payload: LLMQuotaBulkOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only administrators can set LLM quota overrides.")
    get_or_create_global_quota_policy(db)
    ids = resolve_student_ids_for_scope(
        db,
        payload.scope,  # type: ignore[arg-type]
        class_id=payload.class_id,
        subject_id=payload.subject_id,
    )
    n = apply_student_daily_token_overrides(
        db,
        ids,
        int(payload.daily_tokens or 0),
        clear_only=bool(payload.clear_override),
    )
    pol = get_or_create_global_quota_policy(db)
    db.commit()
    return LLMQuotaBulkOverrideResponse(
        affected_students=n,
        default_daily_student_tokens=int(pol.default_daily_student_tokens),
    )


@router.get("/courses/{subject_id}", response_model=CourseLLMConfigResponse)
def get_course_llm_config(
    subject_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _can_manage_course_llm(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can manage course LLM config.")
    course = ensure_course_access_http(subject_id, current_user, db)
    _ensure_course_llm_management_access(current_user, course)

    config = ensure_course_llm_config(db, subject_id, current_user.id)
    db.commit()
    db.refresh(config)
    return _serialize_course_config(config, db)


@router.put("/courses/{subject_id}", response_model=CourseLLMConfigResponse)
def update_course_llm_config(
    subject_id: int,
    payload: CourseLLMConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _can_manage_course_llm(current_user):
        raise HTTPException(status_code=403, detail="Only teachers can manage course LLM config.")
    course = ensure_course_access_http(subject_id, current_user, db)
    _ensure_course_llm_management_access(current_user, course)

    config = ensure_course_llm_config(db, subject_id, current_user.id)
    existing_has_group_rows = (
        db.query(LLMGroup).filter(LLMGroup.config_id == config.id).first() is not None
    )
    # Teacher UI only sends flat "endpoints" and often omits "groups": do not delete API-configured
    # group routing unless explicitly requested.
    preserve_group_routing = (
        existing_has_group_rows
        and not (payload.groups or [])
        and not payload.replace_group_routing_with_flat_endpoints
    )

    config.is_enabled = payload.is_enabled
    config.response_language = payload.response_language
    config.max_input_tokens = payload.max_input_tokens
    config.max_output_tokens = (
        UNLIMITED_OUTPUT_TOKEN_SENTINEL if payload.max_output_tokens is None else payload.max_output_tokens
    )
    config.system_prompt = payload.system_prompt
    config.teacher_prompt = payload.teacher_prompt
    config.updated_by = current_user.id

    if preserve_group_routing:
        db.commit()
        db.refresh(config)
        return _serialize_course_config(config, db)

    db.query(CourseLLMConfigEndpoint).filter(CourseLLMConfigEndpoint.config_id == config.id).delete()
    db.query(LLMGroup).filter(LLMGroup.config_id == config.id).delete()
    db.flush()

    seen_preset_ids: set[int] = set()

    def _bind_endpoint_row(priority: int, preset_id: int, group_id: Optional[int] = None) -> None:
        if preset_id in seen_preset_ids:
            raise HTTPException(
                status_code=400,
                detail="每个端点在同一课程中只能出现一次。若需多副本，请为同一供应商另建不同名称的端点配置。",
            )
        seen_preset_ids.add(preset_id)
        preset = db.query(LLMEndpointPreset).filter(LLMEndpointPreset.id == preset_id).first()
        if not preset:
            raise HTTPException(status_code=400, detail=f"Endpoint preset {preset_id} not found.")
        if preset.validation_status != "validated" or not preset.supports_vision:
            raise HTTPException(
                status_code=400,
                detail=f"Endpoint preset {preset.name} has not passed vision validation and cannot be assigned.",
            )
        db.add(
            CourseLLMConfigEndpoint(
                config_id=config.id,
                group_id=group_id,
                preset_id=preset.id,
                priority=priority,
            )
        )

    if payload.groups and len(payload.groups) > 0:
        for gi, grp in enumerate(payload.groups):
            if not grp.members or len(grp.members) == 0:
                raise HTTPException(status_code=400, detail="每个 LLM 组至少需要包含一个已校验的端点。")
            g = LLMGroup(
                config_id=config.id,
                priority=gi + 1,
                name=(grp.name or "").strip() or f"group {gi + 1}",
            )
            db.add(g)
            db.flush()
            for mj, mem in enumerate(grp.members):
                _bind_endpoint_row(priority=mj + 1, preset_id=mem.preset_id, group_id=g.id)
    else:
        for item in sorted(payload.endpoints, key=lambda row: (row.priority, row.preset_id)):
            _bind_endpoint_row(priority=item.priority, preset_id=item.preset_id, group_id=None)

    db.commit()
    db.refresh(config)
    return _serialize_course_config(config, db)
