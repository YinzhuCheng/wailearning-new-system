"""Bidirectional sync between User (student accounts) and Student (roster rows).

Ensures deployment seeds and admin CRUD stay aligned: every learner is a
canonical Student row, and student login accounts bind through users.student_id.
Username/student_no matching is limited to explicit repair/reconciliation.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.domains.courses.access import prepare_student_course_context, sync_student_course_enrollments
from apps.backend.courseeval_backend.db.models import Student, User, UserRole
from apps.backend.courseeval_backend.domains.roster.identity import (
    clean_student_text,
    ensure_student_row_defaults,
    ensure_student_user_defaults,
    find_user_for_student,
)
from apps.backend.courseeval_backend.domains.roster.reconciliation import sync_student_roster_from_user_accounts


def _clean(s: object | None) -> str:
    return clean_student_text(s)


def sync_student_user_from_roster_row(db: Session, student: Student) -> None:
    """Ensure a User row exists and is bound to this Student row. Does not commit."""
    ensure_student_row_defaults(student, db)
    student_no = _clean(student.student_no)

    display_name = _clean(student.name) or student_no
    user = find_user_for_student(db, student)

    if not user:
        if db.query(User.id).filter(User.username == student_no).first():
            # A same-username account exists but cannot be safely assigned to this
            # Student. Leave it for audit/repair instead of masking drift or
            # colliding with the global unique username constraint.
            return
        user = User(
            username=student_no,
            hashed_password=get_password_hash(student_no),
            real_name=display_name,
            role=UserRole.STUDENT.value,
            class_id=student.class_id,
            student_id=student.id,
            is_active=True,
        )
        db.add(user)
        db.flush()
        sync_student_course_enrollments(student, db)
        prepare_student_course_context(user, db)
        return

    if (user.role or "").strip() != UserRole.STUDENT.value:
        user.role = UserRole.STUDENT.value
    if _clean(user.username) != student_no:
        occupied = db.query(User.id).filter(User.username == student_no, User.id != user.id).first()
        if not occupied:
            user.username = student_no
    if user.student_id != student.id:
        user.student_id = student.id
    user.class_id = student.class_id
    if _clean(user.real_name) != display_name:
        user.real_name = display_name
    if not user.is_active:
        user.is_active = True
    ensure_student_user_defaults(user, db)
    db.flush()
    sync_student_course_enrollments(student, db)
    prepare_student_course_context(user, db)


def sync_student_users_from_roster(db: Session) -> None:
    """For each roster row, align the bound User account."""
    for st in db.query(Student).all():
        sync_student_user_from_roster_row(db, st)


def sync_roster_from_all_student_users(db: Session):
    """Ensure Student rows exist for every student User."""
    ids = [
        uid
        for (uid,) in db.query(User.id)
        .filter(User.role == UserRole.STUDENT.value, User.is_active.is_(True))
        .all()
    ]
    if not ids:
        return None
    return sync_student_roster_from_user_accounts(db, ids)


def reconcile_student_users_and_roster(db: Session) -> dict[str, int]:
    """
    Full reconciliation for deployment/migrations.

    1. Users (student) -> roster rows when missing.
    2. Roster rows -> user accounts aligned (names, class, role).

    Does not commit.
    """
    db.flush()
    res = sync_roster_from_all_student_users(db)
    sync_student_users_from_roster(db)
    return {
        "users_to_roster_created": res.created if res else 0,
        "users_to_roster_updated": res.updated if res else 0,
        "users_to_roster_skipped": res.skipped if res else 0,
        "users_to_roster_errors": len(res.errors) if res else 0,
    }
