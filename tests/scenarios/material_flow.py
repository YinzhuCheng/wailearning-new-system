"""Factories and UI-shaped API helpers for material chapter integration tests."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import Class, CourseEnrollment, CourseMaterialChapter, Student, Subject, SubjectClassLink, User, UserRole
from tests.scenarios.llm_scenario import login_api


def make_subject_with_roster(
    *,
    assign_subject_teacher: bool = True,
    enroll_student: bool = True,
) -> dict[str, Any]:
    """Minimal class + subject + teacher + student (+ enrollment)."""
    uid = uuid.uuid4().hex[:10]
    db = SessionLocal()
    try:
        klass = Class(name=f"mat-class-{uid}", grade=2026)
        db.add(klass)
        db.flush()

        teacher = User(
            username=f"mat_teach_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="Mat Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()

        stu_u = f"mat_stu_{uid}"
        su = User(
            username=stu_u,
            hashed_password=get_password_hash("sp"),
            real_name="Mat Student",
            role=UserRole.STUDENT.value,
            class_id=klass.id,
        )
        db.add(su)
        db.flush()

        stud = Student(name="Mat Student", student_no=stu_u, class_id=klass.id)
        db.add(stud)
        db.flush()

        course = Subject(
            name=f"mat-course-{uid}",
            teacher_id=(teacher.id if assign_subject_teacher else None),
            class_id=klass.id,
        )
        db.add(course)
        db.flush()
        db.add(
            SubjectClassLink(
                subject_id=course.id,
                class_id=klass.id,
                enrollment_mode="all_in_class",
            )
        )

        if enroll_student:
            db.add(
                CourseEnrollment(
                    subject_id=course.id,
                    student_id=stud.id,
                    class_id=klass.id,
                    enrollment_type="required",
                )
            )

        db.commit()
        db.refresh(course)
        db.refresh(klass)
        # Mirror bootstrap backfill: uncategorized bucket must exist before chapter tree queries.
        unc = (
            db.query(CourseMaterialChapter)
            .filter(
                CourseMaterialChapter.subject_id == course.id,
                CourseMaterialChapter.is_uncategorized.is_(True),
            )
            .first()
        )
        if not unc:
            unc = CourseMaterialChapter(
                subject_id=course.id,
                parent_id=None,
                title="未分类",
                sort_order=0,
                is_uncategorized=True,
            )
            db.add(unc)
            db.commit()
        return {
            "uid": uid,
            "class_id": klass.id,
            "subject_id": course.id,
            "teacher_id": teacher.id,
            "teacher_username": teacher.username,
            "teacher_password": "tp",
            "student_id": stud.id,
            "student_username": stu_u,
            "student_password": "sp",
        }
    finally:
        db.close()


def ensure_class_teacher_same_class(class_id: int, *, username_suffix: str | None = None) -> dict[str, Any]:
    """Class teacher user in the same class (not necessarily subject teacher)."""
    suf = username_suffix or uuid.uuid4().hex[:6]
    db = SessionLocal()
    try:
        u = User(
            username=f"mat_ct_{suf}",
            hashed_password=get_password_hash("cp"),
            real_name="Class Teacher",
            role=UserRole.CLASS_TEACHER.value,
            class_id=class_id,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return {"username": u.username, "password": "cp", "user_id": u.id}
    finally:
        db.close()


def ensure_foreign_teacher() -> dict[str, Any]:
    """Another teacher user not tied to our subject (no course creation here)."""
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        t = User(
            username=f"mat_foreign_{uid}",
            hashed_password=get_password_hash("fp"),
            real_name="Foreign",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        return {"username": t.username, "password": "fp", "user_id": t.id}
    finally:
        db.close()


def get_uncategorized_id(subject_id: int) -> int:
    db = SessionLocal()
    try:
        row = (
            db.query(CourseMaterialChapter)
            .filter(
                CourseMaterialChapter.subject_id == subject_id,
                CourseMaterialChapter.is_uncategorized.is_(True),
            )
            .first()
        )
        assert row is not None
        return row.id
    finally:
        db.close()


# --- UI-shaped HTTP sequences (same paths the SPA calls) ---


def ui_chapter_tree(client: TestClient, headers: dict[str, str], subject_id: int):
    return client.get("/api/material-chapters/tree", headers=headers, params={"subject_id": subject_id})


def ui_create_chapter(client: TestClient, headers: dict[str, str], subject_id: int, title: str, parent_id: int | None):
    return client.post(
        f"/api/material-chapters?subject_id={subject_id}",
        headers=headers,
        json={"title": title, "parent_id": parent_id},
    )


def ui_reorder_chapters(client: TestClient, headers: dict[str, str], subject_id: int, parent_id: int | None, ids: list[int]):
    return client.post(
        f"/api/material-chapters/reorder?subject_id={subject_id}",
        headers=headers,
        json={"parent_id": parent_id, "ordered_chapter_ids": ids},
    )


def ui_add_homework_link(
    client: TestClient,
    headers: dict[str, str],
    subject_id: int,
    chapter_id: int,
    homework_id: int,
):
    return client.post(
        f"/api/material-chapters/homework-links?subject_id={subject_id}",
        headers=headers,
        json={"chapter_id": chapter_id, "homework_id": homework_id},
    )


def ui_remove_homework_link(client: TestClient, headers: dict[str, str], subject_id: int, link_id: int):
    return client.delete(
        f"/api/material-chapters/homework-links/{link_id}?subject_id={subject_id}",
        headers=headers,
    )


def ui_materials_list(
    client: TestClient,
    headers: dict[str, str],
    *,
    class_id: int,
    subject_id: int,
    chapter_id: int | None = None,
):
    params: dict[str, Any] = {"class_id": class_id, "subject_id": subject_id, "page": 1, "page_size": 100}
    if chapter_id is not None:
        params["chapter_id"] = chapter_id
    return client.get("/api/materials", headers=headers, params=params)


def ui_create_material(
    client: TestClient,
    headers: dict[str, str],
    *,
    class_id: int,
    subject_id: int,
    title: str,
    content: str | None = None,
    chapter_ids: list[int] | None = None,
):
    body: dict[str, Any] = {
        "title": title,
        "content": content,
        "class_id": class_id,
        "subject_id": subject_id,
    }
    if chapter_ids is not None:
        body["chapter_ids"] = chapter_ids
    return client.post("/api/materials", headers=headers, json=body)


def ui_update_material(
    client: TestClient,
    headers: dict[str, str],
    material_id: int,
    payload: dict[str, Any],
):
    return client.put(f"/api/materials/{material_id}", headers=headers, json=payload)


def ui_notification_sync(client: TestClient, headers: dict[str, str], subject_id: int):
    return client.get("/api/notifications/sync-status", headers=headers, params={"subject_id": subject_id})


def ui_notifications_list(client: TestClient, headers: dict[str, str], subject_id: int):
    return client.get("/api/notifications", headers=headers, params={"subject_id": subject_id, "page": 1, "page_size": 50})


def headers_for(client: TestClient, username: str, password: str) -> dict[str, str]:
    return login_api(client, username, password)
