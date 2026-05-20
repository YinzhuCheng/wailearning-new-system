"""
PCQ1-PCQ5: System-wide LLM quota pool with course attribution, template clone,
preset purge + re-sync, and student-quotas API.

The daily cap and quota calendar come from admin policy / student override.
Course IDs stay on logs and student summaries for attribution only; they do not
create independent daily token pools.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.llm_grading import ensure_course_llm_config, process_grading_task
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    Homework,
    HomeworkGradingTask,
    LLMEndpointPreset,
    Student,
    Subject,
    User,
    UserRole,
)
from tests.scenarios.llm_scenario import ensure_admin, json_llm_response, login_api, make_grading_course_with_homework


def _validated_preset_row(*, uid: str, name_suffix: str = "") -> LLMEndpointPreset:
    return LLMEndpointPreset(
        name=f"pcq-preset-{uid}{name_suffix}",
        base_url="https://api.virtual.test/v1/",
        api_key="sk-test",
        model_name="virtual",
        max_retries=0,
        initial_backoff_seconds=1,
        is_active=True,
        supports_vision=True,
        validation_status="validated",
        text_validation_status="passed",
        vision_validation_status="passed",
    )


def test_pcq1_two_courses_share_system_pool_but_keep_course_attribution(client: TestClient) -> None:
    """
    Same numeric daily cap: grading reserves large estimated prompt budgets, so the cap must be generous.
    After two successful runs (one per course), each course's ledger must show ~only that course's prompt
    tokens (would fail if logs/reservations were still merged across subjects into one pool).
    """
    ensure_admin()
    ctx = make_grading_course_with_homework(daily_student_token_limit=500_000)
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        teacher = db.query(User).filter(User.id == ctx["teacher_id"]).first()
        klass = db.query(Class).filter(Class.id == ctx["class_id"]).first()
        stud = db.query(Student).filter(Student.id == ctx["student_id"]).first()
        assert teacher and klass and stud

        p2 = _validated_preset_row(uid=uid, name_suffix="-b")
        db.add(p2)
        db.flush()

        course_b = Subject(name=f"pcq-course-b-{uid}", teacher_id=teacher.id, class_id=klass.id)
        db.add(course_b)
        db.flush()

        db.add(
            CourseEnrollment(
                subject_id=course_b.id,
                student_id=stud.id,
                class_id=klass.id,
                enrollment_type="required",
            )
        )
        cfg_b = CourseLLMConfig(
            subject_id=course_b.id,
            is_enabled=True,
            max_input_tokens=16000,
            max_output_tokens=1200,
        )
        db.add(cfg_b)
        db.flush()
        db.add(CourseLLMConfigEndpoint(config_id=cfg_b.id, preset_id=p2.id, priority=1))

        hw_b = Homework(
            title="pcq hw b",
            content="b",
            class_id=klass.id,
            subject_id=course_b.id,
            max_score=100,
            auto_grading_enabled=True,
            created_by=teacher.id,
        )
        db.add(hw_b)
        db.commit()
        hw_b_id = hw_b.id
        subject_b_id = course_b.id
    finally:
        db.close()

    st = login_api(client, ctx["student_username"], ctx["student_password"])
    assert (
        client.post(
            f"/api/homeworks/{ctx['homework_id']}/submission",
            headers=st,
            json={"content": "course A burn"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/homeworks/{hw_b_id}/submission",
            headers=st,
            json={"content": "course B burn"},
        ).status_code
        == 200
    )

    db = SessionLocal()
    try:
        tid_a = (
            db.query(HomeworkGradingTask)
            .filter(HomeworkGradingTask.homework_id == ctx["homework_id"])
            .order_by(HomeworkGradingTask.id.desc())
            .first()
            .id
        )
        tid_b = (
            db.query(HomeworkGradingTask)
            .filter(HomeworkGradingTask.homework_id == hw_b_id)
            .order_by(HomeworkGradingTask.id.desc())
            .first()
            .id
        )
    finally:
        db.close()

    fake = lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(70.0, "ok"))
    with mock.patch.object(httpx.Client, "post", fake):
        process_grading_task(tid_a)
        process_grading_task(tid_b)

    db = SessionLocal()
    try:
        ta = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid_a).first()
        tb = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid_b).first()
        assert ta.status == "success", (ta.error_code, ta.error_message)
        assert tb.status == "success", (tb.error_code, tb.error_message)
    finally:
        db.close()

    qa = client.get(f"/api/llm-settings/courses/student-quota/{ctx['subject_id']}", headers=st).json()
    qb = client.get(f"/api/llm-settings/courses/student-quota/{subject_b_id}", headers=st).json()
    ua_total = int(qa["student_used_tokens_today"] or 0)
    ub_total = int(qb["student_used_tokens_today"] or 0)
    ua_course = int(qa["course_used_tokens_today"] or 0)
    ub_course = int(qb["course_used_tokens_today"] or 0)
    assert ua_total == ub_total == 20
    assert ua_course == 10 and ub_course == 10


def test_pcq2_empty_course_clones_llm_from_latest_validated_peer(client: TestClient) -> None:
    """Teacher GET course LLM when the row exists but has zero endpoints must pull template from another course."""
    ensure_admin()
    ctx = make_grading_course_with_homework()
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        teacher = db.query(User).filter(User.id == ctx["teacher_id"]).first()
        klass = db.query(Class).filter(Class.id == ctx["class_id"]).first()
        stud = db.query(Student).filter(Student.id == ctx["student_id"]).first()

        course_c = Subject(name=f"pcq-empty-{uid}", teacher_id=teacher.id, class_id=klass.id)
        db.add(course_c)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=course_c.id,
                student_id=stud.id,
                class_id=klass.id,
                enrollment_type="required",
            )
        )
        cfg_c = CourseLLMConfig(subject_id=course_c.id, is_enabled=False)
        db.add(cfg_c)
        db.commit()
        subject_c_id = course_c.id
    finally:
        db.close()

    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.get(f"/api/llm-settings/courses/{subject_c_id}", headers=th)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "quota_timezone" not in body
    assert len(body.get("endpoints") or []) >= 1
    assert body["endpoints"][0]["preset_id"] == ctx["preset_id"]


def test_pcq3_deactivate_primary_preset_then_peer_course_resyncs_from_survivor(client: TestClient) -> None:
    """
    Course A and C share preset p1; B uses p2. After p1 is deactivated, C loses endpoints and the next
    ensure_course_llm_config must clone from B (still valid).
    """
    ensure_admin()
    ctx = make_grading_course_with_homework()
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        teacher = db.query(User).filter(User.id == ctx["teacher_id"]).first()
        klass = db.query(Class).filter(Class.id == ctx["class_id"]).first()
        stud = db.query(Student).filter(Student.id == ctx["student_id"]).first()

        p2 = _validated_preset_row(uid=uid, name_suffix="-survivor")
        db.add(p2)
        db.flush()

        course_b = Subject(name=f"pcq-survivor-{uid}", teacher_id=teacher.id, class_id=klass.id)
        db.add(course_b)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=course_b.id,
                student_id=stud.id,
                class_id=klass.id,
                enrollment_type="required",
            )
        )
        cfg_b = CourseLLMConfig(
            subject_id=course_b.id,
            is_enabled=True,
            max_input_tokens=8000,
            max_output_tokens=600,
        )
        db.add(cfg_b)
        db.flush()
        db.add(CourseLLMConfigEndpoint(config_id=cfg_b.id, preset_id=p2.id, priority=1))

        course_c = Subject(name=f"pcq-shadow-{uid}", teacher_id=teacher.id, class_id=klass.id)
        db.add(course_c)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=course_c.id,
                student_id=stud.id,
                class_id=klass.id,
                enrollment_type="required",
            )
        )
        cfg_a = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == ctx["subject_id"]).one()
        cfg_c = CourseLLMConfig(
            subject_id=course_c.id,
            is_enabled=True,
            max_input_tokens=16000,
            max_output_tokens=1200,
        )
        db.add(cfg_c)
        db.flush()
        db.add(CourseLLMConfigEndpoint(config_id=cfg_c.id, preset_id=ctx["preset_id"], priority=1))

        now = datetime.now(timezone.utc)
        cfg_b.updated_at = now
        cfg_a.updated_at = now
        cfg_c.updated_at = now
        db.commit()

        subject_b_id = course_b.id
        subject_c_id = course_c.id
        preset_survivor_id = p2.id
        teacher_id = teacher.id
    finally:
        db.close()

    ah = login_api(client, "pytest_admin", "pytest_admin_pass")
    r_off = client.put(
        f"/api/llm-settings/presets/{ctx['preset_id']}",
        headers=ah,
        json={"is_active": False},
    )
    assert r_off.status_code == 200, r_off.text

    db = SessionLocal()
    try:
        cfg_c2 = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == subject_c_id).one()
        assert (
            db.query(CourseLLMConfigEndpoint)
            .filter(CourseLLMConfigEndpoint.config_id == cfg_c2.id)
            .count()
            == 0
        )
    finally:
        db.close()

    db = SessionLocal()
    try:
        cfg_c3 = ensure_course_llm_config(db, subject_c_id, teacher_id)
        db.commit()
        db.refresh(cfg_c3)
        ep_ids = [
            r.preset_id
            for r in db.query(CourseLLMConfigEndpoint)
            .filter(CourseLLMConfigEndpoint.config_id == cfg_c3.id)
            .all()
        ]
        assert ep_ids == [preset_survivor_id]
    finally:
        db.close()

    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r_view = client.get(f"/api/llm-settings/courses/{subject_c_id}", headers=th)
    assert r_view.status_code == 200
    eps = r_view.json().get("endpoints") or []
    assert len(eps) == 1
    assert eps[0]["preset_id"] == preset_survivor_id

    r_b = client.get(f"/api/llm-settings/courses/{subject_b_id}", headers=th)
    assert len(r_b.json().get("endpoints") or []) == 1


def test_pcq4_student_quotas_summary_splits_usage_by_subject(client: TestClient) -> None:
    """GET student-quotas must attribute burned tokens to the matching course row only."""
    ensure_admin()
    ctx = make_grading_course_with_homework(daily_student_token_limit=400_000)
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        teacher = db.query(User).filter(User.id == ctx["teacher_id"]).first()
        klass = db.query(Class).filter(Class.id == ctx["class_id"]).first()
        stud = db.query(Student).filter(Student.id == ctx["student_id"]).first()

        p2 = _validated_preset_row(uid=uid)
        db.add(p2)
        db.flush()

        course_b = Subject(name=f"pcq-split-{uid}", teacher_id=teacher.id, class_id=klass.id)
        db.add(course_b)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=course_b.id,
                student_id=stud.id,
                class_id=klass.id,
                enrollment_type="required",
            )
        )
        cfg_b = CourseLLMConfig(
            subject_id=course_b.id,
            is_enabled=True,
            max_input_tokens=16000,
            max_output_tokens=1200,
        )
        db.add(cfg_b)
        db.flush()
        db.add(CourseLLMConfigEndpoint(config_id=cfg_b.id, preset_id=p2.id, priority=1))

        hw_b = Homework(
            title="pcq split hw",
            content="x",
            class_id=klass.id,
            subject_id=course_b.id,
            max_score=100,
            auto_grading_enabled=True,
            created_by=teacher.id,
        )
        db.add(hw_b)
        db.commit()
        hw_b_id = hw_b.id
        sid_b = course_b.id
    finally:
        db.close()

    st = login_api(client, ctx["student_username"], ctx["student_password"])
    before = client.get("/api/llm-settings/courses/student-quotas", headers=st).json()
    by_id = {c["subject_id"]: c for c in before["courses"]}
    used_a0 = int(by_id[ctx["subject_id"]]["student_used_tokens_today"] or 0)
    used_b0 = int(by_id[sid_b]["student_used_tokens_today"] or 0)
    course_used_a0 = int(by_id[ctx["subject_id"]]["course_used_tokens_today"] or 0)
    course_used_b0 = int(by_id[sid_b]["course_used_tokens_today"] or 0)

    assert (
        client.post(
            f"/api/homeworks/{ctx['homework_id']}/submission",
            headers=st,
            json={"content": "only A"},
        ).status_code
        == 200
    )
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()

    with mock.patch.object(
        httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(80.0, "graded"))
    ):
        process_grading_task(tid)

    after = client.get("/api/llm-settings/courses/student-quotas", headers=st).json()
    by_id2 = {c["subject_id"]: c for c in after["courses"]}
    used_a1 = int(by_id2[ctx["subject_id"]]["student_used_tokens_today"] or 0)
    used_b1 = int(by_id2[sid_b]["student_used_tokens_today"] or 0)
    course_used_a1 = int(by_id2[ctx["subject_id"]]["course_used_tokens_today"] or 0)
    course_used_b1 = int(by_id2[sid_b]["course_used_tokens_today"] or 0)
    assert used_a1 >= used_a0 + 10
    assert used_b1 == used_a1
    assert used_b1 >= used_b0 + 10
    assert course_used_a1 >= course_used_a0 + 10
    assert course_used_b1 == course_used_b0


def test_pcq5_non_student_cannot_read_student_quotas_summary(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.get("/api/llm-settings/courses/student-quotas", headers=th)
    assert r.status_code == 403
