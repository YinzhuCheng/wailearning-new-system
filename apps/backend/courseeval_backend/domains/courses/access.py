from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseEnrollmentBlock,
    Student,
    Subject,
    SubjectClassLink,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.roster.identity import resolve_bound_student_for_user


def subject_linked_class_ids(db: Session, subject_id: int) -> list[int]:
    rows = db.query(SubjectClassLink.class_id).filter(SubjectClassLink.subject_id == subject_id).order_by(SubjectClassLink.id.asc()).all()
    return [int(r[0]) for r in rows]


def refresh_subject_primary_class_id(course: Subject, db: Session) -> None:
    """Keep ``Subject.class_id`` aligned with the first linked class."""
    ct = (course.course_type or "required").strip().lower()
    if ct == "elective":
        course.class_id = None
        return
    linked = subject_linked_class_ids(db, course.id)
    course.class_id = linked[0] if linked else course.class_id


def subject_teacher_user_ids(db: Session, subject_id: int) -> list[int]:
    """Notify course teacher plus class teachers for every linked administrative class."""
    course = db.query(Subject).filter(Subject.id == subject_id).first()
    if not course:
        return []
    ids: list[int] = []
    if course.teacher_id:
        ids.append(int(course.teacher_id))
    class_ids = subject_linked_class_ids(db, subject_id)
    for cid in class_ids:
        class_teachers = (
            db.query(User.id).filter(User.role == UserRole.CLASS_TEACHER.value, User.class_id == cid).all()
        )
        ids.extend(int(r[0]) for r in class_teachers)
    return sorted(set(ids))


def _pending_course_enrollment_subject_ids(db: Session, student_id: int) -> set[int]:
    subject_ids: set[int] = set()
    for obj in tuple(db.identity_map.values()) + tuple(db.new):
        if isinstance(obj, CourseEnrollment) and getattr(obj, "student_id", None) == student_id and obj.subject_id:
            subject_ids.add(int(obj.subject_id))
    return subject_ids


def prepare_student_course_context(user: User, db: Session) -> None:
    """
    For student accounts: resolve the canonical Student row through
    users.student_id, repair missing default-data bindings only when necessary,
    then ensure CourseEnrollment rows.
    """
    if user.role != UserRole.STUDENT or not user.username:
        return

    student = get_student_profile_for_user(user, db)
    if not student:
        # Default-data recovery: a student-role user may exist before its canonical
        # Student row or explicit users.student_id binding has been created.
        from apps.backend.courseeval_backend.domains.roster.reconciliation import sync_student_roster_from_user_accounts

        sync_student_roster_from_user_accounts(db, [user.id])
        db.flush()
        student = get_student_profile_for_user(user, db)
    if student:
        sync_student_course_enrollments(student, db, respect_enrollment_blocks=True)
    db.flush()


def get_student_profile_for_user(user: User, db: Session) -> Optional[Student]:
    """Canonical Student for this login, resolved through users.student_id."""
    return resolve_bound_student_for_user(user, db)


def get_accessible_courses_query(user: User, db: Session):
    query = db.query(Subject)

    if user.role == UserRole.ADMIN:
        return query

    if user.role == UserRole.STUDENT:
        prepare_student_course_context(user, db)
        db.commit()

        student = get_student_profile_for_user(user, db)
        if not student:
            return query.filter(False)
        enrolled_subject_ids = [
            row[0]
            for row in db.query(CourseEnrollment.subject_id)
            .filter(CourseEnrollment.student_id == student.id)
            .all()
        ]
        visible_ids = sorted(set(enrolled_subject_ids))
        if not visible_ids:
            return query.filter(False)
        return query.filter(Subject.id.in_(visible_ids))

    if user.role == UserRole.TEACHER:
        return query.filter(Subject.teacher_id == user.id)

    if user.role == UserRole.CLASS_TEACHER:
        if not user.class_id:
            return query.filter(Subject.teacher_id == user.id)

        link_ids = [
            row[0]
            for row in db.query(SubjectClassLink.subject_id)
            .filter(SubjectClassLink.class_id == user.class_id)
            .distinct()
            .all()
        ]
        if not link_ids:
            return query.filter(Subject.teacher_id == user.id)
        class_course_query = query.filter(Subject.id.in_(link_ids))
        return class_course_query.union(query.filter(Subject.teacher_id == user.id))

    return query.filter(False)


def get_student_elective_catalog_query(user: User, db: Session):
    """
    Active elective courses system-wide for voluntary student enrollment.
    Restricted to students with a resolved roster profile and account class_id.
    """
    query = db.query(Subject)
    if user.role != UserRole.STUDENT:
        return query.filter(False)
    prepare_student_course_context(user, db)
    db.commit()
    student = get_student_profile_for_user(user, db)
    if not student or not user.class_id:
        return query.filter(False)
    return query.filter(
        Subject.status == "active",
        Subject.course_type == "elective",
    )


def get_student_course_catalog_query(user: User, db: Session):
    """
    All active courses for browse + enrollment hints.
    Electives: voluntary school-wide self enrollment (no administrative class binding on the course).
    """
    query = db.query(Subject)
    if user.role != UserRole.STUDENT:
        return query.filter(False)
    prepare_student_course_context(user, db)
    db.commit()
    student = get_student_profile_for_user(user, db)
    if not student or not user.class_id:
        return query.filter(False)
    return query.filter(Subject.status == "active")


def get_accessible_course_ids(user: User, db: Session) -> list[int]:
    return [course.id for course in get_accessible_courses_query(user, db).all() if course.id]


def get_accessible_class_ids_from_courses(user: User, db: Session) -> list[int]:
    if user.role == UserRole.ADMIN:
        return [class_obj.id for class_obj in db.query(Class).all()]

    class_ids = set()
    if user.role == UserRole.CLASS_TEACHER and user.class_id:
        class_ids.add(user.class_id)
    if user.role == UserRole.STUDENT and user.class_id:
        class_ids.add(user.class_id)

    for course in get_accessible_courses_query(user, db).all():
        class_ids.update(subject_linked_class_ids(db, course.id))

    return sorted(class_ids)


def get_course_or_404(course_id: int, db: Session) -> Subject:
    course = db.query(Subject).filter(Subject.id == course_id).first()
    if not course:
        raise ValueError("Course not found.")
    return course


def ensure_course_access(course_id: int, user: User, db: Session) -> Subject:
    course = get_course_or_404(course_id, db)
    accessible_course_ids = get_accessible_course_ids(user, db)
    if course.id not in accessible_course_ids:
        raise PermissionError("You do not have access to this course.")
    return course


def ensure_course_access_http(course_id: int, user: User, db: Session) -> Subject:
    """Same as ensure_course_access but maps errors to HTTP responses for FastAPI routes."""
    try:
        return ensure_course_access(course_id, user, db)
    except PermissionError:
        raise HTTPException(status_code=403, detail="You do not have access to this course.") from None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


def is_course_instructor(user: User, course: Subject) -> bool:
    """Whether the user may manage course structure (e.g. material chapters). Admin always; else assigned teacher."""
    if user.role == UserRole.ADMIN:
        return True
    if user.role not in (UserRole.TEACHER, UserRole.CLASS_TEACHER):
        return False
    return course.teacher_id is not None and int(course.teacher_id) == int(user.id)


def sync_course_enrollments(course: Subject, db: Session) -> int:
    if (course.course_type or "required").strip().lower() == "elective":
        return 0

    links = db.query(SubjectClassLink).filter(SubjectClassLink.subject_id == course.id).all()

    existing_student_ids = {
        enrollment.student_id
        for enrollment in db.query(CourseEnrollment).filter(CourseEnrollment.subject_id == course.id).all()
    }

    created = 0
    for link in links:
        if (link.enrollment_mode or "all_in_class").strip().lower() != "all_in_class":
            continue
        class_students = db.query(Student).filter(Student.class_id == link.class_id).all()
        for student in class_students:
            if student.id in existing_student_ids:
                continue
            try:
                with db.begin_nested():
                    db.query(CourseEnrollmentBlock).filter(
                        CourseEnrollmentBlock.subject_id == course.id,
                        CourseEnrollmentBlock.student_id == student.id,
                    ).delete(synchronize_session=False)
                    db.add(
                        CourseEnrollment(
                            subject_id=course.id,
                            student_id=student.id,
                            class_id=link.class_id,
                            enrollment_type=course.course_type or "required",
                            can_remove=(course.course_type or "required") == "elective",
                        )
                    )
                    db.flush()
            except IntegrityError:
                enrollment_row = (
                    db.query(CourseEnrollment)
                    .filter(
                        CourseEnrollment.subject_id == course.id,
                        CourseEnrollment.student_id == student.id,
                    )
                    .first()
                )
                if enrollment_row:
                    existing_student_ids.add(student.id)
                continue
            existing_student_ids.add(student.id)
            created += 1

    return created


def sync_student_course_enrollments(
    student: Student, db: Session, *, respect_enrollment_blocks: bool = True
) -> int:
    if not student.class_id:
        return 0

    auto_subject_ids = {
        row[0]
        for row in db.query(SubjectClassLink.subject_id).filter(
            SubjectClassLink.class_id == student.class_id,
            SubjectClassLink.enrollment_mode == "all_in_class",
        )
    }
    courses = db.query(Subject).filter(Subject.id.in_(auto_subject_ids)).all() if auto_subject_ids else []
    existing_course_ids = {
        enrollment.subject_id
        for enrollment in db.query(CourseEnrollment).filter(CourseEnrollment.student_id == student.id).all()
    }
    existing_course_ids.update(_pending_course_enrollment_subject_ids(db, student.id))

    blocked_subject_ids: set[int] = set()
    if respect_enrollment_blocks:
        blocked_subject_ids = {
            row[0]
            for row in db.query(CourseEnrollmentBlock.subject_id).filter(
                CourseEnrollmentBlock.student_id == student.id
            )
        }

    created = 0
    for course in courses:
        if (course.course_type or "required").strip().lower() == "elective":
            continue
        if course.id in existing_course_ids:
            continue
        if course.id in blocked_subject_ids:
            continue
        try:
            with db.begin_nested():
                db.add(
                    CourseEnrollment(
                        subject_id=course.id,
                        student_id=student.id,
                        class_id=student.class_id,
                        enrollment_type=course.course_type or "required",
                        can_remove=(course.course_type or "required") == "elective",
                    )
                )
                db.flush()
        except IntegrityError:
            existing_course_ids.add(course.id)
            continue
        existing_course_ids.add(course.id)
        created += 1

    return created


def remove_course_enrollment(course_id: int, student_id: int, db: Session) -> bool:
    enrollment = (
        db.query(CourseEnrollment)
        .filter(
            CourseEnrollment.subject_id == course_id,
            CourseEnrollment.student_id == student_id,
        )
        .first()
    )
    if not enrollment:
        return False

    db.delete(enrollment)
    if not db.query(CourseEnrollmentBlock).filter(
        CourseEnrollmentBlock.subject_id == course_id,
        CourseEnrollmentBlock.student_id == student_id,
    ).first():
        db.add(CourseEnrollmentBlock(subject_id=course_id, student_id=student_id))
    return True


def get_enrolled_students(course_id: int, db: Session) -> list[CourseEnrollment]:
    return (
        db.query(CourseEnrollment)
        .filter(CourseEnrollment.subject_id == course_id)
        .options(joinedload(CourseEnrollment.student))
        .order_by(CourseEnrollment.id.asc())
        .all()
    )
