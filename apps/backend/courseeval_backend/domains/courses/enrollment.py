from __future__ import annotations

from collections.abc import Sequence

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.api.schemas import (
    CourseEnrollmentResponse,
    CourseRosterStudentInput,
    SubjectRosterEnrollResult,
)
from apps.backend.courseeval_backend.db.models import (
    CourseEnrollment,
    CourseEnrollmentBlock,
    Student,
    Subject,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.courses.access import subject_linked_class_ids


def roster_class_ids_for_course(db: Session, course: Subject) -> set[int]:
    ids = set(subject_linked_class_ids(db, course.id))
    if not ids and course.class_id:
        ids.add(int(course.class_id))
    return ids


def serialize_enrollment(enrollment: CourseEnrollment, db: Session) -> CourseEnrollmentResponse:
    enrollment_type = enrollment.enrollment_type or ("elective" if enrollment.can_remove else "required")
    subj = enrollment.course or db.query(Subject).filter(Subject.id == enrollment.subject_id).first()
    subj_ct = (subj.course_type if subj else "required").strip().lower()
    class_name = enrollment.class_obj.name if enrollment.class_obj else None
    if subj_ct == "elective" or enrollment_type == "elective":
        class_name = "-"
    student_user_id = (
        db.query(User.id)
        .filter(User.role == UserRole.STUDENT.value, User.student_id == enrollment.student_id)
        .scalar()
    )
    return CourseEnrollmentResponse(
        id=enrollment.id,
        subject_id=enrollment.subject_id,
        student_id=enrollment.student_id,
        class_id=enrollment.class_id,
        enrollment_type=enrollment_type,
        can_remove=enrollment_type == "elective",
        created_at=enrollment.created_at,
        student_name=enrollment.student.name if enrollment.student else None,
        student_no=enrollment.student.student_no if enrollment.student else None,
        class_name=class_name,
        student_user_id=student_user_id,
    )


def create_roster_students(
    course: Subject,
    students: Sequence[CourseRosterStudentInput],
    db: Session,
    current_user: User,
) -> list[tuple[Student, str]]:
    seen_student_nos = set()
    enrollment_overrides: list[tuple[Student, str]] = []
    for item in students:
        student_name = item.name.strip()
        student_no = item.student_no.strip()
        if not student_name:
            raise HTTPException(status_code=400, detail="Student name is required.")
        if not student_no:
            raise HTTPException(status_code=400, detail="Student number is required.")
        if student_no in seen_student_nos:
            raise HTTPException(status_code=400, detail=f"Duplicate student number in upload: {student_no}")
        seen_student_nos.add(student_no)

        existing_student = (
            db.query(Student)
            .filter(Student.class_id == course.class_id, Student.student_no == student_no)
            .first()
        )
        if existing_student:
            raise HTTPException(status_code=400, detail=f"Student number already exists in this course roster: {student_no}")

        student = Student(
            name=student_name,
            student_no=student_no,
            gender=item.gender,
            phone=item.phone,
            parent_phone=item.parent_phone,
            address=item.address,
            class_id=course.class_id,
            teacher_id=current_user.id if current_user.role == UserRole.TEACHER.value else course.teacher_id,
        )
        db.add(student)
        enrollment_overrides.append((student, item.enrollment_type or "required"))

    return enrollment_overrides


def enroll_roster_students_for_course(
    course: Subject,
    student_ids: Sequence[int],
    db: Session,
) -> SubjectRosterEnrollResult:
    ct_course = (course.course_type or "required").strip().lower()
    allowed_classes = roster_class_ids_for_course(db, course)
    if ct_course != "elective" and not allowed_classes:
        raise HTTPException(
            status_code=400,
            detail="\u8be5\u5fc5\u4fee\u8bfe\u672a\u7ed1\u5b9a\u4efb\u4f55\u884c\u653f\u73ed\uff0c\u65e0\u6cd5\u4ece\u82b1\u540d\u518c\u8fdb\u8bfe\u3002",
        )

    unique_student_ids = list(dict.fromkeys(student_ids))
    if not unique_student_ids:
        return SubjectRosterEnrollResult()

    enrolled_ids = {
        row[0]
        for row in db.query(CourseEnrollment.student_id).filter(CourseEnrollment.subject_id == course.id).all()
    }

    created = 0
    skipped_already = 0
    skipped_wrong_class = 0
    skipped_missing = 0
    enrollment_type = course.course_type or "required"
    can_remove = enrollment_type == "elective"

    for student_id in unique_student_ids:
        if student_id in enrolled_ids:
            skipped_already += 1
            continue

        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            skipped_missing += 1
            continue

        if ct_course == "elective":
            if not student.class_id:
                skipped_wrong_class += 1
                continue
        elif not student.class_id or int(student.class_id) not in allowed_classes:
            skipped_wrong_class += 1
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
                        class_id=student.class_id,
                        enrollment_type=enrollment_type,
                        can_remove=can_remove,
                    )
                )
                db.flush()
            enrolled_ids.add(student.id)
            created += 1
        except IntegrityError:
            existing = (
                db.query(CourseEnrollment)
                .filter(
                    CourseEnrollment.subject_id == course.id,
                    CourseEnrollment.student_id == student.id,
                )
                .first()
            )
            if existing:
                skipped_already += 1
                continue
            raise

    db.commit()
    return SubjectRosterEnrollResult(
        created=created,
        skipped_already_enrolled=skipped_already,
        skipped_not_in_class_roster=skipped_wrong_class,
        skipped_not_found=skipped_missing,
    )
