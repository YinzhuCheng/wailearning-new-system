from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseDiscussionEntry,
    CourseEnrollment,
    CourseMaterial,
    Homework,
    LearningNote,
    LearningNoteDiscussionEntry,
    Student,
    Subject,
    User,
    UserRole,
)
from tests.scenarios.llm_scenario import login_api


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    yield
    SessionLocal().close()


@pytest.fixture
def client() -> TestClient:
    from apps.backend.courseeval_backend.main import app

    return TestClient(app)


def _scenario() -> dict:
    uid = uuid.uuid4().hex[:8]
    now = datetime(2026, 5, 11, 8, 0, tzinfo=timezone.utc)
    db = SessionLocal()
    try:
        class_a = Class(name=f"rp-class-a-{uid}", grade=2026)
        class_b = Class(name=f"rp-class-b-{uid}", grade=2026)
        db.add_all([class_a, class_b])
        db.flush()

        admin = User(
            username=f"rp_admin_{uid}",
            hashed_password=get_password_hash("pass"),
            real_name="Recent Admin",
            role=UserRole.ADMIN.value,
        )
        teacher = User(
            username=f"rp_teacher_{uid}",
            hashed_password=get_password_hash("pass"),
            real_name="Recent Teacher",
            role=UserRole.TEACHER.value,
        )
        author = User(
            username=f"rp_author_{uid}",
            hashed_password=get_password_hash("pass"),
            real_name="Recent Author",
            role=UserRole.STUDENT.value,
            class_id=class_a.id,
        )
        same_course = User(
            username=f"rp_same_{uid}",
            hashed_password=get_password_hash("pass"),
            real_name="Recent Same",
            role=UserRole.STUDENT.value,
            class_id=class_a.id,
        )
        outsider = User(
            username=f"rp_out_{uid}",
            hashed_password=get_password_hash("pass"),
            real_name="Recent Outsider",
            role=UserRole.STUDENT.value,
            class_id=class_b.id,
        )
        db.add_all([admin, teacher, author, same_course, outsider])
        db.flush()

        author_student = Student(name="Recent Author", student_no=author.username, class_id=class_a.id)
        same_student = Student(name="Recent Same", student_no=same_course.username, class_id=class_a.id)
        out_student = Student(name="Recent Outsider", student_no=outsider.username, class_id=class_b.id)
        db.add_all([author_student, same_student, out_student])
        db.flush()
        author.student_id = author_student.id
        same_course.student_id = same_student.id
        outsider.student_id = out_student.id

        course = Subject(name=f"rp-course-{uid}", teacher_id=teacher.id, class_id=class_a.id, course_type="required")
        other_course = Subject(name=f"rp-other-{uid}", teacher_id=teacher.id, class_id=class_b.id, course_type="required")
        db.add_all([course, other_course])
        db.flush()
        db.add_all(
            [
                CourseEnrollment(
                    subject_id=course.id,
                    student_id=author_student.id,
                    class_id=class_a.id,
                    enrollment_type="required",
                ),
                CourseEnrollment(
                    subject_id=course.id,
                    student_id=same_student.id,
                    class_id=class_a.id,
                    enrollment_type="required",
                ),
                CourseEnrollment(
                    subject_id=other_course.id,
                    student_id=out_student.id,
                    class_id=class_b.id,
                    enrollment_type="required",
                ),
            ]
        )

        material = CourseMaterial(
            title="Published material",
            content="material **body**",
            content_format="markdown",
            attachment_name="source.txt",
            attachment_url="/uploads/source.txt",
            class_id=class_a.id,
            subject_id=course.id,
            created_by=author.id,
            created_at=now + timedelta(minutes=4),
        )
        db.add(material)
        db.flush()
        teacher_homework = Homework(
            title="Teacher homework",
            content="homework **instructions**",
            content_format="markdown",
            class_id=class_a.id,
            subject_id=course.id,
            due_date=now + timedelta(days=7),
            created_by=teacher.id,
            created_at=now + timedelta(minutes=10),
        )
        db.add(teacher_homework)
        db.flush()
        course_comment = CourseDiscussionEntry(
            target_type="material",
            target_id=material.id,
            subject_id=course.id,
            class_id=class_a.id,
            author_user_id=author.id,
            body="course discussion body",
            body_format="plain",
            message_kind="human",
            created_at=now + timedelta(minutes=1),
        )
        assistant_comment = CourseDiscussionEntry(
            target_type="material",
            target_id=material.id,
            subject_id=course.id,
            class_id=class_a.id,
            author_user_id=author.id,
            body="assistant body must be excluded",
            message_kind="llm_assistant",
            created_at=now + timedelta(minutes=6),
        )
        public_note = LearningNote(
            title="Public note",
            description="public note description",
            owner_user_id=author.id,
            subject_id=course.id,
            visibility="course",
            created_at=now + timedelta(minutes=3),
            updated_at=now + timedelta(minutes=3),
        )
        private_note = LearningNote(
            title="Private note",
            description="private note description",
            owner_user_id=author.id,
            subject_id=course.id,
            visibility="private",
            created_at=now + timedelta(minutes=5),
            updated_at=now + timedelta(minutes=5),
        )
        db.add_all([course_comment, assistant_comment, public_note, private_note])
        db.flush()
        note_comment = LearningNoteDiscussionEntry(
            note_id=public_note.id,
            author_user_id=author.id,
            body="note discussion body",
            body_format="markdown",
            message_kind="human",
            created_at=now + timedelta(minutes=2),
        )
        note_assistant = LearningNoteDiscussionEntry(
            note_id=public_note.id,
            author_user_id=author.id,
            body="note assistant body must be excluded",
            message_kind="llm_assistant",
            created_at=now + timedelta(minutes=7),
        )
        private_note_comment = LearningNoteDiscussionEntry(
            note_id=private_note.id,
            author_user_id=author.id,
            body="private note discussion body",
            message_kind="human",
            created_at=now + timedelta(minutes=8),
        )
        db.add_all([note_comment, note_assistant, private_note_comment])
        db.commit()
        return {
            "admin_username": admin.username,
            "teacher_username": teacher.username,
            "teacher_id": teacher.id,
            "author_username": author.username,
            "same_username": same_course.username,
            "outsider_username": outsider.username,
            "author_id": author.id,
            "course_comment_id": course_comment.id,
            "note_comment_id": note_comment.id,
            "material_id": material.id,
            "teacher_homework_id": teacher_homework.id,
            "course_id": course.id,
            "other_course_id": other_course.id,
            "public_note_id": public_note.id,
            "private_note_id": private_note.id,
            "private_note_comment_id": private_note_comment.id,
        }
    finally:
        db.close()


def _ids(response: dict) -> list[str]:
    return [row["id"] for row in response["data"]]


def _group_map(response: dict) -> dict[str, dict]:
    return {row["kind"]: row for row in response["groups"]}


def test_recent_posts_me_returns_visible_items_sorted_newest_first(client: TestClient):
    ctx = _scenario()
    author_headers = login_api(client, ctx["author_username"], "pass")

    resp = client.get("/api/recent-posts/me", headers=author_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["author"]["id"] == ctx["author_id"]
    assert _ids(data) == [
        f"learning-note-discussion:{1_000_000_000 + ctx['private_note_comment_id']}",
        f"learning-note:{ctx['private_note_id']}",
        f"course-material:{ctx['material_id']}",
        f"learning-note:{ctx['public_note_id']}",
        f"learning-note-discussion:{ctx['note_comment_id'] + 1_000_000_000}",
        f"course-discussion:{ctx['course_comment_id']}",
    ]
    assert all("assistant body" not in (row.get("body_preview") or "") for row in data["data"])


def test_recent_posts_kind_filter_returns_materials_only(client: TestClient):
    ctx = _scenario()
    author_headers = login_api(client, ctx["author_username"], "pass")

    resp = client.get("/api/recent-posts/me", headers=author_headers, params={"kind": "material"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["data"][0]["kind"] == "material"
    assert data["data"][0]["target"]["target_type"] == "material"
    assert data["data"][0]["has_attachment"] is True


def test_recent_posts_teacher_feed_includes_linkable_homeworks_and_courses(client: TestClient):
    ctx = _scenario()
    teacher_headers = login_api(client, ctx["teacher_username"], "pass")

    resp = client.get("/api/recent-posts/me", headers=teacher_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    ids = _ids(data)

    assert data["author"]["id"] == ctx["teacher_id"]
    assert f"homework:{ctx['teacher_homework_id']}" in ids
    assert f"course:{ctx['course_id']}" in ids
    assert f"course:{ctx['other_course_id']}" in ids
    homework = next(row for row in data["data"] if row["id"] == f"homework:{ctx['teacher_homework_id']}")
    assert homework["kind"] == "homework"
    assert homework["target"]["target_type"] == "homework"
    course = next(row for row in data["data"] if row["id"] == f"course:{ctx['course_id']}")
    assert course["kind"] == "course"
    assert course["target"]["target_type"] == "course"


def test_recent_posts_grouped_feed_returns_link_type_groups(client: TestClient):
    ctx = _scenario()
    teacher_headers = login_api(client, ctx["teacher_username"], "pass")

    resp = client.get("/api/recent-posts/me/grouped", headers=teacher_headers, params={"group_limit": 1})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    groups = _group_map(data)

    assert data["group_limit"] == 1
    assert [row["kind"] for row in data["groups"]] == ["course", "homework"]
    assert groups["course"]["label"] == "课程"
    assert groups["course"]["total"] == 2
    assert len(groups["course"]["data"]) == 1
    assert groups["course"]["data"][0]["target"]["target_type"] == "course"
    assert groups["homework"]["label"] == "作业"
    assert groups["homework"]["total"] == 1
    assert groups["homework"]["data"][0]["target"]["target_type"] == "homework"


def test_recent_posts_grouped_student_author_hides_empty_teacher_only_groups(client: TestClient):
    ctx = _scenario()
    author_headers = login_api(client, ctx["author_username"], "pass")

    resp = client.get("/api/recent-posts/me/grouped", headers=author_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert [row["kind"] for row in data["groups"]] == ["material", "note", "comment"]
    assert "course" not in _group_map(data)
    assert "homework" not in _group_map(data)


def test_recent_posts_homework_and_course_kind_filters(client: TestClient):
    ctx = _scenario()
    teacher_headers = login_api(client, ctx["teacher_username"], "pass")

    homework_resp = client.get("/api/recent-posts/me", headers=teacher_headers, params={"kind": "homework"})
    assert homework_resp.status_code == 200, homework_resp.text
    assert _ids(homework_resp.json()) == [f"homework:{ctx['teacher_homework_id']}"]

    course_resp = client.get("/api/recent-posts/me", headers=teacher_headers, params={"kind": "course"})
    assert course_resp.status_code == 200, course_resp.text
    assert set(_ids(course_resp.json())) == {f"course:{ctx['course_id']}", f"course:{ctx['other_course_id']}"}


def test_recent_posts_teacher_feed_filters_course_scoped_items_for_student_viewer(client: TestClient):
    ctx = _scenario()
    same_headers = login_api(client, ctx["same_username"], "pass")

    resp = client.get(f"/api/recent-posts/users/{ctx['teacher_id']}", headers=same_headers)
    assert resp.status_code == 200, resp.text
    ids = _ids(resp.json())

    assert f"homework:{ctx['teacher_homework_id']}" in ids
    assert f"course:{ctx['course_id']}" in ids
    assert f"course:{ctx['other_course_id']}" not in ids

    grouped = client.get(f"/api/recent-posts/users/{ctx['teacher_id']}/grouped", headers=same_headers)
    assert grouped.status_code == 200, grouped.text
    groups = _group_map(grouped.json())
    assert groups["course"]["total"] == 1
    assert groups["course"]["data"][0]["id"] == f"course:{ctx['course_id']}"
    assert groups["homework"]["total"] == 1


def test_recent_posts_teacher_feed_hidden_from_unenrolled_student(client: TestClient):
    ctx = _scenario()
    author_headers = login_api(client, ctx["author_username"], "pass")

    resp = client.get(f"/api/recent-posts/users/{ctx['teacher_id']}", headers=author_headers)
    assert resp.status_code == 200, resp.text
    ids = _ids(resp.json())

    assert f"homework:{ctx['teacher_homework_id']}" in ids
    assert f"course:{ctx['course_id']}" in ids
    assert f"course:{ctx['other_course_id']}" not in ids


def test_recent_posts_teacher_feed_empty_for_course_outsider(client: TestClient):
    ctx = _scenario()
    outsider_headers = login_api(client, ctx["outsider_username"], "pass")

    resp = client.get(f"/api/recent-posts/users/{ctx['teacher_id']}", headers=outsider_headers)
    assert resp.status_code == 200, resp.text
    ids = _ids(resp.json())

    assert f"homework:{ctx['teacher_homework_id']}" not in ids
    assert f"course:{ctx['course_id']}" not in ids
    assert f"course:{ctx['other_course_id']}" in ids


def test_recent_posts_other_user_silently_filters_inaccessible_items(client: TestClient):
    ctx = _scenario()
    same_headers = login_api(client, ctx["same_username"], "pass")

    resp = client.get(f"/api/recent-posts/users/{ctx['author_id']}", headers=same_headers)
    assert resp.status_code == 200, resp.text
    ids = _ids(resp.json())

    assert f"learning-note:{ctx['private_note_id']}" not in ids
    assert f"learning-note-discussion:{1_000_000_000 + ctx['note_comment_id']}" in ids
    assert f"course-material:{ctx['material_id']}" in ids
    assert f"course-discussion:{ctx['course_comment_id']}" in ids
    assert resp.json()["total"] == 4


def test_recent_posts_direct_url_for_outsider_returns_empty_feed(client: TestClient):
    ctx = _scenario()
    outsider_headers = login_api(client, ctx["outsider_username"], "pass")

    resp = client.get(f"/api/recent-posts/users/{ctx['author_id']}", headers=outsider_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["author"]["id"] == ctx["author_id"]
    assert data["total"] == 0
    assert data["data"] == []


def test_recent_posts_private_note_hidden_from_admin_when_normal_route_hides_it(client: TestClient):
    ctx = _scenario()
    admin_headers = login_api(client, ctx["admin_username"], "pass")

    feed = client.get(f"/api/recent-posts/users/{ctx['author_id']}", headers=admin_headers)
    assert feed.status_code == 200, feed.text
    ids = _ids(feed.json())
    assert f"learning-note:{ctx['private_note_id']}" not in ids

    normal_route = client.get(f"/api/learning-notes/{ctx['private_note_id']}", headers=admin_headers)
    assert normal_route.status_code == 403


def test_recent_posts_requires_auth_and_unknown_user_404(client: TestClient):
    ctx = _scenario()
    assert client.get("/api/recent-posts/me").status_code == 401
    headers = login_api(client, ctx["author_username"], "pass")
    missing = client.get("/api/recent-posts/users/999999", headers=headers)
    assert missing.status_code == 404
