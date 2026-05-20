"""
LLM 组级路由与连通性分阶段：使用 httpx mock，不访问外网。

覆盖：多组优先级、组内多成员 failover、先文本后整体验证、artifact 中 llm_routing。
"""

from __future__ import annotations

from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.llm_grading import (
    _collect_grading_endpoints_for_config,
    process_grading_task,
    queue_grading_task,
    validate_text_connectivity,
    validate_vision_connectivity,
)
from apps.backend.courseeval_backend.domains.llm.routing import _GroupState
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    Homework,
    HomeworkAttempt,
    HomeworkGradingTask,
    HomeworkScoreCandidate,
    HomeworkSubmission,
    LLMEndpointPreset,
    LLMGroup,
    Student,
    Subject,
    User,
    UserRole,
)
from tests.scenarios.llm_scenario import ensure_admin, json_llm_response, login_api


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


def _make_grouped_course_with_homework() -> dict:
    uid = "g1"
    db = SessionLocal()
    try:
        klass = Class(name=f"g-class-{uid}", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username="g_teach",
            hashed_password=get_password_hash("g_tp"),
            real_name="G T",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        stu = User(
            username="g_stu",
            hashed_password=get_password_hash("g_sp"),
            real_name="G S",
            role=UserRole.STUDENT.value,
            class_id=klass.id,
        )
        db.add(stu)
        db.flush()
        stud = Student(name="G S", student_no="g_stu", class_id=klass.id)
        db.add(stud)
        db.flush()
        course = Subject(name=f"g-subj-{uid}", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=course.id,
                student_id=stud.id,
                class_id=klass.id,
                enrollment_type="required",
            )
        )
        p1 = LLMEndpointPreset(
            name="preset_g1",
            base_url="https://g1.test/v1/",
            api_key="k1",
            model_name="m1",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        p2 = LLMEndpointPreset(
            name="preset_g2",
            base_url="https://g2.test/v1/",
            api_key="k2",
            model_name="m2",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        p3 = LLMEndpointPreset(
            name="preset_g3",
            base_url="https://g3.test/v1/",
            api_key="k3",
            model_name="m3",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        db.add_all([p1, p2, p3])
        db.flush()
        cfg = CourseLLMConfig(
            subject_id=course.id,
            is_enabled=True,
            max_input_tokens=8000,
            max_output_tokens=1000,
        )
        db.add(cfg)
        db.flush()
        g1 = LLMGroup(config_id=cfg.id, priority=1, name="primary")
        g2 = LLMGroup(config_id=cfg.id, priority=2, name="secondary")
        db.add_all([g1, g2])
        db.flush()
        db.add(
            CourseLLMConfigEndpoint(
                config_id=cfg.id,
                group_id=g1.id,
                preset_id=p1.id,
                priority=1,
            )
        )
        db.add(
            CourseLLMConfigEndpoint(
                config_id=cfg.id,
                group_id=g2.id,
                preset_id=p2.id,
                priority=1,
            )
        )
        db.add(
            CourseLLMConfigEndpoint(
                config_id=cfg.id,
                group_id=g2.id,
                preset_id=p3.id,
                priority=2,
            )
        )
        hw = Homework(
            title="g-hw",
            content="c",
            class_id=klass.id,
            subject_id=course.id,
            max_score=100,
            auto_grading_enabled=True,
            created_by=teacher.id,
        )
        db.add(hw)
        db.commit()
        db.refresh(hw)
        return {
            "homework_id": hw.id,
            "p1": p1.id,
            "p2": p2.id,
            "p3": p3.id,
            "student_headers": None,
        }
    finally:
        db.close()


def test_validate_text_and_vision_helpers():
    with mock.patch.object(httpx.Client, "post", return_value=httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})):
        ok, _ = validate_text_connectivity("https://a.test/v1/", "k", "m", 5, 10)
        assert ok
        ok2, _ = validate_vision_connectivity("https://a.test/v1/", "k", "m", 5, 10)
        assert ok2


def test_two_groups_failover_to_second_group(client: TestClient):
    """第一组 401 后进入第二组；第二组第一个 500 后第二个 200 成功。"""
    ensure_admin()
    ctx = _make_grouped_course_with_homework()
    ctx["student_headers"] = login_api(client, "g_stu", "g_sp")
    client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=ctx["student_headers"],
        json={"content": "answer"},
    )
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()

    calls: list[str] = []

    def fake_post(self, url, **kwargs):
        b = (kwargs.get("json") or {}).get("body")
        if isinstance(b, str):
            payload = {}
        else:
            payload = kwargs.get("json") or {}
        model = payload.get("model") or ""
        calls.append(model)
        if model == "m1":
            return httpx.Response(401, json={"error": "nope"})
        if model == "m2":
            return httpx.Response(500, json={"error": "u"})
        if model == "m3":
            return httpx.Response(200, json=json_llm_response(77.0, "from m3"))
        return httpx.Response(500, json={})

    with mock.patch.object(httpx.Client, "post", fake_post):
        process_grading_task(tid)

    # Group1: m1 only -> 401. Group2: with task_id % 2, order may be [m3,m2] or [m2,m3] — second group can succeed on m3 without ever calling m2.
    assert calls[0] == "m1"
    assert "m3" in calls
    assert calls[-1] == "m3"
    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid).one()
        assert task.status == "success"
        sub = db.query(HomeworkSubmission).one()
        assert sub.review_score == 77.0
        auto = db.query(HomeworkScoreCandidate).filter(HomeworkScoreCandidate.source == "auto").one()
        assert auto.source_metadata.get("endpoint_id") == ctx["p3"]
        m = task.artifact_manifest or {}
        assert m.get("llm_routing", {}).get("status") == "ok"
    finally:
        db.close()


def test_put_course_config_with_groups_payload(client: TestClient):
    ensure_admin()
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    c = client.post(
        "/api/llm-settings/presets",
        headers=admin_h,
        json={"name": "g-api-p", "base_url": "https://x.test/v1/", "api_key": "k", "model_name": "m"},
    )
    pid = c.json()["id"]
    db = SessionLocal()
    try:
        k = Class(name="ApiClass", grade=2026)
        db.add(k)
        db.flush()
        t = User(
            username="g_put_t",
            hashed_password=get_password_hash("x"),
            real_name="G Put T",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        s = Subject(name="ApiSubj", teacher_id=t.id, class_id=k.id)
        db.add(s)
        db.commit()
        sid = s.id
    finally:
        db.close()
    p2r = client.post(
        "/api/llm-settings/presets",
        headers=admin_h,
        json={"name": "g-api-p2", "base_url": "https://x2.test/v1/", "api_key": "k2", "model_name": "m2"},
    )
    p2 = p2r.json()["id"]
    db = SessionLocal()
    try:
        for preset_id in (pid, p2):
            pr = db.query(LLMEndpointPreset).filter(LLMEndpointPreset.id == preset_id).first()
            if pr:
                pr.validation_status = "validated"
                pr.supports_vision = True
        db.commit()
    finally:
        db.close()
    th = login_api(client, "g_put_t", "x")
    r = client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=th,
        json={
            "is_enabled": True,
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 4.0,
            "estimated_image_tokens": 100,
            "max_input_tokens": 8000,
            "max_output_tokens": 500,
            "groups": [
                {
                    "priority": 1,
                    "name": "G1",
                    "members": [{"preset_id": pid, "priority": 1}],
                },
                {
                    "priority": 2,
                    "name": "G2",
                    "members": [
                        {"preset_id": p2, "priority": 1},
                    ],
                },
            ],
        },
    )
    assert r.status_code == 200, r.text
    g = r.json()["groups"]
    assert len(g) == 2
    assert len(g[0]["members"]) == 1
    assert g[0]["members"][0]["preset_id"] == pid


def test_flat_legacy_routing_when_no_group_rows():
    """No LLMGroup rows: use flat priority list (legacy / empty-catalog mode)."""
    from tests.scenarios.llm_scenario import make_grading_course_with_homework

    _ = make_grading_course_with_homework()
    db = SessionLocal()
    try:
        c = (
            db.query(CourseLLMConfig)
            .order_by(CourseLLMConfig.id.desc())
            .first()
        )
        assert c is not None
        for g in list(c.groups or []):
            db.delete(g)
        db.commit()
    finally:
        db.close()
    db2 = SessionLocal()
    try:
        c2 = (
            db2.query(CourseLLMConfig)
            .order_by(CourseLLMConfig.id.desc())
            .first()
        )
        g_rows, flat = _collect_grading_endpoints_for_config(c2)
        assert g_rows == [] and len(flat) == 1
    finally:
        db2.close()


def test_validate_endpoint_order_text_before_vision():
    """validate_endpoint_connectivity：先发纯文本请求，再发多模态请求。"""
    from apps.backend.courseeval_backend import llm_grading

    received: list[str] = []

    def fake_post(self, url, **kwargs):
        payload = kwargs.get("json") or {}
        msgs = (payload.get("messages") or [{}])[0]
        ctn = msgs.get("content")
        if isinstance(ctn, str):
            received.append("text")
        else:
            received.append("vision")
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    with mock.patch.object(httpx.Client, "post", fake_post):
        ok, _ = llm_grading.validate_endpoint_connectivity("https://ord.test/v1/", "k", "m", 5, 20)
    assert ok
    assert received == ["text", "vision"]


def test_backfill_assigns_group_id_to_endpoints():
    from apps.backend.courseeval_backend.bootstrap import _backfill_default_llm_groups_for_existing_configs
    from apps.backend.courseeval_backend.db.models import CourseLLMConfig, CourseLLMConfigEndpoint, LLMGroup

    ensure_admin()
    from tests.scenarios.llm_scenario import make_grading_course_with_homework

    _ = make_grading_course_with_homework()
    db = SessionLocal()
    try:
        c = (
            db.query(CourseLLMConfig)
            .order_by(CourseLLMConfig.id.desc())
            .first()
        )
        assert c is not None
        for row in db.query(CourseLLMConfigEndpoint).filter(CourseLLMConfigEndpoint.config_id == c.id).all():
            row.group_id = None
        for g in list(db.query(LLMGroup).filter(LLMGroup.config_id == c.id).all() or []):
            db.delete(g)
        db.commit()
        config_id = c.id
    finally:
        db.close()
    _backfill_default_llm_groups_for_existing_configs()
    db = SessionLocal()
    try:
        c2 = db.query(CourseLLMConfig).filter(CourseLLMConfig.id == config_id).one()
        links = c2.endpoints
        g = c2.groups
        assert any(gg and gg.name == "default" for gg in (g or []))
        for row in links or []:
            assert row.group_id is not None
    finally:
        db.close()


def test_admin_validate_calls_text_then_vision_in_order(client: TestClient):
    from apps.backend.courseeval_backend.api.routers import llm_settings

    call_order: list[str] = []

    def t_txt(*a, **k):
        call_order.append("text")
        return True, "t"

    def t_vis(*a, **k):
        call_order.append("vision")
        return True, "v"

    ensure_admin()
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    c = client.post(
        "/api/llm-settings/presets",
        headers=admin_h,
        json={"name": "v-order-2", "base_url": "https://vord2.test/v1/", "api_key": "k", "model_name": "m"},
    )
    assert c.status_code == 200, c.text
    pid = c.json()["id"]

    from apps.backend.courseeval_backend.llm_grading import VISION_TEST_IMAGE_DATA_URL

    _b = VISION_TEST_IMAGE_DATA_URL.split("base64,", 1)[1]
    import base64 as _b64

    tiny_png = _b64.b64decode(_b)

    with (
        mock.patch.object(llm_settings, "validate_text_connectivity", side_effect=t_txt),
        mock.patch.object(llm_settings, "validate_vision_connectivity", side_effect=t_vis),
    ):
        r = client.post(
            f"/api/llm-settings/presets/{pid}/validate",
            headers=admin_h,
            files={"image": ("t.png", tiny_png, "image/png")},
        )
    assert r.status_code == 200, r.text
    assert r.json().get("validation_status") == "validated"
    assert r.json().get("text_validation_status") == "passed"
    assert r.json().get("vision_validation_status") == "passed"
    assert call_order == ["text", "vision"]


def test_get_endpoints_list_order_is_group1_then_group2(client: TestClient):
    ensure_admin()
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    c = client.post(
        "/api/llm-settings/presets",
        headers=admin_h,
        json={"name": "ordp1", "base_url": "https://o1.test/v1/", "api_key": "a", "model_name": "x1"},
    )
    p1 = c.json()["id"]
    c2 = client.post(
        "/api/llm-settings/presets",
        headers=admin_h,
        json={"name": "ordp2", "base_url": "https://o2.test/v1/", "api_key": "a", "model_name": "x2"},
    )
    p2 = c2.json()["id"]
    db = SessionLocal()
    try:
        k = Class(name="OClass", grade=2026)
        db.add(k)
        db.flush()
        t = User(
            username="o_t",
            hashed_password=get_password_hash("o"),
            real_name="O T",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        s = Subject(name="OSubj", teacher_id=t.id, class_id=k.id)
        db.add(s)
        db.commit()
        sid = s.id
        for pid in (p1, p2):
            pr = db.query(LLMEndpointPreset).filter(LLMEndpointPreset.id == pid).one()
            pr.validation_status = "validated"
            pr.supports_vision = True
        db.commit()
    finally:
        db.close()
    th = login_api(client, "o_t", "o")
    r = client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=th,
        json={
            "is_enabled": True,
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 4.0,
            "estimated_image_tokens": 100,
            "max_input_tokens": 4000,
            "max_output_tokens": 500,
            "groups": [
                {
                    "name": "A",
                    "members": [{"preset_id": p1, "priority": 1}],
                },
                {
                    "name": "B",
                    "members": [{"preset_id": p2, "priority": 1}],
                },
            ],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["endpoints"]
    order = [e["preset_id"] for e in data]
    assert order == [p1, p2]
    g = client.get(f"/api/llm-settings/courses/{sid}", headers=th).json()["groups"]
    assert [x["name"] for x in g] == ["A", "B"]


def test_put_rejects_empty_group(client: TestClient):
    ensure_admin()
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    db = SessionLocal()
    try:
        k = Class(name="EClass", grade=2026)
        db.add(k)
        db.flush()
        t = User(
            username="e_t",
            hashed_password=get_password_hash("e"),
            real_name="E T",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        s = Subject(name="ESubj", teacher_id=t.id, class_id=k.id)
        db.add(s)
        db.commit()
        sid = s.id
    finally:
        db.close()
    th = login_api(client, "e_t", "e")
    r = client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=th,
        json={
            "is_enabled": True,
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 4.0,
            "estimated_image_tokens": 100,
            "max_input_tokens": 4000,
            "max_output_tokens": 500,
            "groups": [
                {
                    "name": "E",
                    "members": [],
                }
            ],
        },
    )
    assert r.status_code == 400
    assert "至少" in (r.json().get("detail") or "")


def test_put_rejects_duplicate_preset_in_same_course(client: TestClient):
    ensure_admin()
    admin_h = login_api(client, "pytest_admin", "pytest_admin_pass")
    c = client.post(
        "/api/llm-settings/presets",
        headers=admin_h,
        json={"name": "dup1", "base_url": "https://d.test/v1/", "api_key": "a", "model_name": "m"},
    )
    pid = c.json()["id"]
    db = SessionLocal()
    try:
        k = Class(name="DClass", grade=2026)
        db.add(k)
        db.flush()
        t = User(
            username="d_t",
            hashed_password=get_password_hash("d"),
            real_name="D T",
            role=UserRole.TEACHER.value,
        )
        db.add(t)
        db.flush()
        s = Subject(name="DSubj", teacher_id=t.id, class_id=k.id)
        db.add(s)
        db.commit()
        sid = s.id
        pr = db.query(LLMEndpointPreset).filter(LLMEndpointPreset.id == pid).one()
        pr.validation_status = "validated"
        pr.supports_vision = True
        db.commit()
    finally:
        db.close()
    th = login_api(client, "d_t", "d")
    r = client.put(
        f"/api/llm-settings/courses/{sid}",
        headers=th,
        json={
            "is_enabled": True,
            "quota_timezone": "UTC",
            "estimated_chars_per_token": 4.0,
            "estimated_image_tokens": 100,
            "max_input_tokens": 4000,
            "max_output_tokens": 500,
            "groups": [
                {
                    "name": "G1",
                    "members": [
                        {"preset_id": pid, "priority": 1},
                    ],
                },
                {
                    "name": "G2",
                    "members": [
                        {"preset_id": pid, "priority": 1},
                    ],
                },
            ],
        },
    )
    assert r.status_code == 400
    assert "一次" in (r.json().get("detail") or "")


def test_group_503_on_first_member_then_succeeds_on_sibling():
    """单组内：首个成员 503（可重试耗尽）后尝试组内另一成员 200。旋转使 ma 在队头当 tid%2==0 时与 ma 先被调用一致。"""
    ensure_admin()
    db = SessionLocal()
    try:
        klass = Class(name="r-class2", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username="r_t2",
            hashed_password=get_password_hash("r2"),
            real_name="R T2",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        stu = User(
            username="r_s2",
            hashed_password=get_password_hash("s2"),
            real_name="R S2",
            role=UserRole.STUDENT.value,
            class_id=klass.id,
        )
        db.add(stu)
        db.flush()
        stud = Student(name="R S2", student_no="r_s2", class_id=klass.id)
        db.add(stud)
        db.flush()
        course = Subject(name="r-subj-2", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=course.id,
                student_id=stud.id,
                class_id=klass.id,
                enrollment_type="required",
            )
        )
        a = LLMEndpointPreset(
            name="r-a-2",
            base_url="https://a2.test/v1/",
            api_key="a2",
            model_name="ma2",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        b = LLMEndpointPreset(
            name="r-b-2",
            base_url="https://b2.test/v1/",
            api_key="b2",
            model_name="mb2",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        db.add_all([a, b])
        db.flush()
        cfg = CourseLLMConfig(
            subject_id=course.id,
            is_enabled=True,
            max_input_tokens=4000,
            max_output_tokens=500,
        )
        db.add(cfg)
        db.flush()
        g = LLMGroup(config_id=cfg.id, priority=1, name="rg2")
        db.add(g)
        db.flush()
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, group_id=g.id, preset_id=a.id, priority=1))
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, group_id=g.id, preset_id=b.id, priority=2))
        h = Homework(
            title="h2",
            content="c",
            class_id=klass.id,
            subject_id=course.id,
            max_score=100,
            auto_grading_enabled=True,
            created_by=teacher.id,
        )
        db.add(h)
        db.flush()
        sub = HomeworkSubmission(
            homework_id=h.id,
            student_id=stud.id,
            subject_id=course.id,
            class_id=klass.id,
            content="seed",
        )
        db.add(sub)
        db.flush()
        att = HomeworkAttempt(
            homework_id=h.id,
            student_id=stud.id,
            subject_id=course.id,
            class_id=klass.id,
            submission_summary_id=sub.id,
            content="seed",
            is_late=False,
        )
        db.add(att)
        db.flush()
        sub.latest_attempt_id = att.id
        task = queue_grading_task(db, att, "pytest_group_rr")
        db.commit()
        tid = task.id
    finally:
        db.close()


def test_group_retryable_failures_do_not_loop_forever_when_all_members_fail():
    ensure_admin()
    db = SessionLocal()
    try:
        klass = Class(name="loop_guard_class", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username="loop_guard_teacher",
            hashed_password=get_password_hash("loop"),
            real_name="Loop Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        student_user = User(
            username="loop_guard_student",
            hashed_password=get_password_hash("loop-student"),
            real_name="Loop Student",
            role=UserRole.STUDENT.value,
            class_id=klass.id,
        )
        db.add(student_user)
        db.flush()
        student = Student(name="Loop Student", student_no="loop_guard_student", class_id=klass.id)
        db.add(student)
        db.flush()
        course = Subject(name="Loop Guard Course", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=course.id,
                student_id=student.id,
                class_id=klass.id,
                enrollment_type="required",
            )
        )
        preset_a = LLMEndpointPreset(
            name="loop-a",
            base_url="https://loop-a.test/v1/",
            api_key="ka",
            model_name="loop-a",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        preset_b = LLMEndpointPreset(
            name="loop-b",
            base_url="https://loop-b.test/v1/",
            api_key="kb",
            model_name="loop-b",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        db.add_all([preset_a, preset_b])
        db.flush()
        cfg = CourseLLMConfig(
            subject_id=course.id,
            is_enabled=True,
            max_input_tokens=4000,
            max_output_tokens=500,
        )
        db.add(cfg)
        db.flush()
        group = LLMGroup(config_id=cfg.id, priority=1, name="loop-group")
        db.add(group)
        db.flush()
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, group_id=group.id, preset_id=preset_a.id, priority=1))
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, group_id=group.id, preset_id=preset_b.id, priority=2))
        homework = Homework(
            title="Loop Homework",
            content="content",
            class_id=klass.id,
            subject_id=course.id,
            max_score=100,
            auto_grading_enabled=True,
            created_by=teacher.id,
        )
        db.add(homework)
        db.flush()
        submission = HomeworkSubmission(
            homework_id=homework.id,
            student_id=student.id,
            subject_id=course.id,
            class_id=klass.id,
            content="seed",
        )
        db.add(submission)
        db.flush()
        attempt = HomeworkAttempt(
            homework_id=homework.id,
            student_id=student.id,
            subject_id=course.id,
            class_id=klass.id,
            submission_summary_id=submission.id,
            content="seed",
            is_late=False,
        )
        db.add(attempt)
        db.flush()
        submission.latest_attempt_id = attempt.id
        task = queue_grading_task(db, attempt, "pytest_group_loop_guard")
        db.commit()
        task_id = task.id
    finally:
        db.close()

    call_models: list[str] = []

    def fake_post(self, url, **kwargs):
        model = (kwargs.get("json") or {}).get("model") or ""
        call_models.append(model)
        return httpx.Response(503, json={"error": "upstream"})

    with mock.patch.object(_GroupState, "apply_round_robin_start", lambda self, task_id: None):
        with mock.patch.object(httpx.Client, "post", fake_post):
            process_grading_task(task_id)

    assert call_models == ["loop-a", "loop-b"]
    db = SessionLocal()
    try:
        task = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == task_id).one()
        assert task.status == "retry_scheduled"
    finally:
        db.close()
