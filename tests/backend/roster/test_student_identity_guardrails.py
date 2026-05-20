from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import Class, Gender, Student, Subject, SubjectClassLink, User, UserRole
from apps.backend.courseeval_backend.domains.courses.access import get_student_profile_for_user, prepare_student_course_context
from apps.backend.courseeval_backend.domains.roster.audit import audit_student_identity
from apps.backend.courseeval_backend.domains.roster.identity import find_user_for_student
from apps.backend.courseeval_backend.domains.roster.reconciliation import sync_student_roster_from_user_accounts
from apps.backend.courseeval_backend.domains.roster.sync import sync_student_user_from_roster_row
from apps.backend.courseeval_backend.main import app
from tests.scenarios.llm_scenario import ensure_admin, login_api


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    ensure_admin()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _admin_headers(client: TestClient) -> dict[str, str]:
    return login_api(client, "pytest_admin", "pytest_admin_pass")


def _class_and_suffix() -> tuple[int, str]:
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        klass = Class(name=f"Guardrail {suffix}", grade=2026)
        db.add(klass)
        db.commit()
        db.refresh(klass)
        return klass.id, suffix
    finally:
        db.close()


def test_find_user_for_student_ignores_same_username_user_bound_to_other_student():
    class_id, suffix = _class_and_suffix()
    db = SessionLocal()
    try:
        target = Student(name="Target", student_no=f"S{suffix}", gender=Gender.MALE, class_id=class_id)
        other = Student(name="Other", student_no=f"O{suffix}", gender=Gender.MALE, class_id=class_id)
        db.add_all([target, other])
        db.flush()
        user = User(
            username=target.student_no,
            hashed_password=get_password_hash("p"),
            real_name="Bound Elsewhere",
            role=UserRole.STUDENT.value,
            class_id=class_id,
            student_id=other.id,
        )
        db.add(user)
        db.commit()

        assert find_user_for_student(db, target) is None
    finally:
        db.close()


def test_get_student_profile_for_user_does_not_repair_mismatched_user_class():
    class_id, suffix = _class_and_suffix()
    db = SessionLocal()
    try:
        other_class = Class(name=f"Other Guardrail {suffix}", grade=2026)
        db.add(other_class)
        db.flush()
        student = Student(name="Bound", student_no=f"S{suffix}", gender=Gender.MALE, class_id=class_id)
        db.add(student)
        db.flush()
        user = User(
            username=f"bound_{suffix}",
            hashed_password=get_password_hash("p"),
            real_name="Bound",
            role=UserRole.STUDENT.value,
            class_id=other_class.id,
            student_id=student.id,
        )
        db.add(user)
        db.commit()

        resolved = get_student_profile_for_user(user, db)

        assert resolved is not None
        assert resolved.id == student.id
        db.refresh(user)
        assert user.class_id == other_class.id
    finally:
        db.close()


def test_sync_student_user_from_roster_row_does_not_rebind_same_username_user_bound_elsewhere():
    class_id, suffix = _class_and_suffix()
    db = SessionLocal()
    try:
        target = Student(name="Target", student_no=f"S{suffix}", gender=Gender.MALE, class_id=class_id)
        other = Student(name="Other", student_no=f"O{suffix}", gender=Gender.MALE, class_id=class_id)
        db.add_all([target, other])
        db.flush()
        user = User(
            username=target.student_no,
            hashed_password=get_password_hash("p"),
            real_name="Bound Elsewhere",
            role=UserRole.STUDENT.value,
            class_id=class_id,
            student_id=other.id,
        )
        db.add(user)
        db.commit()

        sync_student_user_from_roster_row(db, target)
        db.commit()
        db.refresh(user)

        assert user.student_id == other.id
        assert db.query(User).filter(User.student_id == target.id).count() == 0
    finally:
        db.close()


def test_sync_student_roster_from_user_accounts_reports_conflict_when_matching_student_is_already_bound():
    class_id, suffix = _class_and_suffix()
    db = SessionLocal()
    try:
        roster = Student(name="Roster", student_no=f"S{suffix}", gender=Gender.MALE, class_id=class_id)
        db.add(roster)
        db.flush()
        owner = User(
            username=f"owner_{suffix}",
            hashed_password=get_password_hash("p"),
            real_name="Owner",
            role=UserRole.STUDENT.value,
            class_id=class_id,
            student_id=roster.id,
        )
        legacy = User(
            username=roster.student_no,
            hashed_password=get_password_hash("p"),
            real_name="Legacy",
            role=UserRole.STUDENT.value,
            class_id=class_id,
        )
        db.add_all([owner, legacy])
        db.commit()

        result = sync_student_roster_from_user_accounts(db, [legacy.id])

        assert result.created == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert len(result.errors) == 1
        assert result.errors[0].reason == "existing same-class roster row is already bound to another student account"
        assert db.query(User).filter(User.id == legacy.id).one().student_id is None
    finally:
        db.close()


def test_prepare_student_course_context_does_not_bind_legacy_login_to_student_owned_by_other_account(client: TestClient):
    class_id, suffix = _class_and_suffix()
    db = SessionLocal()
    try:
        teacher = User(
            username=f"teacher_{suffix}",
            hashed_password=get_password_hash("p"),
            real_name="Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        subject = Subject(name=f"Course {suffix}", teacher_id=teacher.id, class_id=class_id, course_type="required", status="active")
        db.add(subject)
        db.flush()
        db.add(SubjectClassLink(subject_id=subject.id, class_id=class_id, enrollment_mode="all_in_class"))
        roster = Student(name="Roster", student_no=f"S{suffix}", gender=Gender.MALE, class_id=class_id)
        db.add(roster)
        db.flush()
        owner = User(
            username=f"owner_{suffix}",
            hashed_password=get_password_hash("p"),
            real_name="Owner",
            role=UserRole.STUDENT.value,
            class_id=class_id,
            student_id=roster.id,
        )
        legacy = User(
            username=roster.student_no,
            hashed_password=get_password_hash("p"),
            real_name="Legacy",
            role=UserRole.STUDENT.value,
            class_id=class_id,
        )
        db.add_all([owner, legacy])
        db.commit()
        legacy_username = legacy.username
    finally:
        db.close()

    headers = login_api(client, legacy_username, "p")
    response = client.get("/api/subjects", headers=headers)
    assert response.status_code == 200
    assert response.json() == []

    db = SessionLocal()
    try:
        legacy = db.query(User).filter(User.username == legacy_username).one()
        prepare_student_course_context(legacy, db)
        db.commit()
        db.refresh(legacy)
        assert legacy.student_id is None
    finally:
        db.close()


def test_audit_does_not_offer_legacy_binding_candidate_when_matching_username_is_already_bound_elsewhere():
    class_id, suffix = _class_and_suffix()
    db = SessionLocal()
    try:
        roster = Student(name="Roster", student_no=f"S{suffix}", gender=Gender.MALE, class_id=class_id)
        db.add(roster)
        db.flush()
        owner = User(
            username=f"owner_{suffix}",
            hashed_password=get_password_hash("p"),
            real_name="Owner",
            role=UserRole.STUDENT.value,
            class_id=class_id,
            student_id=roster.id,
        )
        legacy = User(
            username=roster.student_no,
            hashed_password=get_password_hash("p"),
            real_name="Legacy",
            role=UserRole.STUDENT.value,
            class_id=class_id,
        )
        db.add_all([owner, legacy])
        db.commit()

        report = audit_student_identity(db)

        assert report["issues"]["legacy_binding_candidates"] == []
        orphan_rows = [row for row in report["issues"]["student_users_without_students"] if row["user"]["id"] == legacy.id]
        assert len(orphan_rows) == 1
        assert orphan_rows[0]["candidate_count"] == 0
    finally:
        db.close()


def test_students_list_has_user_false_when_only_matching_username_account_is_bound_elsewhere_same_class(client: TestClient):
    class_id, suffix = _class_and_suffix()
    db = SessionLocal()
    try:
        target = Student(name="Target", student_no=f"S{suffix}", gender=Gender.MALE, class_id=class_id)
        other = Student(name="Other", student_no=f"O{suffix}", gender=Gender.MALE, class_id=class_id)
        db.add_all([target, other])
        db.flush()
        user = User(
            username=target.student_no,
            hashed_password=get_password_hash("p"),
            real_name="Bound Elsewhere",
            role=UserRole.STUDENT.value,
            class_id=class_id,
            student_id=other.id,
        )
        db.add(user)
        db.commit()
        target_id = target.id
        student_no = target.student_no
    finally:
        db.close()

    response = client.get("/api/students", headers=_admin_headers(client), params={"page": 1, "page_size": 1000, "search": student_no})
    assert response.status_code == 200
    row = next(item for item in response.json()["data"] if item["id"] == target_id)
    assert row["has_user"] is False


def test_audit_reports_raw_candidate_count_when_legacy_match_is_occupied():
    class_id, suffix = _class_and_suffix()
    db = SessionLocal()
    try:
        roster = Student(name="Roster", student_no=f"S{suffix}", gender=Gender.MALE, class_id=class_id)
        db.add(roster)
        db.flush()
        owner = User(
            username=f"owner_{suffix}",
            hashed_password=get_password_hash("p"),
            real_name="Owner",
            role=UserRole.STUDENT.value,
            class_id=class_id,
            student_id=roster.id,
        )
        legacy = User(
            username=roster.student_no,
            hashed_password=get_password_hash("p"),
            real_name="Legacy",
            role=UserRole.STUDENT.value,
            class_id=class_id,
        )
        db.add_all([owner, legacy])
        db.commit()

        report = audit_student_identity(db)

        issue = next(row for row in report["issues"]["student_users_without_students"] if row["user"]["id"] == legacy.id)
        assert issue["candidate_count"] == 0
        assert issue["raw_candidate_count"] == 1
    finally:
        db.close()


def test_find_user_for_student_reuses_unique_unbound_classless_user():
    class_id, suffix = _class_and_suffix()
    db = SessionLocal()
    try:
        student = Student(name="Target", student_no=f"S{suffix}", gender=Gender.MALE, class_id=class_id)
        db.add(student)
        db.flush()
        user = User(
            username=student.student_no,
            hashed_password=get_password_hash("p"),
            real_name="Classless",
            role=UserRole.STUDENT.value,
            class_id=None,
        )
        db.add(user)
        db.commit()

        found = find_user_for_student(db, student)

        assert found is not None
        assert found.id == user.id
    finally:
        db.close()


def test_sync_student_user_from_roster_row_reuses_unique_unbound_classless_user():
    class_id, suffix = _class_and_suffix()
    db = SessionLocal()
    try:
        student = Student(name="Target", student_no=f"S{suffix}", gender=Gender.MALE, class_id=class_id)
        db.add(student)
        db.flush()
        user = User(
            username=student.student_no,
            hashed_password=get_password_hash("p"),
            real_name="Classless",
            role=UserRole.STUDENT.value,
            class_id=None,
        )
        db.add(user)
        db.commit()

        sync_student_user_from_roster_row(db, student)
        db.commit()
        db.refresh(user)

        assert user.student_id == student.id
        assert user.class_id == class_id
        assert db.query(User).filter(User.username == student.student_no).count() == 1
    finally:
        db.close()


def test_sync_student_roster_from_user_accounts_binds_matching_classless_roster():
    _, suffix = _class_and_suffix()
    db = SessionLocal()
    try:
        student = Student(name="Target", student_no=f"S{suffix}", gender=Gender.MALE, class_id=None)
        db.add(student)
        db.flush()
        user = User(
            username=student.student_no,
            hashed_password=get_password_hash("p"),
            real_name="Classless",
            role=UserRole.STUDENT.value,
            class_id=None,
        )
        db.add(user)
        db.commit()

        result = sync_student_roster_from_user_accounts(db, [user.id])
        db.commit()
        db.refresh(user)
        db.refresh(student)

        assert result.created == 0
        assert result.updated == 1
        assert result.skipped == 0
        assert result.errors == []
        assert user.student_id == student.id
        assert student.name == "Classless"
    finally:
        db.close()


def test_admin_api_create_student_with_student_no_owned_by_other_class_user_keeps_row_unbound(client: TestClient):
    headers = _admin_headers(client)
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        class_a = Class(name=f"ApiGuardA {suffix}", grade=2026)
        class_b = Class(name=f"ApiGuardB {suffix}", grade=2026)
        db.add_all([class_a, class_b])
        db.flush()
        class_a_id = class_a.id
        class_b_id = class_b.id
        db.commit()
    finally:
        db.close()

    shared_no = f"api_guard_{suffix}"
    create_user = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": shared_no,
            "password": "p",
            "real_name": "Bound Elsewhere",
            "role": "student",
            "class_id": class_b_id,
        },
    )
    assert create_user.status_code == 200, create_user.text

    create_student = client.post(
        "/api/students",
        headers=headers,
        json={
            "name": "Roster Only",
            "student_no": shared_no,
            "gender": "male",
            "class_id": class_a_id,
        },
    )
    assert create_student.status_code == 400, create_student.text
