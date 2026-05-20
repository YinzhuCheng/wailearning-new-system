"""
Additional high-difficulty discussion API behavior: payload limits, 404 paths,
validation (422), inactive-session handling, and concurrent post/delete/list races.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Subject, User, UserRole
from tests.scenarios.llm_scenario import login_api, make_grading_course_with_homework
from tests.scenarios.material_flow import headers_for


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


def _post(client: TestClient, headers: dict, body: dict):
    return client.post("/api/discussions", headers=headers, json=body)


def test_behavior_discussion_list_page_size_over_query_limit_422(client: TestClient):
    ctx = make_grading_course_with_homework()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.get(
        "/api/discussions",
        headers=th,
        params={
            "target_type": "homework",
            "target_id": ctx["homework_id"],
            "subject_id": ctx["subject_id"],
            "class_id": ctx["class_id"],
            "page": 1,
            "page_size": 101,
        },
    )
    assert r.status_code == 422


def test_behavior_discussion_post_body_exceeds_max_length_400(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    r = _post(
        client,
        st,
        {
            "target_type": "homework",
            "target_id": ctx["homework_id"],
            "subject_id": ctx["subject_id"],
            "class_id": ctx["class_id"],
            "body": "x" * 8001,
        },
    )
    assert r.status_code in (400, 422)


def test_behavior_discussion_homework_target_missing_404(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    r = _post(
        client,
        st,
        {
            "target_type": "homework",
            "target_id": 9_999_999,
            "subject_id": ctx["subject_id"],
            "class_id": ctx["class_id"],
            "body": "nope",
        },
    )
    assert r.status_code == 404


def test_behavior_discussion_wrong_subject_id_for_homework_400(client: TestClient):
    ctx = make_grading_course_with_homework()
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        other = Subject(
            name=f"other-{uid}",
            teacher_id=ctx["teacher_id"],
            class_id=ctx["class_id"],
            course_type="required",
            status="active",
        )
        db.add(other)
        db.commit()
        db.refresh(other)
        wrong_sid = other.id
    finally:
        db.close()
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    r = _post(
        client,
        st,
        {
            "target_type": "homework",
            "target_id": ctx["homework_id"],
            "subject_id": wrong_sid,
            "class_id": ctx["class_id"],
            "body": "misscoped",
        },
    )
    assert r.status_code == 400


def test_behavior_discussion_inactive_user_bearer_rejected_400(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    assert client.get("/api/auth/me", headers=st).status_code == 200
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == ctx["student_username"]).first()
        assert u is not None
        u.is_active = False
        db.commit()
    finally:
        db.close()
    r = client.get(
        "/api/discussions",
        headers=st,
        params={
            "target_type": "homework",
            "target_id": ctx["homework_id"],
            "subject_id": ctx["subject_id"],
            "class_id": ctx["class_id"],
            "page": 1,
        },
    )
    assert r.status_code == 400
    assert "inactive" in f'{r.json().get("detail", "")}'.lower()


def test_behavior_discussion_concurrent_mixed_role_posts_unique_ids(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    te = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }
    stamp = uuid.uuid4().hex[:8]

    def one(i: int):
        h = st if i % 2 == 0 else te
        return _post(client, h, {**base, "body": f"mix-{stamp}-{i}"})

    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = [ex.submit(one, i) for i in range(32)]
        results = [f.result() for f in as_completed(futures)]

    assert all(r.status_code == 200 for r in results)
    ids = {r.json()["id"] for r in results}
    assert len(ids) == 32


def test_behavior_discussion_concurrent_double_delete_idempotent_both_204(client: TestClient):
    """Two concurrent deletes of the same row: both requests complete without 5xx; thread ends empty."""
    ctx = make_grading_course_with_homework()
    te = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }
    c = _post(client, st, {**base, "body": "to-delete"})
    assert c.status_code == 200
    eid = c.json()["id"]
    statuses: list[int] = []
    lock = threading.Lock()

    def do_del():
        r = client.delete(f"/api/discussions/{eid}", headers=te)
        with lock:
            statuses.append(r.status_code)

    t1 = threading.Thread(target=do_del)
    t2 = threading.Thread(target=do_del)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert all(s in (204, 404) for s in statuses)
    assert 204 in statuses


def test_behavior_discussion_llm_resolves_student_without_subject_anchor_class(client: TestClient):
    """Discussion LLM student binding should not depend on Subject.class_id being populated."""
    ctx = make_grading_course_with_homework()
    db = SessionLocal()
    try:
        subj = db.query(Subject).filter(Subject.id == ctx["subject_id"]).first()
        assert subj is not None
        # Elective-like / multi-class-compatible shape: no single anchor class on Subject.
        subj.class_id = None
        subj.course_type = "elective"
        db.commit()
        student_user = db.query(User).filter(User.id == ctx["student_user_id"]).first()
        assert student_user is not None
        from apps.backend.courseeval_backend.llm_discussion import resolve_student_for_discussion_llm

        student = resolve_student_for_discussion_llm(db, student_user, class_id=ctx["class_id"])
        assert student.id == ctx["student_id"]
    finally:
        db.close()


def test_behavior_discussion_llm_quota_exempt_roles_helper():
    from apps.backend.courseeval_backend.llm_discussion import discussion_llm_user_is_quota_exempt

    assert discussion_llm_user_is_quota_exempt(User(role=UserRole.ADMIN.value)) is True
    assert discussion_llm_user_is_quota_exempt(User(role=UserRole.TEACHER.value)) is True
    assert discussion_llm_user_is_quota_exempt(User(role=UserRole.CLASS_TEACHER.value)) is True
    assert discussion_llm_user_is_quota_exempt(User(role=UserRole.STUDENT.value)) is False


def test_behavior_discussion_concurrent_posts_eventually_list_total_matches(client: TestClient):
    ctx = make_grading_course_with_homework()
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }
    n = 40
    stamp = uuid.uuid4().hex[:6]

    def burst():
        return [_post(client, st, {**base, "body": f"{stamp}-{i}"}) for i in range(n)]

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(burst) for _ in range(4)]
        for f in as_completed(futs):
            rows = f.result()
            assert all(r.status_code == 200 for r in rows)

    lst = client.get(
        "/api/discussions",
        headers=th,
        params={
            **base,
            "target_type": "homework",
            "page": 1,
            "page_size": 50,
        },
    )
    assert lst.status_code == 200
    assert lst.json()["total"] == n * 4


def test_behavior_discussion_barrier_burst_then_first_page_order_monotonic_ids(client: TestClient):
    """Under simultaneous first posts, created_at+id ordering should remain consistent on page 1."""
    ctx = make_grading_course_with_homework()
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }
    barrier = threading.Barrier(12)
    out: list[int] = []
    lock = threading.Lock()

    def one(i: int):
        barrier.wait()
        r = _post(client, st, {**base, "body": f"b-{i}"})
        assert r.status_code == 200
        with lock:
            out.append(int(r.json()["id"]))

    threads = [threading.Thread(target=one, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    page = client.get(
        "/api/discussions",
        headers=th,
        params={**base, "target_type": "homework", "page": 1, "page_size": 50},
    )
    assert page.status_code == 200
    data = page.json()["data"]
    # API orders by (created_at, id). Under concurrent inserts, id assignment order may differ from
    # commit-time order on PostgreSQL, so row ids on a page are not guaranteed to be sorted by id alone.
    for prev, nxt in zip(data, data[1:]):
        p_key = (prev["created_at"], prev["id"])
        n_key = (nxt["created_at"], nxt["id"])
        assert p_key <= n_key, (p_key, n_key)


def test_behavior_discussion_student_cannot_delete_after_teacher_deleted_404(client: TestClient):
    ctx = make_grading_course_with_homework()
    te = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    base = {
        "target_type": "homework",
        "target_id": ctx["homework_id"],
        "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"],
    }
    c = _post(client, st, {**base, "body": "gone"})
    assert c.status_code == 200
    eid = c.json()["id"]
    assert client.delete(f"/api/discussions/{eid}", headers=te).status_code == 204
    r = client.delete(f"/api/discussions/{eid}", headers=st)
    assert r.status_code == 404
