"""Student course visibility follows explicit CourseEnrollment rows after prepare."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    Gender,
    Student,
    Subject,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.courses.access import prepare_student_course_context
from apps.backend.courseeval_backend.main import app


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    yield


def _seed_student_two_courses(db: Session) -> tuple[User, Subject, Subject]:
    suffix = uuid.uuid4().hex[:8]
    klass_a = Class(name=f"class_a_{suffix}", grade=1)
    klass_b = Class(name=f"class_b_{suffix}", grade=1)
    db.add_all([klass_a, klass_b])
    db.flush()

    course_in_a = Subject(
        name=f"math_a_{suffix}",
        class_id=klass_a.id,
        course_type="required",
        status="active",
    )
    course_in_b = Subject(
        name=f"math_b_{suffix}",
        class_id=klass_b.id,
        course_type="required",
        status="active",
    )
    db.add_all([course_in_a, course_in_b])
    db.flush()

    username = f"u1_{suffix}"
    student = Student(name="Student One", student_no=username, gender=Gender.MALE, class_id=klass_a.id)
    db.add(student)
    db.flush()

    db.add(
        CourseEnrollment(
            subject_id=course_in_a.id,
            student_id=student.id,
            class_id=klass_a.id,
            enrollment_type="required",
            can_remove=False,
        )
    )

    user = User(
        username=username,
        hashed_password="x",
        real_name="Student One",
        role=UserRole.STUDENT.value,
        class_id=klass_a.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.refresh(course_in_a)
    db.refresh(course_in_b)
    return user, course_in_a, course_in_b


def test_student_course_list_only_enrolled_subjects():
    db = SessionLocal()
    try:
        user, course_a, course_b = _seed_student_two_courses(db)
    finally:
        db.close()

    client = TestClient(app)
    from apps.backend.courseeval_backend.core.auth import create_access_token

    token = create_access_token(data={"sub": user.username})
    response = client.get("/api/subjects", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert course_a.id in ids
    assert course_b.id not in ids


def test_prepare_does_not_move_conflicting_roster_across_classes_without_binding():
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        klass_a = Class(name=f"class_conflict_a_{suffix}", grade=1)
        klass_b = Class(name=f"class_conflict_b_{suffix}", grade=1)
        db.add_all([klass_a, klass_b])
        db.flush()

        course_a = Subject(name=f"course_conflict_a_{suffix}", class_id=klass_a.id, course_type="required", status="active")
        db.add(course_a)
        db.flush()

        student_no = f"stu_conflict_{suffix}"
        student = Student(name="Student Two", student_no=student_no, gender=Gender.MALE, class_id=klass_b.id)
        db.add(student)
        db.flush()

        user = User(
            username=student_no,
            hashed_password="x",
            real_name="Student Two",
            role=UserRole.STUDENT.value,
            class_id=klass_a.id,
        )
        db.add(user)
        db.commit()

        prepare_student_course_context(user, db)
        db.commit()

        db.refresh(student)
        db.refresh(user)
        assert student.class_id == klass_b.id
        assert user.student_id is None
        enrollment = (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.student_id == student.id, CourseEnrollment.subject_id == course_a.id)
            .first()
        )
        assert enrollment is None
    finally:
        db.close()
