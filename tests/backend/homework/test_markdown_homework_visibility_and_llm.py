"""API + LLM prompt behavior for Markdown fields; student-visible rubric vs teacher-only fields."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.attachments import attachment_is_referenced
from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.llm_grading import _build_scoring_messages
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Class, CourseLLMConfig, CourseMaterial, Homework, HomeworkAttempt, Student, Subject, User, UserRole
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


def test_student_homework_list_and_detail_hide_teacher_only_fields(client: TestClient):
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    hid = ctx["homework_id"]
    rubric = "## 评分\n- 完整性\n- $x^2$ 公式"
    rubric_staff = "## 内部细则\n- 抄袭扣分"
    ref = "参考答案：`OK`"
    db = SessionLocal()
    try:
        hw = db.query(Homework).filter(Homework.id == hid).first()
        assert hw is not None
        class_id = hw.class_id
        hw.rubric_text = rubric
        hw.rubric_staff_only = rubric_staff
        hw.reference_answer = ref
        hw.content = "说明见 **附件**"
        db.commit()
    finally:
        db.close()

    sh = login_api(client, ctx["student_username"], ctx["student_password"])
    r_list = client.get(
        "/api/homeworks",
        params={"class_id": class_id, "subject_id": ctx["subject_id"]},
        headers=sh,
    )
    assert r_list.status_code == 200, r_list.text
    rows = r_list.json().get("data") or []
    match = next((x for x in rows if x["id"] == hid), None)
    assert match is not None
    assert match.get("rubric_text") == rubric
    assert match.get("rubric_staff_only") is None
    assert match.get("reference_answer") is None

    r_one = client.get(f"/api/homeworks/{hid}", headers=sh)
    assert r_one.status_code == 200, r_one.text
    body = r_one.json()
    assert body.get("rubric_text") == rubric
    assert body.get("rubric_staff_only") is None
    assert body.get("reference_answer") is None

    th = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    r_t = client.get(f"/api/homeworks/{hid}", headers=th)
    assert r_t.status_code == 200, r_t.text
    tb = r_t.json()
    assert tb.get("rubric_text") == rubric
    assert tb.get("rubric_staff_only") == rubric_staff
    assert tb.get("reference_answer") == ref


def test_attachment_url_only_in_homework_markdown_counts_as_reference(client: TestClient):
    """Embedded ![](/api/files/download/...) in content must block orphan file deletion."""
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    hid = ctx["homework_id"]
    embed_url = f"/api/files/download/{uuid.uuid4().hex}.png"
    db = SessionLocal()
    try:
        hw = db.query(Homework).filter(Homework.id == hid).first()
        hw.content = f"图：![]({embed_url})"
        hw.attachment_url = None
        hw.attachment_name = None
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        assert attachment_is_referenced(db, embed_url) is True
    finally:
        db.close()


def test_material_content_embedded_attachment_url_is_referenced():
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        klass = Class(name=f"mat_{uid}", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username=f"mat_t_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="T",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        course = Subject(name=f"mat_c_{uid}", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.flush()
        embed_url = f"/api/files/download/{uuid.uuid4().hex}.png"
        db.add(
            CourseMaterial(
                title="doc",
                content=f"![]({embed_url})",
                class_id=klass.id,
                subject_id=course.id,
                created_by=teacher.id,
            )
        )
        db.commit()
        assert attachment_is_referenced(db, embed_url) is True
    finally:
        db.close()


def test_build_scoring_messages_splits_data_url_in_homework_content():
    tiny_png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAusB9Y9nKXUAAAAASUVORK5CYII="
    )
    data_url = f"data:image/png;base64,{tiny_png_b64}"
    md_line = f"题面 ![]({data_url}) 结束"
    hw = Homework(
        title="t",
        content=md_line,
        class_id=1,
        subject_id=1,
        max_score=10,
        grade_precision="integer",
        created_by=1,
        rubric_text=None,
        reference_answer=None,
    )
    att = HomeworkAttempt(
        homework_id=1,
        student_id=1,
        subject_id=1,
        class_id=1,
        content="仅文字",
    )
    cfg = CourseLLMConfig(
        subject_id=1,
        max_input_tokens=8000,
        max_output_tokens=500,
    )
    material = {
        "assignment_texts": [f"作业标题：{hw.title}", "作业要求：\n无"],
        "student_blocks": [],
        "notes_text": "",
    }
    messages = _build_scoring_messages(hw, att, cfg, material)
    user = messages[1]["content"]
    assert isinstance(user, list)
    types = [p.get("type") for p in user]
    assert types.count("image_url") >= 1
    img_urls = [p["image_url"]["url"] for p in user if p.get("type") == "image_url"]
    assert data_url in img_urls
