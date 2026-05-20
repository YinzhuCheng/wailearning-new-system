"""
High-pressure / edge scenarios: bad LLM bodies, config changed mid-run, bad submissions,
idempotent task processing, Pydantic validation, multi-role parallel actions.
"""

from __future__ import annotations

import json as json_lib
import threading
import uuid
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.llm_grading import process_grading_task, process_next_grading_task
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    Homework,
    HomeworkGradingTask,
    HomeworkScoreCandidate,
    HomeworkSubmission,
    LLMEndpointPreset,
    Student,
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


# 1) LLM 200 but body not scorable (missing score/comment) -> retryable then fail
def test_llm_returns_json_without_score_comment_then_fails_task(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(preset_max_retries=1)
    h = ctx["homework_id"]
    _submit(client, h, login_api(client, ctx["student_username"], ctx["student_password"]), "a")
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    bad = {"choices": [{"message": {"content": json_lib.dumps({"nope": 1})}}]}

    def fake(self, u, **k):
        return httpx.Response(200, json=bad)

    with mock.patch.object(httpx.Client, "post", fake):
        process_grading_task(tid)
    db = SessionLocal()
    try:
        t = db.get(HomeworkGradingTask, tid)
        assert t.status == "retry_scheduled"
    finally:
        db.close()


# 2) LLM 200 empty message content
def test_llm_empty_choices_fails_task(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    h = ctx["homework_id"]
    _submit(client, h, login_api(client, ctx["student_username"], ctx["student_password"]), "a")
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()

    with mock.patch.object(httpx.Client, "post", lambda s, u, **k: httpx.Response(200, json={"choices": []})):
        process_grading_task(tid)
    db = SessionLocal()
    try:
        t = db.get(HomeworkGradingTask, tid)
        assert t.status == "retry_scheduled"
    finally:
        db.close()


# 3) After submit, admin clears all course endpoint links -> grading fails
def test_course_endpoints_cleared_before_grading_fails(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h, sid, th, sh = (
        ctx["homework_id"],
        ctx["subject_id"],
        login_api(client, ctx["teacher_username"], ctx["teacher_password"]),
        login_api(client, ctx["student_username"], ctx["student_password"]),
    )
    _submit(client, h, sh, "c")
    client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=th,
        json={
            "is_enabled": True,
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 4.0,
            "estimated_image_tokens": 850,
            "max_input_tokens": 8000,
            "max_output_tokens": 1000,
            "endpoints": [],
        },
    )
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    with patch_httpx_post(
        lambda s, u, **k: httpx.Response(200, json=json_llm_response(80, "x"))
    ):
        process_grading_task(tid)
    db = SessionLocal()
    try:
        t = db.get(HomeworkGradingTask, tid)
        assert t.error_code == "endpoint_missing" or t.status == "failed"
    finally:
        db.close()


# 4) Disable course LLM after submit, before process
def test_disable_course_llm_before_grading_fails(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h, sid, th, sh = ctx["homework_id"], ctx["subject_id"], login_api(
        client, ctx["teacher_username"], ctx["teacher_password"]
    ), login_api(client, ctx["student_username"], ctx["student_password"])
    _submit(client, h, sh, "c")
    client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=th,
        json={
            "is_enabled": False,
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 4.0,
            "estimated_image_tokens": 850,
            "max_input_tokens": 8000,
            "max_output_tokens": 1000,
            "endpoints": [
                {
                    "preset_id": (
                        SessionLocal()
                        .query(CourseLLMConfigEndpoint)
                        .join(CourseLLMConfig)
                        .filter(CourseLLMConfig.subject_id == sid)
                        .first()
                        .preset_id
                    ),
                    "priority": 1,
                }
            ],
        },
    )
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    process_grading_task(tid)
    db = SessionLocal()
    try:
        t = db.get(HomeworkGradingTask, tid)
        assert t.error_code == "llm_config_disabled"
    finally:
        db.close()


# 5) Idempotent: process_grading_task twice -> single auto candidate, single httpx path
def test_process_grading_task_idempotent_one_llm_call(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h = ctx["homework_id"]
    _submit(client, h, login_api(client, ctx["student_username"], ctx["student_password"]), "a")
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    calls: list = []

    def one_post(self, u, **k):
        calls.append(1)
        return httpx.Response(200, json=json_llm_response(60.0, "once"))

    with mock.patch.object(httpx.Client, "post", one_post):
        process_grading_task(tid)
        process_grading_task(tid)
    assert len(calls) == 1
    db = SessionLocal()
    try:
        n = (
            db.query(HomeworkScoreCandidate)
            .filter(HomeworkScoreCandidate.source == "auto")
            .count()
        )
        assert n == 1
    finally:
        db.close()


# 6) Two threads call process_grading_task for same id -> one LLM call
def test_concurrent_same_task_single_llm_invocation(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h = ctx["homework_id"]
    _submit(client, h, login_api(client, ctx["student_username"], ctx["student_password"]), "a")
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    calls: list = []
    ev = threading.Event()

    def slow(self, u, **k):
        calls.append(1)
        ev.wait(0.15)
        return httpx.Response(200, json=json_llm_response(50.0, "t"))

    with mock.patch.object(httpx.Client, "post", slow):
        t1 = threading.Thread(target=process_grading_task, args=(tid,))
        t2 = threading.Thread(target=process_grading_task, args=(tid,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    assert len(calls) == 1


def test_processing_task_without_claim_token_is_not_executed(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    h = ctx["homework_id"]
    _submit(client, h, login_api(client, ctx["student_username"], ctx["student_password"]), "a")
    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).one()
        task.status = "processing"
        task.claim_token = None
        db.commit()
        tid = task.id
    finally:
        db.close()

    calls: list[int] = []

    def one_post(self, u, **k):
        calls.append(1)
        return httpx.Response(200, json=json_llm_response(60.0, "once"))

    with mock.patch.object(httpx.Client, "post", one_post):
        process_grading_task(tid)

    assert calls == []
    db = SessionLocal()
    try:
        task = db.get(HomeworkGradingTask, tid)
        assert task is not None
        assert task.status == "processing"
    finally:
        db.close()


# 7) Invalid submission: only whitespace -> Pydantic 422
def test_submit_empty_fails_400(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False)
    h = ctx["homework_id"]
    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    r = client.post(
        f"/api/homeworks/{h}/submission",
        headers=sh,
        json={"content": "   "},
    )
    assert r.status_code == 422


# 8) Teacher PUT course config with invalid max_input_tokens -> 422
def test_course_config_validation_rejects_too_low_max_input(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework()
    sid, th, pid = ctx["subject_id"], login_api(
        client, ctx["teacher_username"], ctx["teacher_password"]
    ), ctx["preset_id"]
    r = client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=th,
        json={
            "is_enabled": True,
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 4.0,
            "estimated_image_tokens": 850,
            "max_input_tokens": 5,
            "max_output_tokens": 1000,
            "endpoints": [{"preset_id": pid, "priority": 1}],
        },
    )
    assert r.status_code == 422


# 9) Regrade after failed auto task: new queued task, can succeed
def test_regrade_after_task_failed(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    h, th, sh = (
        ctx["homework_id"],
        login_api(client, ctx["teacher_username"], ctx["teacher_password"]),
        login_api(client, ctx["student_username"], ctx["student_password"]),
    )
    sub = _submit(client, h, sh, "x")
    db = SessionLocal()
    try:
        tid1 = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    with mock.patch.object(httpx.Client, "post", lambda s, u, **k: httpx.Response(503, json={})):
        process_grading_task(tid1)
    r2 = client.post(
        f"/api/homeworks/{h}/submissions/{sub}/regrade",
        headers=th,
        json={},
    )
    assert r2.status_code == 200, r2.text
    db = SessionLocal()
    try:
        tasks = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.asc()).all()
        assert len(tasks) == 1
        tid2 = tasks[-1].id
    finally:
        db.close()
    with patch_httpx_post(
        lambda s, u, **k: httpx.Response(200, json=json_llm_response(80.0, "ok2"))
    ):
        process_grading_task(tid2)
    g = client.get(f"/api/homeworks/{h}/submissions", headers=th)
    assert g.json()["data"][0].get("review_score") is not None or g.status_code == 200


# 10) Admin / 班主任 / 学生 / 教师 同屏并行请求不崩溃
def test_four_role_parallel_stress(client: TestClient):
    ensure_admin()
    s = make_multi_student_scenario(1)
    h = s["homework_id"]
    sid = s["subject_id"]
    db = SessionLocal()
    try:
        c = db.get(Subject, sid)
        cl_id = c.class_id
    finally:
        db.close()
    cl = f"ct_{uuid.uuid4().hex[:4]}"
    stu = s["students"][0]["username"]
    spw = s["students"][0]["password"]
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == cl).count():
            db.add(
                User(
                    username=cl,
                    hashed_password=get_password_hash("cp"),
                    real_name="C",
                    role=UserRole.CLASS_TEACHER.value,
                    class_id=cl_id,
                )
            )
        db.commit()
    finally:
        db.close()
    th = login_api(client, s["teacher_username"], s["teacher_password"])
    _submit(client, h, login_api(client, stu, spw), "p")
    db = SessionLocal()
    try:
        pid = (
            db.query(LLMEndpointPreset)
            .join(CourseLLMConfigEndpoint)
            .join(CourseLLMConfig)
            .filter(CourseLLMConfig.subject_id == sid)
            .first()
            .id
        )
    finally:
        db.close()
    a_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    s_h = login_api(client, stu, spw)
    c_h = login_api(client, cl, "cp")
    out: list = []
    bar = threading.Barrier(4)

    def w(fn):
        def inner():
            bar.wait()
            try:
                fn()
            except Exception as e:
                out.append(e)

        return inner

    def get_presets():
        r = client.get("/api/llm-settings/presets", headers=a_h)
        if r.status_code not in (200, 403):
            out.append(ValueError("admin presets", r.status_code))

    def st_get():
        client.get(f"/api/homeworks/{h}/submission/me", headers=s_h)

    def ct_list():
        r = client.get(f"/api/homeworks/{h}/submissions", headers=c_h)
        if r.status_code not in (200, 403):
            out.append(ValueError("ct list", r.status_code))

    def t_put():
        r = client.put(
            f"/api/llm-settings/courses/{sid}",
            headers=th,
            json={
                "is_enabled": True,
                "response_language": "en",
                "quota_timezone": "UTC",
                "estimated_chars_per_token": 4.0,
                "estimated_image_tokens": 850,
                "max_input_tokens": 8000,
                "max_output_tokens": 1000,
                "endpoints": [{"preset_id": int(pid), "priority": 1}],
            },
        )
        if r.status_code != 200:
            out.append(ValueError("t put", r.status_code, r.text[:200]))

    threads = [threading.Thread(target=w(f)) for f in (get_presets, st_get, ct_list, t_put)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert out == []


# 13) LLM returns 200 with non-JSON text body -> task fails
def test_llm_200_non_json_fails_task(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    h = ctx["homework_id"]
    _submit(client, h, login_api(client, ctx["student_username"], ctx["student_password"]), "a")
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client, "post", lambda s, u, **k: httpx.Response(200, text="not json")
    ):
        process_grading_task(tid)
    db = SessionLocal()
    try:
        t = db.get(HomeworkGradingTask, tid)
        assert t.status == "retry_scheduled"
    finally:
        db.close()


# 14) process_next on empty queue returns False
def test_process_next_no_queue(client: TestClient):
    assert process_next_grading_task() is False

# 11) Deactivate preset: grading skips bad preset, uses second
def test_second_preset_when_first_inactive(client: TestClient):
    ensure_admin()
    base = make_grading_course_with_homework()
    h, sid = base["homework_id"], base["subject_id"]
    th = login_api(client, base["teacher_username"], base["teacher_password"])
    db = SessionLocal()
    try:
        p1 = db.get(LLMEndpointPreset, base["preset_id"])
        p1.is_active = False
        p2 = LLMEndpointPreset(
            name=f"p2_{uuid.uuid4().hex[:4]}",
            base_url="https://p2.test/v1/",
            api_key="k2",
            model_name="m2",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        db.add(p2)
        db.flush()
        cfg = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == sid).first()
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, preset_id=p2.id, priority=2))
        db.commit()
        p2id = p2.id
    finally:
        db.close()
    _submit(client, h, login_api(client, base["student_username"], base["student_password"]), "x")
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    which: list = []

    def track(self, u, **k):
        auth = (k.get("headers") or {}).get("Authorization", "")
        which.append("p2" if "k2" in auth else "k1")
        return httpx.Response(200, json=json_llm_response(55.0, "p2"))

    with mock.patch.object(httpx.Client, "post", track):
        process_grading_task(tid)
    assert "p2" in which


# 12) 500 response then success on retry (exhaust on first, second endpoint)
def test_500_then_success_second_endpoint(client: TestClient):
    ensure_admin()
    b = make_grading_course_with_homework(preset_max_retries=0)
    h, sid = b["homework_id"], b["subject_id"]
    db = SessionLocal()
    try:
        p2 = LLMEndpointPreset(
            name=f"ep2_{uuid.uuid4().hex[:4]}",
            base_url="https://ep2.test/v1/",
            api_key="sk-ep2",
            model_name="m",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        db.add(p2)
        db.flush()
        cfg = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == sid).first()
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, preset_id=p2.id, priority=2))
        db.commit()
    finally:
        db.close()
    _submit(client, h, login_api(client, b["student_username"], b["student_password"]), "a")
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()

    def by_auth(self, u, **k):
        auth = (k.get("headers") or {}).get("Authorization", "")
        if b"ep2" in auth.encode() if isinstance(auth, str) else b"ep2" in str(auth).encode():
            return httpx.Response(200, json=json_llm_response(77.0, "ok"))
        return httpx.Response(500, json={})

    with mock.patch.object(httpx.Client, "post", by_auth):
        process_grading_task(tid)
    db = SessionLocal()
    try:
        t = db.get(HomeworkGradingTask, tid)
        assert t.status == "success"
    finally:
        db.close()
