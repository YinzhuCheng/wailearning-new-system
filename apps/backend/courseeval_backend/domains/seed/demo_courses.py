"""Course builders shared by the default demo seed bundle."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.domains.courses.access import sync_course_enrollments
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseExamWeight,
    CourseGradeScheme,
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    LLMEndpointPreset,
    Semester,
    Subject,
    SubjectClassLink,
    User,
)
from apps.backend.courseeval_backend.llm_grading import UNLIMITED_OUTPUT_TOKEN_SENTINEL

_DEMO_COURSE_COVER_DATA_URL = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 960 540'>"
    "<rect width='960' height='540' fill='%230f766e'/>"
    "<path d='M0 420 C160 360 260 470 430 405 C590 345 650 250 960 315 L960 540 L0 540 Z' fill='%2314b8a6'/>"
    "<circle cx='750' cy='130' r='82' fill='%23facc15' opacity='0.9'/>"
    "<rect x='115' y='115' width='390' height='310' rx='28' fill='%23ffffff' opacity='0.92'/>"
    "<rect x='155' y='165' width='250' height='28' rx='14' fill='%230f766e'/>"
    "<rect x='155' y='225' width='300' height='20' rx='10' fill='%2314b8a6'/>"
    "<rect x='155' y='270' width='245' height='20' rx='10' fill='%232dd4bf'/>"
    "<rect x='155' y='315' width='280' height='20' rx='10' fill='%2399f6e4'/>"
    "</svg>"
)


def _first_validated_preset_for_demo_course(db: Session) -> LLMEndpointPreset | None:
    """
    Global preset suitable for demo course LLM binding.

    Prefer rows that pass the same gates as the teacher UI (validated + active
    + vision-capable + text/vision steps not failed). If none match, fall back
    to the bootstrap default preset row so demo bundles still get an endpoint
    link for local installs.
    """

    for preset in (
        db.query(LLMEndpointPreset)
        .filter(
            LLMEndpointPreset.is_active.is_(True),
            LLMEndpointPreset.validation_status == "validated",
            LLMEndpointPreset.supports_vision.is_(True),
        )
        .order_by(LLMEndpointPreset.id.asc())
        .all()
    ):
        text_status = getattr(preset, "text_validation_status", None)
        if text_status == "failed":
            continue
        if text_status not in (None, "passed", "skipped"):
            continue
        vision_status = getattr(preset, "vision_validation_status", None)
        if vision_status == "failed":
            continue
        return preset
    return (
        db.query(LLMEndpointPreset)
        .filter(LLMEndpointPreset.name == "gpt-5.4", LLMEndpointPreset.supports_vision.is_(True))
        .order_by(LLMEndpointPreset.id.asc())
        .first()
    )


def ensure_demo_subject_llm_binding(
    db: Session,
    *,
    subject_id: int,
    teacher_id: int,
    enable_auto_grading: bool,
) -> None:
    """Idempotent: attach first suitable validated preset when the course has no LLM endpoints."""

    cfg = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == subject_id).first()
    if not cfg:
        cfg = CourseLLMConfig(
            subject_id=subject_id,
            created_by=teacher_id,
            updated_by=teacher_id,
            is_enabled=bool(enable_auto_grading),
            max_output_tokens=UNLIMITED_OUTPUT_TOKEN_SENTINEL,
        )
        db.add(cfg)
        db.flush()
    if db.query(CourseLLMConfigEndpoint).filter(CourseLLMConfigEndpoint.config_id == cfg.id).first():
        if enable_auto_grading:
            cfg.is_enabled = True
        return
    preset = _first_validated_preset_for_demo_course(db)
    if not preset:
        return
    db.add(CourseLLMConfigEndpoint(config_id=cfg.id, preset_id=preset.id, priority=1))
    if enable_auto_grading:
        cfg.is_enabled = True
    db.flush()


def _ensure_demo_course_cover(course: Subject) -> None:
    """Attach a simple built-in cover only when the course has no cover yet."""

    if not course.cover_image_url:
        course.cover_image_url = _DEMO_COURSE_COVER_DATA_URL


def _demo_semester_start() -> datetime:
    return datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)


def _demo_semester_end(weeks: int) -> datetime:
    return _demo_semester_start() + timedelta(weeks=weeks, days=-1, hours=23, minutes=59, seconds=59)


def _demo_course_times_json(weekly_schedule: str, weeks: int) -> str:
    start_at = _demo_semester_start()
    end_at = _demo_semester_end(weeks)
    return json.dumps(
        [
            {
                "weekly_schedule": weekly_schedule,
                "course_start_at": start_at.isoformat(),
                "course_end_at": end_at.isoformat(),
            }
        ],
        ensure_ascii=False,
    )


def ensure_demo_course_time(
    course: Subject,
    *,
    weekly_schedule: str,
    weeks: int,
) -> None:
    course.course_times = _demo_course_times_json(weekly_schedule, weeks)


def seed_demo_grade_weights(db: Session, *, course: Subject) -> None:
    """Align demo course with default grade composition (30/20/50) when rows are missing."""

    if not db.query(CourseGradeScheme).filter(CourseGradeScheme.subject_id == course.id).first():
        db.add(
            CourseGradeScheme(
                subject_id=course.id,
                homework_weight=30.0,
                extra_daily_weight=20.0,
            )
        )
    if not db.query(CourseExamWeight).filter(CourseExamWeight.subject_id == course.id).first():
        db.add(CourseExamWeight(subject_id=course.id, exam_type="\u671f\u672b\u8003\u8bd5", weight=50.0))


def ensure_required_demo_course(
    db: Session,
    *,
    teacher: User,
    klass: Class,
    semester: Semester | None,
    name: str,
    description: str,
    weekly_schedule: str,
    weeks: int = 16,
) -> Subject:
    """Ensure the roster-synced required demo course and its course-level setup."""

    course = (
        db.query(Subject)
        .filter(
            Subject.name == name,
            Subject.teacher_id == teacher.id,
            Subject.class_id == klass.id,
        )
        .first()
    )
    if not course:
        course = Subject(
            name=name,
            teacher_id=teacher.id,
            class_id=klass.id,
            semester_id=semester.id if semester else None,
            semester=semester.name if semester else None,
            course_type="required",
            status="active",
            description=description,
        )
        db.add(course)
        db.flush()
        print(f"Created demo course '{name}'.")
    else:
        if semester and course.semester_id != semester.id:
            course.semester_id = semester.id
            course.semester = semester.name
        course.description = description
        print(f"Demo course '{name}' already exists.")

    ensure_demo_course_time(
        course,
        weekly_schedule=weekly_schedule,
        weeks=weeks,
    )
    _ensure_demo_course_cover(course)

    link_row = (
        db.query(SubjectClassLink)
        .filter(SubjectClassLink.subject_id == course.id, SubjectClassLink.class_id == klass.id)
        .first()
    )
    if not link_row:
        db.add(SubjectClassLink(subject_id=course.id, class_id=klass.id, enrollment_mode="all_in_class"))
        db.flush()

    ensure_demo_subject_llm_binding(
        db,
        subject_id=course.id,
        teacher_id=teacher.id,
        enable_auto_grading=True,
    )

    seed_demo_grade_weights(db, course=course)

    enrolled = sync_course_enrollments(course, db)
    if enrolled:
        print(f"Synced demo course enrollments: +{enrolled}.")

    return course
