import json
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.api.schemas import (
    CourseTimeItem,
    StudentCourseCatalogItem,
    SubjectClassLinkResponse,
    SubjectResponse,
)
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    Semester,
    Student,
    Subject,
    SubjectClassLink,
)
from apps.backend.courseeval_backend.semester_utils import normalize_semester_name


def sort_course_times(course_times: List[CourseTimeItem]) -> List[CourseTimeItem]:
    return sorted(
        course_times,
        key=lambda item: (item.course_start_at, item.course_end_at, item.weekly_schedule or ""),
    )


def resolve_course_times(course_times: Optional[List[CourseTimeItem]]) -> List[CourseTimeItem]:
    normalized = [CourseTimeItem.model_validate(item) for item in (course_times or [])]
    return sort_course_times(normalized)


def deserialize_course_times(course: Subject) -> List[CourseTimeItem]:
    if course.course_times:
        try:
            raw_items = json.loads(course.course_times)
            normalized_items = []

            for raw_item in raw_items or []:
                try:
                    normalized_items.append(CourseTimeItem.model_validate(raw_item))
                except Exception:
                    continue

            if normalized_items:
                return sort_course_times(normalized_items)
        except Exception:
            pass

    return []


def serialize_course_times_for_storage(course_times: List[CourseTimeItem]) -> Optional[str]:
    if not course_times:
        return None

    return json.dumps(
        [
            {
                "weekly_schedule": item.weekly_schedule,
                "course_start_at": item.course_start_at.isoformat(),
                "course_end_at": item.course_end_at.isoformat(),
            }
            for item in course_times
        ],
        ensure_ascii=False,
    )


def normalize_semester_label(semester: Optional[str], db: Session) -> Optional[str]:
    if not semester:
        return semester

    normalized = normalize_semester_name(semester)
    if not normalized:
        return normalized

    exact_semester = db.query(Semester).filter(Semester.name == normalized).first()
    if exact_semester:
        return exact_semester.name

    parts = normalized.split("-")
    if len(parts) == 2 and parts[0].isdigit() and parts[1] in {"1", "2"}:
        year, term = parts
        candidates = (
            db.query(Semester)
            .filter(Semester.year == int(year))
            .order_by(Semester.created_at.asc(), Semester.id.asc())
            .all()
        )
        term_index = int(term) - 1
        if 0 <= term_index < len(candidates):
            return candidates[term_index].name
    return normalized


def resolve_semester(
    db: Session,
    *,
    semester_id: Optional[int] = None,
    semester_name: Optional[str] = None,
) -> Optional[Semester]:
    if semester_id:
        semester = db.query(Semester).filter(Semester.id == semester_id).first()
        if not semester:
            raise HTTPException(status_code=400, detail="Semester not found.")
        return semester

    normalized_name = normalize_semester_label(semester_name, db)
    if not normalized_name:
        return None

    semester = db.query(Semester).filter(Semester.name == normalized_name).first()
    if semester:
        return semester

    raise HTTPException(status_code=400, detail="Semester not found.")


def serialize_course(course: Subject, db: Session, *, student_count: Optional[int] = None) -> SubjectResponse:
    if student_count is None:
        student_count = db.query(CourseEnrollment).filter(CourseEnrollment.subject_id == course.id).count()
    semester_label = (
        course.semester_obj.name
        if course.semester_obj
        else normalize_semester_label(course.semester, db)
    )
    course_times = deserialize_course_times(course)

    ct = (course.course_type or "required").strip().lower()
    link_rows = (
        db.query(SubjectClassLink, Class.name)
        .join(Class, Class.id == SubjectClassLink.class_id)
        .filter(SubjectClassLink.subject_id == course.id)
        .order_by(SubjectClassLink.id.asc())
        .all()
    )
    class_links = [
        SubjectClassLinkResponse(
            class_id=link.class_id,
            class_name=name,
            enrollment_mode=(link.enrollment_mode or "all_in_class"),
        )
        for link, name in link_rows
    ]

    if ct == "elective":
        display_class_name = "-"
        display_class_id = None
    else:
        names = [ln.class_name for ln in class_links if ln.class_name]
        display_class_name = "、".join(names) if names else (course.class_obj.name if course.class_obj else None)
        display_class_id = course.class_id

    return SubjectResponse(
        id=course.id,
        name=course.name,
        teacher_id=course.teacher_id,
        class_id=display_class_id,
        semester_id=course.semester_id,
        course_type=course.course_type or "required",
        status=course.status or "active",
        semester=semester_label,
        course_times=course_times,
        description=course.description,
        cover_image_url=course.cover_image_url,
        teacher_name=course.teacher.real_name if course.teacher else None,
        class_name=display_class_name,
        class_links=class_links,
        student_count=student_count,
        created_at=course.created_at,
    )


def serialize_student_course_catalog_item(
    course: Subject,
    db: Session,
    *,
    student: Student,
    enrolled_subject_ids: set[int],
) -> StudentCourseCatalogItem:
    base = serialize_course(course, db)
    ct = (course.course_type or "required").strip().lower()
    is_enrolled = course.id in enrolled_subject_ids
    if ct == "elective":
        if is_enrolled:
            hint = "已选修，可退选。"
        else:
            hint = "选修课不按行政班绑定；可直接选课。"
        can_self = bool(not is_enrolled)
    else:
        if is_enrolled:
            hint = "已在花名册中（通常由教师按班级统一添加）。"
        else:
            hint = "必修课由教师按班级花名册统一加入，不可在此自主选课；若应修而未显示请联系任课教师或管理员。"
        can_self = False
    return StudentCourseCatalogItem(
        **base.model_dump(),
        is_enrolled=is_enrolled,
        enrollment_hint=hint,
        can_self_enroll_elective=can_self,
    )
