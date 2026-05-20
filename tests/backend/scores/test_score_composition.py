"""Course score composition, grade scheme, and score appeals API."""

from __future__ import annotations

import threading
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.api.routers import scores as scores_router
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import HomeworkScoreCandidate, HomeworkSubmission, Notification
from apps.backend.courseeval_backend.domains.scores.composition import (
    OTHER_DAILY_EXAM_TYPE,
)
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework


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
    return TestClient(app)


def _set_homework_score(db, homework_id: int, student_id: int, teacher_id: int, score: float):
    sub = (
        db.query(HomeworkSubmission)
        .filter(HomeworkSubmission.homework_id == homework_id, HomeworkSubmission.student_id == student_id)
        .first()
    )
    assert sub and sub.latest_attempt_id
    db.add(
        HomeworkScoreCandidate(
            attempt_id=sub.latest_attempt_id,
            homework_id=homework_id,
            student_id=student_id,
            source="teacher",
            score=score,
            created_by=teacher_id,
        )
    )
    sub.review_score = score
    db.commit()


def test_grade_scheme_and_weights_must_sum_to_100(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    sid = ctx["subject_id"]

    r = client.put(f"/api/scores/grade-scheme/{sid}", headers=th, json={"homework_weight": 30, "extra_daily_weight": 20})
    assert r.status_code == 200, r.text

    bad = client.put(
        f"/api/scores/weights/{sid}",
        headers=th,
        json={"items": [{"exam_type": "期中", "weight": 60}]},
    )
    assert bad.status_code == 400

    ok = client.put(
        f"/api/scores/weights/{sid}",
        headers=th,
        json={"items": [{"exam_type": "期中", "weight": 50}]},
    )
    assert ok.status_code == 200, ok.text


def test_composition_and_student_appeal(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    sid = ctx["subject_id"]
    hid = ctx["homework_id"]
    cid = ctx["class_id"]
    sem = "2026-春季"

    client.put(f"/api/scores/grade-scheme/{sid}", headers=th, json={"homework_weight": 30, "extra_daily_weight": 20})
    client.put(
        f"/api/scores/weights/{sid}",
        headers=th,
        json={"items": [{"exam_type": "期末", "weight": 50}]},
    )

    assert client.post(f"/api/homeworks/{hid}/submission", headers=sh, json={"content": "hw"}).status_code == 200
    db = SessionLocal()
    try:
        _set_homework_score(db, hid, ctx["student_id"], ctx["teacher_id"], 80.0)
    finally:
        db.close()

    r_other = client.post(
        "/api/scores",
        headers=th,
        json={
            "student_id": ctx["student_id"],
            "subject_id": sid,
            "class_id": cid,
            "score": 90,
            "exam_type": OTHER_DAILY_EXAM_TYPE,
            "semester": sem,
        },
    )
    assert r_other.status_code == 200, r_other.text

    r_exam = client.post(
        "/api/scores",
        headers=th,
        json={
            "student_id": ctx["student_id"],
            "subject_id": sid,
            "class_id": cid,
            "score": 70,
            "exam_type": "期末",
            "semester": sem,
        },
    )
    assert r_exam.status_code == 200, r_exam.text

    comp = client.get(
        "/api/scores/composition/me",
        headers=sh,
        params={"subject_id": sid, "semester": sem},
    )
    assert comp.status_code == 200, comp.text
    body = comp.json()
    assert body["homework_average_percent"] == 80.0
    assert body["other_daily_score"] == 90.0
    assert body["exam_scores"].get("期末") == 70.0
    assert body["weighted_total"] is not None
    assert abs(body["weighted_total"] - 77.0) < 0.01

    ap = client.post(
        f"/api/scores/appeals?subject_id={sid}",
        headers=sh,
        json={"semester": sem, "target_component": "total", "reason_text": "总分有疑问"},
    )
    assert ap.status_code == 200, ap.text

    lst = client.get("/api/scores/appeals", headers=th, params={"subject_id": sid})
    assert lst.status_code == 200
    assert len(lst.json()) >= 1

    aid = lst.json()[0]["id"]
    up = client.put(
        f"/api/scores/appeals/{aid}",
        headers=th,
        json={"teacher_response": "已复核，成绩无误。", "status": "resolved"},
    )
    assert up.status_code == 200, up.text
    assert up.json()["status"] == "resolved"


def test_duplicate_pending_appeal_rejected(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    sid = ctx["subject_id"]
    sem = "2026-春季"

    client.put(f"/api/scores/grade-scheme/{sid}", headers=th, json={"homework_weight": 30, "extra_daily_weight": 20})
    client.put(
        f"/api/scores/weights/{sid}",
        headers=th,
        json={"items": [{"exam_type": "期末", "weight": 50}]},
    )

    p1 = client.post(
        f"/api/scores/appeals?subject_id={sid}",
        headers=sh,
        json={"semester": sem, "target_component": "total", "reason_text": "第一次"},
    )
    assert p1.status_code == 200, p1.text
    p2 = client.post(
        f"/api/scores/appeals?subject_id={sid}",
        headers=sh,
        json={"semester": sem, "target_component": "total", "reason_text": "第二次"},
    )
    assert p2.status_code == 400


def test_appeal_response_invalid_status(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    sid = ctx["subject_id"]
    sem = "2026-春季"

    client.put(f"/api/scores/grade-scheme/{sid}", headers=th, json={"homework_weight": 30, "extra_daily_weight": 20})
    client.put(
        f"/api/scores/weights/{sid}",
        headers=th,
        json={"items": [{"exam_type": "期末", "weight": 50}]},
    )

    ap = client.post(
        f"/api/scores/appeals?subject_id={sid}",
        headers=sh,
        json={"semester": sem, "target_component": "homework_avg", "reason_text": "作业分"},
    )
    assert ap.status_code == 200, ap.text
    aid = ap.json()["id"]

    bad = client.put(
        f"/api/scores/appeals/{aid}",
        headers=th,
        json={"teacher_response": "说明", "status": "not_a_status"},
    )
    assert bad.status_code == 400


@pytest.mark.parametrize(
    ("terminal_status", "next_status"),
    [
        ("resolved", "pending"),
        ("rejected", "resolved"),
    ],
)
def test_terminal_score_appeal_cannot_be_reopened_or_rewritten(
    client: TestClient,
    terminal_status: str,
    next_status: str,
):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    sid = ctx["subject_id"]
    sem = f"2026-lock-{terminal_status}"

    created = client.post(
        f"/api/scores/appeals?subject_id={sid}",
        headers=sh,
        json={"semester": sem, "target_component": "total", "reason_text": f"lock after {terminal_status}"},
    )
    assert created.status_code == 200, created.text
    appeal_id = int(created.json()["id"])

    first_response = f"teacher marked {terminal_status}"
    finalized = client.put(
        f"/api/scores/appeals/{appeal_id}",
        headers=th,
        json={"teacher_response": first_response, "status": terminal_status},
    )
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["status"] == terminal_status

    blocked = client.put(
        f"/api/scores/appeals/{appeal_id}",
        headers=th,
        json={"teacher_response": f"stale rewrite to {next_status}", "status": next_status},
    )
    assert blocked.status_code == 409, blocked.text

    listed = client.get("/api/scores/appeals", headers=th, params={"subject_id": sid})
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json() if int(item["id"]) == appeal_id)
    assert row["status"] == terminal_status
    assert row["teacher_response"] == first_response


def test_concurrent_conflicting_terminal_score_appeal_updates_do_not_both_succeed(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    sid = ctx["subject_id"]

    created = client.post(
        f"/api/scores/appeals?subject_id={sid}",
        headers=sh,
        json={"semester": "2026-concurrent-terminal", "target_component": "total", "reason_text": "race terminal states"},
    )
    assert created.status_code == 200, created.text
    appeal_id = int(created.json()["id"])

    barrier = threading.Barrier(2)
    statuses: list[int] = []
    errors: list[str] = []
    original = scores_router.mark_score_appeal_notifications_handled

    def delayed_mark(db, target_appeal_id: int, status: str) -> None:
        if int(target_appeal_id) == appeal_id:
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
        original(db, target_appeal_id, status)

    def worker(status: str, teacher_response: str) -> None:
        try:
            with TestClient(app) as thread_client:
                resp = thread_client.put(
                    f"/api/scores/appeals/{appeal_id}",
                    headers=th,
                    json={"teacher_response": teacher_response, "status": status},
                )
            statuses.append(resp.status_code)
        except Exception as exc:  # pragma: no cover
            errors.append(str(exc))

    with mock.patch.object(scores_router, "mark_score_appeal_notifications_handled", side_effect=delayed_mark):
        threads = [
            threading.Thread(target=worker, args=("resolved", "resolved first")),
            threading.Thread(target=worker, args=("rejected", "rejected second")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert not errors
    assert sorted(statuses) == [200, 409]


def test_teacher_cannot_leave_score_appeal_pending_after_writing_a_response(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    sid = ctx["subject_id"]

    created = client.post(
        f"/api/scores/appeals?subject_id={sid}",
        headers=sh,
        json={"semester": "2026-pending-rewrite", "target_component": "total", "reason_text": "teacher should decide terminally"},
    )
    assert created.status_code == 200, created.text
    appeal_id = int(created.json()["id"])

    pending = client.put(
        f"/api/scores/appeals/{appeal_id}",
        headers=th,
        json={"teacher_response": "looked at it but keeping pending", "status": "pending"},
    )
    assert pending.status_code == 400, pending.text


def test_finalized_score_appeal_exact_replay_is_idempotent_without_extra_notification_rows(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    sid = ctx["subject_id"]

    created = client.post(
        f"/api/scores/appeals?subject_id={sid}",
        headers=sh,
        json={"semester": "2026-terminal-idempotent", "target_component": "total", "reason_text": "same terminal replay"},
    )
    assert created.status_code == 200, created.text
    appeal_id = int(created.json()["id"])

    first = client.put(
        f"/api/scores/appeals/{appeal_id}",
        headers=th,
        json={"teacher_response": "resolved once", "status": "resolved"},
    )
    assert first.status_code == 200, first.text

    db = SessionLocal()
    try:
        before_rows = db.query(Notification).filter(Notification.related_score_appeal_id == appeal_id).all()
        assert len(before_rows) == 1
    finally:
        db.close()

    replay = client.put(
        f"/api/scores/appeals/{appeal_id}",
        headers=th,
        json={"teacher_response": "resolved once", "status": "resolved"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "resolved"
    assert replay.json()["teacher_response"] == "resolved once"

    db = SessionLocal()
    try:
        after_rows = db.query(Notification).filter(Notification.related_score_appeal_id == appeal_id).all()
        assert len(after_rows) == 1
    finally:
        db.close()


def test_homework_target_score_appeal_links_notification_to_homework(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    sid = ctx["subject_id"]
    hid = ctx["homework_id"]
    sem = "2026-春季"

    client.put(f"/api/scores/grade-scheme/{sid}", headers=th, json={"homework_weight": 30, "extra_daily_weight": 20})
    assert client.post(f"/api/homeworks/{hid}/submission", headers=sh, json={"content": "hw appeal body"}).status_code == 200

    db = SessionLocal()
    try:
        _set_homework_score(db, hid, ctx["student_id"], ctx["teacher_id"], 88.0)
    finally:
        db.close()

    ap = client.post(
        f"/api/scores/appeals?subject_id={sid}",
        headers=sh,
        json={
            "semester": sem,
            "target_component": "homework",
            "homework_id": hid,
            "reason_text": "这次作业评分我有异议，想请老师复核。"
        },
    )
    assert ap.status_code == 200, ap.text
    body = ap.json()
    assert body["target_component"] == "homework"
    assert body["homework_id"] == hid
    assert body["homework_title"]
    assert body["score_id"] is None

    db = SessionLocal()
    try:
        rows = (
            db.query(Notification)
            .filter(Notification.related_score_appeal_id == body["id"])
            .all()
        )
        assert rows
        assert all(row.related_homework_id == hid for row in rows)
    finally:
        db.close()
