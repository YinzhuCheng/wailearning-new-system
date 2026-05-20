"""Focused security hardening follow-up tests.

These cases complement ``test_security_regression.py`` by exercising lifecycle,
dual-gate, subject-scoped, and attachment ACL edges that are easy to miss in a
small point-in-time security smoke.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.api.schemas import UserRole
from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.core.config import Settings, settings
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import (
    Attendance,
    Class,
    CourseEnrollment,
    CourseExamWeight,
    CourseGradeScheme,
    CourseMaterialChapter,
    CourseMaterialHomeworkLink,
    CourseMaterialSection,
    CourseDiscussionEntry,
    CourseLLMConfig,
    CourseMaterial,
    Homework,
    HomeworkGradeAppeal,
    HomeworkSubmission,
    Notification,
    NotificationRead,
    Score,
    ScoreGradeAppeal,
    Student,
    SubjectClassLink,
    Subject,
    User,
)
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework


def _bearer_value(headers: dict[str, str]) -> str:
    return headers["Authorization"].split(" ", 1)[1]


def _create_class_teacher(label: str = "class_teacher") -> dict[str, object]:
    db = SessionLocal()
    try:
        klass = Class(name=f"security-{label}-class", grade=2026)
        db.add(klass)
        db.flush()
        user = User(
            username=f"security_{label}",
            hashed_password=get_password_hash(f"{label}_pass123"),
            real_name=f"Security {label}",
            role=UserRole.CLASS_TEACHER.value,
            class_id=klass.id,
            is_active=True,
        )
        db.add(user)
        db.commit()
        return {"user_id": user.id, "class_id": klass.id, "username": user.username, "password": f"{label}_pass123"}
    finally:
        db.close()


def _create_class_teacher_for_class(class_id: int, label: str = "class_teacher") -> dict[str, object]:
    db = SessionLocal()
    try:
        user = User(
            username=f"security_{label}",
            hashed_password=get_password_hash(f"{label}_pass123"),
            real_name=f"Security {label}",
            role=UserRole.CLASS_TEACHER.value,
            class_id=class_id,
            is_active=True,
        )
        db.add(user)
        db.commit()
        return {"user_id": user.id, "class_id": class_id, "username": user.username, "password": f"{label}_pass123"}
    finally:
        db.close()


def _create_class(name: str) -> int:
    db = SessionLocal()
    try:
        klass = Class(name=name, grade=2026)
        db.add(klass)
        db.commit()
        return int(klass.id)
    finally:
        db.close()


def _create_chapter(subject_id: int, title: str) -> int:
    db = SessionLocal()
    try:
        chapter = CourseMaterialChapter(subject_id=subject_id, title=title, sort_order=50)
        db.add(chapter)
        db.commit()
        return int(chapter.id)
    finally:
        db.close()


def _chapter_order(subject_id: int) -> list[int]:
    db = SessionLocal()
    try:
        return [
            int(row.id)
            for row in db.query(CourseMaterialChapter)
            .filter(CourseMaterialChapter.subject_id == subject_id)
            .order_by(CourseMaterialChapter.sort_order.asc(), CourseMaterialChapter.id.asc())
            .all()
        ]
    finally:
        db.close()


def _create_material_section(subject_id: int, class_id: int, teacher_id: int, chapter_id: int) -> tuple[int, int]:
    db = SessionLocal()
    try:
        material = CourseMaterial(
            title="Security chapter placement material",
            content="placement guard",
            class_id=class_id,
            subject_id=subject_id,
            created_by=teacher_id,
        )
        db.add(material)
        db.flush()
        section = CourseMaterialSection(material_id=material.id, chapter_id=chapter_id, sort_order=1)
        db.add(section)
        db.commit()
        return int(material.id), int(section.id)
    finally:
        db.close()


def _material_section_count(material_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(CourseMaterialSection).filter(CourseMaterialSection.material_id == material_id).count()
    finally:
        db.close()


def _create_course_homework(
    subject_id: int | None,
    class_id: int,
    teacher_id: int,
    title: str = "Security linked homework",
) -> int:
    db = SessionLocal()
    try:
        homework = Homework(
            title=title,
            content="linked homework guard",
            class_id=class_id,
            subject_id=subject_id,
            max_score=100,
            auto_grading_enabled=False,
            created_by=teacher_id,
        )
        db.add(homework)
        db.commit()
        return int(homework.id)
    finally:
        db.close()


def _create_notification(
    subject_id: int | None,
    class_id: int | None,
    teacher_id: int,
    title: str,
    target_student_id: int | None = None,
    target_user_id: int | None = None,
) -> int:
    db = SessionLocal()
    try:
        row = Notification(
            title=title,
            content="security notification guard",
            content_format="plain",
            priority="normal",
            class_id=class_id,
            subject_id=subject_id,
            target_student_id=target_student_id,
            target_user_id=target_user_id,
            created_by=teacher_id,
        )
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


def _notification_scope(notification_id: int) -> tuple[int | None, int | None, int | None]:
    db = SessionLocal()
    try:
        row = db.query(Notification).filter(Notification.id == notification_id).first()
        assert row is not None
        return (
            int(row.subject_id) if row.subject_id is not None else None,
            int(row.class_id) if row.class_id is not None else None,
            int(row.target_user_id) if row.target_user_id is not None else None,
        )
    finally:
        db.close()


def _notification_target_student_id(notification_id: int) -> int | None:
    db = SessionLocal()
    try:
        row = db.query(Notification).filter(Notification.id == notification_id).first()
        assert row is not None
        return int(row.target_student_id) if row.target_student_id is not None else None
    finally:
        db.close()


def _notification_kind(notification_id: int) -> str | None:
    db = SessionLocal()
    try:
        row = db.query(Notification).filter(Notification.id == notification_id).first()
        assert row is not None
        return row.notification_kind
    finally:
        db.close()


def _homework_link_count(chapter_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(CourseMaterialHomeworkLink).filter(CourseMaterialHomeworkLink.chapter_id == chapter_id).count()
    finally:
        db.close()


def _create_discussion_entry(subject_id: int, class_id: int, target_id: int, author_user_id: int) -> int:
    db = SessionLocal()
    try:
        row = CourseDiscussionEntry(
            target_type="homework",
            target_id=target_id,
            subject_id=subject_id,
            class_id=class_id,
            author_user_id=author_user_id,
            body="teacher-owned discussion management guard",
            body_format="plain",
        )
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


def _discussion_exists(entry_id: int) -> bool:
    db = SessionLocal()
    try:
        return db.query(CourseDiscussionEntry).filter(CourseDiscussionEntry.id == entry_id).first() is not None
    finally:
        db.close()


def _linked_class_ids(subject_id: int) -> set[int]:
    db = SessionLocal()
    try:
        return {
            int(row[0])
            for row in db.query(SubjectClassLink.class_id)
            .filter(SubjectClassLink.subject_id == subject_id)
            .all()
        }
    finally:
        db.close()


def _extra_student_for_class(class_id: int, label: str) -> int:
    db = SessionLocal()
    try:
        user = User(
            username=f"security_student_{label}",
            hashed_password=get_password_hash(f"{label}_pass123"),
            real_name=f"Security Student {label}",
            role=UserRole.STUDENT.value,
            class_id=class_id,
            is_active=True,
        )
        db.add(user)
        db.flush()
        student = Student(name=f"Security Student {label}", student_no=user.username, class_id=class_id)
        db.add(student)
        db.flush()
        user.student_id = student.id
        db.commit()
        return int(student.id)
    finally:
        db.close()


def _extra_student_account_for_class(class_id: int, label: str) -> dict[str, object]:
    db = SessionLocal()
    try:
        password = f"{label}_pass123"
        user = User(
            username=f"security_student_{label}",
            hashed_password=get_password_hash(password),
            real_name=f"Security Student {label}",
            role=UserRole.STUDENT.value,
            class_id=class_id,
            is_active=True,
        )
        db.add(user)
        db.flush()
        student = Student(name=f"Security Student {label}", student_no=user.username, class_id=class_id)
        db.add(student)
        db.flush()
        user.student_id = student.id
        db.commit()
        return {"student_id": int(student.id), "username": user.username, "password": password}
    finally:
        db.close()


def _create_teacher(label: str) -> dict[str, object]:
    db = SessionLocal()
    try:
        password = f"{label}_pass123"
        user = User(
            username=f"security_teacher_{label}",
            hashed_password=get_password_hash(password),
            real_name=f"Security Teacher {label}",
            role=UserRole.TEACHER.value,
            is_active=True,
        )
        db.add(user)
        db.commit()
        return {"user_id": int(user.id), "username": user.username, "password": password}
    finally:
        db.close()


def _create_subject(
    name: str,
    teacher_id: int,
    class_id: int | None,
    course_type: str = "required",
) -> int:
    db = SessionLocal()
    try:
        subject = Subject(
            name=name,
            teacher_id=teacher_id,
            class_id=class_id,
            course_type=course_type,
            status="active",
        )
        db.add(subject)
        db.flush()
        if class_id is not None:
            db.add(
                SubjectClassLink(
                    subject_id=subject.id,
                    class_id=class_id,
                    enrollment_mode="all_in_class" if course_type == "required" else "roster_subset",
                )
            )
        db.commit()
        return int(subject.id)
    finally:
        db.close()


def _enroll_student(subject_id: int, student_id: int, class_id: int, enrollment_type: str = "required") -> None:
    db = SessionLocal()
    try:
        if not (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.subject_id == subject_id, CourseEnrollment.student_id == student_id)
            .first()
        ):
            db.add(
                CourseEnrollment(
                    subject_id=subject_id,
                    student_id=student_id,
                    class_id=class_id,
                    enrollment_type=enrollment_type,
                    can_remove=enrollment_type == "elective",
                )
            )
            db.commit()
    finally:
        db.close()


def _enrollment_exists(subject_id: int, student_id: int) -> bool:
    db = SessionLocal()
    try:
        return (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.subject_id == subject_id, CourseEnrollment.student_id == student_id)
            .first()
            is not None
        )
    finally:
        db.close()


def _material_count_for_subject(subject_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(CourseMaterial).filter(CourseMaterial.subject_id == subject_id).count()
    finally:
        db.close()


def _create_visible_teacher_owned_course(client: TestClient, ctx: dict, ct: dict, name: str) -> int:
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    created = client.post(
        "/api/subjects",
        headers=admin_headers,
        json={
            "name": name,
            "teacher_id": ctx["teacher_id"],
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    return int(created.json()["id"])


def _score_count_for_subject(subject_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(Score).filter(Score.subject_id == subject_id).count()
    finally:
        db.close()


def _score_value(score_id: int) -> float:
    db = SessionLocal()
    try:
        row = db.query(Score).filter(Score.id == score_id).first()
        assert row is not None
        return float(row.score)
    finally:
        db.close()


def _exam_weight_count_for_subject(subject_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(CourseExamWeight).filter(CourseExamWeight.subject_id == subject_id).count()
    finally:
        db.close()


def _grade_scheme_for_subject(subject_id: int) -> tuple[float, float] | None:
    db = SessionLocal()
    try:
        row = db.query(CourseGradeScheme).filter(CourseGradeScheme.subject_id == subject_id).first()
        if not row:
            return None
        return (float(row.homework_weight), float(row.extra_daily_weight))
    finally:
        db.close()


def _attendance_count_for_subject(subject_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(Attendance).filter(Attendance.subject_id == subject_id).count()
    finally:
        db.close()


def _notification_count_for_subject(subject_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(Notification).filter(Notification.subject_id == subject_id).count()
    finally:
        db.close()


def _notification_read_count(notification_id: int, user_id: int | None = None) -> int:
    db = SessionLocal()
    try:
        query = db.query(NotificationRead).filter(NotificationRead.notification_id == notification_id)
        if user_id is not None:
            query = query.filter(NotificationRead.user_id == user_id)
        return query.count()
    finally:
        db.close()


def _llm_config_enabled(subject_id: int) -> bool | None:
    db = SessionLocal()
    try:
        row = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == subject_id).first()
        if not row:
            return None
        return bool(row.is_enabled)
    finally:
        db.close()


def _create_score_appeal(subject_id: int, student_id: int, semester: str = "2026-fall") -> int:
    db = SessionLocal()
    try:
        appeal = ScoreGradeAppeal(
            subject_id=subject_id,
            student_id=student_id,
            semester=semester,
            target_component="total",
            reason_text="security appeal guard",
            status="pending",
        )
        db.add(appeal)
        db.commit()
        return int(appeal.id)
    finally:
        db.close()


def _appeal_status(appeal_id: int) -> str:
    db = SessionLocal()
    try:
        row = db.query(ScoreGradeAppeal).filter(ScoreGradeAppeal.id == appeal_id).first()
        assert row is not None
        return str(row.status)
    finally:
        db.close()


def _appeal_count(
    *,
    subject_id: int,
    student_id: int,
    semester: str,
    target_component: str,
    status: str | None = None,
) -> int:
    db = SessionLocal()
    try:
        query = db.query(ScoreGradeAppeal).filter(
            ScoreGradeAppeal.subject_id == subject_id,
            ScoreGradeAppeal.student_id == student_id,
            ScoreGradeAppeal.semester == semester,
            ScoreGradeAppeal.target_component == target_component,
        )
        if status is not None:
            query = query.filter(ScoreGradeAppeal.status == status)
        return query.count()
    finally:
        db.close()


def _set_parent_code(student_id: int, code: str = "PARENT123") -> str:
    db = SessionLocal()
    try:
        row = db.query(Student).filter(Student.id == student_id).first()
        assert row is not None
        row.parent_code = code
        row.parent_code_expires = None
        db.commit()
        return code
    finally:
        db.close()


def _set_parent_code_with_expiry(student_id: int, code: str, expires_at: datetime | None) -> str:
    db = SessionLocal()
    try:
        row = db.query(Student).filter(Student.id == student_id).first()
        assert row is not None
        row.parent_code = code
        row.parent_code_expires = expires_at
        db.commit()
        return code
    finally:
        db.close()


def _parent_code_for_student(student_id: int) -> str | None:
    db = SessionLocal()
    try:
        row = db.query(Student).filter(Student.id == student_id).first()
        assert row is not None
        return row.parent_code
    finally:
        db.close()


def _parent_code_expiry_for_student(student_id: int) -> datetime | None:
    db = SessionLocal()
    try:
        row = db.query(Student).filter(Student.id == student_id).first()
        assert row is not None
        return row.parent_code_expires
    finally:
        db.close()


def _user_id_for_username(username: str) -> int:
    db = SessionLocal()
    try:
        row = db.query(User).filter(User.username == username).first()
        assert row is not None
        return int(row.id)
    finally:
        db.close()


def test_hard01_change_password_invalidates_existing_token(client: TestClient):
    ctx = make_grading_course_with_homework()
    old_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    new_password = "ChangedPass123!"

    r = client.post(
        "/api/auth/change-password",
        headers=old_headers,
        json={
            "current_password": ctx["student_password"],
            "new_password": new_password,
            "confirm_password": new_password,
        },
    )
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me", headers=old_headers).status_code == 401
    assert client.post("/api/auth/login", data={"username": ctx["student_username"], "password": new_password}).status_code == 200


def test_hard02_admin_reset_password_invalidates_existing_token(client: TestClient):
    ctx = make_grading_course_with_homework()
    ensure_admin()
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")

    r = client.post(
        f"/api/users/{ctx['student_user_id']}/reset-password",
        headers=admin_headers,
        json={"new_password": "ResetPass123!"},
    )
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me", headers=student_headers).status_code == 401
    assert client.post("/api/auth/login", data={"username": ctx["student_username"], "password": "ResetPass123!"}).status_code == 200


def test_hard03_inactive_user_token_cannot_access_active_route(client: TestClient):
    ctx = make_grading_course_with_homework()
    ensure_admin()
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")

    r = client.put(f"/api/users/{ctx['student_user_id']}", headers=admin_headers, json={"is_active": False})
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me", headers=student_headers).status_code == 400


def test_hard04_e2e_powerful_route_rejects_missing_seed_token(client: TestClient):
    settings.E2E_DEV_SEED_ENABLED = True
    settings.E2E_DEV_SEED_TOKEN = "hardening-seed"
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = False

    r = client.post("/api/e2e/dev/mock-llm/configure", json={"profiles": {}})
    assert r.status_code == 403


def test_hard05_e2e_powerful_route_requires_admin_bearer_when_configured(client: TestClient):
    ctx = make_grading_course_with_homework()
    ensure_admin()
    settings.E2E_DEV_SEED_ENABLED = True
    settings.E2E_DEV_SEED_TOKEN = "hardening-seed"
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True
    seed = {"X-E2E-Seed-Token": "hardening-seed"}

    assert client.post("/api/e2e/dev/mock-llm/configure", headers=seed, json={"profiles": {}}).status_code == 403

    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r_teacher = client.post(
        "/api/e2e/dev/mock-llm/configure",
        headers={**seed, **teacher_headers},
        json={"profiles": {}},
    )
    assert r_teacher.status_code == 403

    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    r_admin = client.post(
        "/api/e2e/dev/mock-llm/configure",
        headers={**seed, **admin_headers},
        json={"profiles": {}},
    )
    assert r_admin.status_code == 200, r_admin.text


def test_hard06_reset_scenario_remains_seed_only_under_admin_jwt_mode(client: TestClient):
    settings.E2E_DEV_SEED_ENABLED = True
    settings.E2E_DEV_SEED_TOKEN = "hardening-seed"
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True

    r = client.post("/api/e2e/dev/reset-scenario", headers={"X-E2E-Seed-Token": "hardening-seed"})
    assert r.status_code == 200, r.text
    assert r.json()["admin"]["username"]


def test_hard07_student_cannot_patch_own_role_or_class(client: TestClient):
    ctx = make_grading_course_with_homework()
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])

    r = client.put(
        f"/api/users/{ctx['student_user_id']}",
        headers=student_headers,
        json={"role": UserRole.ADMIN.value, "class_id": None},
    )
    assert r.status_code == 403


def test_hard08_non_admin_self_update_cannot_deactivate_account(client: TestClient):
    ctx = make_grading_course_with_homework()
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    r = client.put(f"/api/users/{ctx['teacher_id']}", headers=teacher_headers, json={"is_active": False})
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is True


def test_hard09_teacher_owned_subject_attendance_write_does_not_require_teacher_class_id(client: TestClient):
    ctx = make_grading_course_with_homework()
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    r = client.post(
        "/api/attendance",
        headers=teacher_headers,
        json={
            "student_id": ctx["student_id"],
            "class_id": ctx["class_id"],
            "subject_id": ctx["subject_id"],
            "date": "2026-05-12",
            "status": "present",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["subject_id"] == ctx["subject_id"]


def test_hard10_foreign_teacher_cannot_write_attendance_for_other_course(client: TestClient):
    ctx_a = make_grading_course_with_homework()
    ctx_b = make_grading_course_with_homework()
    foreign_headers = login_api(client, ctx_b["teacher_username"], ctx_b["teacher_password"])

    r = client.post(
        "/api/attendance",
        headers=foreign_headers,
        json={
            "student_id": ctx_a["student_id"],
            "class_id": ctx_a["class_id"],
            "subject_id": ctx_a["subject_id"],
            "date": "2026-05-12",
            "status": "present",
        },
    )
    assert r.status_code in (403, 404)


def test_hard11_attachment_download_path_traversal_like_name_returns_not_found(client: TestClient):
    ctx = make_grading_course_with_homework()
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    r = client.get("/api/files/download/../../.env", headers=teacher_headers)
    assert r.status_code == 404


def test_hard12_attachment_acl_uses_logical_course_scope_not_just_file_possession(client: TestClient):
    ctx = make_grading_course_with_homework()
    other = make_grading_course_with_homework()
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    other_headers = login_api(client, other["teacher_username"], other["teacher_password"])

    upload = client.post(
        "/api/files/upload",
        headers=teacher_headers,
        files={"file": ("acl-proof.txt", b"course scoped attachment", "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    attachment_url = upload.json()["attachment_url"]

    db = SessionLocal()
    try:
        material = CourseMaterial(
            title="ACL proof",
            content="attached",
            attachment_name="acl-proof.txt",
            attachment_url=attachment_url,
            class_id=ctx["class_id"],
            subject_id=ctx["subject_id"],
            created_by=ctx["teacher_id"],
        )
        db.add(material)
        db.commit()
    finally:
        db.close()

    own = client.get("/api/files/download", headers=teacher_headers, params={"attachment_url": attachment_url})
    assert own.status_code == 200, own.text
    foreign = client.get("/api/files/download", headers=other_headers, params={"attachment_url": attachment_url})
    assert foreign.status_code == 403


def test_hard13_require_strong_secrets_rejects_default_secret_outside_production():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            APP_ENV="development",
            REQUIRE_STRONG_SECRETS=True,
            SECRET_KEY="change-me-in-production",
            DATABASE_URL="postgresql://courseeval:strong-pass@127.0.0.1:5432/courseeval_test",
        )


def test_hard14_production_rejects_default_database_placeholder_even_with_strong_secret():
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(
            APP_ENV="production",
            E2E_DEV_SEED_ENABLED=False,
            SECRET_KEY="x" * 40,
            DATABASE_URL="postgresql://courseeval:change-me@127.0.0.1:5432/courseeval",
        )


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/e2e/dev/grading-state", None),
        ("POST", "/api/e2e/dev/worker", {"action": "status"}),
        ("POST", "/api/e2e/dev/process-grading", {"max_tasks": 1}),
        ("POST", "/api/e2e/dev/mark-preset-validated", {"preset_id": 1}),
    ],
)
def test_hard15_powerful_e2e_dev_routes_reject_seed_only_when_admin_jwt_required(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, object] | None,
):
    settings.E2E_DEV_SEED_ENABLED = True
    settings.E2E_DEV_SEED_TOKEN = "hardening-seed"
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True
    response = client.request(method, path, headers={"X-E2E-Seed-Token": "hardening-seed"}, json=body)
    assert response.status_code == 403
    assert "administrator Bearer" in response.text


def test_hard16_teacher_cannot_assign_new_course_to_another_teacher(client: TestClient):
    ctx = make_grading_course_with_homework()
    other = make_grading_course_with_homework()
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    r = client.post(
        "/api/subjects",
        headers=teacher_headers,
        json={
            "name": "teacher ownership hardening",
            "teacher_id": other["teacher_id"],
            "class_id": ctx["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["teacher_id"] == ctx["teacher_id"]


def test_hard17_class_teacher_cannot_create_required_course_for_foreign_class(client: TestClient):
    ct = _create_class_teacher()
    db = SessionLocal()
    try:
        foreign_class = Class(name="security-foreign-class", grade=2026)
        db.add(foreign_class)
        db.commit()
        foreign_class_id = foreign_class.id
    finally:
        db.close()

    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))
    r = client.post(
        "/api/subjects",
        headers=ct_headers,
        json={
            "name": "foreign class hardening",
            "class_id": foreign_class_id,
            "course_type": "required",
            "status": "active",
        },
    )
    assert r.status_code in (400, 403)


def test_hard18_encoded_attachment_traversal_like_name_returns_not_found(client: TestClient):
    ctx = make_grading_course_with_homework()
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    r = client.get("/api/files/download/%2e%2e%2f.env", headers=teacher_headers)
    assert r.status_code == 404


def test_hard19_executable_upload_is_rejected_even_for_authenticated_teacher(client: TestClient):
    ctx = make_grading_course_with_homework()
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    r = client.post(
        "/api/files/upload",
        headers=teacher_headers,
        files={"file": ("payload.exe", b"MZ fake executable", "application/x-msdownload")},
    )
    assert r.status_code == 400


def test_hard20_teacher_cannot_browse_student_only_course_catalog(client: TestClient):
    ctx = make_grading_course_with_homework()
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    r = client.get("/api/subjects/course-catalog", headers=teacher_headers)
    assert r.status_code == 403


def test_hard21_class_teacher_cannot_update_required_course_to_foreign_class_id(client: TestClient):
    ct = _create_class_teacher("ct_update_foreign")
    foreign_class_id = _create_class("security-ct-update-foreign")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))
    created = client.post(
        "/api/subjects",
        headers=ct_headers,
        json={
            "name": "ct owned update foreign class",
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]

    r = client.put(f"/api/subjects/{subject_id}", headers=ct_headers, json={"class_id": foreign_class_id})
    assert r.status_code == 403
    assert _linked_class_ids(subject_id) == {int(ct["class_id"])}


def test_hard22_class_teacher_cannot_update_required_course_with_foreign_class_links(client: TestClient):
    ct = _create_class_teacher("ct_update_links")
    foreign_class_id = _create_class("security-ct-update-link-foreign")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))
    created = client.post(
        "/api/subjects",
        headers=ct_headers,
        json={
            "name": "ct owned update class links",
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]

    r = client.put(
        f"/api/subjects/{subject_id}",
        headers=ct_headers,
        json={
            "class_links": [
                {"class_id": ct["class_id"], "enrollment_mode": "all_in_class"},
                {"class_id": foreign_class_id, "enrollment_mode": "all_in_class"},
            ]
        },
    )
    assert r.status_code == 403
    assert _linked_class_ids(subject_id) == {int(ct["class_id"])}


def test_hard23_class_teacher_cannot_convert_class_bound_required_course_to_elective(client: TestClient):
    ct = _create_class_teacher("ct_update_elective")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))
    created = client.post(
        "/api/subjects",
        headers=ct_headers,
        json={
            "name": "ct owned convert elective",
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]

    r = client.put(f"/api/subjects/{subject_id}", headers=ct_headers, json={"course_type": "elective"})
    assert r.status_code == 403
    detail = client.get(f"/api/subjects/{subject_id}", headers=ct_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["course_type"] == "required"
    assert _linked_class_ids(subject_id) == {int(ct["class_id"])}


def test_hard24_class_teacher_cannot_update_foreign_teacher_course_even_with_own_class_link(client: TestClient):
    ct = _create_class_teacher("ct_foreign_teacher")
    ctx = make_grading_course_with_homework()
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    created = client.post(
        "/api/subjects",
        headers=admin_headers,
        json={
            "name": "foreign teacher own class linked",
            "teacher_id": ctx["teacher_id"],
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.put(
        f"/api/subjects/{created.json()['id']}",
        headers=ct_headers,
        json={"name": "ct should not mutate teacher-owned course"},
    )
    assert r.status_code == 403


def test_hard25_e2e_dev_reset_wrong_bearer_still_rejects_when_seed_is_valid(client: TestClient):
    ensure_admin()
    settings.E2E_DEV_SEED_ENABLED = True
    settings.E2E_DEV_SEED_TOKEN = "hardening-seed"
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True

    r = client.post(
        "/api/e2e/dev/mock-llm/configure",
        headers={"X-E2E-Seed-Token": "hardening-seed", "Authorization": "Bearer definitely.invalid.token"},
        json={"profiles": {}},
    )
    assert r.status_code in (401, 403)


def test_hard26_production_rejects_e2e_seed_even_with_strong_secret_and_database_url():
    with pytest.raises(ValueError, match="E2E_DEV_SEED_ENABLED"):
        Settings(
            APP_ENV="production",
            E2E_DEV_SEED_ENABLED=True,
            SECRET_KEY="x" * 40,
            DATABASE_URL="postgresql://courseeval:strong-pass@127.0.0.1:5432/courseeval_prod",
        )


def test_hard27_attachment_duplicate_db_references_with_same_basename_still_enforce_url_acl(client: TestClient):
    ctx = make_grading_course_with_homework()
    other = make_grading_course_with_homework()
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    other_headers = login_api(client, other["teacher_username"], other["teacher_password"])

    first = client.post(
        "/api/files/upload",
        headers=teacher_headers,
        files={"file": ("collision-a.txt", b"first collision body", "text/plain")},
    )
    assert first.status_code == 200, first.text
    first_url = first.json()["attachment_url"]
    basename = first_url.rsplit("/", 1)[-1]

    db = SessionLocal()
    try:
        db.add_all(
            [
                CourseMaterial(
                    title="ACL collision first",
                    content="attached",
                    attachment_name="collision-a.txt",
                    attachment_url=first_url,
                    class_id=ctx["class_id"],
                    subject_id=ctx["subject_id"],
                    created_by=ctx["teacher_id"],
                ),
                CourseMaterial(
                    title="ACL collision second same basename",
                    content="attached",
                    attachment_name="collision-b.txt",
                    attachment_url=first_url,
                    class_id=other["class_id"],
                    subject_id=other["subject_id"],
                    created_by=other["teacher_id"],
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    ambiguous = client.get(f"/api/files/download/{basename}", headers=teacher_headers)
    assert ambiguous.status_code == 200, ambiguous.text

    exact = client.get(
        f"/api/files/download/{basename}",
        headers=teacher_headers,
        params={"attachment_url": first_url},
    )
    assert exact.status_code == 200, exact.text

    foreign = client.get(
        f"/api/files/download/{basename}",
        headers=other_headers,
        params={"attachment_url": first_url},
    )
    assert foreign.status_code == 403


def test_hard28_upload_rejects_disguised_executable_content_with_safe_extension(client: TestClient):
    ctx = make_grading_course_with_homework()
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    r = client.post(
        "/api/files/upload",
        headers=teacher_headers,
        files={"file": ("payload.txt", b"MZ disguised executable", "text/plain")},
    )
    assert r.status_code == 400


def test_hard29_class_teacher_cannot_delete_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_delete_visible")
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    created = client.post(
        "/api/subjects",
        headers=admin_headers,
        json={
            "name": "ct visible delete guard",
            "teacher_id": ctx["teacher_id"],
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    assert client.get(f"/api/subjects/{subject_id}", headers=ct_headers).status_code == 200
    r = client.delete(f"/api/subjects/{subject_id}", headers=ct_headers)
    assert r.status_code == 403
    assert client.get(f"/api/subjects/{subject_id}", headers=admin_headers).status_code == 200


def test_hard30_class_teacher_cannot_upload_cover_to_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_cover_visible")
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    created = client.post(
        "/api/subjects",
        headers=admin_headers,
        json={
            "name": "ct visible cover guard",
            "teacher_id": ctx["teacher_id"],
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.post(
        f"/api/subjects/{subject_id}/cover-image",
        headers=ct_headers,
        files={"file": ("cover.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    assert r.status_code == 403
    detail = client.get(f"/api/subjects/{subject_id}", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    assert not detail.json().get("cover_image_url")


def test_hard31_class_teacher_cannot_sync_teacher_owned_visible_course_enrollments(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_sync_visible")
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    created = client.post(
        "/api/subjects",
        headers=admin_headers,
        json={
            "name": "ct visible sync guard",
            "teacher_id": ctx["teacher_id"],
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.post(f"/api/subjects/{created.json()['id']}/sync-enrollments", headers=ct_headers)
    assert r.status_code == 403


def test_hard32_class_teacher_cannot_roster_enroll_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_roster_visible")
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    created = client.post(
        "/api/subjects",
        headers=admin_headers,
        json={
            "name": "ct visible roster guard",
            "teacher_id": ctx["teacher_id"],
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]
    student_id = _extra_student_for_class(int(ct["class_id"]), "ct_roster_visible")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.post(f"/api/subjects/{subject_id}/roster-enroll", headers=ct_headers, json={"student_ids": [student_id]})
    assert r.status_code == 403
    assert not _enrollment_exists(subject_id, student_id)


def test_hard33_class_teacher_cannot_change_enrollment_type_on_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_enroll_type_visible")
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    created = client.post(
        "/api/subjects",
        headers=admin_headers,
        json={
            "name": "ct visible enrollment type guard",
            "teacher_id": ctx["teacher_id"],
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]
    student_id = _extra_student_for_class(int(ct["class_id"]), "ct_enroll_type_visible")
    assert client.post(f"/api/subjects/{subject_id}/sync-enrollments", headers=admin_headers).status_code == 200
    assert _enrollment_exists(subject_id, student_id)
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.put(
        f"/api/subjects/{subject_id}/students/{student_id}/enrollment-type",
        headers=ct_headers,
        json={"enrollment_type": "elective"},
    )
    assert r.status_code == 403


def test_hard34_class_teacher_cannot_remove_student_from_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_remove_student_visible")
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    created = client.post(
        "/api/subjects",
        headers=admin_headers,
        json={
            "name": "ct visible remove student guard",
            "teacher_id": ctx["teacher_id"],
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]
    student_id = _extra_student_for_class(int(ct["class_id"]), "ct_remove_student_visible")
    assert client.post(f"/api/subjects/{subject_id}/sync-enrollments", headers=admin_headers).status_code == 200
    assert _enrollment_exists(subject_id, student_id)
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.delete(f"/api/subjects/{subject_id}/students/{student_id}", headers=ct_headers)
    assert r.status_code == 403
    assert _enrollment_exists(subject_id, student_id)


def test_hard35_class_teacher_cannot_create_material_in_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_material_visible")
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    created = client.post(
        "/api/subjects",
        headers=admin_headers,
        json={
            "name": "ct visible material guard",
            "teacher_id": ctx["teacher_id"],
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    subject_id = created.json()["id"]
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    before = _material_count_for_subject(subject_id)
    r = client.post(
        "/api/materials",
        headers=ct_headers,
        json={
            "title": "ct forbidden material",
            "content": "should not publish",
            "content_format": "plain",
            "class_id": ct["class_id"],
            "subject_id": subject_id,
        },
    )
    assert r.status_code == 403
    assert _material_count_for_subject(subject_id) == before


def test_hard36_class_teacher_cannot_create_homework_in_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_homework_visible")
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    created = client.post(
        "/api/subjects",
        headers=admin_headers,
        json={
            "name": "ct visible homework guard",
            "teacher_id": ctx["teacher_id"],
            "class_id": ct["class_id"],
            "course_type": "required",
            "status": "active",
        },
    )
    assert created.status_code == 200, created.text
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.post(
        "/api/homeworks",
        headers=ct_headers,
        json={
            "title": "ct forbidden homework",
            "content": "should not assign",
            "content_format": "plain",
            "class_id": ct["class_id"],
            "subject_id": created.json()["id"],
            "due_date": None,
            "max_score": 100,
            "grade_precision": "integer",
            "auto_grading_enabled": False,
            "allow_late_submission": True,
            "late_submission_affects_score": False,
            "max_submissions": None,
            "llm_routing_spec": None,
        },
    )
    assert r.status_code == 403


def test_hard37_class_teacher_cannot_create_score_for_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_score_create_visible")
    subject_id = _create_visible_teacher_owned_course(client, ctx, ct, "ct visible score create guard")
    student_id = _extra_student_for_class(int(ct["class_id"]), "ct_score_create_visible")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    before = _score_count_for_subject(subject_id)
    r = client.post(
        "/api/scores",
        headers=ct_headers,
        json={
            "student_id": student_id,
            "subject_id": subject_id,
            "class_id": ct["class_id"],
            "semester": "2026-fall",
            "exam_type": "midterm",
            "score": 96,
            "exam_date": None,
        },
    )
    assert r.status_code == 403
    assert _score_count_for_subject(subject_id) == before


def test_hard38_class_teacher_cannot_update_score_for_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_score_update_visible")
    subject_id = _create_visible_teacher_owned_course(client, ctx, ct, "ct visible score update guard")
    student_id = _extra_student_for_class(int(ct["class_id"]), "ct_score_update_visible")
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    created = client.post(
        "/api/scores",
        headers=admin_headers,
        json={
            "student_id": student_id,
            "subject_id": subject_id,
            "class_id": ct["class_id"],
            "semester": "2026-fall",
            "exam_type": "final",
            "score": 88,
            "exam_date": None,
        },
    )
    assert created.status_code == 200, created.text
    score_id = created.json()["id"]
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.put(f"/api/scores/{score_id}", headers=ct_headers, json={"score": 100})
    assert r.status_code == 403
    assert _score_value(score_id) == 88


def test_hard39_class_teacher_cannot_update_exam_weights_for_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_score_weights_visible")
    subject_id = _create_visible_teacher_owned_course(client, ctx, ct, "ct visible weights guard")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    before = _exam_weight_count_for_subject(subject_id)
    r = client.put(
        f"/api/scores/weights/{subject_id}",
        headers=ct_headers,
        json={"items": [{"exam_type": "final", "weight": 40}]},
    )
    assert r.status_code == 403
    assert _exam_weight_count_for_subject(subject_id) == before


def test_hard40_class_teacher_cannot_update_grade_scheme_for_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_grade_scheme_visible")
    subject_id = _create_visible_teacher_owned_course(client, ctx, ct, "ct visible grade scheme guard")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    before = _grade_scheme_for_subject(subject_id)
    r = client.put(
        f"/api/scores/grade-scheme/{subject_id}",
        headers=ct_headers,
        json={"homework_weight": 10, "extra_daily_weight": 10},
    )
    assert r.status_code == 403
    assert _grade_scheme_for_subject(subject_id) == before


def test_hard41_class_teacher_cannot_create_attendance_for_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_attendance_visible")
    subject_id = _create_visible_teacher_owned_course(client, ctx, ct, "ct visible attendance guard")
    student_id = _extra_student_for_class(int(ct["class_id"]), "ct_attendance_visible")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    before = _attendance_count_for_subject(subject_id)
    r = client.post(
        "/api/attendance",
        headers=ct_headers,
        json={
            "student_id": student_id,
            "class_id": ct["class_id"],
            "subject_id": subject_id,
            "date": "2026-05-12",
            "status": "absent",
            "remark": "should not write",
        },
    )
    assert r.status_code == 403
    assert _attendance_count_for_subject(subject_id) == before


def test_hard42_class_teacher_cannot_class_batch_attendance_for_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_attendance_batch_visible")
    subject_id = _create_visible_teacher_owned_course(client, ctx, ct, "ct visible attendance batch guard")
    _extra_student_for_class(int(ct["class_id"]), "ct_attendance_batch_visible")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    before = _attendance_count_for_subject(subject_id)
    r = client.post(
        "/api/attendance/class-batch",
        headers=ct_headers,
        json={
            "class_id": ct["class_id"],
            "subject_id": subject_id,
            "date": "2026-05-13",
            "status": "late",
            "remark": "should not batch write",
        },
    )
    assert r.status_code == 403
    assert _attendance_count_for_subject(subject_id) == before


def test_hard43_class_teacher_cannot_publish_notification_for_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_notification_visible")
    subject_id = _create_visible_teacher_owned_course(client, ctx, ct, "ct visible notification guard")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    before = _notification_count_for_subject(subject_id)
    r = client.post(
        "/api/notifications",
        headers=ct_headers,
        json={
            "title": "forbidden teacher-owned course notice",
            "content": "should not publish",
            "content_format": "plain",
            "priority": "normal",
            "class_id": ct["class_id"],
            "subject_id": subject_id,
        },
    )
    assert r.status_code == 403
    assert _notification_count_for_subject(subject_id) == before


def test_hard44_class_teacher_cannot_update_llm_config_for_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher("ct_llm_config_visible")
    subject_id = _create_visible_teacher_owned_course(client, ctx, ct, "ct visible llm config guard")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    before = _llm_config_enabled(subject_id)
    r = client.put(
        f"/api/llm-settings/courses/{subject_id}",
        headers=ct_headers,
        json={
            "is_enabled": True,
            "response_language": "zh",
            "max_input_tokens": 16000,
            "max_output_tokens": 1000,
            "system_prompt": None,
            "teacher_prompt": "should not mutate",
            "endpoints": [],
            "groups": [],
        },
    )
    assert r.status_code == 403
    assert _llm_config_enabled(subject_id) == before


def test_hard45_class_teacher_cannot_delete_course_teacher_discussion_entry_on_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_discussion_delete_visible")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))
    entry_id = _create_discussion_entry(ctx["subject_id"], ctx["class_id"], ctx["homework_id"], ctx["teacher_id"])

    r = client.delete(f"/api/discussions/{entry_id}", headers=ct_headers)
    assert r.status_code == 403
    assert _discussion_exists(entry_id)


def test_hard46_class_teacher_cannot_reorder_material_chapters_for_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_chapter_reorder_visible")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))
    first = _create_chapter(ctx["subject_id"], "Security reorder first")
    second = _create_chapter(ctx["subject_id"], "Security reorder second")
    before = _chapter_order(ctx["subject_id"])

    r = client.post(
        f"/api/material-chapters/reorder?subject_id={ctx['subject_id']}",
        headers=ct_headers,
        json={"parent_id": None, "ordered_chapter_ids": [second, first]},
    )
    assert r.status_code == 403
    assert _chapter_order(ctx["subject_id"]) == before


def test_hard47_class_teacher_cannot_add_material_placement_for_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_material_placement_visible")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))
    chapter_id = _create_chapter(ctx["subject_id"], "Security placement target")
    other_chapter_id = _create_chapter(ctx["subject_id"], "Security placement other")
    material_id, _section_id = _create_material_section(ctx["subject_id"], ctx["class_id"], ctx["teacher_id"], chapter_id)
    before = _material_section_count(material_id)

    r = client.post(
        f"/api/material-chapters/materials/{material_id}/placements?subject_id={ctx['subject_id']}",
        headers=ct_headers,
        json={"chapter_id": other_chapter_id},
    )
    assert r.status_code == 403
    assert _material_section_count(material_id) == before


def test_hard48_class_teacher_cannot_link_homework_into_teacher_owned_visible_course_directory(client: TestClient):
    ctx = make_grading_course_with_homework()
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_link_visible")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))
    chapter_id = _create_chapter(ctx["subject_id"], "Security homework link target")
    homework_id = _create_course_homework(ctx["subject_id"], ctx["class_id"], ctx["teacher_id"])
    before = _homework_link_count(chapter_id)

    r = client.post(
        f"/api/material-chapters/homework-links?subject_id={ctx['subject_id']}",
        headers=ct_headers,
        json={"chapter_id": chapter_id, "homework_id": homework_id},
    )
    assert r.status_code == 403
    assert _homework_link_count(chapter_id) == before


def test_hard49_class_teacher_cannot_respond_to_appeal_for_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_appeal_visible")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))
    appeal_id = _create_score_appeal(ctx["subject_id"], ctx["student_id"])

    r = client.put(
        f"/api/scores/appeals/{appeal_id}",
        headers=ct_headers,
        json={"teacher_response": "class teacher should not resolve", "status": "resolved"},
    )
    assert r.status_code == 403
    assert _appeal_status(appeal_id) == "pending"


def test_hard50_class_teacher_cannot_revoke_parent_code_for_foreign_class_student_only_visible_through_course_link(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_parent_code_visible")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))
    foreign_class_id = _create_class("security-parent-code-foreign")
    foreign_student_id = _extra_student_for_class(foreign_class_id, "ct_parent_code_foreign")
    db = SessionLocal()
    try:
        db.add(
            SubjectClassLink(
                subject_id=ctx["subject_id"],
                class_id=foreign_class_id,
                enrollment_mode="all_in_class",
            )
        )
        db.commit()
    finally:
        db.close()
    code = _set_parent_code(foreign_student_id, "PARENTVISIBLE")

    before = client.get(f"/api/parent/verify/{code}")
    assert before.status_code == 200
    r = client.delete(f"/api/parent/students/{foreign_student_id}/revoke-code", headers=ct_headers)
    assert r.status_code == 403
    after = client.get(f"/api/parent/verify/{code}")
    assert after.status_code == 200


def test_hard51_class_teacher_batch_score_import_cannot_write_teacher_owned_visible_course(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_batch_score_visible")
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))
    before = _score_count_for_subject(ctx["subject_id"])

    r = client.post(
        "/api/scores/batch",
        headers=ct_headers,
        json={
            "scores": [
                {
                    "student_no": ctx["student_username"],
                    "student_name": "Student One",
                    "class_id": ctx["class_id"],
                    "subject_id": ctx["subject_id"],
                    "semester": "2026-fall",
                    "exam_type": "batch-hardening",
                    "score": 91,
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["success"] == 0
    assert _score_count_for_subject(ctx["subject_id"]) == before


def test_hard52_dashboard_subject_stats_do_not_mix_scores_from_other_visible_courses(client: TestClient):
    ctx_a = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ctx_b = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    assert client.post(
        "/api/scores",
        headers=admin_headers,
        json={
            "student_id": ctx_a["student_id"],
            "subject_id": ctx_a["subject_id"],
            "class_id": ctx_a["class_id"],
            "semester": "2026-fall",
            "exam_type": "dashboard-a",
            "score": 70,
            "exam_date": None,
        },
    ).status_code == 200
    assert client.post(
        "/api/scores",
        headers=admin_headers,
        json={
            "student_id": ctx_b["student_id"],
            "subject_id": ctx_b["subject_id"],
            "class_id": ctx_b["class_id"],
            "semester": "2026-fall",
            "exam_type": "dashboard-b",
            "score": 100,
            "exam_date": None,
        },
    ).status_code == 200
    teacher_headers = login_api(client, ctx_a["teacher_username"], ctx_a["teacher_password"])

    scoped = client.get(f"/api/dashboard/stats?subject_id={ctx_a['subject_id']}", headers=teacher_headers)
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["total_scores"] == 1
    assert scoped.json()["avg_score"] == 70


def test_hard53_parent_homework_requires_subject_enrollment_for_same_class_electives(client: TestClient):
    teacher = _create_teacher("parent_homework_scope")
    class_id = _create_class("security-parent-homework-scope")
    student = _extra_student_account_for_class(class_id, "parent_homework_scope")
    required_subject_id = _create_subject("Parent visible required homework", int(teacher["user_id"]), class_id)
    elective_subject_id = _create_subject("Parent hidden elective homework", int(teacher["user_id"]), class_id, "elective")
    _enroll_student(required_subject_id, int(student["student_id"]), class_id)
    visible_title = "parent-visible-required-homework"
    hidden_title = "parent-hidden-elective-homework"
    _create_course_homework(required_subject_id, class_id, int(teacher["user_id"]), visible_title)
    _create_course_homework(elective_subject_id, class_id, int(teacher["user_id"]), hidden_title)
    parent_code = _set_parent_code(int(student["student_id"]), "HARD53PARENT")

    r = client.get(f"/api/parent/homework/{parent_code}?page_size=100")
    assert r.status_code == 200, r.text
    titles = {row["title"] for row in r.json()["homeworks"]}
    assert visible_title in titles
    assert hidden_title not in titles


def test_hard54_parent_notifications_compose_subject_enrollment_and_target_student_filters(client: TestClient):
    teacher = _create_teacher("parent_notice_scope")
    class_id = _create_class("security-parent-notice-scope")
    student = _extra_student_account_for_class(class_id, "parent_notice_scope_a")
    sibling = _extra_student_account_for_class(class_id, "parent_notice_scope_b")
    required_subject_id = _create_subject("Parent visible required notice", int(teacher["user_id"]), class_id)
    elective_subject_id = _create_subject("Parent hidden elective notice", int(teacher["user_id"]), class_id, "elective")
    _enroll_student(required_subject_id, int(student["student_id"]), class_id)
    visible_required = "parent-visible-required-notice"
    hidden_elective = "parent-hidden-elective-notice"
    hidden_target = "parent-hidden-targeted-sibling-notice"
    visible_class = "parent-visible-class-notice"
    _create_notification(required_subject_id, class_id, int(teacher["user_id"]), visible_required)
    _create_notification(elective_subject_id, class_id, int(teacher["user_id"]), hidden_elective)
    _create_notification(required_subject_id, class_id, int(teacher["user_id"]), hidden_target, int(sibling["student_id"]))
    _create_notification(None, class_id, int(teacher["user_id"]), visible_class)
    parent_code = _set_parent_code(int(student["student_id"]), "HARD54PARENT")

    r = client.get(f"/api/parent/notifications/{parent_code}?page_size=100")
    assert r.status_code == 200, r.text
    titles = {row["title"] for row in r.json()["notifications"]}
    assert visible_required in titles
    assert visible_class in titles
    assert hidden_elective not in titles
    assert hidden_target not in titles


def test_hard55_class_teacher_batch_parent_code_generation_skips_linked_foreign_class_student(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_parent_batch")
    own_student_id = _extra_student_for_class(int(ct["class_id"]), "ct_parent_batch_own")
    foreign_class_id = _create_class("security-parent-code-batch-foreign")
    foreign_student_id = _extra_student_for_class(foreign_class_id, "ct_parent_batch_foreign")
    db = SessionLocal()
    try:
        db.add(
            SubjectClassLink(
                subject_id=ctx["subject_id"],
                class_id=foreign_class_id,
                enrollment_mode="all_in_class",
            )
        )
        db.commit()
    finally:
        db.close()
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.post(
        "/api/parent/students/batch-generate-codes",
        headers=ct_headers,
        json=[own_student_id, foreign_student_id],
    )
    assert r.status_code == 200, r.text
    generated_ids = {row["student_id"] for row in r.json()["students"]}
    assert r.json()["generated_count"] == 1
    assert own_student_id in generated_ids
    assert foreign_student_id not in generated_ids
    assert client.get(f"/api/parent/verify/{_set_parent_code(foreign_student_id, 'HARD55FOREIGN')}").json()["valid"] is True


def test_hard56_parent_scores_and_stats_ignore_other_student_same_class_records(client: TestClient):
    teacher = _create_teacher("parent_score_scope")
    class_id = _create_class("security-parent-score-scope")
    student = _extra_student_account_for_class(class_id, "parent_score_scope_a")
    sibling = _extra_student_account_for_class(class_id, "parent_score_scope_b")
    subject_id = _create_subject("Parent score scoped course", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    _enroll_student(subject_id, int(sibling["student_id"]), class_id)
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    for student_id, exam_type, score in (
        (int(student["student_id"]), "parent-own", 72),
        (int(sibling["student_id"]), "parent-sibling", 99),
    ):
        r = client.post(
            "/api/scores",
            headers=admin_headers,
            json={
                "student_id": student_id,
                "subject_id": subject_id,
                "class_id": class_id,
                "semester": "2026-fall",
                "exam_type": exam_type,
                "score": score,
                "exam_date": None,
            },
        )
        assert r.status_code == 200, r.text
    parent_code = _set_parent_code(int(student["student_id"]), "HARD56PARENT")

    scores = client.get(f"/api/parent/scores/{parent_code}?page_size=100")
    assert scores.status_code == 200, scores.text
    returned_exam_types = {row["exam_type"] for row in scores.json()["scores"]}
    assert returned_exam_types == {"parent-own"}
    stats = client.get(f"/api/parent/stats/{parent_code}")
    assert stats.status_code == 200, stats.text
    assert stats.json()["total_exams"] == 1
    assert stats.json()["average_score"] == 72


def test_hard57_score_appeal_second_submission_after_resolved_creates_one_new_pending(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    first = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_headers,
        json={"semester": "2026-fall", "target_component": "total", "reason_text": "first appeal"},
    )
    assert first.status_code == 200, first.text
    resolved = client.put(
        f"/api/scores/appeals/{first.json()['id']}",
        headers=teacher_headers,
        json={"teacher_response": "resolved", "status": "resolved"},
    )
    assert resolved.status_code == 200, resolved.text

    second = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_headers,
        json={"semester": "2026-fall", "target_component": "total", "reason_text": "second appeal"},
    )
    assert second.status_code == 200, second.text
    assert _appeal_status(first.json()["id"]) == "resolved"
    assert _appeal_count(
        subject_id=ctx["subject_id"],
        student_id=ctx["student_id"],
        semester="2026-fall",
        target_component="total",
        status="pending",
    ) == 1


def test_hard58_score_appeal_duplicate_pending_block_survives_rejected_prior_appeal(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    first = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_headers,
        json={"semester": "2026-fall", "target_component": "total", "reason_text": "first reject path"},
    )
    assert first.status_code == 200, first.text
    rejected = client.put(
        f"/api/scores/appeals/{first.json()['id']}",
        headers=teacher_headers,
        json={"teacher_response": "rejected", "status": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text
    second = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_headers,
        json={"semester": "2026-fall", "target_component": "total", "reason_text": "second pending"},
    )
    assert second.status_code == 200, second.text
    duplicate = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_headers,
        json={"semester": "2026-fall", "target_component": "total", "reason_text": "duplicate pending"},
    )
    assert duplicate.status_code == 400
    assert _appeal_status(first.json()["id"]) == "rejected"
    assert _appeal_count(
        subject_id=ctx["subject_id"],
        student_id=ctx["student_id"],
        semester="2026-fall",
        target_component="total",
        status="pending",
    ) == 1


def test_hard59_dashboard_subject_rankings_and_trends_do_not_mix_other_courses(client: TestClient):
    ctx_a = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ctx_b = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    for ctx, exam_type, score in ((ctx_a, "dash-midterm", 61), (ctx_b, "dash-midterm", 99), (ctx_a, "dash-final", 81)):
        r = client.post(
            "/api/scores",
            headers=admin_headers,
            json={
                "student_id": ctx["student_id"],
                "subject_id": ctx["subject_id"],
                "class_id": ctx["class_id"],
                "semester": "2026-fall",
                "exam_type": exam_type,
                "score": score,
                "exam_date": None,
            },
        )
        assert r.status_code == 200, r.text
    teacher_headers = login_api(client, ctx_a["teacher_username"], ctx_a["teacher_password"])

    classes = client.get(f"/api/dashboard/rankings/classes?subject_id={ctx_a['subject_id']}", headers=teacher_headers)
    assert classes.status_code == 200, classes.text
    assert [row["avg_score"] for row in classes.json()] == [71]
    students = client.get(f"/api/dashboard/rankings/students?subject_id={ctx_a['subject_id']}", headers=teacher_headers)
    assert students.status_code == 200, students.text
    assert students.json()[0]["avg_score"] == 71
    trends = client.get(f"/api/dashboard/analysis/trends?subject_id={ctx_a['subject_id']}", headers=teacher_headers)
    assert trends.status_code == 200, trends.text
    assert trends.json()["dash-midterm"]["avg"] == 61
    assert trends.json()["dash-final"]["avg"] == 81


def test_hard60_dashboard_subject_analysis_only_returns_requested_subject(client: TestClient):
    ctx_a = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ctx_b = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    for ctx, score in ((ctx_a, 64), (ctx_b, 98)):
        r = client.post(
            "/api/scores",
            headers=admin_headers,
            json={
                "student_id": ctx["student_id"],
                "subject_id": ctx["subject_id"],
                "class_id": ctx["class_id"],
                "semester": "2026-fall",
                "exam_type": "dash-analysis",
                "score": score,
                "exam_date": None,
            },
        )
        assert r.status_code == 200, r.text
    teacher_headers = login_api(client, ctx_a["teacher_username"], ctx_a["teacher_password"])

    analysis = client.get(f"/api/dashboard/analysis/subjects?subject_id={ctx_a['subject_id']}", headers=teacher_headers)
    assert analysis.status_code == 200, analysis.text
    payload = analysis.json()
    assert len(payload) == 1
    assert payload[0]["subject_id"] == ctx_a["subject_id"]
    assert payload[0]["avg_score"] == 64


def test_hard61_parent_code_rate_limit_applies_to_invalid_verify_attempts(client: TestClient):
    for idx in range(30):
        r = client.get("/api/parent/verify/NOPE0001")
        assert r.status_code == 200
        assert r.json()["valid"] is False

    limited = client.get("/api/parent/verify/NOPE0001")
    assert limited.status_code == 429


def test_hard62_expired_parent_code_verify_is_invalid_and_read_endpoints_forbid(client: TestClient):
    class_id = _create_class("security-parent-expired")
    student_id = _extra_student_for_class(class_id, "parent_expired")
    code = _set_parent_code_with_expiry(
        student_id,
        "HARD62EXP",
        datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    verify = client.get(f"/api/parent/verify/{code}")
    assert verify.status_code == 200
    assert verify.json()["valid"] is False
    assert "过期" in verify.json()["message"] or "杩囨湡" in verify.json()["message"]
    student = client.get(f"/api/parent/student/{code}")
    assert student.status_code == 403
    homework = client.get(f"/api/parent/homework/{code}")
    assert homework.status_code == 403


def test_hard63_parent_code_regeneration_rotates_code_and_expires_old_code(client: TestClient):
    teacher = _create_teacher("parent_rotate")
    class_id = _create_class("security-parent-rotate")
    student_id = _extra_student_for_class(class_id, "parent_rotate")
    subject_id = _create_subject("Parent rotate teacher course", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, student_id, class_id)
    old_code = _set_parent_code(student_id, "HARD63OLD")
    teacher_headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    generated = client.post(f"/api/parent/students/{student_id}/generate-code", headers=teacher_headers)
    assert generated.status_code == 200, generated.text
    new_code = generated.json()["parent_code"]
    assert new_code != old_code
    assert client.get(f"/api/parent/verify/{old_code}").json()["valid"] is False
    assert client.get(f"/api/parent/verify/{new_code}").json()["valid"] is True


def test_hard64_regular_teacher_can_manage_parent_code_for_student_in_own_course_only(client: TestClient):
    owner = _create_teacher("parent_regular_owner")
    other = _create_teacher("parent_regular_other")
    class_id = _create_class("security-parent-regular-owner")
    student_id = _extra_student_for_class(class_id, "parent_regular_owner")
    subject_id = _create_subject("Parent regular teacher owned course", int(owner["user_id"]), class_id)
    _enroll_student(subject_id, student_id, class_id)
    owner_headers = login_api(client, str(owner["username"]), str(owner["password"]))
    other_headers = login_api(client, str(other["username"]), str(other["password"]))

    denied = client.post(f"/api/parent/students/{student_id}/generate-code", headers=other_headers)
    assert denied.status_code == 403
    allowed = client.post(f"/api/parent/students/{student_id}/generate-code", headers=owner_headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["parent_code"]


def test_hard65_regular_teacher_batch_parent_code_generation_skips_unowned_course_students(client: TestClient):
    owner = _create_teacher("parent_regular_batch_owner")
    other = _create_teacher("parent_regular_batch_other")
    own_class_id = _create_class("security-parent-regular-batch-own")
    foreign_class_id = _create_class("security-parent-regular-batch-foreign")
    own_student_id = _extra_student_for_class(own_class_id, "parent_regular_batch_own")
    foreign_student_id = _extra_student_for_class(foreign_class_id, "parent_regular_batch_foreign")
    subject_id = _create_subject("Parent regular batch owned course", int(owner["user_id"]), own_class_id)
    _enroll_student(subject_id, own_student_id, own_class_id)
    foreign_subject_id = _create_subject("Parent regular batch foreign course", int(other["user_id"]), foreign_class_id)
    _enroll_student(foreign_subject_id, foreign_student_id, foreign_class_id)
    owner_headers = login_api(client, str(owner["username"]), str(owner["password"]))

    r = client.post(
        "/api/parent/students/batch-generate-codes",
        headers=owner_headers,
        json=[own_student_id, foreign_student_id],
    )
    assert r.status_code == 200, r.text
    generated_ids = {row["student_id"] for row in r.json()["students"]}
    assert generated_ids == {own_student_id}
    assert _parent_code_for_student(foreign_student_id) is None


def test_hard66_class_teacher_cannot_manage_parent_code_without_direct_class_even_when_teacher_course_visible(client: TestClient):
    teacher = _create_teacher("parent_ct_visible_teacher")
    ct = _create_class_teacher("parent_ct_linked")
    foreign_class_id = _create_class("security-parent-ct-linked-foreign")
    foreign_student_id = _extra_student_for_class(foreign_class_id, "parent_ct_linked_foreign")
    subject_id = _create_subject("Parent ct linked visible course", int(teacher["user_id"]), foreign_class_id)
    _enroll_student(subject_id, foreign_student_id, foreign_class_id)
    db = SessionLocal()
    try:
        db.add(
            SubjectClassLink(
                subject_id=subject_id,
                class_id=int(ct["class_id"]),
                enrollment_mode="all_in_class",
            )
        )
        db.commit()
    finally:
        db.close()
    ct_headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.post(f"/api/parent/students/{foreign_student_id}/generate-code", headers=ct_headers)
    assert r.status_code == 403
    assert _parent_code_for_student(foreign_student_id) is None


def test_hard67_parent_subject_scope_with_no_enrollments_returns_only_classwide_homework_and_notifications(client: TestClient):
    teacher = _create_teacher("parent_empty_enrollment")
    class_id = _create_class("security-parent-empty-enrollment")
    student_id = _extra_student_for_class(class_id, "parent_empty_enrollment")
    subject_id = _create_subject("Parent hidden no enrollment subject", int(teacher["user_id"]), class_id, "elective")
    hidden_homework = "parent-hidden-no-enrollment-homework"
    visible_homework = "parent-visible-classwide-homework"
    hidden_notice = "parent-hidden-no-enrollment-notice"
    visible_notice = "parent-visible-classwide-notice"
    _create_course_homework(subject_id, class_id, int(teacher["user_id"]), hidden_homework)
    _create_course_homework(None, class_id, int(teacher["user_id"]), visible_homework)
    _create_notification(subject_id, class_id, int(teacher["user_id"]), hidden_notice)
    _create_notification(None, class_id, int(teacher["user_id"]), visible_notice)
    code = _set_parent_code(student_id, "HARD67PARENT")

    homework = client.get(f"/api/parent/homework/{code}?page_size=100")
    assert homework.status_code == 200, homework.text
    homework_titles = {row["title"] for row in homework.json()["homeworks"]}
    assert visible_homework in homework_titles
    assert hidden_homework not in homework_titles
    notices = client.get(f"/api/parent/notifications/{code}?page_size=100")
    assert notices.status_code == 200, notices.text
    notice_titles = {row["title"] for row in notices.json()["notifications"]}
    assert visible_notice in notice_titles
    assert hidden_notice not in notice_titles


def test_hard68_generated_parent_codes_get_future_expiry_and_revoke_clears_expiry(client: TestClient):
    teacher = _create_teacher("parent_expiry_revoke")
    class_id = _create_class("security-parent-expiry-revoke")
    student_id = _extra_student_for_class(class_id, "parent_expiry_revoke")
    subject_id = _create_subject("Parent expiry teacher course", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, student_id, class_id)
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    generated = client.post(f"/api/parent/students/{student_id}/generate-code", headers=headers)
    assert generated.status_code == 200, generated.text
    expiry = _parent_code_expiry_for_student(student_id)
    assert expiry is not None
    assert expiry > datetime.now() + timedelta(days=300)
    revoked = client.delete(f"/api/parent/students/{student_id}/revoke-code", headers=headers)
    assert revoked.status_code == 200, revoked.text
    assert _parent_code_for_student(student_id) is None
    assert _parent_code_expiry_for_student(student_id) is None


def test_hard69_student_cannot_mark_targeted_notification_for_other_student_read(client: TestClient):
    teacher = _create_teacher("notif_read_target_teacher")
    class_id = _create_class("security-notif-read-target")
    student_a = _extra_student_account_for_class(class_id, "notif_read_target_a")
    student_b = _extra_student_account_for_class(class_id, "notif_read_target_b")
    subject_id = _create_subject("Notification read targeted course", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student_a["student_id"]), class_id)
    _enroll_student(subject_id, int(student_b["student_id"]), class_id)
    notification_id = _create_notification(
        subject_id,
        class_id,
        int(teacher["user_id"]),
        "hard69 targeted notice",
        target_student_id=int(student_b["student_id"]),
    )
    student_a_headers = login_api(client, str(student_a["username"]), str(student_a["password"]))

    r = client.post(f"/api/notifications/{notification_id}/read", headers=student_a_headers)

    assert r.status_code == 403
    assert _notification_read_count(notification_id, _user_id_for_username(str(student_a["username"]))) == 0


def test_hard70_teacher_cannot_mark_foreign_target_user_notification_read(client: TestClient):
    owner = _create_teacher("notif_read_owner")
    other = _create_teacher("notif_read_other")
    class_id = _create_class("security-notif-read-user-target")
    notification_id = _create_notification(
        None,
        class_id,
        int(owner["user_id"]),
        "hard70 teacher-targeted notice",
    )
    db = SessionLocal()
    try:
        row = db.query(Notification).filter(Notification.id == notification_id).first()
        assert row is not None
        row.target_user_id = int(owner["user_id"])
        db.commit()
    finally:
        db.close()
    other_headers = login_api(client, str(other["username"]), str(other["password"]))

    r = client.post(f"/api/notifications/{notification_id}/read", headers=other_headers)

    assert r.status_code == 403
    assert _notification_read_count(notification_id, int(other["user_id"])) == 0


def test_hard71_student_cannot_mark_unenrolled_elective_notification_read(client: TestClient):
    teacher = _create_teacher("notif_read_elective_teacher")
    class_id = _create_class("security-notif-read-elective")
    student = _extra_student_account_for_class(class_id, "notif_read_elective")
    subject_id = _create_subject("Notification read hidden elective", int(teacher["user_id"]), class_id, "elective")
    notification_id = _create_notification(subject_id, class_id, int(teacher["user_id"]), "hard71 hidden elective")
    student_headers = login_api(client, str(student["username"]), str(student["password"]))

    visible = client.get("/api/notifications?page_size=100", headers=student_headers)
    assert visible.status_code == 200, visible.text
    assert notification_id not in {row["id"] for row in visible.json()["data"]}
    r = client.post(f"/api/notifications/{notification_id}/read", headers=student_headers)

    assert r.status_code == 403
    assert _notification_read_count(notification_id, _user_id_for_username(str(student["username"]))) == 0


def test_hard72_mark_all_read_only_creates_read_rows_for_visible_notifications(client: TestClient):
    teacher = _create_teacher("notif_mark_all_teacher")
    class_id = _create_class("security-notif-mark-all")
    student = _extra_student_account_for_class(class_id, "notif_mark_all_student")
    peer = _extra_student_account_for_class(class_id, "notif_mark_all_peer")
    required_subject = _create_subject("Notification mark all required", int(teacher["user_id"]), class_id)
    elective_subject = _create_subject("Notification mark all elective", int(teacher["user_id"]), class_id, "elective")
    _enroll_student(required_subject, int(student["student_id"]), class_id)
    visible_general = _create_notification(required_subject, class_id, int(teacher["user_id"]), "hard72 visible general")
    visible_target = _create_notification(
        required_subject,
        class_id,
        int(teacher["user_id"]),
        "hard72 visible target",
        target_student_id=int(student["student_id"]),
    )
    hidden_target = _create_notification(
        required_subject,
        class_id,
        int(teacher["user_id"]),
        "hard72 hidden peer target",
        target_student_id=int(peer["student_id"]),
    )
    hidden_elective = _create_notification(elective_subject, class_id, int(teacher["user_id"]), "hard72 hidden elective")
    student_headers = login_api(client, str(student["username"]), str(student["password"]))

    r = client.post("/api/notifications/mark-all-read", headers=student_headers)

    assert r.status_code == 200, r.text
    user_id = _user_id_for_username(str(student["username"]))
    assert _notification_read_count(visible_general, user_id) == 1
    assert _notification_read_count(visible_target, user_id) == 1
    assert _notification_read_count(hidden_target, user_id) == 0
    assert _notification_read_count(hidden_elective, user_id) == 0


def test_hard73_parent_code_rate_limit_isolated_per_code(client: TestClient):
    class_id = _create_class("security-parent-rate-isolated")
    student_id = _extra_student_for_class(class_id, "parent_rate_isolated")
    valid_code = _set_parent_code(student_id, "HARD73OK")
    for _ in range(30):
        r = client.get("/api/parent/verify/HARD73NO")
        assert r.status_code == 200

    bad_limited = client.get("/api/parent/verify/HARD73NO")
    assert bad_limited.status_code == 429
    good = client.get(f"/api/parent/verify/{valid_code}")
    assert good.status_code == 200
    assert good.json()["valid"] is True


def test_hard74_parent_student_endpoint_rate_limits_repeated_invalid_code(client: TestClient):
    for _ in range(30):
        r = client.get("/api/parent/student/HARD74NO")
        assert r.status_code == 404

    limited = client.get("/api/parent/student/HARD74NO")

    assert limited.status_code == 429


def test_hard75_batch_parent_code_generation_deduplicates_student_ids(client: TestClient):
    teacher = _create_teacher("parent_batch_dedup")
    class_id = _create_class("security-parent-batch-dedup")
    student_id = _extra_student_for_class(class_id, "parent_batch_dedup")
    subject_id = _create_subject("Parent batch dedup course", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, student_id, class_id)
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.post("/api/parent/students/batch-generate-codes", headers=headers, json=[student_id, student_id])

    assert r.status_code == 200, r.text
    assert r.json()["generated_count"] == 1
    assert [row["student_id"] for row in r.json()["students"]] == [student_id]


def test_hard76_class_teacher_batch_generation_stays_direct_class_only_with_duplicates(client: TestClient):
    teacher = _create_teacher("parent_batch_ct_teacher")
    ct = _create_class_teacher("parent_batch_ct")
    own_student_id = _extra_student_for_class(int(ct["class_id"]), "parent_batch_ct_own")
    foreign_class_id = _create_class("security-parent-batch-ct-foreign")
    foreign_student_id = _extra_student_for_class(foreign_class_id, "parent_batch_ct_foreign")
    subject_id = _create_subject("Parent ct foreign visible course", int(teacher["user_id"]), foreign_class_id)
    _enroll_student(subject_id, foreign_student_id, foreign_class_id)
    db = SessionLocal()
    try:
        db.add(
            SubjectClassLink(
                subject_id=subject_id,
                class_id=int(ct["class_id"]),
                enrollment_mode="all_in_class",
            )
        )
        db.commit()
    finally:
        db.close()
    headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.post(
        "/api/parent/students/batch-generate-codes",
        headers=headers,
        json=[own_student_id, foreign_student_id, own_student_id],
    )

    assert r.status_code == 200, r.text
    assert r.json()["generated_count"] == 1
    assert [row["student_id"] for row in r.json()["students"]] == [own_student_id]
    assert _parent_code_for_student(foreign_student_id) is None


def test_hard77_student_course_scoped_notifications_exclude_foreign_class_broadcast(client: TestClient):
    teacher = _create_teacher("notif_subject_class_scope")
    own_class_id = _create_class("security-notif-subject-scope-own")
    foreign_class_id = _create_class("security-notif-subject-scope-foreign")
    student = _extra_student_account_for_class(own_class_id, "notif_subject_scope_student")
    subject_id = _create_subject("Notification subject class scope", int(teacher["user_id"]), own_class_id)
    _enroll_student(subject_id, int(student["student_id"]), own_class_id)
    visible = _create_notification(None, own_class_id, int(teacher["user_id"]), "hard77 own class broadcast")
    hidden = _create_notification(None, foreign_class_id, int(teacher["user_id"]), "hard77 foreign class broadcast")
    headers = login_api(client, str(student["username"]), str(student["password"]))

    r = client.get(f"/api/notifications?subject_id={subject_id}&page_size=100", headers=headers)

    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["data"]}
    assert visible in ids
    assert hidden not in ids


def test_hard78_student_course_scoped_sync_status_excludes_foreign_class_broadcast(client: TestClient):
    teacher = _create_teacher("notif_subject_sync_scope")
    own_class_id = _create_class("security-notif-subject-sync-own")
    foreign_class_id = _create_class("security-notif-subject-sync-foreign")
    student = _extra_student_account_for_class(own_class_id, "notif_subject_sync_student")
    subject_id = _create_subject("Notification subject sync scope", int(teacher["user_id"]), own_class_id)
    _enroll_student(subject_id, int(student["student_id"]), own_class_id)
    _create_notification(None, own_class_id, int(teacher["user_id"]), "hard78 own class broadcast")
    _create_notification(None, foreign_class_id, int(teacher["user_id"]), "hard78 foreign class broadcast")
    headers = login_api(client, str(student["username"]), str(student["password"]))

    sync = client.get(f"/api/notifications/sync-status?subject_id={subject_id}", headers=headers)

    assert sync.status_code == 200, sync.text
    assert sync.json()["total"] == 1
    assert sync.json()["unread_count"] == 1


def test_hard79_student_subject_mark_all_read_does_not_mark_foreign_class_broadcast(client: TestClient):
    teacher = _create_teacher("notif_subject_mark_scope")
    own_class_id = _create_class("security-notif-subject-mark-own")
    foreign_class_id = _create_class("security-notif-subject-mark-foreign")
    student = _extra_student_account_for_class(own_class_id, "notif_subject_mark_student")
    subject_id = _create_subject("Notification subject mark scope", int(teacher["user_id"]), own_class_id)
    _enroll_student(subject_id, int(student["student_id"]), own_class_id)
    visible = _create_notification(None, own_class_id, int(teacher["user_id"]), "hard79 own class broadcast")
    hidden = _create_notification(None, foreign_class_id, int(teacher["user_id"]), "hard79 foreign class broadcast")
    headers = login_api(client, str(student["username"]), str(student["password"]))
    user_id = _user_id_for_username(str(student["username"]))

    r = client.post(f"/api/notifications/mark-all-read?subject_id={subject_id}", headers=headers)

    assert r.status_code == 200, r.text
    assert _notification_read_count(visible, user_id) == 1
    assert _notification_read_count(hidden, user_id) == 0


def test_hard80_teacher_course_scoped_notifications_exclude_unrelated_class_broadcast(client: TestClient):
    teacher = _create_teacher("notif_teacher_subject_scope")
    own_class_id = _create_class("security-notif-teacher-subject-own")
    foreign_class_id = _create_class("security-notif-teacher-subject-foreign")
    subject_id = _create_subject("Notification teacher subject scope", int(teacher["user_id"]), own_class_id)
    visible = _create_notification(None, own_class_id, int(teacher["user_id"]), "hard80 own class broadcast")
    hidden = _create_notification(None, foreign_class_id, int(teacher["user_id"]), "hard80 foreign class broadcast")
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.get(f"/api/notifications?subject_id={subject_id}&page_size=100", headers=headers)

    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["data"]}
    assert visible in ids
    assert hidden not in ids


def test_hard81_teacher_subject_mark_all_read_does_not_mark_unrelated_class_broadcast(client: TestClient):
    teacher = _create_teacher("notif_teacher_mark_scope")
    own_class_id = _create_class("security-notif-teacher-mark-own")
    foreign_class_id = _create_class("security-notif-teacher-mark-foreign")
    subject_id = _create_subject("Notification teacher mark scope", int(teacher["user_id"]), own_class_id)
    visible = _create_notification(None, own_class_id, int(teacher["user_id"]), "hard81 own class broadcast")
    hidden = _create_notification(None, foreign_class_id, int(teacher["user_id"]), "hard81 foreign class broadcast")
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.post(f"/api/notifications/mark-all-read?subject_id={subject_id}", headers=headers)

    assert r.status_code == 200, r.text
    assert _notification_read_count(visible, int(teacher["user_id"])) == 1
    assert _notification_read_count(hidden, int(teacher["user_id"])) == 0


def test_hard82_student_course_scoped_notifications_keep_global_and_own_class_broadcasts(client: TestClient):
    teacher = _create_teacher("notif_subject_global_scope")
    class_id = _create_class("security-notif-subject-global")
    student = _extra_student_account_for_class(class_id, "notif_subject_global_student")
    subject_id = _create_subject("Notification subject global scope", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    own = _create_notification(None, class_id, int(teacher["user_id"]), "hard82 own class broadcast")
    global_notice = _create_notification(None, None, int(teacher["user_id"]), "hard82 global broadcast")
    subject_notice = _create_notification(subject_id, class_id, int(teacher["user_id"]), "hard82 subject notice")
    headers = login_api(client, str(student["username"]), str(student["password"]))

    r = client.get(f"/api/notifications?subject_id={subject_id}&page_size=100", headers=headers)

    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["data"]}
    assert {own, global_notice, subject_notice}.issubset(ids)


def test_hard83_student_course_scoped_notifications_still_hide_peer_target_broadcast(client: TestClient):
    teacher = _create_teacher("notif_subject_peer_target")
    class_id = _create_class("security-notif-subject-peer-target")
    student = _extra_student_account_for_class(class_id, "notif_subject_peer_student")
    peer = _extra_student_account_for_class(class_id, "notif_subject_peer_peer")
    subject_id = _create_subject("Notification subject peer target", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    _enroll_student(subject_id, int(peer["student_id"]), class_id)
    visible = _create_notification(None, class_id, int(teacher["user_id"]), "hard83 own class broadcast")
    hidden = _create_notification(
        None,
        class_id,
        int(teacher["user_id"]),
        "hard83 peer target broadcast",
        target_student_id=int(peer["student_id"]),
    )
    headers = login_api(client, str(student["username"]), str(student["password"]))

    r = client.get(f"/api/notifications?subject_id={subject_id}&page_size=100", headers=headers)

    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["data"]}
    assert visible in ids
    assert hidden not in ids


def test_hard84_student_subject_list_and_detail_agree_on_foreign_class_broadcast_denial(client: TestClient):
    teacher = _create_teacher("notif_subject_detail_scope")
    own_class_id = _create_class("security-notif-subject-detail-own")
    foreign_class_id = _create_class("security-notif-subject-detail-foreign")
    student = _extra_student_account_for_class(own_class_id, "notif_subject_detail_student")
    subject_id = _create_subject("Notification subject detail scope", int(teacher["user_id"]), own_class_id)
    _enroll_student(subject_id, int(student["student_id"]), own_class_id)
    hidden = _create_notification(None, foreign_class_id, int(teacher["user_id"]), "hard84 foreign class broadcast")
    headers = login_api(client, str(student["username"]), str(student["password"]))

    listed = client.get(f"/api/notifications?subject_id={subject_id}&page_size=100", headers=headers)
    detail = client.get(f"/api/notifications/{hidden}", headers=headers)

    assert listed.status_code == 200, listed.text
    assert hidden not in {row["id"] for row in listed.json()["data"]}
    assert detail.status_code == 403


def test_hard85_student_course_scope_excludes_other_linked_class_broadcast(client: TestClient):
    teacher = _create_teacher("notif_multiclass_student")
    own_class_id = _create_class("security-notif-multiclass-own")
    other_class_id = _create_class("security-notif-multiclass-other")
    student = _extra_student_account_for_class(own_class_id, "notif_multiclass_student")
    subject_id = _create_subject("Notification multiclass student", int(teacher["user_id"]), own_class_id)
    db = SessionLocal()
    try:
        db.add(SubjectClassLink(subject_id=subject_id, class_id=other_class_id, enrollment_mode="all_in_class"))
        db.commit()
    finally:
        db.close()
    _enroll_student(subject_id, int(student["student_id"]), own_class_id)
    visible = _create_notification(None, own_class_id, int(teacher["user_id"]), "hard85 own linked class broadcast")
    hidden = _create_notification(None, other_class_id, int(teacher["user_id"]), "hard85 other linked class broadcast")
    headers = login_api(client, str(student["username"]), str(student["password"]))

    listed = client.get(f"/api/notifications?subject_id={subject_id}&page_size=100", headers=headers)
    sync = client.get(f"/api/notifications/sync-status?subject_id={subject_id}", headers=headers)

    assert listed.status_code == 200, listed.text
    ids = {row["id"] for row in listed.json()["data"]}
    assert visible in ids
    assert hidden not in ids
    assert sync.status_code == 200, sync.text
    assert sync.json()["total"] == 1
    assert sync.json()["unread_count"] == 1


def test_hard86_student_mark_all_read_subject_scope_skips_other_linked_class_broadcast(client: TestClient):
    teacher = _create_teacher("notif_multiclass_mark")
    own_class_id = _create_class("security-notif-multiclass-mark-own")
    other_class_id = _create_class("security-notif-multiclass-mark-other")
    student = _extra_student_account_for_class(own_class_id, "notif_multiclass_mark_student")
    subject_id = _create_subject("Notification multiclass mark", int(teacher["user_id"]), own_class_id)
    db = SessionLocal()
    try:
        db.add(SubjectClassLink(subject_id=subject_id, class_id=other_class_id, enrollment_mode="all_in_class"))
        db.commit()
    finally:
        db.close()
    _enroll_student(subject_id, int(student["student_id"]), own_class_id)
    visible = _create_notification(None, own_class_id, int(teacher["user_id"]), "hard86 own linked class broadcast")
    hidden = _create_notification(None, other_class_id, int(teacher["user_id"]), "hard86 other linked class broadcast")
    headers = login_api(client, str(student["username"]), str(student["password"]))
    user_id = _user_id_for_username(str(student["username"]))

    marked = client.post(f"/api/notifications/mark-all-read?subject_id={subject_id}", headers=headers)

    assert marked.status_code == 200, marked.text
    assert _notification_read_count(visible, user_id) == 1
    assert _notification_read_count(hidden, user_id) == 0


def test_hard87_student_unscoped_notifications_exclude_other_linked_class_broadcast(client: TestClient):
    teacher = _create_teacher("notif_multiclass_unscoped")
    own_class_id = _create_class("security-notif-multiclass-unscoped-own")
    other_class_id = _create_class("security-notif-multiclass-unscoped-other")
    student = _extra_student_account_for_class(own_class_id, "notif_multiclass_unscoped_student")
    subject_id = _create_subject("Notification multiclass unscoped", int(teacher["user_id"]), own_class_id)
    db = SessionLocal()
    try:
        db.add(SubjectClassLink(subject_id=subject_id, class_id=other_class_id, enrollment_mode="all_in_class"))
        db.commit()
    finally:
        db.close()
    _enroll_student(subject_id, int(student["student_id"]), own_class_id)
    visible = _create_notification(None, own_class_id, int(teacher["user_id"]), "hard87 own class unscoped")
    hidden = _create_notification(None, other_class_id, int(teacher["user_id"]), "hard87 other linked class unscoped")
    headers = login_api(client, str(student["username"]), str(student["password"]))

    listed = client.get("/api/notifications?page_size=100", headers=headers)

    assert listed.status_code == 200, listed.text
    ids = {row["id"] for row in listed.json()["data"]}
    assert visible in ids
    assert hidden not in ids


def test_hard88_student_subject_notification_with_other_linked_class_id_is_hidden(client: TestClient):
    teacher = _create_teacher("notif_multiclass_subject_row")
    own_class_id = _create_class("security-notif-multiclass-subject-own")
    other_class_id = _create_class("security-notif-multiclass-subject-other")
    student = _extra_student_account_for_class(own_class_id, "notif_multiclass_subject_student")
    subject_id = _create_subject("Notification multiclass subject row", int(teacher["user_id"]), own_class_id)
    db = SessionLocal()
    try:
        db.add(SubjectClassLink(subject_id=subject_id, class_id=other_class_id, enrollment_mode="all_in_class"))
        db.commit()
    finally:
        db.close()
    _enroll_student(subject_id, int(student["student_id"]), own_class_id)
    visible = _create_notification(subject_id, own_class_id, int(teacher["user_id"]), "hard88 own class subject row")
    hidden = _create_notification(subject_id, other_class_id, int(teacher["user_id"]), "hard88 other class subject row")
    headers = login_api(client, str(student["username"]), str(student["password"]))

    listed = client.get(f"/api/notifications?subject_id={subject_id}&page_size=100", headers=headers)
    detail = client.get(f"/api/notifications/{hidden}", headers=headers)

    assert listed.status_code == 200, listed.text
    ids = {row["id"] for row in listed.json()["data"]}
    assert visible in ids
    assert hidden not in ids
    assert detail.status_code == 403


def test_hard89_class_teacher_course_scope_excludes_other_linked_class_broadcast(client: TestClient):
    teacher = _create_teacher("notif_multiclass_ct_teacher")
    own_class_id = _create_class("security-notif-multiclass-ct-own")
    other_class_id = _create_class("security-notif-multiclass-ct-other")
    ct = _create_class_teacher_for_class(own_class_id, "notif_multiclass_ct")
    subject_id = _create_subject("Notification multiclass class teacher", int(teacher["user_id"]), own_class_id)
    db = SessionLocal()
    try:
        db.add(SubjectClassLink(subject_id=subject_id, class_id=other_class_id, enrollment_mode="all_in_class"))
        db.commit()
    finally:
        db.close()
    visible = _create_notification(None, own_class_id, int(teacher["user_id"]), "hard89 own linked class broadcast")
    hidden = _create_notification(None, other_class_id, int(teacher["user_id"]), "hard89 other linked class broadcast")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))

    listed = client.get(f"/api/notifications?subject_id={subject_id}&page_size=100", headers=headers)
    sync = client.get(f"/api/notifications/sync-status?subject_id={subject_id}", headers=headers)

    assert listed.status_code == 200, listed.text
    ids = {row["id"] for row in listed.json()["data"]}
    assert visible in ids
    assert hidden not in ids
    assert sync.status_code == 200, sync.text
    assert sync.json()["total"] == 1


def test_hard90_admin_course_scope_keeps_all_linked_class_broadcasts(client: TestClient):
    ensure_admin()
    teacher = _create_teacher("notif_multiclass_admin_teacher")
    own_class_id = _create_class("security-notif-multiclass-admin-own")
    other_class_id = _create_class("security-notif-multiclass-admin-other")
    subject_id = _create_subject("Notification multiclass admin", int(teacher["user_id"]), own_class_id)
    db = SessionLocal()
    try:
        db.add(SubjectClassLink(subject_id=subject_id, class_id=other_class_id, enrollment_mode="all_in_class"))
        db.commit()
    finally:
        db.close()
    first = _create_notification(None, own_class_id, int(teacher["user_id"]), "hard90 own linked class broadcast")
    second = _create_notification(None, other_class_id, int(teacher["user_id"]), "hard90 other linked class broadcast")
    headers = login_api(client, "pytest_admin", "pytest_admin_pass")

    listed = client.get(f"/api/notifications?subject_id={subject_id}&page_size=100", headers=headers)

    assert listed.status_code == 200, listed.text
    ids = {row["id"] for row in listed.json()["data"]}
    assert {first, second}.issubset(ids)


def test_hard91_assigned_teacher_course_scope_keeps_all_linked_class_broadcasts(client: TestClient):
    teacher = _create_teacher("notif_multiclass_teacher")
    own_class_id = _create_class("security-notif-multiclass-teacher-own")
    other_class_id = _create_class("security-notif-multiclass-teacher-other")
    subject_id = _create_subject("Notification multiclass assigned teacher", int(teacher["user_id"]), own_class_id)
    db = SessionLocal()
    try:
        db.add(SubjectClassLink(subject_id=subject_id, class_id=other_class_id, enrollment_mode="all_in_class"))
        db.commit()
    finally:
        db.close()
    first = _create_notification(None, own_class_id, int(teacher["user_id"]), "hard91 own linked class broadcast")
    second = _create_notification(None, other_class_id, int(teacher["user_id"]), "hard91 other linked class broadcast")
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    listed = client.get(f"/api/notifications?subject_id={subject_id}&page_size=100", headers=headers)
    sync = client.get(f"/api/notifications/sync-status?subject_id={subject_id}", headers=headers)

    assert listed.status_code == 200, listed.text
    ids = {row["id"] for row in listed.json()["data"]}
    assert {first, second}.issubset(ids)
    assert sync.status_code == 200, sync.text
    assert sync.json()["total"] == 2


def test_hard92_regular_teacher_cannot_create_global_unscoped_notification(client: TestClient):
    teacher = _create_teacher("notif_global_create_teacher")
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))
    before = _notification_count_for_subject(None)

    r = client.post(
        "/api/notifications",
        headers=headers,
        json={
            "title": "hard92 teacher global broadcast",
            "content": "global broadcast should be admin-only",
            "class_id": None,
            "subject_id": None,
        },
    )

    assert r.status_code == 403
    assert _notification_count_for_subject(None) == before


def test_hard93_class_teacher_cannot_create_global_unscoped_notification(client: TestClient):
    ct = _create_class_teacher("notif_global_create_ct")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    before = _notification_count_for_subject(None)

    r = client.post(
        "/api/notifications",
        headers=headers,
        json={
            "title": "hard93 class teacher global broadcast",
            "content": "class teacher global broadcast should be admin-only",
            "class_id": None,
            "subject_id": None,
        },
    )

    assert r.status_code == 403
    assert _notification_count_for_subject(None) == before


def test_hard94_admin_can_create_global_unscoped_notification_visible_to_all_roles(client: TestClient):
    ensure_admin()
    teacher = _create_teacher("notif_global_admin_teacher")
    class_id = _create_class("security-notif-global-admin-class")
    student = _extra_student_account_for_class(class_id, "notif_global_admin_student")
    student_headers = login_api(client, str(student["username"]), str(student["password"]))
    teacher_headers = login_api(client, str(teacher["username"]), str(teacher["password"]))
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")

    created = client.post(
        "/api/notifications",
        headers=admin_headers,
        json={
            "title": "hard94 admin global broadcast",
            "content": "admin global broadcast",
            "class_id": None,
            "subject_id": None,
        },
    )

    assert created.status_code == 200, created.text
    notification_id = created.json()["id"]
    assert _notification_scope(notification_id)[:2] == (None, None)
    for headers in (student_headers, teacher_headers, admin_headers):
        listed = client.get("/api/notifications?page_size=100", headers=headers)
        assert listed.status_code == 200, listed.text
        assert notification_id in {row["id"] for row in listed.json()["data"]}


def test_hard95_teacher_cannot_update_class_notification_into_global_broadcast(client: TestClient):
    teacher = _create_teacher("notif_global_update_teacher")
    class_id = _create_class("security-notif-global-update")
    notification_id = _create_notification(None, class_id, int(teacher["user_id"]), "hard95 class notice")
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"class_id": 0, "subject_id": None, "title": "hard95 widened global notice"},
    )

    assert r.status_code == 403
    assert _notification_scope(notification_id)[:2] == (None, class_id)


def test_hard96_class_teacher_cannot_update_direct_class_notification_into_global_broadcast(client: TestClient):
    ct = _create_class_teacher("notif_ct_to_global")
    class_id = int(ct["class_id"])
    notification_id = _create_notification(None, class_id, int(ct["user_id"]), "hard96 class teacher notice")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"class_id": 0, "title": "hard96 widened global notice"},
    )

    assert r.status_code == 403
    assert _notification_scope(notification_id)[:2] == (None, class_id)


def test_hard97_admin_can_update_owned_or_foreign_notice_into_global_broadcast(client: TestClient):
    ensure_admin()
    teacher = _create_teacher("notif_admin_global_update_teacher")
    class_id = _create_class("security-notif-admin-global-update")
    notification_id = _create_notification(None, class_id, int(teacher["user_id"]), "hard97 class notice")
    headers = login_api(client, "pytest_admin", "pytest_admin_pass")

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"class_id": 0, "subject_id": None, "title": "hard97 admin global notice"},
    )

    assert r.status_code == 200, r.text
    assert _notification_scope(notification_id)[:2] == (None, None)


def test_hard98_teacher_global_broadcast_attempt_does_not_inflate_unrelated_student_sync(client: TestClient):
    teacher = _create_teacher("notif_global_inflate_teacher")
    target_class_id = _create_class("security-notif-global-inflate-target")
    other_class_id = _create_class("security-notif-global-inflate-other")
    target_student = _extra_student_account_for_class(target_class_id, "notif_global_inflate_target")
    other_student = _extra_student_account_for_class(other_class_id, "notif_global_inflate_other")
    target_subject_id = _create_subject("Notification global inflate target", int(teacher["user_id"]), target_class_id)
    _enroll_student(target_subject_id, int(target_student["student_id"]), target_class_id)
    other_headers = login_api(client, str(other_student["username"]), str(other_student["password"]))
    teacher_headers = login_api(client, str(teacher["username"]), str(teacher["password"]))
    before = client.get("/api/notifications/sync-status", headers=other_headers)
    assert before.status_code == 200, before.text

    r = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={
            "title": "hard98 attempted global",
            "content": "must not reach unrelated student",
            "class_id": None,
            "subject_id": None,
        },
    )
    after = client.get("/api/notifications/sync-status", headers=other_headers)

    assert r.status_code == 403
    assert after.status_code == 200, after.text
    assert after.json()["unread_count"] == before.json()["unread_count"]
    assert after.json()["total"] == before.json()["total"]


def test_hard99_teacher_cannot_create_global_target_user_notification_for_other_teacher(client: TestClient):
    owner = _create_teacher("notif_global_target_owner")
    other = _create_teacher("notif_global_target_other")
    owner_headers = login_api(client, str(owner["username"]), str(owner["password"]))
    other_headers = login_api(client, str(other["username"]), str(other["password"]))
    before = client.get("/api/notifications/sync-status", headers=other_headers)
    assert before.status_code == 200, before.text

    r = client.post(
        "/api/notifications",
        headers=owner_headers,
        json={
            "title": "hard99 target other teacher",
            "content": "teacher must not inject another teacher's global inbox",
            "class_id": None,
            "subject_id": None,
            "target_user_id": int(other["user_id"]),
        },
    )
    after = client.get("/api/notifications/sync-status", headers=other_headers)

    assert r.status_code == 403
    assert after.status_code == 200, after.text
    assert after.json()["unread_count"] == before.json()["unread_count"]
    assert after.json()["total"] == before.json()["total"]


def test_hard100_admin_password_reset_kind_is_admin_only_in_global_list(client: TestClient):
    ensure_admin()
    teacher = _create_teacher("notif_password_reset_hidden_teacher")
    teacher_headers = login_api(client, str(teacher["username"]), str(teacher["password"]))
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    db = SessionLocal()
    try:
        row = Notification(
            title="hard100 reset request",
            content="reserved system notification",
            content_format="plain",
            priority="normal",
            class_id=None,
            subject_id=None,
            target_user_id=int(teacher["user_id"]),
            notification_kind="password_reset_request",
            created_by=1,
        )
        db.add(row)
        db.commit()
        notification_id = int(row.id)
    finally:
        db.close()

    teacher_list = client.get("/api/notifications?page_size=100", headers=teacher_headers)
    teacher_detail = client.get(f"/api/notifications/{notification_id}", headers=teacher_headers)
    admin_list = client.get("/api/notifications?page_size=100", headers=admin_headers)

    assert teacher_list.status_code == 200, teacher_list.text
    assert notification_id not in {row["id"] for row in teacher_list.json()["data"]}
    assert teacher_detail.status_code == 403
    assert admin_list.status_code == 200, admin_list.text
    assert notification_id in {row["id"] for row in admin_list.json()["data"]}


def test_hard101_teacher_cannot_update_general_notice_to_password_reset_kind(client: TestClient):
    teacher = _create_teacher("notif_kind_update_teacher")
    class_id = _create_class("security-notif-kind-update")
    notification_id = _create_notification(None, class_id, int(teacher["user_id"]), "hard101 class notice")
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"notification_kind": "password_reset_request"},
    )

    assert r.status_code == 403
    assert _notification_kind(notification_id) != "password_reset_request"


def test_hard102_teacher_cannot_create_course_notification_for_unenrolled_target_student(client: TestClient):
    teacher = _create_teacher("notif_target_unenrolled_teacher")
    class_id = _create_class("security-notif-target-unenrolled")
    enrolled_student = _extra_student_account_for_class(class_id, "notif_target_enrolled")
    unenrolled_student = _extra_student_account_for_class(class_id, "notif_target_unenrolled")
    subject_id = _create_subject("Notification target unenrolled", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(enrolled_student["student_id"]), class_id)
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))
    before = _notification_count_for_subject(subject_id)

    r = client.post(
        "/api/notifications",
        headers=headers,
        json={
            "title": "hard102 unenrolled target",
            "content": "must not store unenrolled target",
            "class_id": class_id,
            "subject_id": subject_id,
            "target_student_id": int(unenrolled_student["student_id"]),
        },
    )

    assert r.status_code == 400
    assert _notification_count_for_subject(subject_id) == before


def test_hard103_teacher_can_create_course_notification_for_enrolled_target_student(client: TestClient):
    teacher = _create_teacher("notif_target_enrolled_teacher")
    class_id = _create_class("security-notif-target-enrolled")
    student = _extra_student_account_for_class(class_id, "notif_target_enrolled_ok")
    subject_id = _create_subject("Notification target enrolled", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.post(
        "/api/notifications",
        headers=headers,
        json={
            "title": "hard103 enrolled target",
            "content": "target is valid",
            "class_id": class_id,
            "subject_id": subject_id,
            "target_student_id": int(student["student_id"]),
        },
    )

    assert r.status_code == 200, r.text
    assert int(r.json()["target_student_id"]) == int(student["student_id"])


def test_hard104_teacher_cannot_target_student_from_different_class_on_class_notice(client: TestClient):
    teacher = _create_teacher("notif_target_foreign_class_teacher")
    own_class_id = _create_class("security-notif-target-own-class")
    other_class_id = _create_class("security-notif-target-other-class")
    other_student = _extra_student_account_for_class(other_class_id, "notif_target_other_class_student")
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))
    before = _notification_count_for_subject(None)

    r = client.post(
        "/api/notifications",
        headers=headers,
        json={
            "title": "hard104 foreign class target",
            "content": "target class mismatch",
            "class_id": own_class_id,
            "subject_id": None,
            "target_student_id": int(other_student["student_id"]),
        },
    )

    assert r.status_code == 400
    assert _notification_count_for_subject(None) == before


def test_hard105_admin_can_create_global_target_student_notification(client: TestClient):
    ensure_admin()
    class_id = _create_class("security-notif-admin-target-student")
    student = _extra_student_account_for_class(class_id, "notif_admin_global_target_student")
    headers = login_api(client, "pytest_admin", "pytest_admin_pass")

    r = client.post(
        "/api/notifications",
        headers=headers,
        json={
            "title": "hard105 admin target student",
            "content": "admin global student target",
            "class_id": None,
            "subject_id": None,
            "target_student_id": int(student["student_id"]),
        },
    )

    assert r.status_code == 200, r.text
    assert int(r.json()["target_student_id"]) == int(student["student_id"])


def test_hard106_teacher_cannot_target_other_teacher_user(client: TestClient):
    owner = _create_teacher("notif_target_user_owner")
    other = _create_teacher("notif_target_user_other")
    class_id = _create_class("security-notif-target-user")
    subject_id = _create_subject("Notification target user", int(owner["user_id"]), class_id)
    headers = login_api(client, str(owner["username"]), str(owner["password"]))
    before = _notification_count_for_subject(subject_id)

    r = client.post(
        "/api/notifications",
        headers=headers,
        json={
            "title": "hard106 other teacher target user",
            "content": "must not target other teacher",
            "class_id": class_id,
            "subject_id": subject_id,
            "target_user_id": int(other["user_id"]),
        },
    )

    assert r.status_code == 403
    assert _notification_count_for_subject(subject_id) == before


def test_hard107_teacher_can_target_self_user_on_owned_course_notification(client: TestClient):
    teacher = _create_teacher("notif_target_self_teacher")
    class_id = _create_class("security-notif-target-self")
    subject_id = _create_subject("Notification target self", int(teacher["user_id"]), class_id)
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.post(
        "/api/notifications",
        headers=headers,
        json={
            "title": "hard107 self target user",
            "content": "self target is valid",
            "class_id": class_id,
            "subject_id": subject_id,
            "target_user_id": int(teacher["user_id"]),
        },
    )

    assert r.status_code == 200, r.text
    assert _notification_scope(int(r.json()["id"]))[2] == int(teacher["user_id"])


def test_hard108_notification_cannot_target_student_and_user_together(client: TestClient):
    teacher = _create_teacher("notif_dual_target_teacher")
    class_id = _create_class("security-notif-dual-target")
    student = _extra_student_account_for_class(class_id, "notif_dual_target_student")
    subject_id = _create_subject("Notification dual target", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))
    before = _notification_count_for_subject(subject_id)

    r = client.post(
        "/api/notifications",
        headers=headers,
        json={
            "title": "hard108 dual target",
            "content": "cannot target both",
            "class_id": class_id,
            "subject_id": subject_id,
            "target_student_id": int(student["student_id"]),
            "target_user_id": int(teacher["user_id"]),
        },
    )

    assert r.status_code == 400
    assert _notification_count_for_subject(subject_id) == before


def test_hard109_teacher_cannot_update_notice_to_unenrolled_target_student(client: TestClient):
    teacher = _create_teacher("notif_update_unenrolled_teacher")
    class_id = _create_class("security-notif-update-unenrolled")
    enrolled_student = _extra_student_account_for_class(class_id, "notif_update_enrolled")
    unenrolled_student = _extra_student_account_for_class(class_id, "notif_update_unenrolled")
    subject_id = _create_subject("Notification update target unenrolled", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(enrolled_student["student_id"]), class_id)
    notification_id = _create_notification(subject_id, class_id, int(teacher["user_id"]), "hard109 course notice")
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"target_student_id": int(unenrolled_student["student_id"])},
    )

    assert r.status_code == 400
    assert _notification_target_student_id(notification_id) is None


def test_hard110_teacher_cannot_update_notice_to_other_teacher_target_user(client: TestClient):
    owner = _create_teacher("notif_update_target_owner")
    other = _create_teacher("notif_update_target_other")
    class_id = _create_class("security-notif-update-target-user")
    subject_id = _create_subject("Notification update target user", int(owner["user_id"]), class_id)
    notification_id = _create_notification(subject_id, class_id, int(owner["user_id"]), "hard110 course notice")
    headers = login_api(client, str(owner["username"]), str(owner["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"target_user_id": int(other["user_id"])},
    )

    assert r.status_code == 403
    assert _notification_scope(notification_id)[2] is None


def test_hard111_admin_can_update_notice_to_valid_target_student(client: TestClient):
    ensure_admin()
    teacher = _create_teacher("notif_admin_update_target_teacher")
    class_id = _create_class("security-notif-admin-update-target")
    student = _extra_student_account_for_class(class_id, "notif_admin_update_target_student")
    subject_id = _create_subject("Notification admin update target", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    notification_id = _create_notification(subject_id, class_id, int(teacher["user_id"]), "hard111 course notice")
    headers = login_api(client, "pytest_admin", "pytest_admin_pass")

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"target_student_id": int(student["student_id"])},
    )

    assert r.status_code == 200, r.text
    assert _notification_target_student_id(notification_id) == int(student["student_id"])


def test_hard112_teacher_cannot_create_null_subject_class_zero_notification(client: TestClient):
    teacher = _create_teacher("notif_create_class_zero_teacher")
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))
    before = _notification_count_for_subject(None)

    r = client.post(
        "/api/notifications",
        headers=headers,
        json={
            "title": "hard112 class zero create",
            "content": "class zero should not bypass global write guard",
            "class_id": 0,
            "subject_id": None,
        },
    )

    assert r.status_code == 403
    assert _notification_count_for_subject(None) == before


def test_hard113_teacher_can_explicitly_clear_target_student_without_widening_outside_course(
    client: TestClient,
):
    teacher = _create_teacher("notif_clear_student_teacher")
    class_id = _create_class("security-notif-clear-student")
    student = _extra_student_account_for_class(class_id, "notif_clear_student")
    other_class_id = _create_class("security-notif-clear-student-other")
    other_student = _extra_student_account_for_class(other_class_id, "notif_clear_student_other")
    subject_id = _create_subject("Notification clear student target", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    notification_id = _create_notification(
        subject_id,
        class_id,
        int(teacher["user_id"]),
        "hard113 clear target student",
        target_student_id=int(student["student_id"]),
    )
    teacher_headers = login_api(client, str(teacher["username"]), str(teacher["password"]))
    student_headers = login_api(client, str(student["username"]), str(student["password"]))
    other_headers = login_api(client, str(other_student["username"]), str(other_student["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=teacher_headers,
        json={"target_student_id": None},
    )
    student_list = client.get(f"/api/notifications?subject_id={subject_id}&page_size=100", headers=student_headers)
    other_list = client.get("/api/notifications?page_size=100", headers=other_headers)

    assert r.status_code == 200, r.text
    assert r.json()["target_student_id"] is None
    assert _notification_target_student_id(notification_id) is None
    assert notification_id in {row["id"] for row in student_list.json()["data"]}
    assert notification_id not in {row["id"] for row in other_list.json()["data"]}


def test_hard114_teacher_cannot_switch_student_target_to_self_user_without_clearing_student_first(
    client: TestClient,
):
    teacher = _create_teacher("notif_switch_student_user_teacher")
    class_id = _create_class("security-notif-switch-student-user")
    student = _extra_student_account_for_class(class_id, "notif_switch_student_user")
    subject_id = _create_subject("Notification switch student to user", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    notification_id = _create_notification(
        subject_id,
        class_id,
        int(teacher["user_id"]),
        "hard114 student to self user",
        target_student_id=int(student["student_id"]),
    )
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"target_user_id": int(teacher["user_id"])},
    )

    assert r.status_code == 400
    assert _notification_target_student_id(notification_id) == int(student["student_id"])
    assert _notification_scope(notification_id)[2] is None


def test_hard115_teacher_can_switch_student_target_to_self_user_after_explicit_clear(client: TestClient):
    teacher = _create_teacher("notif_switch_after_clear_teacher")
    class_id = _create_class("security-notif-switch-after-clear")
    student = _extra_student_account_for_class(class_id, "notif_switch_after_clear_student")
    subject_id = _create_subject("Notification switch after clear", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    notification_id = _create_notification(
        subject_id,
        class_id,
        int(teacher["user_id"]),
        "hard115 switch after clear",
        target_student_id=int(student["student_id"]),
    )
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"target_student_id": None, "target_user_id": int(teacher["user_id"])},
    )

    assert r.status_code == 200, r.text
    assert r.json()["target_student_id"] is None
    assert int(r.json()["target_user_id"]) == int(teacher["user_id"])
    assert _notification_target_student_id(notification_id) is None
    assert _notification_scope(notification_id)[2] == int(teacher["user_id"])


def test_hard116_teacher_cannot_switch_self_user_target_to_student_without_clearing_user_first(
    client: TestClient,
):
    teacher = _create_teacher("notif_switch_user_student_teacher")
    class_id = _create_class("security-notif-switch-user-student")
    student = _extra_student_account_for_class(class_id, "notif_switch_user_student")
    subject_id = _create_subject("Notification switch user to student", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    notification_id = _create_notification(
        subject_id,
        class_id,
        int(teacher["user_id"]),
        "hard116 self user to student",
        target_user_id=int(teacher["user_id"]),
    )
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"target_student_id": int(student["student_id"])},
    )

    assert r.status_code == 400
    assert _notification_scope(notification_id)[2] == int(teacher["user_id"])
    assert _notification_target_student_id(notification_id) is None


def test_hard117_teacher_can_switch_self_user_target_to_student_after_explicit_clear(client: TestClient):
    teacher = _create_teacher("notif_switch_user_clear_teacher")
    class_id = _create_class("security-notif-switch-user-clear")
    student = _extra_student_account_for_class(class_id, "notif_switch_user_clear_student")
    subject_id = _create_subject("Notification switch user clear", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    notification_id = _create_notification(
        subject_id,
        class_id,
        int(teacher["user_id"]),
        "hard117 user clear to student",
        target_user_id=int(teacher["user_id"]),
    )
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"target_user_id": None, "target_student_id": int(student["student_id"])},
    )

    assert r.status_code == 200, r.text
    assert int(r.json()["target_student_id"]) == int(student["student_id"])
    assert r.json()["target_user_id"] is None
    assert _notification_scope(notification_id)[2] is None
    assert _notification_target_student_id(notification_id) == int(student["student_id"])


def test_hard118_teacher_cannot_clear_subject_and_class_to_global_while_clearing_target(
    client: TestClient,
):
    teacher = _create_teacher("notif_clear_scope_target_teacher")
    class_id = _create_class("security-notif-clear-scope-target")
    student = _extra_student_account_for_class(class_id, "notif_clear_scope_target_student")
    subject_id = _create_subject("Notification clear scope target", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    notification_id = _create_notification(
        subject_id,
        class_id,
        int(teacher["user_id"]),
        "hard118 clear to global",
        target_student_id=int(student["student_id"]),
    )
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"subject_id": None, "class_id": 0, "target_student_id": None},
    )

    assert r.status_code == 403
    assert _notification_scope(notification_id)[:2] == (subject_id, class_id)
    assert _notification_target_student_id(notification_id) == int(student["student_id"])


def test_hard119_admin_can_clear_subject_class_and_targets_to_global_notice(client: TestClient):
    ensure_admin()
    teacher = _create_teacher("notif_admin_clear_all_teacher")
    class_id = _create_class("security-notif-admin-clear-all")
    student = _extra_student_account_for_class(class_id, "notif_admin_clear_all_student")
    subject_id = _create_subject("Notification admin clear all", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    notification_id = _create_notification(
        subject_id,
        class_id,
        int(teacher["user_id"]),
        "hard119 admin clear all",
        target_student_id=int(student["student_id"]),
    )
    headers = login_api(client, "pytest_admin", "pytest_admin_pass")

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"subject_id": None, "class_id": 0, "target_student_id": None},
    )

    assert r.status_code == 200, r.text
    assert _notification_scope(notification_id)[:2] == (None, None)
    assert _notification_target_student_id(notification_id) is None


def test_hard120_admin_can_clear_target_user_from_system_password_reset_notice(client: TestClient):
    ensure_admin()
    teacher = _create_teacher("notif_admin_clear_reset_target")
    db = SessionLocal()
    try:
        row = Notification(
            title="hard120 reset target user",
            content="system reset notice",
            content_format="plain",
            priority="important",
            class_id=None,
            subject_id=None,
            target_user_id=int(teacher["user_id"]),
            notification_kind="password_reset_request",
            created_by=1,
        )
        db.add(row)
        db.commit()
        notification_id = int(row.id)
    finally:
        db.close()
    headers = login_api(client, "pytest_admin", "pytest_admin_pass")

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"target_user_id": None},
    )

    assert r.status_code == 200, r.text
    assert _notification_scope(notification_id)[2] is None


def test_hard121_homework_grade_system_notification_normalizes_dual_targets_on_existing_row():
    from apps.backend.courseeval_backend.domains.homework.notifications import upsert_homework_grade_notification

    teacher = _create_teacher("notif_grade_system_teacher")
    class_id = _create_class("security-notif-grade-system")
    student = _extra_student_account_for_class(class_id, "notif_grade_system_student")
    other = _create_teacher("notif_grade_system_other")
    subject_id = _create_subject("Notification grade system", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    db = SessionLocal()
    try:
        homework = Homework(
            title="hard121 graded homework",
            content="grade notice",
            class_id=class_id,
            subject_id=subject_id,
            max_score=100,
            created_by=int(teacher["user_id"]),
        )
        db.add(homework)
        db.flush()
        student_row = db.query(Student).filter(Student.id == int(student["student_id"])).one()
        stale = Notification(
            title="hard121 stale",
            content="stale",
            class_id=class_id,
            subject_id=subject_id,
            target_student_id=None,
            target_user_id=int(other["user_id"]),
            related_homework_id=homework.id,
            related_student_id=student_row.id,
            notification_kind="grade_complete",
            created_by=int(teacher["user_id"]),
        )
        db.add(stale)
        db.commit()

        updated = upsert_homework_grade_notification(
            db,
            homework=homework,
            student=student_row,
            score=95,
            comment="ok",
            source_label="manual",
            created_by_user_id=int(teacher["user_id"]),
        )
        db.commit()
        db.refresh(updated)

        assert int(updated.target_student_id) == int(student["student_id"])
        assert updated.target_user_id is None
        assert int(updated.related_homework_id) == int(homework.id)
    finally:
        db.close()


def test_hard122_homework_appeal_system_notification_targets_teacher_users_only():
    from apps.backend.courseeval_backend.domains.homework.appeals import notify_teachers_grade_appeal

    teacher = _create_teacher("notif_appeal_system_teacher")
    class_id = _create_class("security-notif-appeal-system")
    student = _extra_student_account_for_class(class_id, "notif_appeal_system_student")
    subject_id = _create_subject("Notification appeal system", int(teacher["user_id"]), class_id)
    _enroll_student(subject_id, int(student["student_id"]), class_id)
    db = SessionLocal()
    try:
        homework = Homework(
            title="hard122 appeal homework",
            content="appeal",
            class_id=class_id,
            subject_id=subject_id,
            max_score=100,
            created_by=int(teacher["user_id"]),
        )
        db.add(homework)
        db.flush()
        submission = HomeworkSubmission(
            homework_id=homework.id,
            student_id=int(student["student_id"]),
            subject_id=subject_id,
            class_id=class_id,
            content="appeal submission",
            content_format="plain",
        )
        db.add(submission)
        db.flush()
        appeal = HomeworkGradeAppeal(
            homework_id=homework.id,
            student_id=int(student["student_id"]),
            submission_id=submission.id,
            reason_text="appeal reason with enough length",
            status="pending",
        )
        db.add(appeal)
        db.commit()
        db.refresh(homework)
        db.refresh(appeal)

        rows = notify_teachers_grade_appeal(
            db,
            appeal=appeal,
            homework=homework,
            student_name="Appeal Student",
            creator_user_id=int(student["student_id"]),
        )
        db.commit()
        assert rows
        for row in rows:
            db.refresh(row)
            assert row.target_student_id is None
            assert row.target_user_id is not None
            assert int(row.subject_id) == subject_id
            assert int(row.class_id) == class_id
            assert row.notification_kind == "grade_appeal"
    finally:
        db.close()


def test_hard123_teacher_can_publish_course_notification_to_linked_secondary_class(client: TestClient):
    teacher = _create_teacher("notif_multiclass_publish_teacher")
    primary_class_id = _create_class("security-notif-multiclass-primary")
    linked_class_id = _create_class("security-notif-multiclass-linked")
    subject_id = _create_subject("Notification multiclass publish", int(teacher["user_id"]), primary_class_id)
    db = SessionLocal()
    try:
        db.add(
            SubjectClassLink(
                subject_id=subject_id,
                class_id=linked_class_id,
                enrollment_mode="all_in_class",
            )
        )
        db.commit()
    finally:
        db.close()

    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.post(
        "/api/notifications",
        headers=headers,
        json={
            "title": "hard123 linked class publish",
            "content": "course teacher should be able to target any linked class on the course",
            "class_id": linked_class_id,
            "subject_id": subject_id,
        },
    )

    assert r.status_code == 200, r.text
    assert _notification_scope(int(r.json()["id"]))[:2] == (subject_id, linked_class_id)


def test_hard124_teacher_can_retarget_course_notification_to_linked_secondary_class(client: TestClient):
    teacher = _create_teacher("notif_multiclass_retarget_teacher")
    primary_class_id = _create_class("security-notif-multiclass-retarget-primary")
    linked_class_id = _create_class("security-notif-multiclass-retarget-linked")
    subject_id = _create_subject("Notification multiclass retarget", int(teacher["user_id"]), primary_class_id)
    db = SessionLocal()
    try:
        db.add(
            SubjectClassLink(
                subject_id=subject_id,
                class_id=linked_class_id,
                enrollment_mode="all_in_class",
            )
        )
        db.commit()
    finally:
        db.close()

    notification_id = _create_notification(
        subject_id,
        primary_class_id,
        int(teacher["user_id"]),
        "hard124 linked class retarget",
    )
    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.put(
        f"/api/notifications/{notification_id}",
        headers=headers,
        json={"class_id": linked_class_id},
    )

    assert r.status_code == 200, r.text
    assert _notification_scope(notification_id)[:2] == (subject_id, linked_class_id)


def test_hard125_teacher_can_create_attendance_for_linked_secondary_class_course(client: TestClient):
    teacher = _create_teacher("attendance_multiclass_create_teacher")
    primary_class_id = _create_class("security-attendance-multiclass-primary")
    linked_class_id = _create_class("security-attendance-multiclass-linked")
    student_id = _extra_student_for_class(linked_class_id, "attendance_multiclass_linked_student")
    subject_id = _create_subject("Attendance multiclass create", int(teacher["user_id"]), primary_class_id)
    db = SessionLocal()
    try:
        db.add(
            SubjectClassLink(
                subject_id=subject_id,
                class_id=linked_class_id,
                enrollment_mode="all_in_class",
            )
        )
        db.commit()
    finally:
        db.close()

    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.post(
        "/api/attendance",
        headers=headers,
        json={
            "student_id": student_id,
            "class_id": linked_class_id,
            "subject_id": subject_id,
            "date": "2026-05-14T09:00:00Z",
            "status": "present",
            "remark": "hard125 linked class attendance",
        },
    )

    assert r.status_code == 200, r.text
    assert _attendance_count_for_subject(subject_id) == 1


def test_hard126_teacher_can_create_homework_for_linked_secondary_class_course(client: TestClient):
    teacher = _create_teacher("homework_multiclass_create_teacher")
    primary_class_id = _create_class("security-homework-multiclass-primary")
    linked_class_id = _create_class("security-homework-multiclass-linked")
    subject_id = _create_subject("Homework multiclass create", int(teacher["user_id"]), primary_class_id)
    db = SessionLocal()
    try:
        db.add(
            SubjectClassLink(
                subject_id=subject_id,
                class_id=linked_class_id,
                enrollment_mode="all_in_class",
            )
        )
        db.commit()
    finally:
        db.close()

    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.post(
        "/api/homeworks",
        headers=headers,
        json={
            "title": "hard126 linked class homework",
            "content": "course teacher should be able to create homework for any linked class on the course",
            "class_id": linked_class_id,
            "subject_id": subject_id,
            "max_score": 100,
            "auto_grading_enabled": False,
        },
    )

    assert r.status_code == 200, r.text
    assert int(r.json()["subject_id"]) == subject_id
    assert int(r.json()["class_id"]) == linked_class_id


def test_hard127_teacher_can_class_batch_attendance_for_linked_secondary_class_course(client: TestClient):
    teacher = _create_teacher("attendance_multiclass_batch_teacher")
    primary_class_id = _create_class("security-attendance-batch-multiclass-primary")
    linked_class_id = _create_class("security-attendance-batch-multiclass-linked")
    _extra_student_for_class(linked_class_id, "attendance_multiclass_batch_student")
    subject_id = _create_subject("Attendance multiclass batch", int(teacher["user_id"]), primary_class_id)
    db = SessionLocal()
    try:
        db.add(
            SubjectClassLink(
                subject_id=subject_id,
                class_id=linked_class_id,
                enrollment_mode="all_in_class",
            )
        )
        db.commit()
    finally:
        db.close()

    headers = login_api(client, str(teacher["username"]), str(teacher["password"]))

    r = client.post(
        "/api/attendance/class-batch",
        headers=headers,
        json={
            "class_id": linked_class_id,
            "subject_id": subject_id,
            "date": "2026-05-14T10:00:00Z",
            "status": "late",
            "remark": "hard127 linked class batch attendance",
        },
    )

    assert r.status_code == 200, r.text
    assert r.json()["success"] >= 1
    assert r.json()["failed"] == 0


def test_hard128_class_teacher_cannot_update_teacher_owned_visible_homework(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher("ct_homework_update_visible")
    subject_id = _create_visible_teacher_owned_course(client, ctx, ct, "ct visible homework update guard")
    homework_id = _create_course_homework(subject_id, int(ct["class_id"]), ctx["teacher_id"], "ct update forbidden homework")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.put(
        f"/api/homeworks/{homework_id}",
        headers=headers,
        json={"title": "ct should not update this homework"},
    )

    assert r.status_code == 403


def test_hard129_class_teacher_cannot_delete_teacher_owned_visible_homework(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher("ct_homework_delete_visible")
    subject_id = _create_visible_teacher_owned_course(client, ctx, ct, "ct visible homework delete guard")
    homework_id = _create_course_homework(subject_id, int(ct["class_id"]), ctx["teacher_id"], "ct delete forbidden homework")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.delete(f"/api/homeworks/{homework_id}", headers=headers)

    assert r.status_code == 403


def test_hard130_linked_secondary_class_homework_remains_readable_after_create(client: TestClient):
    teacher = _create_teacher("homework_multiclass_read_teacher")
    primary_class_id = _create_class("security-homework-multiclass-read-primary")
    linked_class_id = _create_class("security-homework-multiclass-read-linked")
    student = _extra_student_account_for_class(linked_class_id, "homework_multiclass_read_student")
    subject_id = _create_subject("Homework multiclass read", int(teacher["user_id"]), primary_class_id)
    _enroll_student(subject_id, int(student["student_id"]), linked_class_id)
    db = SessionLocal()
    try:
        db.add(
            SubjectClassLink(
                subject_id=subject_id,
                class_id=linked_class_id,
                enrollment_mode="all_in_class",
            )
        )
        db.commit()
    finally:
        db.close()

    teacher_headers = login_api(client, str(teacher["username"]), str(teacher["password"]))
    created = client.post(
        "/api/homeworks",
        headers=teacher_headers,
        json={
            "title": "hard130 linked class readable homework",
            "content": "this homework should remain readable after creation",
            "class_id": linked_class_id,
            "subject_id": subject_id,
            "max_score": 100,
            "auto_grading_enabled": False,
        },
    )
    assert created.status_code == 200, created.text
    homework_id = int(created.json()["id"])

    teacher_detail = client.get(f"/api/homeworks/{homework_id}", headers=teacher_headers)
    student_headers = login_api(client, str(student["username"]), str(student["password"]))
    student_detail = client.get(f"/api/homeworks/{homework_id}", headers=student_headers)

    assert teacher_detail.status_code == 200, teacher_detail.text
    assert student_detail.status_code == 200, student_detail.text


def test_hard131_class_teacher_cannot_review_teacher_owned_visible_homework_submission(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_review_visible")
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    submission = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "hard131 submission"},
    )
    assert submission.status_code == 200, submission.text
    submission_id = int(submission.json()["id"])

    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    r = client.put(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{submission_id}/review",
        headers=headers,
        json={"review_score": 95, "review_comment": "ct should not review"},
    )

    assert r.status_code == 403


def test_hard132_class_teacher_cannot_regrade_teacher_owned_visible_homework_submission(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=True, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_regrade_visible")
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    submission = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "hard132 submission"},
    )
    assert submission.status_code == 200, submission.text
    submission_id = int(submission.json()["id"])

    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{submission_id}/regrade",
        headers=headers,
        json={},
    )

    assert r.status_code == 403


def test_hard133_class_teacher_cannot_batch_update_teacher_owned_visible_homework_policy(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher("ct_homework_batch_policy_visible")
    subject_id = _create_visible_teacher_owned_course(client, ctx, ct, "ct visible homework batch policy guard")
    homework_id = _create_course_homework(subject_id, int(ct["class_id"]), ctx["teacher_id"], "ct batch policy forbidden homework")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.post(
        "/api/homeworks/batch-late-submission",
        headers=headers,
        json={
            "homework_ids": [homework_id],
            "allow_late_submission": True,
            "late_submission_affects_score": False,
        },
    )

    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 0
    assert homework_id in r.json()["forbidden_ids"]


def test_hard134_class_teacher_cannot_list_teacher_owned_visible_homework_submissions(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_list_visible")
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    submission = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "hard134 submission"},
    )
    assert submission.status_code == 200, submission.text

    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    r = client.get(f"/api/homeworks/{ctx['homework_id']}/submissions", headers=headers)

    assert r.status_code == 403


def test_hard135_class_teacher_cannot_read_teacher_owned_visible_homework_submission_status(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_status_visible")
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    submission = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "hard135 submission"},
    )
    assert submission.status_code == 200, submission.text
    submission_id = int(submission.json()["id"])

    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    r = client.get(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{submission_id}/status",
        headers=headers,
    )

    assert r.status_code == 403


def test_hard136_class_teacher_cannot_read_teacher_owned_visible_homework_submission_history(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_history_visible")
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    submission = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "hard136 submission"},
    )
    assert submission.status_code == 200, submission.text
    submission_id = int(submission.json()["id"])

    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    r = client.get(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{submission_id}/history",
        headers=headers,
    )

    assert r.status_code == 403


def test_hard137_class_teacher_cannot_acknowledge_teacher_owned_visible_homework_appeal(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_appeal_ack_visible")
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    submission = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "hard137 submission"},
    )
    assert submission.status_code == 200, submission.text
    submission_id = int(submission.json()["id"])

    review = client.put(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{submission_id}/review",
        headers=teacher_headers,
        json={"review_score": 88, "review_comment": "teacher-reviewed before appeal"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{submission_id}/appeal",
        headers=student_headers,
        json={"reason_text": "hard137 appeal reason long enough for submission"},
    )
    assert appeal.status_code == 200, appeal.text

    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{submission_id}/appeal/acknowledge",
        headers=headers,
    )

    assert r.status_code == 403

    db = SessionLocal()
    try:
        row = db.query(HomeworkGradeAppeal).filter(HomeworkGradeAppeal.submission_id == submission_id).first()
        assert row is not None
        assert row.status == "pending"
    finally:
        db.close()


def test_hard138_class_teacher_cannot_download_teacher_owned_visible_homework_submissions(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_download_visible")
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    submission = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "hard138 submission"},
    )
    assert submission.status_code == 200, submission.text
    submission_id = int(submission.json()["id"])

    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submissions/download",
        headers=headers,
        json={"submission_ids": [submission_id]},
    )

    assert r.status_code == 403


def test_hard139_class_teacher_cannot_list_teacher_owned_visible_course_students_for_homework_status(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_course_students_visible")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.get(f"/api/homeworks/courses/{ctx['subject_id']}/students", headers=headers)

    assert r.status_code == 403


def test_hard140_class_teacher_cannot_list_teacher_owned_visible_student_homeworks_for_course(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_student_rows_visible")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.get(
        f"/api/homeworks/courses/{ctx['subject_id']}/students/{ctx['student_id']}/homeworks",
        headers=headers,
    )

    assert r.status_code == 403


def test_hard141_class_teacher_cannot_batch_regrade_teacher_owned_visible_homework_submissions(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=True, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_batch_regrade_visible")
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    submission = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "hard141 submission"},
    )
    assert submission.status_code == 200, submission.text
    submission_id = int(submission.json()["id"])

    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    r = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submissions/batch-regrade",
        headers=headers,
        json={"submission_ids": [submission_id], "only_latest_attempt": True},
    )

    assert r.status_code == 403


def test_hard142_class_teacher_cannot_respond_to_teacher_owned_visible_homework_appeal(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_appeal_resolve_visible")
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    submission = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "hard142 submission"},
    )
    assert submission.status_code == 200, submission.text
    submission_id = int(submission.json()["id"])

    review = client.put(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{submission_id}/review",
        headers=teacher_headers,
        json={"review_score": 86, "review_comment": "teacher-reviewed before hard142 appeal"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{submission_id}/appeal",
        headers=student_headers,
        json={"reason_text": "hard142 appeal reason long enough for submission"},
    )
    assert appeal.status_code == 200, appeal.text

    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    r = client.put(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{submission_id}/appeal",
        headers=headers,
        json={"teacher_response": "ct should not resolve", "status": "resolved"},
    )

    assert r.status_code == 403

    db = SessionLocal()
    try:
        row = db.query(HomeworkGradeAppeal).filter(HomeworkGradeAppeal.submission_id == submission_id).first()
        assert row is not None
        assert row.status == "pending"
        assert not row.teacher_response
    finally:
        db.close()


def test_hard143_class_teacher_cannot_create_teacher_owned_visible_material_chapter(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_material_chapter_create_visible")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))

    r = client.post(
        f"/api/material-chapters?subject_id={ctx['subject_id']}",
        headers=headers,
        json={"title": "hard143 forbidden chapter", "parent_id": None},
    )

    assert r.status_code == 403


def test_hard144_class_teacher_cannot_update_teacher_owned_visible_material_chapter(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_material_chapter_update_visible")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    chapter_id = _create_chapter(ctx["subject_id"], "hard144 original chapter")

    r = client.put(
        f"/api/material-chapters/{chapter_id}",
        headers=headers,
        json={"title": "hard144 forbidden rename"},
    )

    assert r.status_code == 403


def test_hard145_class_teacher_cannot_delete_teacher_owned_visible_material_chapter(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_material_chapter_delete_visible")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    chapter_id = _create_chapter(ctx["subject_id"], "hard145 delete chapter")

    r = client.delete(f"/api/material-chapters/{chapter_id}", headers=headers)

    assert r.status_code == 403


def test_hard146_class_teacher_cannot_remove_teacher_owned_visible_material_placement(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_material_placement_delete_visible")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    chapter_id = _create_chapter(ctx["subject_id"], "hard146 placement chapter")
    material_id, section_id = _create_material_section(ctx["subject_id"], ctx["class_id"], ctx["teacher_id"], chapter_id)

    r = client.delete(
        f"/api/material-chapters/placements/{section_id}?subject_id={ctx['subject_id']}",
        headers=headers,
    )

    assert r.status_code == 403
    assert _material_section_count(material_id) == 1


def test_hard147_class_teacher_cannot_remove_teacher_owned_visible_homework_link(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    ct = _create_class_teacher_for_class(ctx["class_id"], "ct_homework_link_delete_visible")
    headers = login_api(client, str(ct["username"]), str(ct["password"]))
    chapter_id = _create_chapter(ctx["subject_id"], "hard147 homework link chapter")
    homework_id = _create_course_homework(ctx["subject_id"], ctx["class_id"], ctx["teacher_id"], "hard147 linked homework")

    db = SessionLocal()
    try:
        link = CourseMaterialHomeworkLink(
            chapter_id=chapter_id,
            homework_id=homework_id,
            sort_order=0,
        )
        db.add(link)
        db.commit()
        link_id = int(link.id)
    finally:
        db.close()

    r = client.delete(
        f"/api/material-chapters/homework-links/{link_id}?subject_id={ctx['subject_id']}",
        headers=headers,
    )

    assert r.status_code == 403
    assert _homework_link_count(chapter_id) == 1
