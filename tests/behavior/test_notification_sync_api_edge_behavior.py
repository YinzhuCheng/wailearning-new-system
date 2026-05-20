"""High-difficulty API regressions for notification sync-status vs list visibility (behavior layer).

These complement existing coverage in ``test_complex_regression_roundtrip_behavior.py`` (c6/c7/c7b)
by stressing **contract alignment** between ``GET /api/notifications`` and
``GET /api/notifications/sync-status``, ``latest_updated_at`` semantics, multi-course scoping,
and concurrent publish paths.

Requires the standard behavior ``client`` fixture (SQLite reset per test).
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import CourseEnrollment, Notification, NotificationRead, Student, Subject
from apps.backend.courseeval_backend.main import app
from tests.scenarios.llm_scenario import login_api, make_grading_course_with_homework


def _subject_meta(client: TestClient, subject_id: int) -> dict[str, int]:
    db = SessionLocal()
    try:
        subj = db.query(Subject).filter(Subject.id == subject_id).one()
        return {"class_id": int(subj.class_id), "teacher_id": int(subj.teacher_id)}
    finally:
        db.close()


def test_ns01_list_totals_match_sync_status_for_student_subject_scope(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    meta = _subject_meta(client, ctx["subject_id"])

    created = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={
            "title": "ns01",
            "content": "body",
            "class_id": meta["class_id"],
            "subject_id": ctx["subject_id"],
        },
    )
    assert created.status_code == 200, created.text

    lst = client.get(
        "/api/notifications",
        headers=student_headers,
        params={"subject_id": ctx["subject_id"], "page": 1, "page_size": 20},
    )
    sync = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    assert lst.status_code == 200
    assert sync.status_code == 200
    body = lst.json()
    snap = sync.json()
    assert int(body["total"]) == int(snap["total"])
    assert int(body["unread_count"]) == int(snap["unread_count"])


def test_ns02_second_course_only_second_subject_sync_counts_isolated_rows(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    meta = _subject_meta(client, ctx["subject_id"])

    db = SessionLocal()
    try:
        course = db.query(Subject).filter(Subject.id == ctx["subject_id"]).one()
        second = Subject(
            name=f"ns02-extra-{uuid.uuid4().hex[:6]}",
            teacher_id=course.teacher_id,
            class_id=course.class_id,
            course_type="required",
            status="active",
        )
        db.add(second)
        db.flush()
        student = db.query(Student).filter(Student.id == ctx["student_id"]).one()
        db.add(
            CourseEnrollment(
                subject_id=second.id,
                student_id=student.id,
                class_id=course.class_id,
                enrollment_type="required",
            )
        )
        db.commit()
        sid_b = int(second.id)
        class_id = int(course.class_id)
    finally:
        db.close()

    a = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={"title": "only-a", "content": "a", "class_id": class_id, "subject_id": ctx["subject_id"]},
    )
    b = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={"title": "only-b", "content": "b", "class_id": class_id, "subject_id": sid_b},
    )
    assert a.status_code == 200 and b.status_code == 200

    sync_a = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    sync_b = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": sid_b})
    assert sync_a.status_code == 200 and sync_b.status_code == 200
    assert sync_a.json()["unread_count"] >= 1
    assert sync_b.json()["unread_count"] >= 1
    assert sync_a.json()["total"] >= 1
    assert sync_b.json()["total"] >= 1


def test_ns03_broadcast_subject_null_visible_inside_course_scoped_sync(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    meta = _subject_meta(client, ctx["subject_id"])

    created = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={
            "title": "broadcast",
            "content": "no subject row",
            "class_id": meta["class_id"],
            "subject_id": None,
        },
    )
    assert created.status_code == 200, created.text

    scoped = client.get(
        "/api/notifications/sync-status",
        headers=student_headers,
        params={"subject_id": ctx["subject_id"]},
    )
    assert scoped.status_code == 200
    assert scoped.json()["unread_count"] >= 1


def test_ns04_patch_notification_advances_latest_updated_at_in_sync(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    meta = _subject_meta(client, ctx["subject_id"])

    created = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={
            "title": "before-patch",
            "content": "v1",
            "class_id": meta["class_id"],
            "subject_id": ctx["subject_id"],
        },
    )
    assert created.status_code == 200
    nid = int(created.json()["id"])

    before = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    assert before.status_code == 200
    t0 = before.json().get("latest_updated_at")

    updated = client.put(
        f"/api/notifications/{nid}",
        headers=teacher_headers,
        json={"title": "after-patch-ns04"},
    )
    assert updated.status_code == 200, updated.text

    after = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    assert after.status_code == 200
    t1 = after.json().get("latest_updated_at")
    assert t1 != t0


def test_ns05_delete_notification_lowers_sync_total(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    meta = _subject_meta(client, ctx["subject_id"])

    row = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={
            "title": "to-delete",
            "content": "x",
            "class_id": meta["class_id"],
            "subject_id": ctx["subject_id"],
        },
    )
    assert row.status_code == 200
    nid = int(row.json()["id"])

    tot_before = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    assert tot_before.status_code == 200
    n0 = int(tot_before.json()["total"])

    deleted = client.delete(f"/api/notifications/{nid}", headers=teacher_headers)
    assert deleted.status_code == 200, deleted.text

    tot_after = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    assert tot_after.status_code == 200
    assert int(tot_after.json()["total"]) == n0 - 1


def test_ns06_concurrent_creates_settle_with_coherent_sync_unread(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    meta = _subject_meta(client, ctx["subject_id"])

    errors: list[str] = []

    def post_one(i: int) -> None:
        try:
            r = client.post(
                "/api/notifications",
                headers=teacher_headers,
                json={
                    "title": f"conc-{i}-{uuid.uuid4().hex[:4]}",
                    "content": "c",
                    "class_id": meta["class_id"],
                    "subject_id": ctx["subject_id"],
                },
            )
            assert r.status_code == 200, r.text
        except Exception as exc:  # pragma: no cover
            errors.append(str(exc))

    threads = [threading.Thread(target=post_one, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors

    sync = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    assert sync.status_code == 200
    assert int(sync.json()["unread_count"]) >= 4


def test_ns07_single_mark_read_drops_sync_unread_by_one(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    meta = _subject_meta(client, ctx["subject_id"])

    a = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={
            "title": "read-one-a",
            "content": "a",
            "class_id": meta["class_id"],
            "subject_id": ctx["subject_id"],
        },
    )
    b = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={
            "title": "read-one-b",
            "content": "b",
            "class_id": meta["class_id"],
            "subject_id": ctx["subject_id"],
        },
    )
    assert a.status_code == 200 and b.status_code == 200
    nid = int(a.json()["id"])

    before = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    assert before.status_code == 200
    u0 = int(before.json()["unread_count"])
    assert u0 >= 2

    read = client.post(f"/api/notifications/{nid}/read", headers=student_headers)
    assert read.status_code == 200, read.text

    after = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    assert after.status_code == 200
    assert int(after.json()["unread_count"]) == u0 - 1


def test_ns08_mark_all_read_zeros_sync_for_subject_whilst_other_subject_stays_hot(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    meta = _subject_meta(client, ctx["subject_id"])

    db = SessionLocal()
    try:
        course = db.query(Subject).filter(Subject.id == ctx["subject_id"]).one()
        second = Subject(
            name=f"ns08-extra-{uuid.uuid4().hex[:6]}",
            teacher_id=course.teacher_id,
            class_id=course.class_id,
            course_type="required",
            status="active",
        )
        db.add(second)
        db.flush()
        student = db.query(Student).filter(Student.id == ctx["student_id"]).one()
        db.add(
            CourseEnrollment(
                subject_id=second.id,
                student_id=student.id,
                class_id=course.class_id,
                enrollment_type="required",
            )
        )
        db.commit()
        sid_b = int(second.id)
        class_id = int(course.class_id)
    finally:
        db.close()

    client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={"title": "m1", "content": "m1", "class_id": class_id, "subject_id": ctx["subject_id"]},
    )
    client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={"title": "m2", "content": "m2", "class_id": class_id, "subject_id": sid_b},
    )

    marked = client.post(
        "/api/notifications/mark-all-read",
        headers=student_headers,
        params={"subject_id": ctx["subject_id"]},
    )
    assert marked.status_code == 200, marked.text

    sync_a = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    sync_b = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": sid_b})
    assert sync_a.json()["unread_count"] == 0
    assert sync_b.json()["unread_count"] >= 1


def test_ns09_student_sync_status_for_foreign_subject_returns_403(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])

    db = SessionLocal()
    try:
        course = db.query(Subject).filter(Subject.id == ctx["subject_id"]).one()
        orphan = Subject(
            name=f"ns09-orphan-{uuid.uuid4().hex[:6]}",
            teacher_id=course.teacher_id,
            class_id=None,
            course_type="required",
            status="active",
        )
        db.add(orphan)
        db.commit()
        orphan_id = int(orphan.id)
    finally:
        db.close()

    foreign = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": orphan_id})
    assert foreign.status_code == 403


def test_ns10_parallel_sync_reads_do_not_duplicate_notification_read_rows(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    meta = _subject_meta(client, ctx["subject_id"])

    created = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={
            "title": "parallel-read",
            "content": "pr",
            "class_id": meta["class_id"],
            "subject_id": ctx["subject_id"],
        },
    )
    assert created.status_code == 200
    nid = int(created.json()["id"])

    def read_once() -> None:
        r = client.post(f"/api/notifications/{nid}/read", headers=student_headers)
        assert r.status_code == 200, r.text

    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(read_once) for _ in range(6)]
        for fut in as_completed(futs):
            fut.result()

    db = SessionLocal()
    try:
        rows = db.query(NotificationRead).filter(NotificationRead.notification_id == nid).all()
        assert len(rows) == 1
        assert rows[0].is_read is True
    finally:
        db.close()


def test_ns11_delete_while_mark_read_is_inflight_converges_without_orphan_reads(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    meta = _subject_meta(client, ctx["subject_id"])

    created = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={
            "title": "delete-read-race",
            "content": "race",
            "class_id": meta["class_id"],
            "subject_id": ctx["subject_id"],
        },
    )
    assert created.status_code == 200, created.text
    nid = int(created.json()["id"])

    barrier = threading.Barrier(2)
    results: list[tuple[str, int, str]] = []
    errors: list[str] = []

    def mark_read() -> None:
        try:
            with TestClient(app) as thread_client:
                barrier.wait(timeout=10)
                resp = thread_client.post(f"/api/notifications/{nid}/read", headers=student_headers)
                results.append(("read", resp.status_code, resp.text))
        except Exception as exc:  # pragma: no cover
            errors.append(f"read:{exc}")

    def delete_row() -> None:
        try:
            with TestClient(app) as thread_client:
                barrier.wait(timeout=10)
                resp = thread_client.delete(f"/api/notifications/{nid}", headers=teacher_headers)
                results.append(("delete", resp.status_code, resp.text))
        except Exception as exc:  # pragma: no cover
            errors.append(f"delete:{exc}")

    threads = [threading.Thread(target=mark_read), threading.Thread(target=delete_row)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    statuses = {kind: status for kind, status, _ in results}
    assert statuses.get("delete") == 200, results
    assert statuses.get("read") in {200, 403, 404}, results

    db = SessionLocal()
    try:
        assert db.query(Notification).filter(Notification.id == nid).count() == 0
        assert db.query(NotificationRead).filter(NotificationRead.notification_id == nid).count() == 0
    finally:
        db.close()


def test_ns12_delete_while_mark_all_read_is_inflight_converges_without_orphan_reads(client: TestClient) -> None:
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    meta = _subject_meta(client, ctx["subject_id"])

    created_ids: list[int] = []
    for i in range(3):
        created = client.post(
            "/api/notifications",
            headers=teacher_headers,
            json={
                "title": f"delete-bulk-read-{i}",
                "content": "bulk",
                "class_id": meta["class_id"],
                "subject_id": ctx["subject_id"],
            },
        )
        assert created.status_code == 200, created.text
        created_ids.append(int(created.json()["id"]))

    target_id = created_ids[0]
    barrier = threading.Barrier(2)
    results: list[tuple[str, int, str]] = []
    errors: list[str] = []

    def mark_all() -> None:
        try:
            with TestClient(app) as thread_client:
                barrier.wait(timeout=10)
                resp = thread_client.post(
                    "/api/notifications/mark-all-read",
                    headers=student_headers,
                    params={"subject_id": ctx["subject_id"]},
                )
                results.append(("mark_all", resp.status_code, resp.text))
        except Exception as exc:  # pragma: no cover
            errors.append(f"mark_all:{exc}")

    def delete_row() -> None:
        try:
            with TestClient(app) as thread_client:
                barrier.wait(timeout=10)
                resp = thread_client.delete(f"/api/notifications/{target_id}", headers=teacher_headers)
                results.append(("delete", resp.status_code, resp.text))
        except Exception as exc:  # pragma: no cover
            errors.append(f"delete:{exc}")

    threads = [threading.Thread(target=mark_all), threading.Thread(target=delete_row)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    statuses = {kind: status for kind, status, _ in results}
    assert statuses.get("delete") == 200, results
    assert statuses.get("mark_all") == 200, results

    db = SessionLocal()
    try:
        assert db.query(Notification).filter(Notification.id.in_(created_ids)).count() == 2
        assert db.query(NotificationRead).filter(NotificationRead.notification_id.in_(created_ids)).count() == 2
    finally:
        db.close()
