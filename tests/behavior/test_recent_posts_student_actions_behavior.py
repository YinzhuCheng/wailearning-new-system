"""Behavior coverage for recent-posts feeds and student action entry contracts."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import Class, CourseEnrollment, Homework, Student, User, UserRole
from apps.backend.courseeval_backend.domains.roster.sync import sync_student_user_from_roster_row
from tests.scenarios.llm_scenario import ensure_admin, make_grading_course_with_homework
from tests.scenarios.material_flow import headers_for


def _admin_headers(client: TestClient) -> dict[str, str]:
    ensure_admin()
    return headers_for(client, "pytest_admin", "pytest_admin_pass")


def _create_material(client: TestClient, headers: dict[str, str], ctx: dict, title: str) -> dict:
    r = client.post(
        "/api/materials",
        headers=headers,
        json={
            "title": title,
            "content": f"material body {title}",
            "content_format": "plain",
            "attachment_name": None,
            "attachment_url": None,
            "class_id": ctx["class_id"],
            "subject_id": ctx["subject_id"],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _create_homework(client: TestClient, headers: dict[str, str], ctx: dict, title: str) -> dict:
    r = client.post(
        "/api/homeworks",
        headers=headers,
        json={
            "title": title,
            "content": f"homework body {title}",
            "content_format": "plain",
            "attachment_name": None,
            "attachment_url": None,
            "class_id": ctx["class_id"],
            "subject_id": ctx["subject_id"],
            "due_date": None,
            "max_score": 100,
            "grade_precision": "integer",
            "auto_grading_enabled": False,
            "rubric_text": None,
            "rubric_staff_only": None,
            "reference_answer": None,
            "response_language": None,
            "allow_late_submission": True,
            "late_submission_affects_score": False,
            "max_submissions": None,
            "llm_routing_spec": None,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _create_note(
    client: TestClient,
    headers: dict[str, str],
    ctx: dict,
    title: str,
    *,
    visibility: str = "course",
) -> dict:
    r = client.post(
        "/api/learning-notes",
        headers=headers,
        json={
            "title": title,
            "description": f"note body {title}",
            "subject_id": ctx["subject_id"] if visibility == "course" else None,
            "visibility": visibility,
            "copy_from_subject_id": None,
            "copy_chapters": False,
            "copy_materials": False,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _create_discussion(client: TestClient, headers: dict[str, str], ctx: dict, title: str) -> dict:
    r = client.post(
        "/api/discussions",
        headers=headers,
        json={
            "target_type": "homework",
            "target_id": ctx["homework_id"],
            "subject_id": ctx["subject_id"],
            "class_id": ctx["class_id"],
            "body": title,
            "body_format": "plain",
            "linked_targets": [],
            "invoke_llm": False,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _teacher_user_id(ctx: dict) -> int:
    return int(ctx["teacher_id"])


def _bind_student_by_login(client: TestClient, ctx: dict) -> dict[str, str]:
    return headers_for(client, ctx["student_username"], ctx["student_password"])


def _seed_second_unenrolled_student(ctx: dict) -> int:
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        st = Student(name=f"Unenrolled {uid}", student_no=f"unenrolled_{uid}", class_id=ctx["class_id"])
        db.add(st)
        db.commit()
        db.refresh(st)
        return int(st.id)
    finally:
        db.close()


def _seed_enrolled_roster_only_student(ctx: dict, *, student_no: str | None = None, class_id: int | None = None) -> int:
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        st = Student(
            name=f"Roster Only {uid}",
            student_no=student_no or f"roster_only_{uid}",
            class_id=class_id or ctx["class_id"],
        )
        db.add(st)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=ctx["subject_id"],
                student_id=st.id,
                class_id=st.class_id,
                enrollment_type="required",
                can_remove=False,
            )
        )
        db.commit()
        db.refresh(st)
        return int(st.id)
    finally:
        db.close()


def test_recent_posts_grouped_student_view_matches_linkable_target_family(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = _bind_student_by_login(client, ctx)

    _create_material(client, th, ctx, "rp material")
    _create_note(client, th, ctx, "rp course note", visibility="course")
    _create_discussion(client, th, ctx, "rp teacher discussion")

    r = client.get(f"/api/recent-posts/users/{_teacher_user_id(ctx)}/grouped", headers=st)
    assert r.status_code == 200, r.text
    kinds = {group["kind"] for group in r.json()["groups"]}
    assert {"course", "homework", "material", "note", "comment"}.issubset(kinds)


def test_recent_posts_admin_does_not_bypass_private_note_visibility(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    admin = _admin_headers(client)

    private_note = _create_note(client, th, ctx, "rp private note", visibility="private")
    course_note = _create_note(client, th, ctx, "rp visible course note", visibility="course")

    r = client.get(
        f"/api/recent-posts/users/{_teacher_user_id(ctx)}",
        headers=admin,
        params={"kind": "note", "page_size": 50},
    )
    assert r.status_code == 200, r.text
    titles = {row["title"] for row in r.json()["data"]}
    assert course_note["title"] in titles
    assert private_note["title"] not in titles


def test_recent_posts_foreign_teacher_sees_author_but_not_inaccessible_titles(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    _create_material(client, th, ctx, "foreign hidden material")
    _create_note(client, th, ctx, "foreign hidden course note", visibility="course")

    db = SessionLocal()
    try:
        other = User(
            username=f"rp_foreign_{uuid.uuid4().hex[:8]}",
            hashed_password=get_password_hash("pw"),
            real_name="Foreign Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(other)
        db.commit()
        other_username = other.username
    finally:
        db.close()
    other_h = headers_for(client, other_username, "pw")

    r = client.get(f"/api/recent-posts/users/{_teacher_user_id(ctx)}", headers=other_h, params={"page_size": 50})
    assert r.status_code == 200, r.text
    assert r.json()["author"]["id"] == ctx["teacher_id"]
    assert r.json()["total"] == 0
    assert r.json()["data"] == []


def test_recent_posts_homework_kind_paginates_newest_first_by_id_tiebreak(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    older = _create_homework(client, th, ctx, f"rp hw older {uuid.uuid4().hex[:6]}")
    newer = _create_homework(client, th, ctx, f"rp hw newer {uuid.uuid4().hex[:6]}")

    page1 = client.get(
        f"/api/recent-posts/users/{_teacher_user_id(ctx)}",
        headers=th,
        params={"kind": "homework", "page": 1, "page_size": 1},
    )
    page2 = client.get(
        f"/api/recent-posts/users/{_teacher_user_id(ctx)}",
        headers=th,
        params={"kind": "homework", "page": 2, "page_size": 1},
    )
    assert page1.status_code == 200, page1.text
    assert page2.status_code == 200, page2.text
    assert page1.json()["data"][0]["title"] == newer["title"]
    assert page2.json()["data"][0]["title"] == older["title"]


def test_recent_posts_group_limit_caps_each_group_without_losing_totals(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    for i in range(3):
        _create_homework(client, th, ctx, f"rp grouped hw {i} {uuid.uuid4().hex[:4]}")
        _create_material(client, th, ctx, f"rp grouped material {i} {uuid.uuid4().hex[:4]}")

    r = client.get(f"/api/recent-posts/users/{_teacher_user_id(ctx)}/grouped", headers=th, params={"group_limit": 1})
    assert r.status_code == 200, r.text
    groups = {group["kind"]: group for group in r.json()["groups"]}
    assert groups["homework"]["total"] >= 4
    assert len(groups["homework"]["data"]) == 1
    assert groups["material"]["total"] >= 3
    assert len(groups["material"]["data"]) == 1


def test_recent_posts_future_from_filter_returns_empty_page(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    _create_material(client, th, ctx, "rp time filter material")
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    r = client.get(
        f"/api/recent-posts/users/{_teacher_user_id(ctx)}",
        headers=th,
        params={"from_created_at": future, "page_size": 50},
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0
    assert r.json()["data"] == []


def test_course_discussion_response_exposes_student_author_student_id(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    st = _bind_student_by_login(client, ctx)

    created = _create_discussion(client, st, ctx, "student discussion author id")
    assert created["author_user_id"] == ctx["student_user_id"]
    assert created["author_student_id"] == ctx["student_id"]


def test_learning_note_discussion_response_exposes_student_author_student_id(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    st = _bind_student_by_login(client, ctx)
    note = _create_note(client, st, ctx, "student course note", visibility="course")

    r = client.post(
        f"/api/learning-notes/{note['id']}/discussion",
        headers=st,
        json={"body": "student note discussion author id", "body_format": "plain", "linked_targets": []},
    )
    assert r.status_code == 200, r.text
    assert r.json()["author_user_id"] == ctx["student_user_id"]
    assert r.json()["author_student_id"] == ctx["student_id"]


def test_admin_students_list_exposes_bound_user_id_after_login_reconciliation(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    _bind_student_by_login(client, ctx)
    admin = _admin_headers(client)

    r = client.get("/api/students", headers=admin, params={"class_id": ctx["class_id"], "page_size": 100})
    assert r.status_code == 200, r.text
    row = next(item for item in r.json()["data"] if int(item["id"]) == int(ctx["student_id"]))
    assert row["has_user"] is True
    assert row["bound_user_id"] == ctx["student_user_id"]


def test_course_roster_students_include_bound_student_user_id(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    _bind_student_by_login(client, ctx)

    r = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=th)
    assert r.status_code == 200, r.text
    row = next(item for item in r.json() if int(item["student_id"]) == int(ctx["student_id"]))
    assert row["student_user_id"] == ctx["student_user_id"]


def test_course_roster_students_is_read_only_for_roster_only_enrollment(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    student_id = _seed_enrolled_roster_only_student(ctx)

    r = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=th)
    assert r.status_code == 200, r.text
    row = next(item for item in r.json() if int(item["student_id"]) == student_id)
    assert row["student_user_id"] is None

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.student_id == student_id).first() is None
    finally:
        db.close()


def test_admin_students_list_is_read_only_for_roster_only_enrollment(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    admin = _admin_headers(client)
    student_id = _seed_enrolled_roster_only_student(ctx)

    first = client.get("/api/students", headers=admin, params={"class_id": ctx["class_id"], "page_size": 100})
    second = client.get("/api/students", headers=admin, params={"class_id": ctx["class_id"], "page_size": 100})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    first_row = next(item for item in first.json()["data"] if int(item["id"]) == student_id)
    second_row = next(item for item in second.json()["data"] if int(item["id"]) == student_id)
    assert first_row["has_user"] is False
    assert first_row["bound_user_id"] is None
    assert second_row["has_user"] is False
    assert second_row["bound_user_id"] is None

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.student_id == student_id).first() is None
    finally:
        db.close()


def test_admin_student_detail_is_read_only_for_roster_only_enrollment(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    admin = _admin_headers(client)
    student_id = _seed_enrolled_roster_only_student(ctx)

    first = client.get(f"/api/students/{student_id}", headers=admin)
    second = client.get(f"/api/students/{student_id}", headers=admin)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["has_user"] is False
    assert first.json()["bound_user_id"] is None
    assert second.json()["has_user"] is False
    assert second.json()["bound_user_id"] is None

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.student_id == student_id).count() == 0
    finally:
        db.close()


def test_read_heavy_roster_students_and_users_endpoints_do_not_reconcile_roster_only_rows(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    admin = _admin_headers(client)
    student_ids = [_seed_enrolled_roster_only_student(ctx) for _ in range(4)]

    for _ in range(3):
        roster = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=th)
        students = client.get("/api/students", headers=admin, params={"class_id": ctx["class_id"], "page_size": 100})
        users = client.get("/api/users", headers=admin, params={"page_size": 100})
        assert roster.status_code == 200, roster.text
        assert students.status_code == 200, students.text
        assert users.status_code == 200, users.text

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.student_id.in_(student_ids)).count() == 0
        assert (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.subject_id == ctx["subject_id"], CourseEnrollment.student_id.in_(student_ids))
            .count()
            == len(student_ids)
        )
    finally:
        db.close()


def test_explicit_roster_sync_creates_bound_user_for_roster_only_enrollment(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    student_id = _seed_enrolled_roster_only_student(ctx)

    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.id == student_id).one()
        sync_student_user_from_roster_row(db, st)
        db.commit()
    finally:
        db.close()

    first = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=th)
    second = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=th)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    first_row = next(item for item in first.json() if int(item["student_id"]) == student_id)
    second_row = next(item for item in second.json() if int(item["student_id"]) == student_id)
    assert first_row["student_user_id"] == second_row["student_user_id"]

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.student_id == student_id).count() == 1
        assert (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.subject_id == ctx["subject_id"], CourseEnrollment.student_id == student_id)
            .count()
            == 1
        )
    finally:
        db.close()


def test_explicit_roster_sync_reconciles_multiple_roster_only_enrollments_with_distinct_users(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    student_ids = [_seed_enrolled_roster_only_student(ctx) for _ in range(3)]

    db = SessionLocal()
    try:
        for st in db.query(Student).filter(Student.id.in_(student_ids)).all():
            sync_student_user_from_roster_row(db, st)
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=th)
    assert r.status_code == 200, r.text
    rows = {int(item["student_id"]): item for item in r.json() if int(item["student_id"]) in student_ids}
    assert set(rows) == set(student_ids)
    user_ids = {rows[student_id]["student_user_id"] for student_id in student_ids}
    assert len(user_ids) == len(student_ids)
    assert all(isinstance(user_id, int) for user_id in user_ids)

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.student_id.in_(student_ids)).count() == len(student_ids)
    finally:
        db.close()


def test_explicit_roster_sync_shared_by_course_roster_and_admin_students_list(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    admin = _admin_headers(client)
    student_id = _seed_enrolled_roster_only_student(ctx)

    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.id == student_id).one()
        sync_student_user_from_roster_row(db, st)
        db.commit()
    finally:
        db.close()

    roster = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=th)
    assert roster.status_code == 200, roster.text
    roster_row = next(item for item in roster.json() if int(item["student_id"]) == student_id)
    assert isinstance(roster_row["student_user_id"], int)

    students = client.get("/api/students", headers=admin, params={"class_id": ctx["class_id"], "page_size": 100})
    assert students.status_code == 200, students.text
    student_row = next(item for item in students.json()["data"] if int(item["id"]) == student_id)
    assert student_row["has_user"] is True
    assert student_row["bound_user_id"] == roster_row["student_user_id"]


def test_course_roster_students_forbidden_teacher_does_not_mutate_roster_only_student(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    student_no = f"blocked_roster_{uuid.uuid4().hex[:8]}"
    _seed_enrolled_roster_only_student(ctx, student_no=student_no)

    db = SessionLocal()
    try:
        other = User(
            username=f"rp_forbidden_{uuid.uuid4().hex[:8]}",
            hashed_password=get_password_hash("pw"),
            real_name="Forbidden Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(other)
        db.commit()
        other_username = other.username
    finally:
        db.close()

    other_h = headers_for(client, other_username, "pw")
    r = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=other_h)
    assert r.status_code == 403

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.username == student_no).first() is None
    finally:
        db.close()


def test_course_roster_students_leave_occupied_username_unbound(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    student_no = f"occupied_roster_{uuid.uuid4().hex[:8]}"
    student_id = _seed_enrolled_roster_only_student(ctx, student_no=student_no)

    db = SessionLocal()
    try:
        db.add(
            User(
                username=student_no,
                hashed_password=get_password_hash("pw"),
                real_name="Non Student Occupant",
                role=UserRole.TEACHER.value,
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=th)
    assert r.status_code == 200, r.text
    row = next(item for item in r.json() if int(item["student_id"]) == student_id)
    assert row["student_user_id"] is None

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.student_id == student_id).first() is None
        occupant = db.query(User).filter(User.username == student_no).one()
        assert occupant.role == UserRole.TEACHER.value
    finally:
        db.close()


def test_explicit_roster_sync_reactivates_inactive_bound_student_user(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    student_id = _seed_enrolled_roster_only_student(ctx)

    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.id == student_id).one()
        user = User(
            username=st.student_no,
            hashed_password=get_password_hash(st.student_no),
            real_name=st.name,
            role=UserRole.STUDENT.value,
            class_id=st.class_id,
            student_id=student_id,
            is_active=False,
        )
        db.add(user)
        db.commit()
        user_id = int(user.id)
    finally:
        db.close()

    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.id == student_id).one()
        sync_student_user_from_roster_row(db, st)
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=th)
    assert r.status_code == 200, r.text
    row = next(item for item in r.json() if int(item["student_id"]) == student_id)
    assert row["student_user_id"] == user_id

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.id == user_id).one().is_active is True
    finally:
        db.close()


def test_explicit_roster_sync_repairs_bound_user_class_without_duplicate_account(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])

    db = SessionLocal()
    try:
        old_class = Class(name=f"Old Class {uuid.uuid4().hex[:8]}", grade=9)
        db.add(old_class)
        db.commit()
        old_class_id = int(old_class.id)
    finally:
        db.close()

    student_id = _seed_enrolled_roster_only_student(ctx)
    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.id == student_id).one()
        user = User(
            username=st.student_no,
            hashed_password=get_password_hash(st.student_no),
            real_name=st.name,
            role=UserRole.STUDENT.value,
            class_id=old_class_id,
            student_id=student_id,
            is_active=True,
        )
        db.add(user)
        db.commit()
        user_id = int(user.id)
    finally:
        db.close()

    db = SessionLocal()
    try:
        st = db.query(Student).filter(Student.id == student_id).one()
        sync_student_user_from_roster_row(db, st)
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=th)
    assert r.status_code == 200, r.text
    row = next(item for item in r.json() if int(item["student_id"]) == student_id)
    assert row["student_user_id"] == user_id

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.student_id == student_id).count() == 1
        assert old_class_id != ctx["class_id"]
        assert db.query(User).filter(User.id == user_id).one().class_id == ctx["class_id"]
        assert db.query(Student).filter(Student.id == student_id).one().class_id == ctx["class_id"]
    finally:
        db.close()


def test_student_homework_status_rejects_unenrolled_same_class_student(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    unenrolled_id = _seed_second_unenrolled_student(ctx)

    r = client.get(f"/api/homeworks/courses/{ctx['subject_id']}/students/{unenrolled_id}/homeworks", headers=th)
    assert r.status_code == 403
    assert "not enrolled" in r.json()["detail"]


def test_student_homework_status_reports_attempt_count_review_and_submission_link(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = _bind_student_by_login(client, ctx)
    for body in ("first answer", "second answer"):
        r = client.post(
            f"/api/homeworks/{ctx['homework_id']}/submission",
            headers=st,
            json={
                "content": body,
                "content_format": "plain",
                "attachment_name": None,
                "attachment_url": None,
                "remove_attachment": False,
                "used_llm_assist": False,
                "submission_mode": "full",
            },
        )
        assert r.status_code == 200, r.text
    hist = client.get(f"/api/homeworks/{ctx['homework_id']}/submission/me/history", headers=st)
    assert hist.status_code == 200, hist.text
    submission_id = hist.json()["summary"]["id"]
    reviewed = client.put(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{submission_id}/review",
        headers=th,
        json={"review_score": 91, "review_comment": "solid"},
    )
    assert reviewed.status_code == 200, reviewed.text

    status = client.get(
        f"/api/homeworks/courses/{ctx['subject_id']}/students/{ctx['student_id']}/homeworks",
        headers=th,
    )
    assert status.status_code == 200, status.text
    row = next(item for item in status.json()["data"] if int(item["homework_id"]) == int(ctx["homework_id"]))
    assert row["submission_id"] == submission_id
    assert row["attempt_count"] == 2
    assert row["review_score"] == 91
