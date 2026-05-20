from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.db.models import (
    Class,
    Subject,
    SubjectClassLink,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.courses.access import (
    refresh_subject_primary_class_id,
    subject_linked_class_ids,
)


def can_create_course(current_user: User) -> bool:
    return current_user.role in [UserRole.ADMIN, UserRole.CLASS_TEACHER, UserRole.TEACHER]


def normalize_course_class_name(*, course_name: str, class_name: Optional[str]) -> str:
    if class_name and class_name.strip():
        return class_name.strip()
    return f"{course_name.strip()}课程班"


def replace_subject_class_links(db: Session, course: Subject, link_items: list[tuple[int, str]]) -> None:
    if not link_items:
        raise HTTPException(status_code=400, detail="必修课至少需要绑定一个行政班级。")
    db.query(SubjectClassLink).filter(SubjectClassLink.subject_id == course.id).delete(synchronize_session=False)
    seen: set[int] = set()
    for cid, mode in link_items:
        cid_int = int(cid)
        if cid_int in seen:
            continue
        seen.add(cid_int)
        m = (mode or "all_in_class").strip().lower()
        if m not in ("all_in_class", "roster_subset"):
            m = "all_in_class"
        class_row = db.query(Class).filter(Class.id == cid_int).first()
        if not class_row:
            raise HTTPException(status_code=400, detail="班级不存在。")
        db.add(SubjectClassLink(subject_id=course.id, class_id=cid_int, enrollment_mode=m))
    db.flush()
    refresh_subject_primary_class_id(course, db)


def required_course_duplicate(
    db: Session,
    *,
    name: str,
    semester_id: Optional[int],
    sorted_class_ids: tuple[int, ...],
    exclude_subject_id: Optional[int] = None,
) -> Optional[Subject]:
    q = db.query(Subject).filter(Subject.name == name, Subject.semester_id == semester_id)
    if exclude_subject_id is not None:
        q = q.filter(Subject.id != exclude_subject_id)
    for candidate in q.all():
        if (candidate.course_type or "required").strip().lower() == "elective":
            continue
        existing_ids = tuple(sorted(subject_linked_class_ids(db, candidate.id)))
        if not existing_ids and candidate.class_id:
            existing_ids = tuple(sorted([int(candidate.class_id)]))
        if existing_ids == sorted_class_ids:
            return candidate
    return None
