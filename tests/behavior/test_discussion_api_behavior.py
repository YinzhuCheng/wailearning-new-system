"""
Behavior tests for course discussions API: concurrency, auth, validation,
pagination, material scope, and cross-role delete rules.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from fastapi.testclient import TestClient
from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Class, CourseDiscussionEntry, CourseMaterial, Homework, Subject, User, UserRole
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework
from tests.scenarios.material_flow import ensure_foreign_teacher, get_uncategorized_id, headers_for, make_subject_with_roster, ui_create_material


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _post_discussion(client: TestClient, headers: dict, body: dict):
    return client.post("/api/discussions", headers=headers, json=body)


def _list_discussion(client: TestClient, headers: dict, params: dict):
    return client.get("/api/discussions", headers=headers, params=params)


def test_behavior_discussion_concurrent_posts_unique_ids(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }
    uid = uuid.uuid4().hex[:8]

    def one(i: int):
        return _post_discussion(client, st, {**base, "body": f"c-{uid}-{i}"})

    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = [ex.submit(one, i) for i in range(24)]
        results = [f.result() for f in as_completed(futures)]

    assert all(r.status_code == 200 for r in results)
    ids = {r.json()["id"] for r in results}
    assert len(ids) == 24


def test_behavior_discussion_list_unauthenticated_401(client: TestClient):
    ctx = make_grading_course_with_homework()
    r = client.get(
        "/api/discussions",
        params={
            "target_type": "homework",
            "target_id": ctx["homework_id"],
            "subject_id": ctx["subject_id"],
            "class_id": ctx["class_id"],
            "page": 1,
        },
    )
    assert r.status_code == 401


def test_behavior_discussion_wrong_class_for_subject_post_400(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    db = SessionLocal()
    try:
        other = Class(name="iso-class", grade=2025)
        db.add(other)
        db.commit()
        db.refresh(other)
        wrong = other.id
    finally:
        db.close()
    r = _post_discussion(
        client,
        st,
        {
            "target_type": "homework",
            "target_id": ctx["homework_id"],
            "subject_id": ctx["subject_id"],
            "class_id": wrong,
            "body": "x",
        },
    )
    assert r.status_code == 400


def test_behavior_discussion_teacher_invoke_llm_allowed_200(client: TestClient, monkeypatch):
    ctx = make_grading_course_with_homework()
    te = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    monkeypatch.setattr(
        "apps.backend.courseeval_backend.api.routers.discussions.threading.Thread",
        lambda *args, **kwargs: type("NoopThread", (), {"start": lambda self: None})(),
    )
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
        "body": "@LLM\nhello",
        "invoke_llm": True,
    }
    r = client.post("/api/discussions", headers=te, json=base)
    assert r.status_code == 200, r.text
    assert r.json()["llm_invocation"] is True


def test_behavior_discussion_student_cannot_delete_teacher_message_403(client: TestClient):
    ctx = make_grading_course_with_homework()
    te = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }
    c = _post_discussion(client, te, {**base, "body": "teacher-msg"})
    assert c.status_code == 200
    d = client.delete(f"/api/discussions/{c.json()['id']}", headers=st)
    assert d.status_code == 403


def test_behavior_discussion_teacher_can_delete_student_message_204(client: TestClient):
    ctx = make_grading_course_with_homework()
    te = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }
    c = _post_discussion(client, st, {**base, "body": "stu-msg"})
    assert c.status_code == 200
    d = client.delete(f"/api/discussions/{c.json()['id']}", headers=te)
    assert d.status_code == 204


def test_behavior_discussion_list_includes_author_avatar_url(client: TestClient):
    ctx = make_grading_course_with_homework()
    te = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    db = SessionLocal()
    try:
        teacher = db.query(User).filter(User.username == ctx["teacher_username"]).first()
        assert teacher is not None
        teacher.avatar_url = "/uploads/test-avatar.png"
        db.commit()
    finally:
        db.close()

    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }
    created = _post_discussion(client, te, {**base, "body": "avatar-row"})
    assert created.status_code == 200, created.text
    listed = _list_discussion(client, te, {**base, "page": 1, "page_size": 10})
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json()["data"] if item["id"] == created.json()["id"])
    assert row["author_avatar_url"] == "/uploads/test-avatar.png"


def test_behavior_discussion_pagination_exact_counts(client: TestClient):
    """11 replies, page_size 10: page1 has 10 rows, page2 has 1."""
    ctx = make_grading_course_with_homework()
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid, sid, cid = ctx["homework_id"], ctx["subject_id"], ctx["class_id"]
    for i in range(11):
        r = client.post(
            "/api/discussions",
            headers=student_h,
            json={
                "target_type": "homework",
                "target_id": hid,
                "subject_id": sid,
                "class_id": cid,
                "body": f"msg-{i}",
            },
        )
        assert r.status_code == 200, r.text
    p1 = client.get(
        "/api/discussions",
        headers=teacher_h,
        params={
            "target_type": "homework",
            "target_id": hid,
            "subject_id": sid,
            "class_id": cid,
            "page": 1,
            "page_size": 10,
        },
    )
    assert p1.status_code == 200, p1.text
    d1 = p1.json()
    assert d1["total"] == 11
    assert d1["page_size"] == 10
    assert len(d1["data"]) == 10
    p2 = client.get(
        "/api/discussions",
        headers=teacher_h,
        params={
            "target_type": "homework",
            "target_id": hid,
            "subject_id": sid,
            "class_id": cid,
            "page": 2,
            "page_size": 10,
        },
    )
    assert p2.status_code == 200, p2.text
    assert len(p2.json()["data"]) == 1


def test_behavior_discussion_material_wrong_subject_list_400(client: TestClient):
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    m = ui_create_material(
        client,
        th,
        class_id=ctx["class_id"],
        subject_id=ctx["subject_id"],
        title="m1",
        chapter_ids=[unc],
    )
    assert m.status_code == 200, m.text
    mid = m.json()["id"]
    db = SessionLocal()
    try:
        k = Class(name="other2", grade=2024)
        db.add(k)
        db.flush()
        other_course = Subject(name="other-subj", teacher_id=ctx["teacher_id"], class_id=k.id)
        db.add(other_course)
        db.commit()
        db.refresh(other_course)
        other_sid = other_course.id
    finally:
        db.close()
    r = _list_discussion(
        client,
        th,
        {
            "target_type": "material",
            "target_id": mid,
            "subject_id": other_sid,
            "class_id": ctx["class_id"],
            "page": 1,
        },
    )
    assert r.status_code == 400


def test_behavior_patch_me_discussion_prefs_validation_422(client: TestClient):
    ensure_admin()
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        u = User(
            username=f"disc_u_{uid}",
            hashed_password=get_password_hash("pw12345678"),
            real_name="R",
            role=UserRole.TEACHER.value,
        )
        db.add(u)
        db.commit()
    finally:
        db.close()
    h = headers_for(client, f"disc_u_{uid}", "pw12345678")
    assert client.patch("/api/auth/me", headers=h, json={}).status_code == 422
    assert client.patch("/api/auth/me", headers=h, json={"discussion_page_size": 4}).status_code == 422
    assert client.patch("/api/auth/me", headers=h, json={"discussion_page_size": 51}).status_code == 422


def test_behavior_discussion_homework_without_subject_post_rejected_400(client: TestClient):
    ctx = make_grading_course_with_homework()
    te = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    db = SessionLocal()
    try:
        hw = Homework(
            title="orphan",
            content="x",
            class_id=ctx["class_id"],
            subject_id=None,
            max_score=10,
            grade_precision="integer",
            auto_grading_enabled=False,
            created_by=ctx["teacher_id"],
        )
        db.add(hw)
        db.commit()
        db.refresh(hw)
        hid = hw.id
    finally:
        db.close()
    r = _post_discussion(
        client,
        te,
        {
            "target_type": "homework",
            "target_id": hid,
            "subject_id": ctx["subject_id"],
            "class_id": ctx["class_id"],
            "body": "should fail scope",
        },
    )
    assert r.status_code == 400


def test_behavior_discussion_material_post_delete_list_empty(client: TestClient):
    uid = uuid.uuid4().hex[:10]
    db = SessionLocal()
    try:
        klass = Class(name=f"c-{uid}", grade=2026)
        db.add(klass)
        db.flush()
        t = User(
            username=f"t_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="T",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        course = Subject(name=f"s-{uid}", teacher_id=t.id, class_id=klass.id)
        db.add(course)
        db.flush()
        mat = CourseMaterial(
            title="doc",
            content="c",
            class_id=klass.id,
            subject_id=course.id,
            created_by=t.id,
        )
        db.add(mat)
        db.commit()
        db.refresh(mat)
        mid, sid, cid = mat.id, course.id, klass.id
    finally:
        db.close()
    th = login_api(client, f"t_{uid}", "tp")
    cr = client.post(
        "/api/discussions",
        headers=th,
        json={
            "target_type": "material",
            "target_id": mid,
            "subject_id": sid,
            "class_id": cid,
            "body": "note",
        },
    )
    assert cr.status_code == 200, cr.text
    eid = cr.json()["id"]
    assert client.delete(f"/api/discussions/{eid}", headers=th).status_code == 204
    lst = client.get(
        "/api/discussions",
        headers=th,
        params={
            "target_type": "material",
            "target_id": mid,
            "subject_id": sid,
            "class_id": cid,
        },
    )
    assert lst.status_code == 200
    assert lst.json()["total"] == 0


def test_behavior_discussion_link_targets_search_and_round_trip(client: TestClient):
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    material = ui_create_material(
        client,
        th,
        class_id=ctx["class_id"],
        subject_id=ctx["subject_id"],
        title="linkable material card",
        chapter_ids=[unc],
    )
    assert material.status_code == 200, material.text

    search = client.get(
        "/api/discussions/link-targets",
        headers=th,
        params={"target_type": "material", "q": "linkable", "preferred_subject_id": ctx["subject_id"]},
    )
    assert search.status_code == 200, search.text
    rows = search.json()["data"]
    assert any(row["target_type"] == "material" and row["target_id"] == material.json()["id"] for row in rows)

    created = _post_discussion(
        client,
        th,
        {
            "target_type": "material",
            "target_id": material.json()["id"],
            "subject_id": ctx["subject_id"],
            "class_id": ctx["class_id"],
            "body": "message with a structured link",
            "linked_targets": [{"target_type": "material", "target_id": material.json()["id"]}],
        },
    )
    assert created.status_code == 200, created.text
    linked = created.json()["linked_targets"]
    assert linked[0]["target_type"] == "material"
    assert linked[0]["target_id"] == material.json()["id"]
    assert linked[0]["title"] == "linkable material card"
    assert linked[0]["available"] is True

    listed = _list_discussion(
        client,
        th,
        {
            "target_type": "material",
            "target_id": material.json()["id"],
            "subject_id": ctx["subject_id"],
            "class_id": ctx["class_id"],
            "page": 1,
            "page_size": 10,
        },
    )
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json()["data"] if item["id"] == created.json()["id"])
    assert row["linked_targets"][0]["title"] == "linkable material card"


def test_behavior_discussion_link_targets_dedupe_limit_and_unavailable_fallback(client: TestClient):
    ctx = make_grading_course_with_homework()
    te = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }

    duplicate = _post_discussion(
        client,
        te,
        {
            **base,
            "body": "dedupe linked target",
            "linked_targets": [
                {"target_type": "homework", "target_id": ctx["homework_id"]},
                {"target_type": "homework", "target_id": ctx["homework_id"]},
            ],
        },
    )
    assert duplicate.status_code == 200, duplicate.text
    assert len(duplicate.json()["linked_targets"]) == 1

    over_limit = _post_discussion(
        client,
        te,
        {
            **base,
            "body": "too many links",
            "linked_targets": [{"target_type": "homework", "target_id": ctx["homework_id"] + i} for i in range(13)],
        },
    )
    assert over_limit.status_code == 400

    db = SessionLocal()
    try:
        row = db.query(CourseDiscussionEntry).filter(CourseDiscussionEntry.id == duplicate.json()["id"]).first()
        assert row is not None
        row.linked_targets = [{"target_type": "homework", "target_id": 999999}]
        db.commit()
    finally:
        db.close()

    listed = _list_discussion(client, te, {**base, "page": 1, "page_size": 10})
    assert listed.status_code == 200, listed.text
    patched = next(item for item in listed.json()["data"] if item["id"] == duplicate.json()["id"])
    assert patched["linked_targets"][0]["target_type"] == "homework"
    assert patched["linked_targets"][0]["available"] is False
    assert patched["linked_targets"][0]["title"]


def test_behavior_discussion_course_and_comment_link_targets_round_trip_and_locator(client: TestClient):
    ctx = make_grading_course_with_homework()
    teacher = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    student = headers_for(client, ctx["student_username"], ctx["student_password"])
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }
    for idx in range(7):
        r = _post_discussion(client, student if idx % 2 else teacher, {**base, "body": f"locator seed {idx}"})
        assert r.status_code == 200, r.text
    target = _post_discussion(client, student, {**base, "body": "hard-to-find target comment"})
    assert target.status_code == 200, target.text

    course_search = client.get(
        "/api/discussions/link-targets",
        headers=student,
        params={"target_type": "course", "preferred_subject_id": ctx["subject_id"]},
    )
    assert course_search.status_code == 200, course_search.text
    assert any(row["target_type"] == "course" and row["target_id"] == ctx["subject_id"] for row in course_search.json()["data"])

    comment_search = client.get(
        "/api/discussions/link-targets",
        headers=student,
        params={"target_type": "discussion_entry", "q": "hard-to-find", "preferred_subject_id": ctx["subject_id"]},
    )
    assert comment_search.status_code == 200, comment_search.text
    comment_rows = comment_search.json()["data"]
    assert comment_rows
    comment_card = next(row for row in comment_rows if row["target_id"] == target.json()["id"])
    assert comment_card["meta"]["discussion_family"] == "course"
    assert comment_card["meta"]["thread_target_type"] == "homework"

    linked = _post_discussion(
        client,
        student,
        {
            **base,
            "body": "links to course and another comment",
            "linked_targets": [
                {"target_type": "course", "target_id": ctx["subject_id"]},
                {"target_type": "discussion_entry", "target_id": target.json()["id"]},
            ],
        },
    )
    assert linked.status_code == 200, linked.text
    types = [item["target_type"] for item in linked.json()["linked_targets"]]
    assert types == ["course", "discussion_entry"]
    assert linked.json()["linked_targets"][1]["meta"]["entry_id"] == target.json()["id"]

    locator = client.get(
        f"/api/discussions/entries/{target.json()['id']}/locator",
        headers=student,
        params={"page_size": 5},
    )
    assert locator.status_code == 200, locator.text
    assert locator.json()["page"] == 2
    assert locator.json()["thread_target_id"] == ctx["homework_id"]


def test_behavior_discussion_comment_link_rejects_invisible_course_comment(client: TestClient):
    ctx = make_grading_course_with_homework()
    student = headers_for(client, ctx["student_username"], ctx["student_password"])
    foreign = ensure_foreign_teacher()
    foreign_headers = headers_for(client, foreign["username"], foreign["password"])
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }
    target = _post_discussion(client, student, {**base, "body": "private after enrollment removal"})
    assert target.status_code == 200, target.text

    search = client.get(
        "/api/discussions/link-targets",
        headers=foreign_headers,
        params={"target_type": "discussion_entry", "q": "private after enrollment removal"},
    )
    assert search.status_code == 200, search.text
    assert search.json()["data"] == []
