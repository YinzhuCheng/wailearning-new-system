"""Ephemeral test data and mock integrations for Playwright / local E2E."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_password_hash, get_current_user_optional
from apps.backend.courseeval_backend.core.config import settings
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.llm_grading import (
    UNLIMITED_OUTPUT_TOKEN_SENTINEL,
    process_next_grading_task,
    start_grading_worker,
    worker_manager,
)
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    CourseMaterial,
    CourseMaterialChapter,
    CourseMaterialHomeworkLink,
    CourseMaterialSection,
    Gender,
    Homework,
    HomeworkGradingTask,
    LLMEndpointPreset,
    Student,
    Subject,
    SubjectClassLink,
    User,
    UserRole,
)

def require_e2e_dev_api_exposed() -> None:
    """Block every /api/e2e route unless current settings allow the dev API.

    The router stays registered so tests can toggle ``E2E_DEV_SEED_ENABLED`` at runtime
    without reloading ``main``; production still returns **404** for all paths here
    when ``expose_e2e_dev_api()`` is false (defense in depth).
    """
    if not settings.expose_e2e_dev_api():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


router = APIRouter(
    prefix="/api/e2e",
    tags=["e2e-dev"],
    dependencies=[Depends(require_e2e_dev_api_exposed)],
)

_mock_llm_lock = threading.Lock()
_mock_llm_profiles: dict[str, dict[str, Any]] = {}


def _reset_mock_llm_state() -> None:
    with _mock_llm_lock:
        _mock_llm_profiles.clear()


def _record_mock_llm_request(profile: str, record: dict[str, Any]) -> None:
    with _mock_llm_lock:
        slot = _mock_llm_profiles.setdefault(profile, {"steps": [], "cursor": 0, "repeat_last": True, "requests": []})
        requests = slot.setdefault("requests", [])
        record["request_index"] = len(requests) + 1
        requests.append(record)
        if len(requests) > 200:
            del requests[:-200]


def _next_mock_llm_step(profile: str) -> dict[str, Any]:
    with _mock_llm_lock:
        slot = _mock_llm_profiles.setdefault(profile, {"steps": [], "cursor": 0, "repeat_last": True, "requests": []})
        steps = list(slot.get("steps") or [])
        cursor = int(slot.get("cursor") or 0)
        repeat_last = bool(slot.get("repeat_last", True))
        if not steps:
            step = {"kind": "ok", "score": 80.0, "comment": f"{profile}:ok"}
        elif cursor < len(steps):
            step = dict(steps[cursor] or {})
            slot["cursor"] = cursor + 1
        elif repeat_last:
            step = dict(steps[-1] or {})
        else:
            step = {"kind": "ok", "score": 80.0, "comment": f"{profile}:default"}
        return step


def _is_validation_request(payload: dict[str, Any]) -> bool:
    messages = payload.get("messages") or []
    if not messages:
        return False
    first = messages[0]
    content = first.get("content")
    if isinstance(content, str):
        return "single word: OK" in content or "reply with OK" in content
    if isinstance(content, list):
        joined = " ".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
        return "reply with OK" in joined
    return False


def _mock_llm_success_body(profile: str, step: dict[str, Any], *, validation: bool) -> dict[str, Any]:
    if validation:
        content = str(step.get("text") or "OK")
    elif step.get("text") is not None:
        content = str(step.get("text"))
    else:
        payload = {
            "score": float(step.get("score", 80.0)),
            "comment": str(step.get("comment") or f"{profile}:ok"),
        }
        content = json.dumps(payload, ensure_ascii=False)
    usage = step.get("usage") or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    return {
        "choices": [{"message": {"content": content}}],
        "usage": usage,
    }


def _require_seed_token(x_e2e_seed_token: str | None) -> None:
    if not settings.E2E_DEV_SEED_ENABLED:
        raise HTTPException(status_code=404, detail="E2E dev seed is disabled.")
    expected = (settings.E2E_DEV_SEED_TOKEN or "").strip()
    if not expected or (x_e2e_seed_token or "").strip() != expected:
        raise HTTPException(status_code=403, detail="Invalid E2E seed token.")


def _require_e2e_admin_when_configured(current_user: User | None, *, require_admin_jwt: bool) -> None:
    """Optional second factor for powerful /api/e2e/dev/* routes when E2E_DEV_REQUIRE_ADMIN_JWT is true."""
    if not require_admin_jwt:
        return
    if not getattr(settings, "E2E_DEV_REQUIRE_ADMIN_JWT", False):
        return
    if current_user is None or getattr(current_user, "role", None) != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=403,
            detail="This E2E dev endpoint requires an administrator Bearer token when E2E_DEV_REQUIRE_ADMIN_JWT is enabled.",
        )


def _require_e2e_call_gates(
    x_e2e_seed_token: str | None,
    current_user: User | None,
    *,
    require_admin_jwt: bool,
) -> None:
    _require_seed_token(x_e2e_seed_token)
    _require_e2e_admin_when_configured(current_user, require_admin_jwt=require_admin_jwt)


@router.post("/dev/reset-scenario")
def reset_e2e_scenario(
    x_e2e_seed_token: str | None = Header(None, alias="X-E2E-Seed-Token"),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Create isolated users/classes/courses for UI tests. Safe to call repeatedly (new suffix each time).
    """
    _require_e2e_call_gates(x_e2e_seed_token, current_user, require_admin_jwt=False)
    _reset_mock_llm_state()

    suffix = uuid.uuid4().hex[:10]
    pwd = "E2eTest1!"
    hpwd = get_password_hash(pwd)

    c1 = Class(name=f"E2E甲班_{suffix}", grade=2026)
    c2 = Class(name=f"E2E乙班_{suffix}", grade=2026)
    db.add_all([c1, c2])
    db.flush()

    admin = User(
        username=f"e2e_adm_{suffix}",
        hashed_password=get_password_hash("E2eAdmin1!"),
        real_name="E2E管理员",
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    t_own = User(
        username=f"e2e_teach_own_{suffix}",
        hashed_password=hpwd,
        real_name=f"E2E任课甲_{suffix}",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    t_other = User(
        username=f"e2e_teach_other_{suffix}",
        hashed_password=hpwd,
        real_name=f"E2E任课乙_{suffix}",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    ct = User(
        username=f"e2e_class_teacher_{suffix}",
        hashed_password=hpwd,
        real_name=f"E2E班主任_{suffix}",
        role=UserRole.CLASS_TEACHER.value,
        class_id=c1.id,
        is_active=True,
    )
    db.add_all([admin, t_own, t_other, ct])
    db.flush()

    st_plain = Student(
        name="E2E学生甲",
        student_no=f"e2e_stu_plain_{suffix}",
        gender=Gender.MALE,
        class_id=c1.id,
    )
    st_drop = Student(
        name="E2E退选生",
        student_no=f"e2e_stu_drop_{suffix}",
        gender=Gender.MALE,
        class_id=c1.id,
    )
    st_b = Student(
        name="E2E学生乙",
        student_no=f"e2e_stu_b_{suffix}",
        gender=Gender.FEMALE,
        class_id=c1.id,
    )
    db.add_all([st_plain, st_drop, st_b])
    db.flush()

    u_plain = User(
        username=st_plain.student_no,
        hashed_password=hpwd,
        real_name=st_plain.name,
        role=UserRole.STUDENT.value,
        class_id=c1.id,
        student_id=st_plain.id,
        is_active=True,
    )
    u_drop = User(
        username=st_drop.student_no,
        hashed_password=hpwd,
        real_name=st_drop.name,
        role=UserRole.STUDENT.value,
        class_id=c1.id,
        student_id=st_drop.id,
        is_active=True,
    )
    u_b = User(
        username=st_b.student_no,
        hashed_password=hpwd,
        real_name=st_b.name,
        role=UserRole.STUDENT.value,
        class_id=c1.id,
        student_id=st_b.id,
        is_active=True,
    )
    db.add_all([u_plain, u_drop, u_b])
    db.flush()

    # Parent SPA accepts 8-character parent codes. Keep enough entropy for
    # persistent E2E SQLite while matching the browser input contract.
    st_plain.parent_code = f"P{suffix[:7].upper()}"
    st_plain.parent_code_expires = None

    db.flush()
    course_req = Subject(
        name=f"E2E必修课_{suffix}",
        teacher_id=t_own.id,
        class_id=c1.id,
        course_type="required",
        status="active",
    )
    course_el = Subject(
        name=f"E2E选修课_{suffix}",
        teacher_id=t_own.id,
        class_id=None,
        course_type="elective",
        status="active",
    )
    course_other = Subject(
        name=f"E2E乙班课_{suffix}",
        teacher_id=t_other.id,
        class_id=c2.id,
        course_type="required",
        status="active",
    )
    course_orphan = Subject(
        name=f"E2E无班级课_{suffix}",
        teacher_id=t_own.id,
        class_id=None,
        course_type="required",
        status="active",
    )
    db.add_all([course_req, course_el, course_other, course_orphan])
    db.flush()

    db.add(SubjectClassLink(subject_id=course_req.id, class_id=c1.id, enrollment_mode="all_in_class"))
    db.add(SubjectClassLink(subject_id=course_other.id, class_id=c2.id, enrollment_mode="all_in_class"))
    db.flush()

    # st_plain / st_drop 已在必修课；st_b 仅在花名册，用于「从花名册进课」勾选
    for st in (st_plain, st_drop):
        db.add(
            CourseEnrollment(
                subject_id=course_req.id,
                student_id=st.id,
                class_id=c1.id,
                enrollment_type="required",
                can_remove=False,
            )
        )

    hw = Homework(
        title=f"E2E_UI作业_{suffix}",
        content="用于 Playwright UI 测试的作业说明。",
        class_id=c1.id,
        subject_id=course_req.id,
        max_score=100.0,
        grade_precision="integer",
        auto_grading_enabled=True,
        allow_late_submission=True,
        late_submission_affects_score=False,
        created_by=t_own.id,
    )
    db.add(hw)
    db.flush()

    hw_extra = Homework(
        title=f"E2E扩展作业_{suffix}",
        content="用于阅读页展示未归档作业和章节作业入口。",
        class_id=c1.id,
        subject_id=course_req.id,
        max_score=100.0,
        grade_precision="integer",
        auto_grading_enabled=True,
        allow_late_submission=True,
        late_submission_affects_score=False,
        created_by=t_own.id,
    )
    db.add(hw_extra)
    db.flush()

    unc = (
        db.query(CourseMaterialChapter)
        .filter(
            CourseMaterialChapter.subject_id == course_req.id,
            CourseMaterialChapter.is_uncategorized.is_(True),
        )
        .first()
    )
    if not unc:
        unc = CourseMaterialChapter(
            subject_id=course_req.id,
            parent_id=None,
            title="未分类",
            sort_order=0,
            is_uncategorized=True,
        )
        db.add(unc)
        db.flush()

    # Two named root chapters so reorder E2E has sibling IDs under parent_id=None (uncategorized excluded from reorder API).
    ch_extra_a = CourseMaterialChapter(
        subject_id=course_req.id,
        parent_id=None,
        title=f"E2E章节A_{suffix}",
        sort_order=1,
        is_uncategorized=False,
    )
    ch_extra_b = CourseMaterialChapter(
        subject_id=course_req.id,
        parent_id=None,
        title=f"E2E章节B_{suffix}",
        sort_order=2,
        is_uncategorized=False,
    )
    db.add_all([ch_extra_a, ch_extra_b])
    db.flush()

    mat_disc = CourseMaterial(
        title=f"E2E讨论资料_{suffix}",
        content="用于讨论区 E2E 的资料正文。",
        class_id=c1.id,
        subject_id=course_req.id,
        created_by=t_own.id,
    )
    db.add(mat_disc)
    db.flush()
    db.add(
        CourseMaterialSection(
            material_id=mat_disc.id,
            chapter_id=ch_extra_a.id,
            sort_order=0,
        )
    )

    mat_a2 = CourseMaterial(
        title=f"E2E章节A补充资料_{suffix}",
        content="用于在阅读页展示“本章资料”的第二条入口。",
        class_id=c1.id,
        subject_id=course_req.id,
        created_by=t_own.id,
    )
    mat_b1 = CourseMaterial(
        title=f"E2E章节B资料_{suffix}",
        content="用于目录页点击章节后切换到另一个章节资料。",
        class_id=c1.id,
        subject_id=course_req.id,
        created_by=t_own.id,
    )
    mat_loose = CourseMaterial(
        title=f"E2E未归档资料_{suffix}",
        content="用于阅读页展示未归档资料入口。",
        class_id=c1.id,
        subject_id=course_req.id,
        created_by=t_own.id,
    )
    db.add_all([mat_a2, mat_b1, mat_loose])
    db.flush()
    db.add_all([
        CourseMaterialSection(
            material_id=mat_a2.id,
            chapter_id=ch_extra_a.id,
            sort_order=1,
        ),
        CourseMaterialSection(
            material_id=mat_b1.id,
            chapter_id=ch_extra_b.id,
            sort_order=0,
        ),
        CourseMaterialSection(
            material_id=mat_loose.id,
            chapter_id=unc.id,
            sort_order=0,
        ),
    ])
    db.flush()

    db.add_all([
        CourseMaterialHomeworkLink(
            chapter_id=ch_extra_a.id,
            homework_id=hw.id,
            sort_order=0,
        ),
        CourseMaterialHomeworkLink(
            chapter_id=unc.id,
            homework_id=hw_extra.id,
            sort_order=0,
        ),
    ])
    db.flush()

    # Course LLM for discussion assistant + grading E2E: mock chat completions (plain text for discussion prompts).
    api_self_port = (os.environ.get("E2E_API_PORT") or "8012").strip()
    api_self_base = f"http://127.0.0.1:{api_self_port}"
    disc_profile = f"discuss_{suffix}"
    llm_preset = LLMEndpointPreset(
        name=f"e2e_discussion_{suffix}",
        base_url=f"{api_self_base}/api/e2e/dev/mock-llm/{disc_profile}/v1/",
        api_key="e2e-discussion-mock-key",
        model_name="e2e-discussion-mock",
        max_retries=0,
        initial_backoff_seconds=1,
        is_active=True,
        supports_vision=True,
        validation_status="validated",
        text_validation_status="passed",
        vision_validation_status="passed",
    )
    db.add(llm_preset)
    db.flush()
    llm_cfg = CourseLLMConfig(
        subject_id=course_req.id,
        is_enabled=True,
        max_input_tokens=16000,
        max_output_tokens=UNLIMITED_OUTPUT_TOKEN_SENTINEL,
    )
    db.add(llm_cfg)
    db.flush()
    db.add(
        CourseLLMConfigEndpoint(
            config_id=llm_cfg.id,
            preset_id=llm_preset.id,
            priority=1,
            group_id=None,
        )
    )
    with _mock_llm_lock:
        _mock_llm_profiles[disc_profile] = {
            "steps": [
                {
                    "kind": "ok",
                    "text": "【E2E助教】收到，请继续努力学习。",
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                }
            ],
            "cursor": 0,
            "repeat_last": True,
            "requests": [],
        }

    db.commit()
    db.refresh(mat_disc)

    return {
        "suffix": suffix,
        "password_teacher_student": pwd,
        "password_admin": "E2eAdmin1!",
        "admin": {"username": admin.username, "password": "E2eAdmin1!"},
        "teacher_own": {"username": t_own.username, "password": pwd},
        "teacher_other": {"username": t_other.username, "password": pwd},
        "student_plain": {
            "username": u_plain.username,
            "password": pwd,
            "student_row_id": st_plain.id,
            "student_user_id": u_plain.id,
        },
        "student_drop": {
            "username": u_drop.username,
            "password": pwd,
            "student_row_id": st_drop.id,
            "student_user_id": u_drop.id,
        },
        "student_b": {
            "username": u_b.username,
            "password": pwd,
            "student_row_id": st_b.id,
            "student_user_id": u_b.id,
        },
        "class_id_1": c1.id,
        "class_id_2": c2.id,
        "class_name_1": c1.name,
        "course_required_id": course_req.id,
        "course_elective_id": course_el.id,
        "course_other_teacher_id": course_other.id,
        "course_orphan_id": course_orphan.id,
        "homework_id": hw.id,
        "homework_extra_id": hw_extra.id,
        "material_discussion_id": mat_disc.id,
        "discussion_llm_profile": disc_profile,
        "user_ids_for_batch": [u_plain.id, u_b.id],
        "teacher_user_id": t_own.id,
        "class_teacher": {"username": ct.username, "password": pwd},
        "parent_code": st_plain.parent_code,
    }


@router.post("/dev/mock-llm/configure")
def configure_mock_llm(
    payload: dict[str, Any] = Body(default_factory=dict),
    x_e2e_seed_token: str | None = Header(None, alias="X-E2E-Seed-Token"),
    current_user: User | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    _require_e2e_call_gates(x_e2e_seed_token, current_user, require_admin_jwt=True)
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        raise HTTPException(status_code=400, detail="profiles must be an object.")
    with _mock_llm_lock:
        _mock_llm_profiles.clear()
        for profile, cfg in profiles.items():
            row = cfg if isinstance(cfg, dict) else {}
            _mock_llm_profiles[str(profile)] = {
                "steps": list(row.get("steps") or []),
                "cursor": 0,
                "repeat_last": bool(row.get("repeat_last", True)),
                "requests": [],
            }
    return {"profiles": sorted(_mock_llm_profiles.keys())}


@router.get("/dev/mock-llm/state")
def mock_llm_state(
    x_e2e_seed_token: str | None = Header(None, alias="X-E2E-Seed-Token"),
    current_user: User | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    _require_e2e_call_gates(x_e2e_seed_token, current_user, require_admin_jwt=True)
    with _mock_llm_lock:
        return {
            "profiles": {
                name: {
                    "cursor": int(cfg.get("cursor") or 0),
                    "repeat_last": bool(cfg.get("repeat_last", True)),
                    "steps": list(cfg.get("steps") or []),
                    "requests": list(cfg.get("requests") or []),
                }
                for name, cfg in _mock_llm_profiles.items()
            }
        }


@router.get("/dev/grading-state")
def grading_state_for_e2e(
    x_e2e_seed_token: str | None = Header(None, alias="X-E2E-Seed-Token"),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_e2e_call_gates(x_e2e_seed_token, current_user, require_admin_jwt=True)
    rows = (
        db.query(HomeworkGradingTask.status, func.count(HomeworkGradingTask.id))
        .group_by(HomeworkGradingTask.status)
        .all()
    )
    counts = {str(status or "unknown"): int(count or 0) for status, count in rows}
    return {
        "worker": {
            "enabled": bool(settings.ENABLE_LLM_GRADING_WORKER),
            "leader_only": bool(settings.LLM_GRADING_WORKER_LEADER),
            "running": worker_manager.is_running(),
            "poll_seconds": int(settings.LLM_GRADING_WORKER_POLL_SECONDS or 0),
        },
        "tasks": {
            "queued": counts.get("queued", 0),
            "processing": counts.get("processing", 0),
            "retry_scheduled": counts.get("retry_scheduled", 0),
            "success": counts.get("success", 0),
            "failed": counts.get("failed", 0),
            "total": sum(counts.values()),
        },
    }


@router.post("/dev/worker")
def control_worker_for_e2e(
    payload: dict[str, Any] = Body(default_factory=dict),
    x_e2e_seed_token: str | None = Header(None, alias="X-E2E-Seed-Token"),
    current_user: User | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    _require_e2e_call_gates(x_e2e_seed_token, current_user, require_admin_jwt=True)
    action = str(payload.get("action") or "status").strip().lower()
    if action == "start":
        if not settings.ENABLE_LLM_GRADING_WORKER:
            return {"ok": False, "action": action, "running": False, "detail": "worker disabled by settings"}
        start_grading_worker()
    elif action == "stop":
        worker_manager.stop()
    elif action != "status":
        raise HTTPException(status_code=400, detail="action must be one of: start, stop, status")
    return {"ok": True, "action": action, "running": worker_manager.is_running()}


@router.post("/dev/process-grading")
def process_grading_tasks_for_e2e(
    payload: dict[str, Any] = Body(default_factory=dict),
    x_e2e_seed_token: str | None = Header(None, alias="X-E2E-Seed-Token"),
    current_user: User | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    _require_e2e_call_gates(x_e2e_seed_token, current_user, require_admin_jwt=True)
    max_tasks = int(payload.get("max_tasks") or 1)
    max_tasks = max(0, min(max_tasks, 50))
    processed = 0
    for _ in range(max_tasks):
        if not process_next_grading_task():
            break
        processed += 1
    return {"processed": processed}


@router.post("/dev/mark-preset-validated")
def mark_preset_validated_for_e2e(
    payload: dict[str, Any] = Body(default_factory=dict),
    x_e2e_seed_token: str | None = Header(None, alias="X-E2E-Seed-Token"),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_e2e_call_gates(x_e2e_seed_token, current_user, require_admin_jwt=True)
    preset_id = payload.get("preset_id")
    try:
        preset_id = int(preset_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="preset_id must be an integer.") from exc
    preset = db.query(LLMEndpointPreset).filter(LLMEndpointPreset.id == preset_id).first()
    if not preset:
        raise HTTPException(status_code=404, detail="Endpoint preset not found.")
    preset.validation_status = "validated"
    preset.validation_message = str(payload.get("validation_message") or "e2e dev forced validated")
    preset.text_validation_status = "passed"
    preset.text_validation_message = "e2e dev forced validated"
    preset.vision_validation_status = "passed"
    preset.vision_validation_message = "e2e dev forced validated"
    preset.supports_vision = True
    preset.validated_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": preset.id, "validation_status": preset.validation_status, "supports_vision": preset.supports_vision}


@router.post("/dev/mock-llm/{profile}/v1/chat/completions")
async def mock_llm_chat_completions(
    profile: str,
    request: Request,
):
    if not settings.E2E_DEV_SEED_ENABLED:
        raise HTTPException(status_code=404, detail="E2E dev seed is disabled.")
    try:
        payload = await request.json()
    except Exception as exc:  # pragma: no cover - malformed request path
        raise HTTPException(status_code=400, detail=f"invalid json body: {exc}") from exc

    validation = _is_validation_request(payload if isinstance(payload, dict) else {})
    step = _next_mock_llm_step(profile)
    kind = str(step.get("kind") or "ok").strip().lower()
    sleep_seconds = float(step.get("sleep_seconds") or 0.0)
    _record_mock_llm_request(
        profile,
        {
            "kind": kind,
            "validation": validation,
            "model": payload.get("model"),
            "max_tokens": payload.get("max_tokens"),
            "sleep_seconds": sleep_seconds,
            "ts": time.time(),
        },
    )

    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    if kind in {"timeout", "sleep_then_ok"}:
        body = _mock_llm_success_body(profile, step, validation=validation)
        return JSONResponse(body)
    if kind == "http_error":
        status_code = int(step.get("status_code") or 500)
        body = step.get("body")
        if isinstance(body, (dict, list)):
            return JSONResponse(body, status_code=status_code)
        return PlainTextResponse(str(body or f"{profile}:{status_code}"), status_code=status_code)
    if kind in {"invalid_json", "malformed_json"}:
        text_body = step.get("body")
        if text_body is None:
            text_body = '{"choices":[{"message":{"content":"not-json-comment"}}],"usage":{"prompt_tokens":10}}'
        return PlainTextResponse(str(text_body), media_type="application/json")
    if kind in {"empty_body", "empty_response_body"}:
        return PlainTextResponse("", media_type="application/json")
    if kind == "bad_grading_payload":
        body = {
            "choices": [{"message": {"content": str(step.get("content") or "plain text, not score json")}}],
            "usage": step.get("usage") or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        return JSONResponse(body)
    if kind == "empty_message":
        body = {
            "choices": [{"message": {"content": ""}}],
            "usage": step.get("usage") or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        return JSONResponse(body)
    if kind == "rate_limit":
        body = step.get("body") or {"error": "rate limited"}
        return JSONResponse(body, status_code=int(step.get("status_code") or 429))

    body = _mock_llm_success_body(profile, step, validation=validation)
    return JSONResponse(body)
