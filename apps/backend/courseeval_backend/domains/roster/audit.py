from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.db.models import Student, User, UserRole
from apps.backend.courseeval_backend.domains.roster.identity import clean_student_text


def _student_payload(student: Student) -> dict[str, Any]:
    return {
        "id": student.id,
        "name": student.name,
        "student_no": student.student_no,
        "class_id": student.class_id,
    }


def _user_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "role": user.role,
        "class_id": user.class_id,
        "student_id": user.student_id,
        "is_active": bool(getattr(user, "is_active", True)),
    }


def _same_class_or_unscoped(user: User, student: Student) -> bool:
    return user.class_id is None or student.class_id == user.class_id


def _legacy_student_matches(user: User, students_by_no: dict[str, list[Student]]) -> list[Student]:
    username = clean_student_text(user.username)
    if not username:
        return []
    return [
        student
        for student in students_by_no.get(username, [])
        if _same_class_or_unscoped(user, student)
    ]


def _legacy_user_matches(student: Student, student_users: list[User]) -> list[User]:
    student_no = clean_student_text(student.student_no)
    if not student_no:
        return []
    return [
        user
        for user in student_users
        if clean_student_text(user.username) == student_no and _same_class_or_unscoped(user, student)
    ]


def audit_student_identity(db: Session) -> dict[str, Any]:
    """Return a read-only audit of canonical Student rows and student User bindings."""
    students = db.query(Student).order_by(Student.id.asc()).all()
    users = db.query(User).order_by(User.id.asc()).all()
    student_users = [
        user
        for user in users
        if (user.role or "").strip() == UserRole.STUDENT.value and bool(getattr(user, "is_active", True))
    ]
    student_ids = {student.id for student in students}

    users_by_student_id: dict[int, list[User]] = defaultdict(list)
    for user in users:
        if user.student_id is not None:
            users_by_student_id[int(user.student_id)].append(user)

    students_by_no: dict[str, list[Student]] = defaultdict(list)
    for student in students:
        student_no = clean_student_text(student.student_no)
        if student_no:
            students_by_no[student_no].append(student)

    student_users_by_username: dict[str, list[User]] = defaultdict(list)
    for user in student_users:
        username = clean_student_text(user.username)
        if username:
            student_users_by_username[username].append(user)

    issues: dict[str, list[dict[str, Any]]] = {
        "students_without_accounts": [],
        "student_users_without_students": [],
        "legacy_binding_candidates": [],
        "duplicate_student_numbers": [],
        "multiple_users_for_student": [],
        "multiple_students_for_user": [],
        "invalid_user_student_bindings": [],
        "username_student_no_mismatches_bound": [],
        "unassigned_students": [],
    }

    for student_no, matching_students in sorted(students_by_no.items()):
        if len(matching_students) < 2:
            continue
        same_scope_groups: dict[tuple[int | None, str], list[Student]] = defaultdict(list)
        for student in matching_students:
            same_scope_groups[(student.class_id, student_no)].append(student)
        issues["duplicate_student_numbers"].append(
            {
                "student_no": student_no,
                "count": len(matching_students),
                "same_class_or_unassigned_duplicate": any(
                    len(group) > 1 for group in same_scope_groups.values()
                ),
                "students": [_student_payload(student) for student in matching_students],
            }
        )

    for user in users:
        if user.student_id is None:
            continue
        if user.student_id not in student_ids:
            issues["invalid_user_student_bindings"].append(
                {
                    "reason": "missing_student",
                    "user": _user_payload(user),
                    "student_id": user.student_id,
                }
            )
            continue
        if (user.role or "").strip() != UserRole.STUDENT.value:
            issues["invalid_user_student_bindings"].append(
                {
                    "reason": "non_student_user_has_student_id",
                    "user": _user_payload(user),
                    "student": _student_payload(db.query(Student).filter(Student.id == user.student_id).one()),
                }
            )

    for student in students:
        if student.class_id is None:
            issues["unassigned_students"].append({"student": _student_payload(student)})

        explicit_users = [
            user
            for user in users_by_student_id.get(int(student.id), [])
            if (user.role or "").strip() == UserRole.STUDENT.value
        ]
        legacy_users = [
            user
            for user in _legacy_user_matches(student, student_users)
            if user.student_id is None or user.student_id == student.id
        ]
        candidate_users = {user.id: user for user in [*explicit_users, *legacy_users]}

        if not explicit_users and not legacy_users:
            issues["students_without_accounts"].append({"student": _student_payload(student)})
        if len(candidate_users) > 1:
            issues["multiple_users_for_student"].append(
                {
                    "student": _student_payload(student),
                    "users": [_user_payload(user) for user in candidate_users.values()],
                }
            )

        for user in explicit_users:
            if clean_student_text(user.username) != clean_student_text(student.student_no):
                issues["username_student_no_mismatches_bound"].append(
                    {
                        "user": _user_payload(user),
                        "student": _student_payload(student),
                    }
                )

    for user in student_users:
        bound_student = (
            db.query(Student).filter(Student.id == user.student_id).first()
            if user.student_id is not None
            else None
        )
        if user.student_id is not None and bound_student:
            continue

        matches = _legacy_student_matches(user, students_by_no)
        unbound_matches = [
            student
            for student in matches
            if not any(
                bound_user.id != user.id
                for bound_user in users_by_student_id.get(int(student.id), [])
                if (bound_user.role or "").strip() == UserRole.STUDENT.value
            )
        ]
        if len(matches) > 1:
            issues["multiple_students_for_user"].append(
                {
                    "user": _user_payload(user),
                    "students": [_student_payload(student) for student in matches],
                }
            )
            continue
        if len(unbound_matches) == 1:
            issues["legacy_binding_candidates"].append(
                {
                    "user": _user_payload(user),
                    "student": _student_payload(unbound_matches[0]),
                    "match": "username_equals_student_no",
                }
            )
            continue
        issues["student_users_without_students"].append(
            {
                "user": _user_payload(user),
                "candidate_count": len(unbound_matches),
                "raw_candidate_count": len(matches),
            }
        )

    return {
        "summary": {
            "students": len(students),
            "users": len(users),
            "student_users": len(student_users),
            "issues": {key: len(value) for key, value in issues.items()},
        },
        "issues": issues,
    }
