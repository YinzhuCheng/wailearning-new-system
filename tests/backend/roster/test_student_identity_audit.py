from __future__ import annotations

import pytest
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import Class, Gender, Student, User, UserRole
from apps.backend.courseeval_backend.domains.roster.audit import audit_student_identity


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()


def _password() -> str:
    return get_password_hash("audit-pass")


def test_student_identity_audit_reports_clean_bound_student_without_issues():
    db = SessionLocal()
    try:
        klass = Class(name="Audit Clean", grade=2026)
        db.add(klass)
        db.flush()
        student = Student(name="Clean Student", student_no="A100", gender=Gender.MALE, class_id=klass.id)
        db.add(student)
        db.flush()
        db.add(
            User(
                username="A100",
                hashed_password=_password(),
                real_name="Clean Student",
                role=UserRole.STUDENT.value,
                class_id=klass.id,
                student_id=student.id,
            )
        )
        db.commit()

        report = audit_student_identity(db)

        assert report["summary"]["students"] == 1
        assert report["summary"]["student_users"] == 1
        assert all(count == 0 for count in report["summary"]["issues"].values())
    finally:
        db.close()


def test_student_identity_audit_reports_missing_accounts_and_orphan_student_users():
    db = SessionLocal()
    try:
        klass = Class(name="Audit Missing", grade=2026)
        db.add(klass)
        db.flush()
        student = Student(name="No Account", student_no="M100", gender=Gender.FEMALE, class_id=klass.id)
        db.add(student)
        db.add(
            User(
                username="orphan-user",
                hashed_password=_password(),
                real_name="Orphan User",
                role=UserRole.STUDENT.value,
                class_id=klass.id,
            )
        )
        db.commit()

        report = audit_student_identity(db)

        assert [row["student"]["id"] for row in report["issues"]["students_without_accounts"]] == [student.id]
        assert [row["user"]["username"] for row in report["issues"]["student_users_without_students"]] == [
            "orphan-user"
        ]
    finally:
        db.close()


def test_student_identity_audit_reports_safe_legacy_binding_candidate():
    db = SessionLocal()
    try:
        klass = Class(name="Audit Legacy", grade=2026)
        db.add(klass)
        db.flush()
        student = Student(name="Legacy Student", student_no="L100", gender=Gender.MALE, class_id=klass.id)
        db.add(student)
        db.add(
            User(
                username="L100",
                hashed_password=_password(),
                real_name="Legacy Student",
                role=UserRole.STUDENT.value,
                class_id=klass.id,
            )
        )
        db.commit()

        report = audit_student_identity(db)

        candidates = report["issues"]["legacy_binding_candidates"]
        assert len(candidates) == 1
        assert candidates[0]["student"]["id"] == student.id
        assert candidates[0]["user"]["username"] == "L100"
        assert report["issues"]["students_without_accounts"] == []
    finally:
        db.close()


def test_student_identity_audit_reports_duplicate_and_ambiguous_user_match():
    db = SessionLocal()
    try:
        class_a = Class(name="Audit Dup A", grade=2026)
        class_b = Class(name="Audit Dup B", grade=2026)
        db.add_all([class_a, class_b])
        db.flush()
        student_a = Student(name="Dup A", student_no="DUP100", gender=Gender.MALE, class_id=class_a.id)
        student_b = Student(name="Dup B", student_no="DUP100", gender=Gender.FEMALE, class_id=class_b.id)
        db.add_all([student_a, student_b])
        db.add(
            User(
                username="DUP100",
                hashed_password=_password(),
                real_name="Ambiguous",
                role=UserRole.STUDENT.value,
            )
        )
        db.commit()

        report = audit_student_identity(db)

        duplicate = report["issues"]["duplicate_student_numbers"][0]
        assert duplicate["student_no"] == "DUP100"
        assert duplicate["count"] == 2
        ambiguous = report["issues"]["multiple_students_for_user"][0]
        assert ambiguous["user"]["username"] == "DUP100"
        assert {row["id"] for row in ambiguous["students"]} == {student_a.id, student_b.id}
        assert report["issues"]["legacy_binding_candidates"] == []
    finally:
        db.close()


def test_student_identity_audit_reports_multiple_user_candidates_for_one_student():
    db = SessionLocal()
    try:
        klass = Class(name="Audit Multi User", grade=2026)
        db.add(klass)
        db.flush()
        student = Student(name="Multi User", student_no="MU100", gender=Gender.MALE, class_id=klass.id)
        db.add(student)
        db.flush()
        db.add_all(
            [
                User(
                    username="login-mu100",
                    hashed_password=_password(),
                    real_name="Explicit User",
                    role=UserRole.STUDENT.value,
                    class_id=klass.id,
                    student_id=student.id,
                ),
                User(
                    username="MU100",
                    hashed_password=_password(),
                    real_name="Legacy Candidate",
                    role=UserRole.STUDENT.value,
                    class_id=klass.id,
                ),
            ]
        )
        db.commit()

        report = audit_student_identity(db)

        conflicts = report["issues"]["multiple_users_for_student"]
        assert len(conflicts) == 1
        assert conflicts[0]["student"]["id"] == student.id
        assert {row["username"] for row in conflicts[0]["users"]} == {"login-mu100", "MU100"}
        assert report["issues"]["legacy_binding_candidates"] == []
    finally:
        db.close()


def test_student_identity_audit_reports_invalid_bindings_mismatches_and_unassigned_students():
    db = SessionLocal()
    try:
        klass = Class(name="Audit Invalid", grade=2026)
        db.add(klass)
        db.flush()
        bound_student = Student(name="Bound", student_no="REAL100", gender=Gender.MALE, class_id=klass.id)
        teacher_bound_student = Student(
            name="Teacher Bound Profile",
            student_no="REAL200",
            gender=Gender.FEMALE,
            class_id=klass.id,
        )
        unassigned = Student(name="Unassigned", student_no="UN100", gender=Gender.FEMALE, class_id=None)
        db.add_all([bound_student, teacher_bound_student, unassigned])
        db.flush()
        db.add_all(
            [
                User(
                    username="login100",
                    hashed_password=_password(),
                    real_name="Bound",
                    role=UserRole.STUDENT.value,
                    class_id=klass.id,
                    student_id=bound_student.id,
                ),
                User(
                    username="teacher-bound",
                    hashed_password=_password(),
                    real_name="Teacher Bound",
                    role=UserRole.TEACHER.value,
                    student_id=teacher_bound_student.id,
                ),
            ]
        )
        db.commit()
        db.execute(text("PRAGMA foreign_keys=OFF"))
        db.execute(
            text(
                """
                INSERT INTO users
                    (username, hashed_password, real_name, role, class_id, student_id, token_version, is_active)
                VALUES
                    (:username, :hashed_password, :real_name, :role, NULL, :student_id, 0, 1)
                """
            ),
            {
                "username": "missing-bound",
                "hashed_password": _password(),
                "real_name": "Missing Bound",
                "role": UserRole.STUDENT.value,
                "student_id": 999999,
            },
        )
        db.execute(text("PRAGMA foreign_keys=ON"))
        db.commit()

        report = audit_student_identity(db)

        reasons = {row["reason"] for row in report["issues"]["invalid_user_student_bindings"]}
        assert reasons == {"missing_student", "non_student_user_has_student_id"}
        mismatches = report["issues"]["username_student_no_mismatches_bound"]
        assert [row["user"]["username"] for row in mismatches] == ["login100"]
        assert [row["student"]["id"] for row in report["issues"]["unassigned_students"]] == [unassigned.id]
    finally:
        db.close()
