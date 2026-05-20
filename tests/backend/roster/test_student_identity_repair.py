from __future__ import annotations

import pytest

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import Class, Gender, Student, User, UserRole
from apps.backend.courseeval_backend.domains.roster.repair import repair_student_identity


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()


def _password() -> str:
    return get_password_hash("repair-pass")


def test_student_identity_repair_dry_run_reports_default_repairs_without_mutating():
    db = SessionLocal()
    try:
        klass = Class(name="Repair Dry Run", grade=2026)
        db.add(klass)
        db.flush()
        legacy = Student(name="Legacy Student", student_no="stu1", gender=Gender.MALE, class_id=klass.id)
        roster_only = Student(name="Roster Only", student_no="stu3", gender=Gender.FEMALE, class_id=klass.id)
        db.add_all([legacy, roster_only])
        db.add_all(
            [
                User(
                    username="stu1",
                    hashed_password=_password(),
                    real_name="Legacy Student",
                    role=UserRole.STUDENT.value,
                    class_id=klass.id,
                ),
                User(
                    username="stu2",
                    hashed_password=_password(),
                    real_name="User Only",
                    role=UserRole.STUDENT.value,
                    class_id=klass.id,
                ),
            ]
        )
        db.commit()

        report = repair_student_identity(db, apply=False)
        db.rollback()

        assert report["applied"] is False
        assert report["blocked"] is False
        assert report["planned"] == {
            "bind_legacy_student_users": 1,
            "create_students_from_student_users": 1,
            "create_student_users_from_students": 1,
        }
        assert db.query(User).filter(User.username == "stu1").one().student_id is None
        assert db.query(Student).filter(Student.student_no == "stu2").first() is None
        assert db.query(User).filter(User.username == "stu3").first() is None
    finally:
        db.close()


def test_student_identity_repair_apply_migrates_default_student_accounts():
    db = SessionLocal()
    try:
        klass = Class(name="Repair Apply", grade=2026)
        db.add(klass)
        db.flush()
        legacy = Student(name="Legacy Student", student_no="stu1", gender=Gender.MALE, class_id=klass.id)
        roster_only = Student(name="Roster Only", student_no="stu3", gender=Gender.FEMALE, class_id=klass.id)
        db.add_all([legacy, roster_only])
        db.add_all(
            [
                User(
                    username="stu1",
                    hashed_password=_password(),
                    real_name="Legacy Student",
                    role=UserRole.STUDENT.value,
                    class_id=klass.id,
                ),
                User(
                    username="stu2",
                    hashed_password=_password(),
                    real_name="User Only",
                    role=UserRole.STUDENT.value,
                    class_id=None,
                ),
            ]
        )
        db.commit()

        report = repair_student_identity(db, apply=True)
        db.commit()

        assert report["applied"] is True
        assert report["blocked"] is False
        assert report["after"]["issues"]["legacy_binding_candidates"] == 0
        assert report["after"]["issues"]["student_users_without_students"] == 0
        assert report["after"]["issues"]["students_without_accounts"] == 0

        legacy_user = db.query(User).filter(User.username == "stu1").one()
        user_only = db.query(User).filter(User.username == "stu2").one()
        roster_user = db.query(User).filter(User.username == "stu3").one()
        user_only_student = db.query(Student).filter(Student.student_no == "stu2").one()
        assert legacy_user.student_id == legacy.id
        assert user_only.student_id == user_only_student.id
        assert user_only_student.class_id is not None
        assert roster_user.student_id == roster_only.id
        assert roster_user.class_id == klass.id
    finally:
        db.close()


def test_student_identity_repair_apply_blocks_ambiguous_default_accounts():
    db = SessionLocal()
    try:
        class_a = Class(name="Repair Conflict A", grade=2026)
        class_b = Class(name="Repair Conflict B", grade=2026)
        db.add_all([class_a, class_b])
        db.flush()
        db.add_all(
            [
                Student(name="Dup A", student_no="dup1", gender=Gender.MALE, class_id=class_a.id),
                Student(name="Dup B", student_no="dup1", gender=Gender.FEMALE, class_id=class_b.id),
                User(
                    username="dup1",
                    hashed_password=_password(),
                    real_name="Ambiguous Default",
                    role=UserRole.STUDENT.value,
                    class_id=None,
                ),
            ]
        )
        db.commit()

        report = repair_student_identity(db, apply=True)
        db.rollback()

        assert report["applied"] is False
        assert report["blocked"] is True
        assert "multiple_students_for_user" in report["blocking_issues"]
        assert db.query(User).filter(User.username == "dup1").one().student_id is None
    finally:
        db.close()
