"""
API flows mimicking UI → backend → UI checks for material chapters + cross-features.

Uses the same /api routes as the SPA. Forty scenarios: chapters, placements, permissions,
notifications, homework + mocked LLM, concurrency, and error paths.
"""

from __future__ import annotations

import threading
import uuid
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.backend.courseeval_backend.db.database import Base, SessionLocal, engine
from apps.backend.courseeval_backend.llm_grading import process_grading_task
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Homework, HomeworkGradingTask, Subject
from tests.scenarios.llm_scenario import ensure_admin, json_llm_response, make_grading_course_with_homework, make_multi_student_scenario
from tests.scenarios.material_flow import (
    ensure_class_teacher_same_class,
    ensure_foreign_teacher,
    get_uncategorized_id,
    headers_for,
    make_subject_with_roster,
    ui_chapter_tree,
    ui_create_chapter,
    ui_add_homework_link,
    ui_create_material,
    ui_materials_list,
    ui_notification_sync,
    ui_notifications_list,
    ui_remove_homework_link,
    ui_reorder_chapters,
    ui_update_material,
)


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _admin_headers(c: TestClient) -> dict[str, str]:
    ensure_admin()
    return headers_for(c, "pytest_admin", "pytest_admin_pass")


def _class_id_for_subject(subject_id: int) -> int:
    db = SessionLocal()
    try:
        s = db.query(Subject).filter(Subject.id == subject_id).first()
        assert s and s.class_id
        return int(s.class_id)
    finally:
        db.close()


# --- 1–12: chapters & materials ---


def test_ui01_teacher_tree_contains_uncategorized_bucket(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    r = ui_chapter_tree(client, th, ctx["subject_id"])
    assert r.status_code == 200, r.text
    flat = []
    stack = list(r.json()["nodes"])
    while stack:
        n = stack.pop()
        flat.append(n)
        stack.extend(n.get("children") or [])
    assert any(x.get("is_uncategorized") for x in flat)


def test_ui02_student_reads_tree_but_cannot_create_chapter(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    assert ui_chapter_tree(client, st, ctx["subject_id"]).status_code == 200
    assert ui_create_chapter(client, st, ctx["subject_id"], "hack", None).status_code == 403


def test_ui03_non_instructor_teacher_cannot_create_chapter(client: TestClient) -> None:
    ctx = make_subject_with_roster(assign_subject_teacher=False)
    foreign = ensure_foreign_teacher()
    h = headers_for(client, foreign["username"], foreign["password"])
    assert ui_create_chapter(client, h, ctx["subject_id"], "x", None).status_code == 403


def test_ui04_three_level_chapter_nesting(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    id1 = ui_create_chapter(client, th, ctx["subject_id"], "L1", None).json()["id"]
    id2 = ui_create_chapter(client, th, ctx["subject_id"], "L2", id1).json()["id"]
    ui_create_chapter(client, th, ctx["subject_id"], "L3", id2)
    titles = []
    stack = list(ui_chapter_tree(client, th, ctx["subject_id"]).json()["nodes"])
    while stack:
        n = stack.pop()
        titles.append(n["title"])
        stack.extend(n.get("children") or [])
    assert {"L1", "L2", "L3"}.issubset(set(titles))


def test_ui05_material_without_chapter_ids_lands_in_uncategorized(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    r = ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="doc-a", content="# hi")
    assert r.status_code == 200
    assert unc in r.json().get("chapter_ids", [])
    rows = ui_materials_list(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], chapter_id=unc).json()["data"]
    assert any(x["title"] == "doc-a" for x in rows)


def test_ui06_same_material_two_chapters_listed_in_both(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    bid = ui_create_chapter(client, th, ctx["subject_id"], "Bucket", None).json()["id"]
    unc = get_uncategorized_id(ctx["subject_id"])
    mid = ui_create_material(
        client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="dup", chapter_ids=[unc, bid]
    ).json()["id"]
    assert any(x["id"] == mid for x in ui_materials_list(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], chapter_id=unc).json()["data"])
    assert any(x["id"] == mid for x in ui_materials_list(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], chapter_id=bid).json()["data"])


def test_ui07_put_material_replaces_chapter_placements(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    only = ui_create_chapter(client, th, ctx["subject_id"], "OnlyHere", None).json()["id"]
    mid = ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="mv", chapter_ids=[unc, only]).json()["id"]
    assert ui_update_material(client, th, mid, {"chapter_ids": [only]}).json()["chapter_ids"] == [only]
    assert not any(
        x["id"] == mid
        for x in ui_materials_list(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], chapter_id=unc).json()["data"]
    )


def test_ui08_reorder_root_chapters_excluding_uncategorized(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    y = ui_create_chapter(client, th, ctx["subject_id"], "B", None).json()["id"]
    x = ui_create_chapter(client, th, ctx["subject_id"], "A", None).json()["id"]
    assert ui_reorder_chapters(client, th, ctx["subject_id"], None, [y, x]).status_code == 200
    roots = ui_chapter_tree(client, th, ctx["subject_id"]).json()["nodes"]
    non_uc = [n["title"] for n in roots if not n.get("is_uncategorized")]
    assert non_uc.index("B") < non_uc.index("A")


def test_ui09_section_reorder_changes_slice_order(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    m1 = ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="first", chapter_ids=[unc]).json()
    m2 = ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="second", chapter_ids=[unc]).json()
    p1 = next(p for p in m1["placements"] if p["chapter_id"] == unc)
    p2 = next(p for p in m2["placements"] if p["chapter_id"] == unc)
    ro = client.post(
        f"/api/material-chapters/sections/reorder?subject_id={ctx['subject_id']}",
        headers=th,
        json={"chapter_id": unc, "ordered_section_ids": [p2["section_id"], p1["section_id"]]},
    )
    assert ro.status_code == 200
    rows = ui_materials_list(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], chapter_id=unc).json()["data"]
    assert [rows[0]["id"], rows[1]["id"]] == [m2["id"], m1["id"]]


def test_ui10_teacher_links_homework_into_chapter_and_student_reads_link(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    chapter_id = ui_create_chapter(client, th, ctx["subject_id"], "Homework chapter", None).json()["id"]

    db = SessionLocal()
    try:
        homework = Homework(
            title="Chapter linked homework",
            content="Do the linked exercise.",
            class_id=ctx["class_id"],
            subject_id=ctx["subject_id"],
            max_score=100,
            auto_grading_enabled=False,
            created_by=ctx["teacher_id"],
        )
        db.add(homework)
        db.commit()
        db.refresh(homework)
        homework_id = homework.id
    finally:
        db.close()

    linked = ui_add_homework_link(client, th, ctx["subject_id"], chapter_id, homework_id)
    assert linked.status_code == 200, linked.text
    assert linked.json()["homework_id"] == homework_id

    tree = ui_chapter_tree(client, st, ctx["subject_id"])
    assert tree.status_code == 200, tree.text
    root = next(node for node in tree.json()["nodes"] if node["id"] == chapter_id)
    assert root["homework_links"][0]["title"] == "Chapter linked homework"


def test_ui11_student_and_foreign_teacher_cannot_manage_homework_links(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    foreign = ensure_foreign_teacher()
    fh = headers_for(client, foreign["username"], foreign["password"])
    chapter_id = ui_create_chapter(client, th, ctx["subject_id"], "Guarded", None).json()["id"]

    db = SessionLocal()
    try:
        homework = Homework(
            title="Guarded linked homework",
            content="x",
            class_id=ctx["class_id"],
            subject_id=ctx["subject_id"],
            created_by=ctx["teacher_id"],
        )
        db.add(homework)
        db.commit()
        db.refresh(homework)
        homework_id = homework.id
    finally:
        db.close()

    assert ui_add_homework_link(client, st, ctx["subject_id"], chapter_id, homework_id).status_code == 403
    assert ui_add_homework_link(client, fh, ctx["subject_id"], chapter_id, homework_id).status_code == 403
    ok = ui_add_homework_link(client, th, ctx["subject_id"], chapter_id, homework_id)
    assert ok.status_code == 200, ok.text
    link_id = ok.json()["link_id"]
    assert ui_remove_homework_link(client, st, ctx["subject_id"], link_id).status_code == 403


def test_ui10_delete_chapter_moves_sections_to_uncategorized(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    ch = ui_create_chapter(client, th, ctx["subject_id"], "Temp", None).json()
    unc = get_uncategorized_id(ctx["subject_id"])
    mid = ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="t", chapter_ids=[ch["id"]]).json()["id"]
    assert client.delete(f"/api/material-chapters/{ch['id']}?subject_id={ctx['subject_id']}", headers=th).status_code == 200
    assert unc in client.get(f"/api/materials/{mid}", headers=th).json()["chapter_ids"]


def test_ui11_cannot_delete_last_placement_via_api(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    sec = ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="solo", chapter_ids=[unc]).json()["placements"][0]["section_id"]
    assert client.delete(f"/api/material-chapters/placements/{sec}?subject_id={ctx['subject_id']}", headers=th).status_code == 400


def test_ui12_invalid_chapter_id_on_create_returns_400(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    assert (
        ui_create_material(
            client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="bad", chapter_ids=[999999]
        ).status_code
        == 400
    )


# --- 13–18: permissions ---


def test_ui13_admin_can_create_chapter_without_being_course_teacher(client: TestClient) -> None:
    ctx = make_subject_with_roster(assign_subject_teacher=False)
    ah = _admin_headers(client)
    assert ui_create_chapter(client, ah, ctx["subject_id"], "AdminCh", None).status_code == 200


def test_ui14_class_teacher_sees_materials_but_not_chapter_mutations(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    ct = ensure_class_teacher_same_class(ctx["class_id"])
    ch = headers_for(client, ct["username"], ct["password"])
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="vis")
    assert ui_materials_list(client, ch, class_id=ctx["class_id"], subject_id=ctx["subject_id"]).status_code == 200
    assert ui_create_chapter(client, ch, ctx["subject_id"], "no", None).status_code == 403


def test_ui15_student_list_matches_detail(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    mid = ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="read", content="# md").json()["id"]
    assert any(x["id"] == mid for x in ui_materials_list(client, st, class_id=ctx["class_id"], subject_id=ctx["subject_id"], chapter_id=unc).json()["data"])
    assert client.get(f"/api/materials/{mid}", headers=st).json()["title"] == "read"


def test_ui16_non_creator_teacher_cannot_update_material(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    owner = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    foreign = ensure_foreign_teacher()
    fh = headers_for(client, foreign["username"], foreign["password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    mid = ui_create_material(client, owner, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="mine", chapter_ids=[unc]).json()["id"]
    assert ui_update_material(client, fh, mid, {"title": "stolen", "chapter_ids": [unc]}).status_code == 403


def test_ui17_duplicate_placement_returns_400(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    mid = ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="d", chapter_ids=[unc]).json()["id"]
    assert (
        client.post(
            f"/api/material-chapters/materials/{mid}/placements?subject_id={ctx['subject_id']}",
            headers=th,
            json={"chapter_id": unc},
        ).status_code
        == 400
    )


def test_ui18_section_reorder_wrong_ids_returns_400(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    assert (
        client.post(
            f"/api/material-chapters/sections/reorder?subject_id={ctx['subject_id']}",
            headers=th,
            json={"chapter_id": unc, "ordered_section_ids": [1, 2, 999]},
        ).status_code
        == 400
    )


# --- 19–26: notifications & logs ---


def test_ui19_course_notification_visible_to_student(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    client.post(
        "/api/notifications",
        headers=th,
        json={"title": "course news", "content": "hello", "class_id": ctx["class_id"], "subject_id": ctx["subject_id"], "priority": "normal"},
    )
    titles = [n["title"] for n in ui_notifications_list(client, st, ctx["subject_id"]).json()["data"]]
    assert "course news" in titles


def test_ui20_notification_sync_total_non_decreasing_after_material(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    before = ui_notification_sync(client, th, ctx["subject_id"]).json()["total"]
    ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="sync")
    after = ui_notification_sync(client, th, ctx["subject_id"]).json()["total"]
    assert after >= before


def test_ui21_grade_complete_notification_after_llm_success(client: TestClient) -> None:
    ensure_admin()
    g = make_grading_course_with_homework()
    st = headers_for(client, g["student_username"], g["student_password"])
    client.post(f"/api/homeworks/{g['homework_id']}/submission", headers=st, json={"content": "ans"})
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()
    with mock.patch.object(httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(88.0, "ok"))):
        process_grading_task(tid)
    titles = [n.get("title") or "" for n in ui_notifications_list(client, st, g["subject_id"]).json()["data"]]
    assert any("作业已批改" in t for t in titles)


def test_ui22_mark_all_read_clears_unread_sync(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    client.post("/api/notifications", headers=th, json={"title": "t", "content": "c", "class_id": ctx["class_id"], "subject_id": ctx["subject_id"]})
    client.post("/api/notifications/mark-all-read", headers=st, params={"subject_id": ctx["subject_id"]})
    assert ui_notification_sync(client, st, ctx["subject_id"]).json()["unread_count"] == 0


def test_ui23_concurrent_material_create_and_notification(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    errs: list[str] = []

    def worker(fn):
        try:
            c = TestClient(app)
            h = headers_for(c, ctx["teacher_username"], ctx["teacher_password"])
            fn(c, h)
        except Exception as e:  # noqa: BLE001
            errs.append(str(e))

    def mat(c, h):
        r = ui_create_material(c, h, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title=f"c-{uuid.uuid4().hex[:5]}")
        assert r.status_code == 200, r.text

    def note(c, h):
        r = c.post(
            "/api/notifications",
            headers=h,
            json={"title": "n", "content": "c", "class_id": ctx["class_id"], "subject_id": ctx["subject_id"]},
        )
        assert r.status_code == 200, r.text

    t1 = threading.Thread(target=worker, args=(mat,))
    t2 = threading.Thread(target=worker, args=(note,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert not errs


def test_ui24_material_create_appears_in_operation_logs(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    ah = _admin_headers(client)
    ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="logged")
    logs = client.get("/api/logs", headers=ah, params={"page": 1, "page_size": 80}).json()["data"]
    assert any(x.get("target_type") == "课程资料" for x in logs)


def test_ui25_chapter_delete_logged(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    ah = _admin_headers(client)
    cid = ui_create_chapter(client, th, ctx["subject_id"], "gone", None).json()["id"]
    client.delete(f"/api/material-chapters/{cid}?subject_id={ctx['subject_id']}", headers=th)
    logs = client.get("/api/logs", headers=ah, params={"target_type": "资料章节", "page": 1, "page_size": 30}).json()["data"]
    assert logs


def test_ui26_material_update_logged(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    ah = _admin_headers(client)
    mid = ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="u1").json()["id"]
    ui_update_material(client, th, mid, {"title": "u2"})
    logs = client.get("/api/logs", headers=ah, params={"action": "修改", "page": 1, "page_size": 40}).json()["data"]
    assert any(x.get("target_type") == "课程资料" for x in logs)


# --- 27–36: homework + LLM x materials ---


def test_ui27_llm_401_then_manual_review_materials_untouched(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    cid = _class_id_for_subject(ctx["subject_id"])
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    ui_create_material(client, th, class_id=cid, subject_id=ctx["subject_id"], title="keep")
    sub_id = client.post(f"/api/homeworks/{ctx['homework_id']}/submission", headers=st, json={"content": "x"}).json()["id"]
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    with mock.patch.object(httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(401, json={"e": 1})):
        process_grading_task(tid)
    assert (
        client.put(
            f"/api/homeworks/{ctx['homework_id']}/submissions/{sub_id}/review",
            headers=th,
            json={"review_score": 60.0, "review_comment": "manual"},
        ).status_code
        == 200
    )
    assert ui_materials_list(client, st, class_id=cid, subject_id=ctx["subject_id"]).json()["total"] >= 1


def test_ui28_llm_429_then_success_retry(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    cid = _class_id_for_subject(ctx["subject_id"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    ui_create_material(client, th, class_id=cid, subject_id=ctx["subject_id"], title="stable")
    client.post(f"/api/homeworks/{ctx['homework_id']}/submission", headers=st, json={"content": "c"})
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).order_by(HomeworkGradingTask.id.desc()).first().id
    finally:
        db.close()
    n = {"v": 0}

    def post_impl(self, url, **kwargs):
        n["v"] += 1
        if n["v"] == 1:
            return httpx.Response(429, json={"rate": True})
        return httpx.Response(200, json=json_llm_response(71.0, "ok"))

    with mock.patch.object(httpx.Client, "post", post_impl):
        process_grading_task(tid)
    db = SessionLocal()
    try:
        assert db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == tid, HomeworkGradingTask.status == "success").count() == 1
    finally:
        db.close()


def test_ui29_llm_non_json_content_fails_task(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    client.post(f"/api/homeworks/{ctx['homework_id']}/submission", headers=st, json={"content": "x"})
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json={"choices": [{"message": {"content": "NOT_JSON"}}]}),
    ):
        process_grading_task(tid)
    db = SessionLocal()
    try:
        assert (
            db.query(HomeworkGradingTask)
            .filter(HomeworkGradingTask.id == tid, HomeworkGradingTask.status == "retry_scheduled")
            .count()
            == 1
        )
    finally:
        db.close()


def test_ui30_two_students_parallel_submit_material_count_stable(client: TestClient) -> None:
    ensure_admin()
    s = make_multi_student_scenario(2)
    cid = _class_id_for_subject(s["subject_id"])
    th = headers_for(client, s["teacher_username"], s["teacher_password"])
    ui_create_material(client, th, class_id=cid, subject_id=s["subject_id"], title="multi")

    def submit(un: str, pw: str):
        c = TestClient(app)
        h = headers_for(c, un, pw)
        assert c.post(f"/api/homeworks/{s['homework_id']}/submission", headers=h, json={"content": un}).status_code == 200

    t1 = threading.Thread(target=submit, args=(s["students"][0]["username"], s["students"][0]["password"]))
    t2 = threading.Thread(target=submit, args=(s["students"][1]["username"], s["students"][1]["password"]))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    db = SessionLocal()
    try:
        tids = [row.id for row in db.query(HomeworkGradingTask).filter(HomeworkGradingTask.homework_id == s["homework_id"]).all()]
    finally:
        db.close()
    with mock.patch.object(httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(55.0, "ok"))):
        for tid in tids:
            process_grading_task(tid)
    assert ui_materials_list(client, th, class_id=cid, subject_id=s["subject_id"]).json()["total"] >= 1


def test_ui31_llm_500_response_fails_task(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(preset_max_retries=0)
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    client.post(f"/api/homeworks/{ctx['homework_id']}/submission", headers=st, json={"content": "z"})
    db = SessionLocal()
    try:
        tid = db.query(HomeworkGradingTask).one().id
    finally:
        db.close()
    with mock.patch.object(httpx.Client, "post", lambda self, url, **kwargs: httpx.Response(500, json={"error": "srv"})):
        process_grading_task(tid)
    db = SessionLocal()
    try:
        assert (
            db.query(HomeworkGradingTask)
            .filter(HomeworkGradingTask.id == tid, HomeworkGradingTask.status == "retry_scheduled")
            .count()
            == 1
        )
    finally:
        db.close()


def test_ui32_material_filter_by_chapter_excludes_other_bucket(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    a = ui_create_chapter(client, th, ctx["subject_id"], "A-only", None).json()["id"]
    b = ui_create_chapter(client, th, ctx["subject_id"], "B-only", None).json()["id"]
    ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="in-a", chapter_ids=[a])
    ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="in-b", chapter_ids=[b])
    assert ui_materials_list(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], chapter_id=a).json()["total"] == 1


def test_ui33_student_cannot_access_foreign_subject_materials(client: TestClient) -> None:
    a = make_subject_with_roster()
    b = make_subject_with_roster()
    tha = headers_for(client, a["teacher_username"], a["teacher_password"])
    mid = ui_create_material(client, tha, class_id=a["class_id"], subject_id=a["subject_id"], title="secret").json()["id"]
    st_b = headers_for(client, b["student_username"], b["student_password"])
    assert client.get(f"/api/materials/{mid}", headers=st_b).status_code == 403


def test_ui34_add_placement_via_api_then_list_updates(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    extra = ui_create_chapter(client, th, ctx["subject_id"], "Extra", None).json()["id"]
    unc = get_uncategorized_id(ctx["subject_id"])
    mid = ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="ref", chapter_ids=[unc]).json()["id"]
    assert (
        client.post(
            f"/api/material-chapters/materials/{mid}/placements?subject_id={ctx['subject_id']}",
            headers=th,
            json={"chapter_id": extra},
        ).status_code
        == 200
    )
    assert extra in client.get(f"/api/materials/{mid}", headers=th).json()["chapter_ids"]


def test_ui35_chapter_tree_survives_material_notification_interleave(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    ui_create_chapter(client, th, ctx["subject_id"], "N1", None)
    client.post("/api/notifications", headers=th, json={"title": "mix", "content": "x", "class_id": ctx["class_id"], "subject_id": ctx["subject_id"]})
    ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="mix-m")
    assert ui_chapter_tree(client, th, ctx["subject_id"]).status_code == 200


def test_ui36_put_material_remove_attachment_flag(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    mid = ui_create_material(
        client,
        th,
        class_id=ctx["class_id"],
        subject_id=ctx["subject_id"],
        title="att",
        chapter_ids=[unc],
    ).json()["id"]
    ui_update_material(client, th, mid, {"attachment_url": "http://fake/x.pdf", "attachment_name": "x.pdf"})
    assert ui_update_material(client, th, mid, {"remove_attachment": True}).json().get("attachment_url") in (None, "")


# --- 37–40: edge cases ---


def test_ui37_empty_chapter_ids_defaults_uncategorized_on_create(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    unc = get_uncategorized_id(ctx["subject_id"])
    r = client.post(
        "/api/materials",
        headers=th,
        json={"title": "e", "class_id": ctx["class_id"], "subject_id": ctx["subject_id"], "chapter_ids": []},
    )
    assert r.status_code == 200
    assert unc in r.json().get("chapter_ids", [])


def test_ui38_student_notification_sync_for_subject(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    client.post("/api/notifications", headers=th, json={"title": "s", "content": "c", "class_id": ctx["class_id"], "subject_id": ctx["subject_id"]})
    assert ui_notification_sync(client, st, ctx["subject_id"]).status_code == 200


def test_ui39_teacher_lists_all_materials_while_student_sees_course_slice(client: TestClient) -> None:
    ctx = make_subject_with_roster()
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    ui_create_material(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"], title="both")
    assert ui_materials_list(client, th, class_id=ctx["class_id"], subject_id=ctx["subject_id"]).json()["total"] >= 1
    assert ui_materials_list(client, st, class_id=ctx["class_id"], subject_id=ctx["subject_id"]).json()["total"] >= 1


def test_ui40_cross_subject_chapter_id_rejected_on_material_create(client: TestClient) -> None:
    a = make_subject_with_roster()
    b = make_subject_with_roster()
    th = headers_for(client, a["teacher_username"], a["teacher_password"])
    other_ch = ui_create_chapter(client, headers_for(client, b["teacher_username"], b["teacher_password"]), b["subject_id"], "Other", None).json()["id"]
    assert (
        ui_create_material(
            client,
            th,
            class_id=a["class_id"],
            subject_id=a["subject_id"],
            title="bad-ref",
            chapter_ids=[other_ch],
        ).status_code
        == 400
    )
