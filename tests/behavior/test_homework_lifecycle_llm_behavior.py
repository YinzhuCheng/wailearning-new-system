"""H1–H3: Homework lifecycle vs LLM grading queue."""

from __future__ import annotations

from unittest import mock

import httpx
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.llm_grading import process_grading_task
from apps.backend.courseeval_backend.db.models import Homework, HomeworkGradingTask, HomeworkSubmission, LLMTokenUsageLog
from tests.scenarios.llm_scenario import ensure_admin, json_llm_response, login_api, make_grading_course_with_homework


def test_h1_disable_auto_grading_with_queued_task_fails_processing(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=st,
        json={"content": "queued"},
    )
    client.put(
        f"/api/homeworks/{ctx['homework_id']}",
        headers=th,
        json={"auto_grading_enabled": False},
    )
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()
    process_grading_task(tid)
    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).first()
        assert task.status == "failed"
        assert task.error_code == "auto_grading_disabled"
    finally:
        db.close()


def test_h2_regrade_creates_new_grading_task(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    sub = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=st,
        json={"content": "first try"},
    )
    assert sub.status_code == 200, sub.text
    sid = sub.json()["id"]
    db = SessionLocal()
    try:
        n1 = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.homework_id == ctx["homework_id"]).count()
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(50.0, "auto"))
    ):
        db = SessionLocal()
        try:
            tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
        finally:
            db.close()
        process_grading_task(tid)

    reg = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submissions/{sid}/regrade",
        headers=th,
        json={},
    )
    assert reg.status_code == 200, reg.text
    db = SessionLocal()
    try:
        n2 = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.homework_id == ctx["homework_id"]).count()
        assert n2 == n1 + 1
    finally:
        db.close()


def test_h2_delete_homework_removes_grading_tasks(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=st,
        json={"content": "to delete"},
    )
    hid = ctx["homework_id"]
    r_del = client.delete(f"/api/homeworks/{hid}", headers=th)
    assert r_del.status_code == 200, r_del.text
    db = SessionLocal()
    try:
        assert db.query(Homework).filter(Homework.id == hid).first() is None
        assert db.query(HomeworkGradingTask).filter(HomeworkGradingTask.homework_id == hid).count() == 0
        assert db.query(HomeworkSubmission).filter(HomeworkSubmission.homework_id == hid).count() == 0
    finally:
        db.close()


def test_h3_multiple_attempts_each_graded_usage_accumulates(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(daily_student_token_limit=500_000)
    db = SessionLocal()
    try:
        hw = db.query(Homework).filter(Homework.id == ctx["homework_id"]).first()
        hw.max_submissions = 5
        db.commit()
    finally:
        db.close()

    st = login_api(client, ctx["student_username"], ctx["student_password"])
    for i in range(3):
        r = client.post(
            f"/api/homeworks/{ctx['homework_id']}/submission",
            headers=st,
            json={"content": f"attempt {i}"},
        )
        assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tids = [
            row[0]
            for row in db.query(HomeworkGradingTask.id).filter(HomeworkGradingTask.homework_id == ctx["homework_id"]).all()
        ]
    finally:
        db.close()
    assert len(tids) == 3

    fake = lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(80.0 + float(kwargs.get("n", 0)), "ok"))
    with mock.patch.object(httpx.Client, "post", fake):
        for tid in tids:
            process_grading_task(tid)

    db = SessionLocal()
    try:
        logs = db.query(LLMTokenUsageLog).filter(LLMTokenUsageLog.student_id == ctx["student_id"]).all()
        assert len(logs) >= 3
        assert sum(int(x.total_tokens or 0) for x in logs) >= 45
    finally:
        db.close()
