"""Learning-note API regressions for visibility, copying, editing, and discussion.

These tests target a newer product surface that is easy to under-cover because it
looks similar to course materials while intentionally using note-owned tables.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseMaterial,
    CourseMaterialChapter,
    CourseMaterialSection,
    Attendance,
    LearningNoteDiscussionEntry,
    Student,
    Subject,
    User,
    UserRole,
)
from apps.backend.courseeval_backend.domains.discussion_links import LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET
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
    db = SessionLocal()
    try:
        c1 = Class(name=f"ln-class-a-{uid}", grade=2026)
        c2 = Class(name=f"ln-class-b-{uid}", grade=2026)
        db.add_all([c1, c2])
        db.flush()

        teacher = User(
            username=f"ln_teacher_{uid}",
            hashed_password=get_password_hash("pass"),
            real_name="Learning Note Teacher",
            role=UserRole.TEACHER.value,
        )
        same_student_user = User(
            username=f"ln_stu_same_{uid}",
            hashed_password=get_password_hash("pass"),
            real_name="Learning Note Same Student",
            role=UserRole.STUDENT.value,
            class_id=c1.id,
        )
        owner_user = User(
            username=f"ln_stu_owner_{uid}",
            hashed_password=get_password_hash("pass"),
            real_name="Learning Note Owner",
            role=UserRole.STUDENT.value,
            class_id=c1.id,
        )
        outsider_user = User(
            username=f"ln_stu_out_{uid}",
            hashed_password=get_password_hash("pass"),
            real_name="Learning Note Outsider",
            role=UserRole.STUDENT.value,
            class_id=c2.id,
        )
        db.add_all([teacher, same_student_user, owner_user, outsider_user])
        db.flush()

        owner_student = Student(name="Owner", student_no=owner_user.username, class_id=c1.id)
        same_student = Student(name="Same", student_no=same_student_user.username, class_id=c1.id)
        outsider_student = Student(name="Outsider", student_no=outsider_user.username, class_id=c2.id)
        db.add_all([owner_student, same_student, outsider_student])
        db.flush()

        course = Subject(name=f"ln-course-{uid}", teacher_id=teacher.id, class_id=c1.id, course_type="required")
        other_course = Subject(name=f"ln-other-{uid}", teacher_id=teacher.id, class_id=c2.id, course_type="required")
        db.add_all([course, other_course])
        db.flush()
        for student in (owner_student, same_student):
            db.add(
                CourseEnrollment(
                    subject_id=course.id,
                    student_id=student.id,
                    class_id=c1.id,
                    enrollment_type="required",
                )
            )
        db.add(
            CourseEnrollment(
                subject_id=other_course.id,
                student_id=outsider_student.id,
                class_id=c2.id,
                enrollment_type="required",
            )
        )

        root = CourseMaterialChapter(subject_id=course.id, title="Outline root", sort_order=1)
        child = CourseMaterialChapter(subject_id=course.id, title="Outline child", sort_order=2)
        db.add_all([root, child])
        db.flush()
        child.parent_id = root.id
        mat = CourseMaterial(
            title="Copied material",
            content="## copied body",
            content_format="markdown",
            attachment_name="source.txt",
            attachment_url="/api/files/download/source.txt?attachment_url=/uploads/source.txt",
            class_id=c1.id,
            subject_id=course.id,
            created_by=teacher.id,
        )
        db.add(mat)
        db.flush()
        db.add(CourseMaterialSection(material_id=mat.id, chapter_id=child.id, sort_order=3))
        db.commit()
        return {
            "teacher_username": teacher.username,
            "owner_username": owner_user.username,
            "same_username": same_student_user.username,
            "outsider_username": outsider_user.username,
            "course_id": course.id,
            "other_course_id": other_course.id,
            "root_chapter_id": root.id,
            "child_chapter_id": child.id,
            "material_id": mat.id,
        }
    finally:
        db.close()


def _create_note(client: TestClient, headers: dict, **payload) -> dict:
    body = {"title": "ln note", **payload}
    resp = client.post("/api/learning-notes", headers=headers, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_ln01_private_note_is_owner_only_and_absent_from_public_list(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    same = login_api(client, ctx["same_username"], "pass")
    note = _create_note(client, owner, title="private note")

    mine = client.get("/api/learning-notes?scope=mine", headers=owner)
    assert mine.status_code == 200
    assert note["id"] in {row["id"] for row in mine.json()["data"]}

    public = client.get("/api/learning-notes?scope=public", headers=same)
    assert public.status_code == 200
    assert note["id"] not in {row["id"] for row in public.json()["data"]}
    assert client.get(f"/api/learning-notes/{note['id']}", headers=same).status_code == 403


def test_ln02_public_unbound_note_is_visible_to_any_authenticated_user(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    outsider = login_api(client, ctx["outsider_username"], "pass")
    note = _create_note(client, owner, title="global public", visibility="course", subject_id=None)

    public = client.get("/api/learning-notes?scope=public", headers=outsider)
    assert public.status_code == 200
    assert note["id"] in {row["id"] for row in public.json()["data"]}
    detail = client.get(f"/api/learning-notes/{note['id']}", headers=outsider)
    assert detail.status_code == 200
    assert detail.json()["subject_id"] is None


def test_ln03_course_public_note_is_same_course_visible_not_global(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    same = login_api(client, ctx["same_username"], "pass")
    outsider = login_api(client, ctx["outsider_username"], "pass")
    note = _create_note(client, owner, title="course public", visibility="course", subject_id=ctx["course_id"])

    assert client.get(f"/api/learning-notes/{note['id']}", headers=same).status_code == 200
    assert client.get(f"/api/learning-notes/{note['id']}", headers=outsider).status_code == 403
    out_public = client.get("/api/learning-notes?scope=public", headers=outsider)
    assert note["id"] not in {row["id"] for row in out_public.json()["data"]}


def test_ln04_subject_public_filter_excludes_unbound_global_notes(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    unbound = _create_note(client, owner, title="global", visibility="course", subject_id=None)
    bound = _create_note(client, owner, title="bound", visibility="course", subject_id=ctx["course_id"])

    filtered = client.get(
        f"/api/learning-notes?scope=public&subject_id={ctx['course_id']}",
        headers=owner,
    )
    ids = {row["id"] for row in filtered.json()["data"]}
    assert bound["id"] in ids
    assert unbound["id"] not in ids


def test_ln05_owner_can_clear_subject_binding_to_make_public_note_global(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    outsider = login_api(client, ctx["outsider_username"], "pass")
    note = _create_note(client, owner, visibility="course", subject_id=ctx["course_id"])

    updated = client.put(f"/api/learning-notes/{note['id']}", headers=owner, json={"subject_id": None})
    assert updated.status_code == 200, updated.text
    assert updated.json()["subject_id"] is None
    assert client.get(f"/api/learning-notes/{note['id']}", headers=outsider).status_code == 200


def test_ln06_copy_course_outline_and_materials_creates_note_owned_tree(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    note = _create_note(
        client,
        owner,
        title="copied tree",
        copy_from_subject_id=ctx["course_id"],
        copy_chapters=True,
        copy_materials=True,
    )
    assert note["source_subject_id"] == ctx["course_id"]
    assert note["copied_materials"] is True
    assert note["chapters"]
    flat_resources = []

    def walk(nodes):
        for node in nodes:
            flat_resources.extend(node["resources"])
            walk(node["children"])

    walk(note["chapters"])
    assert len(flat_resources) == 1
    assert flat_resources[0]["source_material_id"] == ctx["material_id"]
    assert flat_resources[0]["attachment_url"]


def test_ln07_copied_resource_can_be_moved_to_loose_by_explicit_null_chapter_id(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    note = _create_note(
        client,
        owner,
        copy_from_subject_id=ctx["course_id"],
        copy_chapters=True,
        copy_materials=True,
    )
    resource = note["chapters"][0]["children"][0]["resources"][0]
    moved = client.put(
        f"/api/learning-notes/{note['id']}/resources/{resource['id']}",
        headers=owner,
        json={"chapter_id": None, "attachment_url": None, "attachment_name": None},
    )
    assert moved.status_code == 200, moved.text
    detail = moved.json()
    assert detail["loose_resources"][0]["id"] == resource["id"]
    assert detail["loose_resources"][0]["chapter_id"] is None
    assert detail["loose_resources"][0]["attachment_url"] is None


def test_ln08_child_chapter_can_be_promoted_to_root_by_explicit_null_parent_id(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    note = _create_note(client, owner, copy_from_subject_id=ctx["course_id"], copy_chapters=True)
    child = note["chapters"][0]["children"][0]
    moved = client.put(
        f"/api/learning-notes/{note['id']}/chapters/{child['id']}",
        headers=owner,
        json={"parent_id": None},
    )
    assert moved.status_code == 200, moved.text
    root_ids = {node["id"] for node in moved.json()["chapters"]}
    assert child["id"] in root_ids


def test_ln09_public_reader_cannot_mutate_note_or_add_resource(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    same = login_api(client, ctx["same_username"], "pass")
    note = _create_note(client, owner, visibility="course", subject_id=ctx["course_id"])
    assert client.put(f"/api/learning-notes/{note['id']}", headers=same, json={"title": "bad"}).status_code == 403
    assert client.post(f"/api/learning-notes/{note['id']}/resources", headers=same, json={"title": "bad"}).status_code == 403
    assert client.delete(f"/api/learning-notes/{note['id']}", headers=same).status_code == 403


def test_ln10_discussion_scope_private_vs_public_and_author_metadata(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    same = login_api(client, ctx["same_username"], "pass")
    private_note = _create_note(client, owner, title="private discussion")
    public_note = _create_note(client, owner, title="public discussion", visibility="course", subject_id=None)

    blocked = client.get(f"/api/learning-notes/{private_note['id']}/discussion", headers=same)
    assert blocked.status_code == 403
    posted = client.post(
        f"/api/learning-notes/{public_note['id']}/discussion",
        headers=same,
        json={"body": "same student comment", "body_format": "plain"},
    )
    assert posted.status_code == 200, posted.text
    listing = client.get(f"/api/learning-notes/{public_note['id']}/discussion", headers=owner)
    assert listing.status_code == 200
    row = listing.json()["data"][0]
    assert row["author_username"] == ctx["same_username"]
    assert row["body_format"] == "plain"


def test_ln10b_discussion_link_targets_round_trip_and_search(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    note = _create_note(client, owner, title="linked note", visibility="course", subject_id=ctx["course_id"])

    search = client.get(
        "/api/discussions/link-targets",
        headers=owner,
        params={"target_type": "learning_note", "q": "linked"},
    )
    assert search.status_code == 200, search.text
    assert any(row["target_id"] == note["id"] and row["title"] == "linked note" for row in search.json()["data"])

    posted = client.post(
        f"/api/learning-notes/{note['id']}/discussion",
        headers=owner,
        json={
            "body": "note discussion with links",
            "linked_targets": [
                {"target_type": "learning_note", "target_id": note["id"]},
                {"target_type": "material", "target_id": ctx["material_id"]},
            ],
        },
    )
    assert posted.status_code == 200, posted.text
    linked = posted.json()["linked_targets"]
    assert [item["target_type"] for item in linked] == ["learning_note", "material"]
    assert all(item["available"] for item in linked)

    listing = client.get(f"/api/learning-notes/{note['id']}/discussion", headers=owner)
    assert listing.status_code == 200
    row = next(item for item in listing.json()["data"] if item["id"] == posted.json()["id"])
    assert {item["target_type"] for item in row["linked_targets"]} == {"learning_note", "material"}


def test_ln10c_discussion_link_targets_unavailable_fallback_for_viewer(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    same = login_api(client, ctx["same_username"], "pass")
    note = _create_note(client, owner, title="public thread", visibility="course", subject_id=ctx["course_id"])
    private_target = _create_note(client, owner, title="private target")

    posted = client.post(
        f"/api/learning-notes/{note['id']}/discussion",
        headers=owner,
        json={
            "body": "private card should degrade for same-course viewer",
            "linked_targets": [{"target_type": "learning_note", "target_id": private_target["id"]}],
        },
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["linked_targets"][0]["available"] is True

    listing = client.get(f"/api/learning-notes/{note['id']}/discussion", headers=same)
    assert listing.status_code == 200, listing.text
    row = next(item for item in listing.json()["data"] if item["id"] == posted.json()["id"])
    linked = row["linked_targets"][0]
    assert linked["target_type"] == "learning_note"
    assert linked["target_id"] == private_target["id"]
    assert linked["available"] is False

    db = SessionLocal()
    try:
        entry = db.query(LearningNoteDiscussionEntry).filter(LearningNoteDiscussionEntry.id == posted.json()["id"]).first()
        assert entry is not None
        entry.linked_targets = [{"target_type": "material", "target_id": 999999}]
        db.commit()
    finally:
        db.close()

    deleted_target = client.get(f"/api/learning-notes/{note['id']}/discussion", headers=owner)
    assert deleted_target.status_code == 200
    row = next(item for item in deleted_target.json()["data"] if item["id"] == posted.json()["id"])
    assert row["linked_targets"][0]["available"] is False


def test_ln10d_learning_note_comment_link_target_search_round_trip_and_locator(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    same = login_api(client, ctx["same_username"], "pass")
    note = _create_note(client, owner, title="note with searchable comments", visibility="course", subject_id=ctx["course_id"])
    for idx in range(22):
        actor = same if idx % 2 else owner
        created = client.post(
            f"/api/learning-notes/{note['id']}/discussion",
            headers=actor,
            json={"body": f"note thread seed {idx}", "body_format": "plain"},
        )
        assert created.status_code == 200, created.text
    target = client.post(
        f"/api/learning-notes/{note['id']}/discussion",
        headers=same,
        json={"body": "deep note comment target", "body_format": "plain"},
    )
    assert target.status_code == 200, target.text
    target_card_id = LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET + target.json()["id"]

    search = client.get(
        "/api/discussions/link-targets",
        headers=owner,
        params={"target_type": "discussion_entry", "q": "deep note comment target", "preferred_subject_id": ctx["course_id"]},
    )
    assert search.status_code == 200, search.text
    rows = search.json()["data"]
    card = next(row for row in rows if row["target_id"] == target_card_id)
    assert card["meta"]["discussion_family"] == "learning_note"
    assert card["meta"]["note_id"] == note["id"]

    linked = client.post(
        f"/api/learning-notes/{note['id']}/discussion",
        headers=owner,
        json={
            "body": "links to note comment",
            "linked_targets": [{"target_type": "discussion_entry", "target_id": target_card_id}],
        },
    )
    assert linked.status_code == 200, linked.text
    linked_card = linked.json()["linked_targets"][0]
    assert linked_card["target_type"] == "discussion_entry"
    assert linked_card["target_id"] == target_card_id
    assert linked_card["meta"]["entry_id"] == target.json()["id"]

    locator = client.get(
        f"/api/learning-notes/discussion-entries/{target_card_id}/locator",
        headers=owner,
        params={"page_size": 20},
    )
    assert locator.status_code == 200, locator.text
    assert locator.json()["note_id"] == note["id"]
    assert locator.json()["page"] == 2


def test_ln10e_private_note_comment_link_degrades_for_public_viewer_without_body_leak(client: TestClient):
    ctx = _scenario()
    owner = login_api(client, ctx["owner_username"], "pass")
    same = login_api(client, ctx["same_username"], "pass")
    public_note = _create_note(client, owner, title="public target host", visibility="course", subject_id=ctx["course_id"])
    private_note = _create_note(client, owner, title="private target host")
    private_comment = client.post(
        f"/api/learning-notes/{private_note['id']}/discussion",
        headers=owner,
        json={"body": "secret private note comment body"},
    )
    assert private_comment.status_code == 200, private_comment.text
    private_target_id = LEARNING_NOTE_DISCUSSION_TARGET_ID_OFFSET + private_comment.json()["id"]
    posted = client.post(
        f"/api/learning-notes/{public_note['id']}/discussion",
        headers=owner,
        json={
            "body": "contains private comment card",
            "linked_targets": [{"target_type": "discussion_entry", "target_id": private_target_id}],
        },
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["linked_targets"][0]["available"] is True

    listing = client.get(f"/api/learning-notes/{public_note['id']}/discussion", headers=same)
    assert listing.status_code == 200, listing.text
    row = next(item for item in listing.json()["data"] if item["id"] == posted.json()["id"])
    card = row["linked_targets"][0]
    assert card["available"] is False
    assert "secret private note comment body" not in card["title"]
    assert "secret private note comment body" not in (card.get("secondary_text") or "")


def test_ln11_attendance_single_create_parses_iso_date_string_for_sqlite(client: TestClient):
    """Attendance is calendar-driven in the UI; single-create must parse date strings before DB insert."""
    ctx = _scenario()
    teacher = login_api(client, ctx["teacher_username"], "pass")
    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.student_no == ctx["owner_username"]).first()
        class_id = student.class_id
        student_id = student.id
    finally:
        db.close()

    created = client.post(
        "/api/attendance",
        headers=teacher,
        json={
            "student_id": student_id,
            "class_id": class_id,
            "subject_id": ctx["course_id"],
            "date": "2026-05-07",
            "status": "late",
            "remark": "calendar date click",
        },
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["status"] == "late"
    assert payload["subject_id"] == ctx["course_id"]

    duplicate = client.post(
        "/api/attendance",
        headers=teacher,
        json={
            "student_id": student_id,
            "class_id": class_id,
            "subject_id": ctx["course_id"],
            "date": "2026-05-07",
            "status": "present",
        },
    )
    assert duplicate.status_code == 400


def test_ln12_attendance_single_create_concurrent_duplicate_requests_do_not_create_two_rows(client: TestClient):
    """Single-create attendance should remain idempotent under concurrent duplicate writes."""
    ctx = _scenario()
    teacher = login_api(client, ctx["teacher_username"], "pass")
    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.student_no == ctx["owner_username"]).first()
        class_id = student.class_id
        student_id = student.id
    finally:
        db.close()

    payload = {
        "student_id": student_id,
        "class_id": class_id,
        "subject_id": ctx["course_id"],
        "date": "2026-05-08",
        "status": "present",
        "remark": "concurrent duplicate create",
    }

    from apps.backend.courseeval_backend.main import app

    barrier = threading.Barrier(2)

    def post_once():
        with TestClient(app) as local_client:
            barrier.wait(timeout=30)
            return local_client.post("/api/attendance", headers=teacher, json=payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = [future.result() for future in [executor.submit(post_once), executor.submit(post_once)]]

    statuses = sorted(response.status_code for response in responses)

    db = SessionLocal()
    try:
        count = (
            db.query(Attendance)
            .filter(
                Attendance.student_id == student_id,
                Attendance.class_id == class_id,
                Attendance.subject_id == ctx["course_id"],
                Attendance.remark == "concurrent duplicate create",
            )
            .count()
        )
    finally:
        db.close()

    assert statuses == [200, 400], statuses
    assert count == 1, count


def test_ln13_attendance_class_batch_concurrent_duplicate_requests_do_not_create_two_rows(client: TestClient):
    """Class-batch attendance should stay idempotent under concurrent duplicate writes."""
    ctx = _scenario()
    teacher = login_api(client, ctx["teacher_username"], "pass")
    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.student_no == ctx["owner_username"]).first()
        class_id = student.class_id
        student_id = student.id
    finally:
        db.close()

    payload = {
        "class_id": class_id,
        "subject_id": ctx["course_id"],
        "date": "2026-05-09",
        "status": "late",
        "remark": "concurrent class batch",
    }

    from apps.backend.courseeval_backend.main import app

    barrier = threading.Barrier(2)

    def post_once():
        with TestClient(app) as local_client:
            barrier.wait(timeout=30)
            return local_client.post("/api/attendance/class-batch", headers=teacher, json=payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = [future.result() for future in [executor.submit(post_once), executor.submit(post_once)]]

    statuses = sorted(response.status_code for response in responses)

    db = SessionLocal()
    try:
        count = (
            db.query(Attendance)
            .filter(
                Attendance.student_id == student_id,
                Attendance.class_id == class_id,
                Attendance.subject_id == ctx["course_id"],
                Attendance.remark == "concurrent class batch",
            )
            .count()
        )
    finally:
        db.close()

    assert statuses == [200, 200], statuses
    assert count == 1, count
