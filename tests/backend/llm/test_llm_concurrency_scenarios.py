"""
Interleaving and multi-user LLM grading scenarios (threads + mocked httpx).
"""

from __future__ import annotations

import threading
import uuid
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.llm_grading import get_best_score_candidate, process_grading_task, process_next_grading_task
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    HomeworkAttempt,
    HomeworkGradingTask,
    HomeworkSubmission,
    LLMTokenUsageLog,
    Subject,
    User,
    UserRole,
)
from tests.scenarios.llm_scenario import ensure_admin, json_llm_response, login_api, make_grading_course_with_homework, make_multi_student_scenario, patch_httpx_post


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


def _submit(client: TestClient, hid: int, headers: dict, content: str) -> int:
    r = client.post(f"/api/homeworks/{hid}/submission", headers=headers, json={"content": content})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# --- 1) Three students submit in parallel: three tasks, distinct students ---

def test_three_students_concurrent_submissions(client: TestClient):
    ensure_admin()
    s = make_multi_student_scenario(3)
    h = s["homework_id"]
    hdrs = [login_api(client, st["username"], st["password"]) for st in s["students"]]
    barrier = threading.Barrier(3)
    out: list[tuple[int, int]] = []
    lock = threading.Lock()

    def go(i: int):
        barrier.wait()
        r = client.post(
            f"/api/homeworks/{h}/submission",
            headers=hdrs[i],
            json={"content": f"body{i}"},
        )
        with lock:
            out.append((i, r.status_code))

    threads = [threading.Thread(target=go, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(c == 200 for _, c in out)
    db = SessionLocal()
    try:
        assert db.query(HomeworkGradingTask).filter(HomeworkGradingTask.homework_id == h).count() == 3
    finally:
        db.close()


# --- 2) Same student two submissions: two attempts, two tasks, latest attempt id on summary ---

def test_same_student_two_submissions_two_tasks(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h = ctx["homework_id"]
    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    _submit(client, h, sh, "first")
    _submit(client, h, sh, "second")
    db = SessionLocal()
    try:
        assert db.query(HomeworkAttempt).filter(HomeworkAttempt.homework_id == h).count() == 2
        assert db.query(HomeworkGradingTask).filter(HomeworkGradingTask.homework_id == h).count() == 2
    finally:
        db.close()


# --- 3) process_next processes queue FIFO (two students) ---

def test_process_next_fifo_two_tasks(client: TestClient):
    ensure_admin()
    s = make_multi_student_scenario(2)
    h = s["homework_id"]
    for st in s["students"]:
        _submit(client, h, login_api(client, st["username"], st["password"]), "x")
    with patch_httpx_post(
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(55.0, "z"))
    ):
        assert process_next_grading_task() is True
        assert process_next_grading_task() is True
        assert process_next_grading_task() is False
    db = SessionLocal()
    try:
        assert db.query(HomeworkGradingTask).filter(HomeworkGradingTask.status == "success").count() == 2
    finally:
        db.close()


# --- 4) Two parallel GETs of submission list: same JSON ---

def test_parallel_get_submissions_list_consistent(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h = ctx["homework_id"]
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    _submit(client, h, login_api(client, ctx["student_username"], ctx["student_password"]), "g")

    results: list[dict] = []
    lock = threading.Lock()

    def fetch():
        r = client.get(f"/api/homeworks/{h}/submissions", headers=th)
        with lock:
            results.append(r.json())

    t1, t2 = threading.Thread(target=fetch), threading.Thread(target=fetch)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert results[0] == results[1]


# --- 5) Teacher sets score before LLM finishes: auto runs but summary keeps teacher on that attempt ---

def test_teacher_score_before_auto_summary_shows_teacher(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h, th, sth = ctx["homework_id"], login_api(client, ctx["teacher_username"], ctx["teacher_password"]), login_api(
        client, ctx["student_username"], ctx["student_password"]
    )
    sub_id = _submit(client, h, sth, "x")
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()
    client.put(
        f"/api/homeworks/{h}/submissions/{sub_id}/review",
        headers=th,
        json={"review_score": 95.0, "review_comment": "教师先改"},
    )
    with patch_httpx_post(lambda self, u, **k: httpx.Response(200, json=json_llm_response(12.0, "llm低分"))):
        process_grading_task(tid)
    r = client.get(f"/api/homeworks/{h}/submission/me", headers=sth)
    assert r.json()["review_score"] == 95.0


# --- 6) After auto gives high score, lower teacher still wins on same attempt's summary ---

def test_lower_teacher_beats_higher_auto_on_summary(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h, th, sth = ctx["homework_id"], login_api(client, ctx["teacher_username"], ctx["teacher_password"]), login_api(
        client, ctx["student_username"], ctx["student_password"]
    )
    sub = _submit(client, h, sth, "y")
    db = SessionLocal()
    try:
        tsub = db.query(HomeworkSubmission).filter(HomeworkSubmission.id == sub).first()
        att_id = tsub.latest_attempt_id
        tid2 = (
            db.query(HomeworkGradingTask)
            .order_by(HomeworkGradingTask.id.desc())
            .first()
            .id
        )
    finally:
        db.close()
    with patch_httpx_post(lambda self, u, **k: httpx.Response(200, json=json_llm_response(99.0, "llm高"))):
        process_grading_task(tid2)
    r0 = client.get(f"/api/homeworks/{h}/submission/me", headers=sth)
    assert r0.json()["review_score"] == 99.0
    client.put(
        f"/api/homeworks/{h}/submissions/{sub}/review",
        headers=th,
        json={"review_score": 40.0, "review_comment": "严一点"},
    )
    r = client.get(f"/api/homeworks/{h}/submission/me", headers=sth)
    assert r.json()["review_score"] == 40.0
    db = SessionLocal()
    try:
        best = get_best_score_candidate(
            db,
            h,
            ctx["student_id"],
            latest_attempt_id=att_id,
        )
        assert best is not None
        assert best.source == "teacher"
        assert best.score == 40.0
    finally:
        db.close()


# --- 6b) Effective summary score may come from an earlier attempt when it beats a later auto grade ---

def test_new_attempt_auto_visible_when_teacher_scored_only_previous_attempt(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h, th, sth = ctx["homework_id"], login_api(client, ctx["teacher_username"], ctx["teacher_password"]), login_api(
        client, ctx["student_username"], ctx["student_password"]
    )
    s1 = _submit(client, h, sth, "a1")
    db = SessionLocal()
    try:
        t1 = db.query(HomeworkGradingTask).one()
        att1 = t1.attempt_id
    finally:
        db.close()
    client.put(
        f"/api/homeworks/{h}/submissions/{s1}/review",
        headers=th,
        json={"attempt_id": att1, "review_score": 50.0, "review_comment": "v1"},
    )
    s2 = _submit(client, h, sth, "a2")
    db = SessionLocal()
    try:
        t2 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first()
        assert t2.status == "queued"
        t2id = t2.id
    finally:
        db.close()
    with patch_httpx_post(lambda self, u, **k: httpx.Response(200, json=json_llm_response(80.0, "auto2"))):
        process_grading_task(t2id)
    r = client.get(f"/api/homeworks/{h}/submission/me", headers=sth)
    assert r.json()["review_score"] == 80.0


# --- 7) task skips LLM if teacher already graded this attempt (race: teacher first) ---

def test_task_skips_when_teacher_scored_this_attempt(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h, th, sth = ctx["homework_id"], login_api(client, ctx["teacher_username"], ctx["teacher_password"]), login_api(
        client, ctx["student_username"], ctx["student_password"]
    )
    sub = _submit(client, h, sth, "z")
    db = SessionLocal()
    try:
        att_id = (
            db.query(HomeworkSubmission)
            .filter(HomeworkSubmission.id == sub)
            .first()
            .latest_attempt_id
        )
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    client.put(
        f"/api/homeworks/{h}/submissions/{sub}/review",
        headers=th,
        json={"attempt_id": att_id, "review_score": 88.0, "review_comment": "抢跑"},
    )
    calls: list = []

    def no_net(self, *a, **k):
        calls.append(1)
        raise AssertionError("LLM should not be called when teacher already graded this attempt")

    with mock.patch.object(httpx.Client, "post", no_net):
        process_grading_task(tid)
    assert calls == []


# --- 8) Second task sees quota already exhausted (mock) → fail at precheck, one usage log from first ---

def test_second_task_hits_token_cap_after_first_billed(client: TestClient):
    ensure_admin()
    s = make_multi_student_scenario(2)
    h = s["homework_id"]
    for st in s["students"]:
        _submit(client, h, login_api(client, st["username"], st["password"]), "cap")
    db = SessionLocal()
    try:
        tids = [row.id for row in db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.asc()).all()]
    finally:
        db.close()
    with patch_httpx_post(
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(90.0, "c"))
    ), mock.patch(
        "apps.backend.courseeval_backend.llm_grading.reserve_quota_tokens", side_effect=[(True, None), (False, "quota_exceeded_student")]
    ):
        process_grading_task(tids[0])
        process_grading_task(tids[1])
    db = SessionLocal()
    try:
        assert db.query(LLMTokenUsageLog).count() == 1
        tasks = {t.id: t for t in db.query(HomeworkGradingTask).all()}
        assert tasks[tids[0]].status == "success"
        assert tasks[tids[1]].status == "failed"
    finally:
        db.close()


# --- 9) Class teacher visibility does not imply submission-management access ---

def test_class_teacher_cannot_read_submissions_for_visible_course(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h, sid, cid = ctx["homework_id"], ctx["subject_id"], None
    db = SessionLocal()
    try:
        subj = db.get(Subject, sid)
        cid = subj.class_id
    finally:
        db.close()
    u = f"cls_{uuid.uuid4().hex[:5]}"
    db = SessionLocal()
    try:
        db.add(
            User(
                username=u,
                hashed_password=get_password_hash("cpt"),
                real_name="Classteacher",
                role=UserRole.CLASS_TEACHER.value,
                class_id=cid,
            )
        )
        db.commit()
    finally:
        db.close()
    _submit(client, h, login_api(client, ctx["student_username"], ctx["student_password"]), "h")
    ch = login_api(client, u, "cpt")
    r = client.get(f"/api/homeworks/{h}/submissions", headers=ch)
    assert r.status_code == 403, r.text


# --- 10) Auto fails with 401; teacher can still score manually after ---

def test_non_retryable_401_failed_task_teacher_still_reviews(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    h, th, sth = (
        ctx["homework_id"],
        login_api(client, ctx["teacher_username"], ctx["teacher_password"]),
        login_api(client, ctx["student_username"], ctx["student_password"]),
    )
    sub = _submit(client, h, sth, "fail")
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    with patch_httpx_post(
        lambda self, url, **kwargs: httpx.Response(401, json={"e": 1})
    ):
        process_grading_task(tid)
    r = client.put(
        f"/api/homeworks/{h}/submissions/{sub}/review",
        headers=th,
        json={"review_score": 72.0, "review_comment": "人工给分"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["review_score"] == 72.0
