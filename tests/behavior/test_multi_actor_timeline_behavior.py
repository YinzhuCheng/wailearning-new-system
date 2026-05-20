"""M1–M5: Multi-role timelines (HTTP + synchronous grading worker calls)."""

from __future__ import annotations

import random
import threading
import uuid
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.llm_grading import claim_grading_tasks_batch, process_grading_task
from apps.backend.courseeval_backend.domains.llm.token_quota import (
    resolve_max_parallel_grading_tasks,
)
from apps.backend.courseeval_backend.db.models import Homework, HomeworkGradingTask
from tests.scenarios.llm_scenario import ensure_admin, json_llm_response, login_api, make_grading_course_with_homework, make_multi_student_scenario


def test_m1_teacher_saves_config_before_both_grading_runs_use_new_prompt(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    db = SessionLocal()
    try:
        hw = db.query(Homework).filter(Homework.id == ctx["homework_id"]).first()
        hw.max_submissions = 5
        db.commit()
    finally:
        db.close()

    st = login_api(client, ctx["student_username"], ctx["student_password"])
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    assert (
        client.post(
            f"/api/homeworks/{ctx['homework_id']}/submission",
            headers=st,
            json={"content": "first draft"},
        ).status_code
        == 200
    )

    marker = f"TEACHER_MARKER_{uuid.uuid4().hex[:8]}"
    assert (
        client.put(
            f"/api/llm-settings/courses/{ctx['subject_id']}",
            headers=th,
            json={
                "is_enabled": True,
                "teacher_prompt": marker,
                "endpoints": [{"preset_id": ctx["preset_id"], "priority": 1}],
            },
        ).status_code
        == 200
    )

    assert (
        client.post(
            f"/api/homeworks/{ctx['homework_id']}/submission",
            headers=st,
            json={"content": "second draft"},
        ).status_code
        == 200
    )

    db = SessionLocal()
    try:
        tids = [
            t.id
            for t in db.query(HomeworkGradingTask)
            .filter(HomeworkGradingTask.homework_id == ctx["homework_id"])
            .order_by(HomeworkGradingTask.id.asc())
            .all()
        ]
    finally:
        db.close()
    assert len(tids) == 2

    bodies: list[dict] = []

    def fake_post(self, url, **kwargs):
        bodies.append(kwargs.get("json") or {})
        return httpx.Response(200, json=json_llm_response(72.0, "graded"))

    with mock.patch.object(httpx.Client, "post", fake_post):
        for tid in tids:
            process_grading_task(tid)

    assert len(bodies) == 2
    for b in bodies:
        assert marker in str(b)


def test_m2_two_students_parallel_tasks_both_complete(client: TestClient) -> None:
    ensure_admin()
    s = make_multi_student_scenario(2)
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    client.put("/api/llm-settings/admin/quota-policy", headers=ah, json={"max_parallel_grading_tasks": 2})
    h = s["homework_id"]
    for st in s["students"]:
        hdr = login_api(client, st["username"], st["password"])
        r = client.post(f"/api/homeworks/{h}/submission", headers=hdr, json={"content": st["username"]})
        assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        tids = [t.id for t in db.query(HomeworkGradingTask).filter(HomeworkGradingTask.homework_id == h).all()]
    finally:
        db.close()
    assert len(tids) == 2

    with mock.patch.object(
        httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(55.0, "ok"))
    ):
        for tid in tids:
            process_grading_task(tid)

    db = SessionLocal()
    try:
        ok = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.homework_id == h, HomeworkGradingTask.status == "success").count()
        assert ok == 2
    finally:
        db.close()


def test_m3_admin_lowers_cap_second_task_hits_precheck(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(daily_student_token_limit=500_000)
    st = login_api(client, ctx["student_username"], ctx["student_password"])
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")

    assert (
        client.post(
            f"/api/homeworks/{ctx['homework_id']}/submission",
            headers=st,
            json={"content": "uses tokens"},
        ).status_code
        == 200
    )
    db = SessionLocal()
    try:
        tid1 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(80.0, "ok"))
    ):
        process_grading_task(tid1)

    client.put(
        "/api/llm-settings/admin/students/{}/quota-override".format(ctx["student_id"]),
        headers=ah,
        json={"daily_tokens": 25},
    )

    assert (
        client.post(
            f"/api/homeworks/{ctx['homework_id']}/submission",
            headers=st,
            json={"content": "should fail quota"},
        ).status_code
        == 200
    )
    db = SessionLocal()
    try:
        tid2 = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()
    process_grading_task(tid2)
    db = SessionLocal()
    try:
        t2 = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid2).first()
        assert t2.status == "failed"
        assert t2.error_code == "quota_exceeded_student"
    finally:
        db.close()


def test_m4_claim_batch_respects_parallel_cap(client: TestClient) -> None:
    ensure_admin()
    s = make_multi_student_scenario(5)
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    client.put("/api/llm-settings/admin/quota-policy", headers=ah, json={"max_parallel_grading_tasks": 3})
    h = s["homework_id"]
    for st in s["students"]:
        hdr = login_api(client, st["username"], st["password"])
        assert (
            client.post(f"/api/homeworks/{h}/submission", headers=hdr, json={"content": st["username"]}).status_code
            == 200
        )

    db = SessionLocal()
    try:
        cap = resolve_max_parallel_grading_tasks(db)
        claimed = claim_grading_tasks_batch(cap)
        assert len(claimed) == 3
        claimed2 = claim_grading_tasks_batch(cap)
        assert len(claimed2) == 2
    finally:
        db.close()


def test_m4b_claim_batch_randomizes_first_wave_selection(client: TestClient) -> None:
    ensure_admin()
    s = make_multi_student_scenario(5)
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    client.put("/api/llm-settings/admin/quota-policy", headers=ah, json={"max_parallel_grading_tasks": 3})
    h = s["homework_id"]
    for st in s["students"]:
        hdr = login_api(client, st["username"], st["password"])
        assert client.post(f"/api/homeworks/{h}/submission", headers=hdr, json={"content": st["username"]}).status_code == 200

    picks_seen: list[list[int]] = []

    def fake_sample(seq, k):
        chosen = list(reversed(list(seq)[:k]))
        picks_seen.append([task.id for task in chosen])
        return chosen

    db = SessionLocal()
    try:
        with mock.patch("apps.backend.courseeval_backend.llm_grading.random.sample", fake_sample):
            claimed = claim_grading_tasks_batch(3)
        assert len(claimed) == 3
        expected_default = [row[0] for row in db.query(HomeworkGradingTask.id).order_by(HomeworkGradingTask.id.asc()).limit(3).all()]
        assert claimed != expected_default
        assert picks_seen and claimed == picks_seen[0]
    finally:
        db.close()


def test_m5_concurrent_admin_and_teacher_writes_no_500(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    errors: list[BaseException] = []
    lock = threading.Lock()

    def admin_loop():
        try:
            for i in range(5):
                r = client.put(
                    "/api/llm-settings/admin/quota-policy",
                    headers=ah,
                    json={"default_daily_student_tokens": 100_000 + i},
                )
                assert r.status_code == 200, r.text
        except BaseException as exc:
            with lock:
                errors.append(exc)

    def teacher_loop():
        try:
            for i in range(5):
                r = client.put(
                    f"/api/llm-settings/courses/{ctx['subject_id']}",
                    headers=th,
                    json={
                        "is_enabled": True,
                        "teacher_prompt": f"concurrent-{i}",
                        "endpoints": [{"preset_id": ctx["preset_id"], "priority": 1}],
                    },
                )
                assert r.status_code == 200, r.text
        except BaseException as exc:
            with lock:
                errors.append(exc)

    t1 = threading.Thread(target=admin_loop)
    t2 = threading.Thread(target=teacher_loop)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert not errors
