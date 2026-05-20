"""Red-team checks for homework appeal state transitions and gating."""

from __future__ import annotations

import threading
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.api.routers import homework as homework_router
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import HomeworkGradeAppeal, Notification
from tests.scenarios.llm_scenario import ensure_admin, login_api, make_grading_course_with_homework


def _reset_db() -> None:
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()


def test_student_cannot_appeal_when_auto_grading_failed_without_score_or_comment():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework()
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "failed appeal gate"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    from apps.backend.courseeval_backend.llm_grading import process_grading_task
    from apps.backend.courseeval_backend.db.models import HomeworkGradingTask
    from unittest import mock
    import httpx

    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(500, text="llm failed hard without payload"),
    ):
        process_grading_task(tid)

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "this should stay blocked after grading failed"},
    )
    assert appeal.status_code == 400, appeal.text


def test_acknowledge_appeal_marks_notifications_as_acknowledged_not_resolved():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "ack title guard"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 91, "review_comment": "pre-appeal score"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please recheck this scoring decision carefully"},
    )
    assert appeal.status_code == 200, appeal.text

    noted = client.get("/api/notifications", headers=teacher_h)
    assert noted.status_code == 200, noted.text
    before = [row for row in noted.json().get("data", []) if row.get("notification_kind") == "grade_appeal"]
    assert before
    assert all("resolved" not in str(row.get("title") or "") for row in before)

    ack = client.post(f"/api/homeworks/{hid}/submissions/{sub_id}/appeal/acknowledge", headers=teacher_h)
    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == "acknowledged"

    after_resp = client.get("/api/notifications", headers=teacher_h)
    assert after_resp.status_code == 200, after_resp.text
    after = [row for row in after_resp.json().get("data", []) if row.get("notification_kind") == "grade_appeal"]
    assert after
    assert all(row.get("appeal_status") == "acknowledged" for row in after)
    assert all("resolved" not in str(row.get("title") or "") for row in after)


def test_review_after_acknowledge_moves_appeal_to_resolved_state():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "ack then resolve"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 70, "review_comment": "initial score before appeal"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please check this scoring decision one more time"},
    )
    assert appeal.status_code == 200, appeal.text

    ack = client.post(f"/api/homeworks/{hid}/submissions/{sub_id}/appeal/acknowledge", headers=teacher_h)
    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == "acknowledged"

    resolved = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 85, "review_comment": "resolved after teacher review"},
    )
    assert resolved.status_code == 200, resolved.text

    from apps.backend.courseeval_backend.db.models import HomeworkGradeAppeal

    db = SessionLocal()
    try:
        row = db.query(HomeworkGradeAppeal).filter(HomeworkGradeAppeal.submission_id == sub_id).first()
        assert row is not None
        assert row.status == "resolved"
    finally:
        db.close()

    after_resp = client.get("/api/notifications", headers=teacher_h)
    assert after_resp.status_code == 200, after_resp.text
    after = [row for row in after_resp.json().get("data", []) if row.get("notification_kind") == "grade_appeal"]
    assert after
    assert any(row.get("appeal_status") == "resolved" for row in after)


def test_llm_regrade_resolves_pending_homework_appeal_after_success():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=True, course_llm_enabled=True)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "appeal then regrade"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    from apps.backend.courseeval_backend.llm_grading import process_grading_task
    from apps.backend.courseeval_backend.db.models import HomeworkGradingTask, HomeworkGradeAppeal, HomeworkSubmission
    from tests.scenarios.llm_scenario import json_llm_response
    from unittest import mock
    import httpx

    db = SessionLocal()
    try:
        first_tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(61.0, "first auto score")),
    ):
        process_grading_task(first_tid)

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please re-run grading because the first result missed points"},
    )
    assert appeal.status_code == 200, appeal.text

    regrade = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/regrade",
        headers=teacher_h,
        json={},
    )
    assert regrade.status_code == 200, regrade.text

    db = SessionLocal()
    try:
        second_tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(88.0, "regrade fixed result")),
    ):
        process_grading_task(second_tid)

    db = SessionLocal()
    try:
        row = db.query(HomeworkGradeAppeal).filter(HomeworkGradeAppeal.submission_id == sub_id).first()
        assert row is not None
        summary = db.query(HomeworkSubmission).filter(HomeworkSubmission.id == sub_id).first()
        assert summary is not None
        assert summary.latest_task_status == "success"
        assert summary.review_score is not None
        assert row.status == "resolved"
    finally:
        db.close()

    after_resp = client.get("/api/notifications", headers=teacher_h)
    assert after_resp.status_code == 200, after_resp.text
    after = [row for row in after_resp.json().get("data", []) if row.get("notification_kind") == "grade_appeal"]
    assert after
    assert any(row.get("appeal_status") == "resolved" for row in after)


def test_notification_detail_after_resolved_appeal_uses_resolved_title_not_acknowledged_title():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "detail title drift"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 73, "review_comment": "before appeal"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please check the scoring details again"},
    )
    assert appeal.status_code == 200, appeal.text

    ack = client.post(f"/api/homeworks/{hid}/submissions/{sub_id}/appeal/acknowledge", headers=teacher_h)
    assert ack.status_code == 200, ack.text

    resolved = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 86, "review_comment": "after resolution"},
    )
    assert resolved.status_code == 200, resolved.text

    listed = client.get("/api/notifications", headers=teacher_h)
    assert listed.status_code == 200, listed.text
    grade_rows = [row for row in listed.json().get("data", []) if row.get("notification_kind") == "grade_appeal"]
    assert grade_rows
    notif_id = grade_rows[0]["id"]

    detail = client.get(f"/api/notifications/{notif_id}", headers=teacher_h)
    assert detail.status_code == 200, detail.text
    title = str(detail.json().get("title") or "")
    assert detail.json().get("appeal_status") == "resolved"
    assert "宸查槄" not in title


def test_resolved_grade_appeal_notification_exposes_appeal_status_to_clients():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "status field gap"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 71, "review_comment": "before appeal"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please check this score and comment once more"},
    )
    assert appeal.status_code == 200, appeal.text

    resolved = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 89, "review_comment": "resolved after teacher review"},
    )
    assert resolved.status_code == 200, resolved.text

    listed = client.get("/api/notifications", headers=teacher_h)
    assert listed.status_code == 200, listed.text
    grade_rows = [row for row in listed.json().get("data", []) if row.get("notification_kind") == "grade_appeal"]
    assert grade_rows
    assert any(row.get("appeal_status") == "resolved" for row in grade_rows)


def test_resolved_score_appeal_notification_exposes_appeal_status_to_clients():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    created = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_h,
        json={"semester": "2026-fall", "target_component": "total", "reason_text": "score appeal status field"},
    )
    assert created.status_code == 200, created.text
    appeal_id = created.json()["id"]

    resolved = client.put(
        f"/api/scores/appeals/{appeal_id}",
        headers=teacher_h,
        json={"teacher_response": "resolved", "status": "resolved"},
    )
    assert resolved.status_code == 200, resolved.text

    listed = client.get("/api/notifications", headers=teacher_h)
    assert listed.status_code == 200, listed.text
    rows = [row for row in listed.json().get("data", []) if row.get("notification_kind") == "score_grade_appeal"]
    assert rows
    assert any(row.get("appeal_status") == "resolved" for row in rows)


def test_pending_score_appeal_notification_exposes_appeal_status_to_clients():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    created = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_h,
        json={"semester": "2026-fall", "target_component": "total", "reason_text": "score appeal pending state"},
    )
    assert created.status_code == 200, created.text

    listed = client.get("/api/notifications", headers=teacher_h)
    assert listed.status_code == 200, listed.text
    rows = [row for row in listed.json().get("data", []) if row.get("notification_kind") == "score_grade_appeal"]
    assert rows
    assert any(row.get("appeal_status") == "pending" for row in rows)
    assert any(row.get("related_score_appeal_id") for row in rows)


def test_resolved_score_appeal_notification_keeps_target_id_for_read_only_deeplink():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    created = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_h,
        json={"semester": "2026-fall", "target_component": "total", "reason_text": "score appeal read-only deep-link"},
    )
    assert created.status_code == 200, created.text
    appeal_id = created.json()["id"]

    resolved = client.put(
        f"/api/scores/appeals/{appeal_id}",
        headers=teacher_h,
        json={"teacher_response": "resolved", "status": "resolved"},
    )
    assert resolved.status_code == 200, resolved.text

    listed = client.get("/api/notifications", headers=teacher_h)
    assert listed.status_code == 200, listed.text
    rows = [row for row in listed.json().get("data", []) if row.get("notification_kind") == "score_grade_appeal"]
    assert rows
    assert any(
        row.get("appeal_status") == "resolved" and int(row.get("related_score_appeal_id") or 0) == int(appeal_id)
        for row in rows
    )


def test_homework_appeal_notification_list_and_detail_keep_same_acknowledged_status():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "list detail parity"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 76, "review_comment": "before parity appeal"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please check parity between notification list and detail"},
    )
    assert appeal.status_code == 200, appeal.text

    ack = client.post(f"/api/homeworks/{hid}/submissions/{sub_id}/appeal/acknowledge", headers=teacher_h)
    assert ack.status_code == 200, ack.text

    listed = client.get("/api/notifications", headers=teacher_h)
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json().get("data", []) if item.get("notification_kind") == "grade_appeal")
    assert row.get("appeal_status") == "acknowledged"

    detail = client.get(f"/api/notifications/{row['id']}", headers=teacher_h)
    assert detail.status_code == 200, detail.text
    assert detail.json().get("appeal_status") == "acknowledged"


def test_rejected_score_appeal_notification_exposes_terminal_status_and_consistent_detail():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    created = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_h,
        json={"semester": "2026-fall", "target_component": "total", "reason_text": "score appeal rejected projection"},
    )
    assert created.status_code == 200, created.text
    appeal_id = created.json()["id"]

    rejected = client.put(
        f"/api/scores/appeals/{appeal_id}",
        headers=teacher_h,
        json={"teacher_response": "rejected with explanation", "status": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text

    listed = client.get("/api/notifications", headers=teacher_h)
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json().get("data", []) if item.get("notification_kind") == "score_grade_appeal")
    assert row.get("appeal_status") == "rejected"
    assert int(row.get("related_score_appeal_id") or 0) == int(appeal_id)
    assert row.get("appeal_status") == "rejected"

    detail = client.get(f"/api/notifications/{row['id']}", headers=teacher_h)
    assert detail.status_code == 200, detail.text
    assert detail.json().get("appeal_status") == "rejected"
    assert detail.json().get("appeal_status") == "rejected"
    assert "pending" not in str(detail.json().get("content") or "")


def test_rejected_homework_appeal_exposes_terminal_status_teacher_response_and_consistent_notification_projection():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "homework reject projection"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 72, "review_comment": "before reject appeal"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please reject this appeal with an explicit explanation"},
    )
    assert appeal.status_code == 200, appeal.text

    rejected = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=teacher_h,
        json={"teacher_response": "rejected because the original scoring already matches the rubric", "status": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert "teacher_response" in rejected.json()

    mine = client.get(f"/api/homeworks/{hid}/submission/me", headers=student_h)
    assert mine.status_code == 200, mine.text
    assert mine.json()["appeal_status"] == "rejected"
    assert "original scoring already matches the rubric" in str(mine.json().get("appeal_teacher_response") or "")

    history = client.get(f"/api/homeworks/{hid}/submission/me/history", headers=student_h)
    assert history.status_code == 200, history.text
    assert history.json()["summary"]["appeal_status"] == "rejected"
    assert "original scoring already matches the rubric" in str(history.json()["summary"].get("appeal_teacher_response") or "")

    listed = client.get("/api/notifications", headers=teacher_h)
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json().get("data", []) if item.get("notification_kind") == "grade_appeal")
    assert row.get("appeal_status") == "rejected"
    assert row.get("appeal_status") == "rejected"

    detail = client.get(f"/api/notifications/{row['id']}", headers=teacher_h)
    assert detail.status_code == 200, detail.text
    assert detail.json().get("appeal_status") == "rejected"
    assert detail.json().get("appeal_status") == "rejected"
    assert "pending" not in str(detail.json().get("content") or "")


def test_teacher_submission_detail_row_exposes_homework_appeal_reason_and_teacher_response():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "teacher detail row appeal fields"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 81, "review_comment": "before detailed appeal response"},
    )
    assert review.status_code == 200, review.text

    appeal_reason = "please include the derivation detail that was ignored"
    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": appeal_reason},
    )
    assert appeal.status_code == 200, appeal.text

    resolved = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=teacher_h,
        json={"teacher_response": "resolved after rechecking the derivation", "status": "resolved"},
    )
    assert resolved.status_code == 200, resolved.text

    detail = client.get(f"/api/homeworks/{hid}/submissions/{sub_id}/status", headers=teacher_h)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["appeal_status"] == "resolved"
    assert body["appeal_reason_text"] == appeal_reason
    assert "resolved after rechecking the derivation" in str(body.get("appeal_teacher_response") or "")


def test_concurrent_homework_appeal_acknowledge_and_resolve_do_not_both_win():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "ack resolve race"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 77, "review_comment": "before concurrent appeal race"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please review the score and comment carefully"},
    )
    assert appeal.status_code == 200, appeal.text

    barrier = threading.Barrier(2)
    statuses: list[int] = []
    errors: list[str] = []

    def ack_one() -> None:
        try:
            with TestClient(app) as thread_client:
                barrier.wait(timeout=5)
                resp = thread_client.post(f"/api/homeworks/{hid}/submissions/{sub_id}/appeal/acknowledge", headers=teacher_h)
                statuses.append(resp.status_code)
        except Exception as exc:  # pragma: no cover
            errors.append(str(exc))

    def resolve_one() -> None:
        try:
            with TestClient(app) as thread_client:
                barrier.wait(timeout=5)
                resp = thread_client.put(
                    f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
                    headers=teacher_h,
                    json={"teacher_response": "resolved during race", "status": "resolved"},
                )
                statuses.append(resp.status_code)
        except Exception as exc:  # pragma: no cover
            errors.append(str(exc))

    threads = [threading.Thread(target=ack_one), threading.Thread(target=resolve_one)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    assert sorted(statuses) in ([200, 200], [200, 409])

    db = SessionLocal()
    try:
        row = db.query(HomeworkGradeAppeal).filter(HomeworkGradeAppeal.submission_id == sub_id).one()
        assert row.status in {"acknowledged", "resolved"}
        notes = db.query(Notification).filter(Notification.related_appeal_id == row.id).all()
        assert len(notes) == 1
        assert notes[0].notification_kind == "grade_appeal"
    finally:
        db.close()


def test_final_homework_appeal_replay_keeps_notification_projection_stable():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "replay stable"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 84, "review_comment": "before replay"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please recheck the grading details"},
    )
    assert appeal.status_code == 200, appeal.text

    first = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=teacher_h,
        json={"teacher_response": "resolved once", "status": "resolved"},
    )
    assert first.status_code == 200, first.text

    replay = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=teacher_h,
        json={"teacher_response": "resolved once", "status": "resolved"},
    )
    assert replay.status_code == 200, replay.text

    db = SessionLocal()
    try:
        row = db.query(HomeworkGradeAppeal).filter(HomeworkGradeAppeal.submission_id == sub_id).one()
        assert row.status == "resolved"
        assert row.teacher_response == "resolved once"
        notes = db.query(Notification).filter(Notification.related_appeal_id == row.id).all()
        assert len(notes) == 1
        assert notes[0].notification_kind == "grade_appeal"
    finally:
        db.close()


def test_notification_detail_for_homework_appeal_stays_consistent_after_terminal_transition():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "detail consistency"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 80, "review_comment": "before consistency"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please verify list and detail stay aligned"},
    )
    assert appeal.status_code == 200, appeal.text

    ack = client.post(f"/api/homeworks/{hid}/submissions/{sub_id}/appeal/acknowledge", headers=teacher_h)
    assert ack.status_code == 200, ack.text

    resolved = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=teacher_h,
        json={"teacher_response": "resolved for consistency", "status": "resolved"},
    )
    assert resolved.status_code == 200, resolved.text

    listed = client.get("/api/notifications", headers=teacher_h)
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json().get("data", []) if item.get("notification_kind") == "grade_appeal")
    assert row.get("appeal_status") == "resolved"
    detail = client.get(f"/api/notifications/{row['id']}", headers=teacher_h)
    assert detail.status_code == 200, detail.text
    assert detail.json().get("appeal_status") == "resolved"
    assert detail.json().get("appeal_status") == "resolved"


def test_terminal_homework_appeal_cannot_be_rewritten_by_stale_teacher_request():
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "terminal rewrite guard"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 86, "review_comment": "before terminal rewrite"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please protect this appeal from stale rewrites"},
    )
    assert appeal.status_code == 200, appeal.text

    resolved = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=teacher_h,
        json={"teacher_response": "resolved first", "status": "resolved"},
    )
    assert resolved.status_code == 200, resolved.text

    stale = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=teacher_h,
        json={"teacher_response": "stale rewrite to rejected", "status": "rejected"},
    )
    assert stale.status_code == 409, stale.text

    db = SessionLocal()
    try:
        row = db.query(HomeworkGradeAppeal).filter(HomeworkGradeAppeal.submission_id == sub_id).one()
        assert row.status == "resolved"
        assert row.teacher_response == "resolved first"
    finally:
        db.close()


def test_stale_reject_request_cannot_overwrite_already_resolved_homework_appeal(monkeypatch):
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "stale reject overwrite"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 87, "review_comment": "before stale reject overwrite"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please prevent stale reject from overwriting resolve"},
    )
    assert appeal.status_code == 200, appeal.text

    stale_loaded = threading.Event()
    allow_stale_continue = threading.Event()
    original_can_transition = homework_router.can_transition_homework_appeal_status

    def blocking_can_transition(current_status, next_status):
        if next_status == "rejected":
            stale_loaded.set()
            assert allow_stale_continue.wait(timeout=5), "stale reject thread did not resume in time"
        return original_can_transition(current_status, next_status)

    monkeypatch.setattr(homework_router, "can_transition_homework_appeal_status", blocking_can_transition)

    stale_result: dict[str, object] = {}

    def stale_reject() -> None:
        with TestClient(app) as thread_client:
            stale_result["response"] = thread_client.put(
                f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
                headers=teacher_h,
                json={"teacher_response": "stale reject should lose", "status": "rejected"},
            )

    thread = threading.Thread(target=stale_reject, name="stale-reject-thread")
    thread.start()
    assert stale_loaded.wait(timeout=5), "stale reject request did not reach the loaded-state barrier"

    resolved = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=teacher_h,
        json={"teacher_response": "resolved wins", "status": "resolved"},
    )
    assert resolved.status_code == 200, resolved.text

    allow_stale_continue.set()
    thread.join(timeout=10)
    assert not thread.is_alive(), "stale reject thread did not finish"
    stale_response = stale_result["response"]
    assert stale_response.status_code == 409, stale_response.text

    db = SessionLocal()
    try:
        row = db.query(HomeworkGradeAppeal).filter(HomeworkGradeAppeal.submission_id == sub_id).one()
        assert row.status == "resolved"
        assert row.teacher_response == "resolved wins"
        notes = db.query(Notification).filter(Notification.related_appeal_id == row.id).all()
        assert len(notes) == 1
        assert notes[0].notification_kind == "grade_appeal"
    finally:
        db.close()


def test_stale_resolve_request_cannot_overwrite_already_rejected_homework_appeal(monkeypatch):
    _reset_db()
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    client = TestClient(app)
    student_h = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_h = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    hid = ctx["homework_id"]

    sub = client.post(f"/api/homeworks/{hid}/submission", headers=student_h, json={"content": "stale resolve overwrite"})
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    review = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/review",
        headers=teacher_h,
        json={"review_score": 78, "review_comment": "before stale resolve overwrite"},
    )
    assert review.status_code == 200, review.text

    appeal = client.post(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=student_h,
        json={"reason_text": "please prevent stale resolve from overwriting reject"},
    )
    assert appeal.status_code == 200, appeal.text

    stale_loaded = threading.Event()
    allow_stale_continue = threading.Event()
    original_can_transition = homework_router.can_transition_homework_appeal_status

    def blocking_can_transition(current_status, next_status):
        if next_status == "resolved":
            stale_loaded.set()
            assert allow_stale_continue.wait(timeout=5), "stale resolve thread did not resume in time"
        return original_can_transition(current_status, next_status)

    monkeypatch.setattr(homework_router, "can_transition_homework_appeal_status", blocking_can_transition)

    stale_result: dict[str, object] = {}

    def stale_resolve() -> None:
        with TestClient(app) as thread_client:
            stale_result["response"] = thread_client.put(
                f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
                headers=teacher_h,
                json={"teacher_response": "stale resolve should lose", "status": "resolved"},
            )

    thread = threading.Thread(target=stale_resolve, name="stale-resolve-thread")
    thread.start()
    assert stale_loaded.wait(timeout=5), "stale resolve request did not reach the loaded-state barrier"

    rejected = client.put(
        f"/api/homeworks/{hid}/submissions/{sub_id}/appeal",
        headers=teacher_h,
        json={"teacher_response": "rejected wins", "status": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text

    allow_stale_continue.set()
    thread.join(timeout=10)
    assert not thread.is_alive(), "stale resolve thread did not finish"
    stale_response = stale_result["response"]
    assert stale_response.status_code == 409, stale_response.text

    db = SessionLocal()
    try:
        row = db.query(HomeworkGradeAppeal).filter(HomeworkGradeAppeal.submission_id == sub_id).one()
        assert row.status == "rejected"
        assert row.teacher_response == "rejected wins"
        notes = db.query(Notification).filter(Notification.related_appeal_id == row.id).all()
        assert len(notes) == 1
        assert notes[0].notification_kind == "grade_appeal"
    finally:
        db.close()
