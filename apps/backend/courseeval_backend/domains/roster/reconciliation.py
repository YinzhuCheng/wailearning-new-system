"""Sync canonical Student rows from active student User accounts."""

from __future__ import annotations

from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.api.schemas import (
    StudentRosterUpsertFromUsersError,
    StudentRosterUpsertFromUsersResponse,
)
from apps.backend.courseeval_backend.db.models import Class, Gender, Student, User, UserRole
from apps.backend.courseeval_backend.domains.courses.access import prepare_student_course_context
from apps.backend.courseeval_backend.domains.roster.identity import (
    ensure_student_user_defaults,
    get_bound_student_for_user,
)


def _student_no_conflict(
    db: Session,
    *,
    student_no: str,
    class_id: int,
    exclude_student_id: int | None = None,
) -> Student | None:
    query = db.query(Student).filter(Student.student_no == student_no, Student.class_id == class_id)
    if exclude_student_id is not None:
        query = query.filter(Student.id != exclude_student_id)
    return query.first()


def sync_student_roster_from_user_accounts(db: Session, user_ids: Iterable[int]) -> StudentRosterUpsertFromUsersResponse:
    """
    Ensure canonical Student rows exist for active student users and stay aligned.

    The student login contract is:
    - active student users always bind through ``users.student_id``
    - ``users.username`` mirrors ``students.student_no``
    - ``users.class_id`` mirrors ``students.class_id``
    """

    ids = list(dict.fromkeys(int(x) for x in user_ids if x is not None))
    if not ids:
        return StudentRosterUpsertFromUsersResponse(total=0, created=0, updated=0, skipped=0, errors=[])

    users = db.query(User).filter(User.id.in_(ids)).all()
    user_map = {u.id: u for u in users}

    created = 0
    updated = 0
    skipped = 0
    errors: list[StudentRosterUpsertFromUsersError] = []

    for uid in ids:
        user = user_map.get(uid)
        if not user:
            errors.append(StudentRosterUpsertFromUsersError(user_id=uid, reason="用户不存在"))
            continue
        if (user.role or "").strip() != UserRole.STUDENT.value:
            errors.append(
                StudentRosterUpsertFromUsersError(
                    user_id=user.id,
                    username=user.username,
                    reason="仅支持学生角色账号",
                )
            )
            continue
        if not bool(getattr(user, "is_active", True)):
            skipped += 1
            continue

        ensure_student_user_defaults(user, db)
        student_no = (user.username or "").strip()
        if not student_no:
            errors.append(
                StudentRosterUpsertFromUsersError(
                    user_id=user.id,
                    username=user.username,
                    reason="用户名为空，无法作为学号写入花名册",
                )
            )
            continue

        display_name = (user.real_name or "").strip() or student_no
        target_class_id = int(user.class_id)
        bound_student = get_bound_student_for_user(user, db)
        if bound_student:
            changed = False
            if bound_student.class_id != target_class_id:
                bound_student.class_id = target_class_id
                changed = True
            if (bound_student.name or "").strip() != display_name:
                bound_student.name = display_name
                changed = True
            if (bound_student.student_no or "").strip() != student_no:
                conflict = _student_no_conflict(
                    db,
                    student_no=student_no,
                    class_id=target_class_id,
                    exclude_student_id=bound_student.id,
                )
                if conflict:
                    errors.append(
                        StudentRosterUpsertFromUsersError(
                            user_id=user.id,
                            username=user.username,
                            reason="目标学号已被同班其他花名册学生占用，无法自动同步到当前绑定档案",
                        )
                    )
                    prepare_student_course_context(user, db)
                    continue
                bound_student.student_no = student_no
                changed = True
            updated += 1 if changed else 0
            skipped += 0 if changed else 1
            prepare_student_course_context(user, db)
            continue

        existing_same_class = _student_no_conflict(db, student_no=student_no, class_id=target_class_id)
        classless_matches = db.query(Student).filter(Student.student_no == student_no, Student.class_id.is_(None)).all()
        adoptable_classless = classless_matches[0] if len(classless_matches) == 1 else None
        matched_student = existing_same_class or adoptable_classless
        if matched_student:
            existing_binding = (
                db.query(User)
                .filter(
                    User.role == UserRole.STUDENT.value,
                    User.student_id == matched_student.id,
                    User.id != user.id,
                )
                .first()
            )
            if existing_binding:
                errors.append(
                    StudentRosterUpsertFromUsersError(
                        user_id=user.id,
                        username=user.username,
                        reason="existing same-class roster row is already bound to another student account",
                    )
                )
                continue
            user.student_id = matched_student.id
            changed = False
            if (matched_student.name or "").strip() != display_name:
                matched_student.name = display_name
                changed = True
            if matched_student.class_id != target_class_id:
                matched_student.class_id = target_class_id
                changed = True
            updated += 1 if changed else 0
            skipped += 0 if changed else 1
            prepare_student_course_context(user, db)
            continue

        if not db.query(Class.id).filter(Class.id == target_class_id).first():
            errors.append(
                StudentRosterUpsertFromUsersError(
                    user_id=user.id,
                    username=user.username,
                    reason="所属班级不存在",
                )
            )
            continue

        conflict = db.query(Student).filter(Student.student_no == student_no, Student.class_id != target_class_id).first()
        if conflict:
            errors.append(
                StudentRosterUpsertFromUsersError(
                    user_id=user.id,
                    username=user.username,
                    reason="该学号已在其他班级的花名册中，请先处理重复或调整班级后再同步",
                )
            )
            continue

        roster = Student(
            name=display_name,
            student_no=student_no,
            gender=Gender.MALE,
            class_id=target_class_id,
        )
        db.add(roster)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            db.expunge(roster)
            raced = _student_no_conflict(db, student_no=student_no, class_id=target_class_id)
            if raced:
                user.student_id = raced.id
                changed = False
                if (raced.name or "").strip() != display_name:
                    raced.name = display_name
                    changed = True
                if raced.class_id != target_class_id:
                    raced.class_id = target_class_id
                    changed = True
                updated += 1 if changed else 0
                skipped += 0 if changed else 1
                prepare_student_course_context(user, db)
                continue
            errors.append(
                StudentRosterUpsertFromUsersError(
                    user_id=user.id,
                    username=user.username,
                    reason="花名册写入冲突，请重试或检查学号是否重复",
                )
            )
            continue

        created += 1
        user.student_id = roster.id
        prepare_student_course_context(user, db)

    return StudentRosterUpsertFromUsersResponse(
        total=len(ids),
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )
