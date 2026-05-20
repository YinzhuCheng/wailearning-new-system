from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.db.models import Class, Student, User, UserRole


TEMPORARY_STUDENT_CLASS_NAME = "待分班"
TEMPORARY_STUDENT_CLASS_GRADE = 0


def clean_student_text(value: object | None) -> str:
    return (str(value).strip() if value is not None else "").strip()


def get_or_create_temporary_student_class(db: Session) -> Class:
    klass = (
        db.query(Class)
        .filter(
            Class.name == TEMPORARY_STUDENT_CLASS_NAME,
            Class.grade == TEMPORARY_STUDENT_CLASS_GRADE,
        )
        .order_by(Class.id.asc())
        .first()
    )
    if klass:
        return klass

    klass = Class(name=TEMPORARY_STUDENT_CLASS_NAME, grade=TEMPORARY_STUDENT_CLASS_GRADE)
    db.add(klass)
    db.flush()
    return klass


def ensure_student_class_id(db: Session, class_id: int | None) -> int:
    if class_id is not None:
        return int(class_id)
    return int(get_or_create_temporary_student_class(db).id)


def generate_student_no(db: Session) -> str:
    """Generate a unique temporary student number for roster imports without one."""
    prefix = f"SYS{datetime.now(timezone.utc):%Y%m%d}"
    existing = {
        row[0]
        for row in db.query(Student.student_no)
        .filter(Student.student_no.like(f"{prefix}%"))
        .all()
        if row[0]
    }
    for obj in tuple(db.new):
        if isinstance(obj, Student) and obj.student_no:
            existing.add(str(obj.student_no))

    next_index = len(existing) + 1
    while True:
        candidate = f"{prefix}{next_index:04d}"
        if candidate not in existing:
            return candidate
        next_index += 1


def resolve_bound_student_for_user(user: User, db: Session) -> Optional[Student]:
    """
    Resolve the canonical Student row for a student-role User without mutating.
    """
    if (user.role or "").strip() != UserRole.STUDENT.value:
        return None

    student_id = getattr(user, "student_id", None)
    if not student_id:
        return None

    return db.query(Student).filter(Student.id == student_id).first()


def get_bound_student_for_user(user: User, db: Session) -> Optional[Student]:
    """
    Resolve the canonical Student row for a student-role User and repair stale
    binding fields.
    """
    student = resolve_bound_student_for_user(user, db)
    if student:
        if student.class_id and user.class_id != student.class_id:
            user.class_id = student.class_id
            db.flush()
        return student

    if (user.role or "").strip() == UserRole.STUDENT.value and getattr(user, "student_id", None):
        user.student_id = None
        db.flush()
    return None


def ensure_student_row_defaults(student: Student, db: Session) -> None:
    if not clean_student_text(student.student_no):
        student.student_no = generate_student_no(db)
    student.class_id = ensure_student_class_id(db, student.class_id)
    db.flush()


def ensure_student_user_defaults(user: User, db: Session) -> None:
    if (user.role or "").strip() != UserRole.STUDENT.value:
        return
    user.class_id = ensure_student_class_id(db, user.class_id)
    db.flush()


def find_user_for_student(db: Session, student: Student) -> Optional[User]:
    if student.id:
        user = (
            db.query(User)
            .filter(User.role == UserRole.STUDENT.value, User.student_id == student.id)
            .first()
        )
        if user:
            return user

    student_no = clean_student_text(student.student_no)
    if not student_no:
        return None

    query = db.query(User).filter(
        User.role == UserRole.STUDENT.value,
        User.username == student_no,
        or_(User.student_id.is_(None), User.student_id == student.id),
    )
    if student.class_id:
        same_class_user = query.filter(User.class_id == student.class_id).first()
        if same_class_user:
            return same_class_user
        if student_no and db.query(Student.id).filter(Student.student_no == student_no).count() == 1:
            classless_candidates = query.filter(User.class_id.is_(None)).all()
            if len(classless_candidates) == 1:
                return classless_candidates[0]
        return None
    candidates = query.all()
    return candidates[0] if len(candidates) == 1 else None
