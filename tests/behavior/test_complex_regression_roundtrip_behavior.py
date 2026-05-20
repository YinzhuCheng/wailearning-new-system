"""Complex API-level regression scenarios for multi-step state convergence."""

from __future__ import annotations

import threading
import uuid
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.llm_grading import process_grading_task
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseLLMConfig,
    Homework,
    HomeworkGradingTask,
    Notification,
    NotificationRead,
    ScoreGradeAppeal,
    Student,
    Subject,
    SubjectClassLink,
    User,
    UserRole,
)
from tests.scenarios.llm_scenario import ensure_admin, json_llm_response, login_api, make_grading_course_with_homework, make_multi_student_scenario


def _add_student_user(*, class_id: int, username: str, password: str, real_name: str) -> dict[str, int | str]:
    db = SessionLocal()
    try:
        user = User(
            username=username,
            hashed_password=get_password_hash(password),
            real_name=real_name,
            role=UserRole.STUDENT.value,
            class_id=class_id,
        )
        db.add(user)
        db.flush()
        student = Student(name=real_name, student_no=username, class_id=class_id)
        db.add(student)
        db.commit()
        return {"user_id": user.id, "student_id": student.id, "username": username}
    finally:
        db.close()


def _subject_class_and_teacher(subject_id: int) -> dict[str, int]:
    db = SessionLocal()
    try:
        subject = db.query(Subject).filter(Subject.id == subject_id).first()
        assert subject is not None
        return {"class_id": int(subject.class_id), "teacher_id": int(subject.teacher_id)}
    finally:
        db.close()


def _latest_task_id(homework_id: int) -> int:
    db = SessionLocal()
    try:
        task = (
            db.query(HomeworkGradingTask)
            .filter(HomeworkGradingTask.homework_id == homework_id)
            .order_by(HomeworkGradingTask.id.desc())
            .first()
        )
        assert task is not None
        return int(task.id)
    finally:
        db.close()


def _notification_ids_for_user(client: TestClient, headers: dict[str, str], *, subject_id: int | None = None) -> list[int]:
    resp = client.get("/api/notifications", headers=headers, params={"subject_id": subject_id} if subject_id else None)
    assert resp.status_code == 200, resp.text
    return [int(row["id"]) for row in resp.json()["data"]]


def _seed_class_move_context() -> dict[str, int]:
    ensure_admin()
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        klass_a = Class(name=f"class-a-{uid}", grade=2026)
        klass_b = Class(name=f"class-b-{uid}", grade=2026)
        db.add_all([klass_a, klass_b])
        db.flush()

        teacher = User(
            username=f"teacher_move_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="Teacher Move",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()

        course_a = Subject(name=f"required-a-{uid}", teacher_id=teacher.id, class_id=klass_a.id, course_type="required", status="active")
        course_b = Subject(name=f"required-b-{uid}", teacher_id=teacher.id, class_id=klass_b.id, course_type="required", status="active")
        db.add_all([course_a, course_b])
        db.flush()
        db.add_all(
            [
                SubjectClassLink(subject_id=course_a.id, class_id=klass_a.id, enrollment_mode="all_in_class"),
                SubjectClassLink(subject_id=course_b.id, class_id=klass_b.id, enrollment_mode="all_in_class"),
            ]
        )
        db.flush()

        student = Student(name="Move Student", student_no=f"move_{uid}", class_id=klass_a.id)
        db.add(student)
        db.flush()

        user = User(
            username=student.student_no,
            hashed_password=get_password_hash("sp"),
            real_name="Move Student",
            role=UserRole.STUDENT.value,
            class_id=klass_a.id,
        )
        db.add(user)
        db.commit()
        return {
            "class_a_id": int(klass_a.id),
            "class_b_id": int(klass_b.id),
            "course_a_id": int(course_a.id),
            "course_b_id": int(course_b.id),
            "user_id": int(user.id),
            "student_id": int(student.id),
            "teacher_id": int(teacher.id),
        }
    finally:
        db.close()


def test_c1_score_appeal_can_reopen_after_resolve(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    first = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_headers,
        json={"semester": "2026-spring", "target_component": "total", "reason_text": "first pass"},
    )
    assert first.status_code == 200, first.text

    closed = client.put(
        f"/api/scores/appeals/{first.json()['id']}",
        headers=teacher_headers,
        json={"teacher_response": "checked", "status": "resolved"},
    )
    assert closed.status_code == 200, closed.text

    second = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_headers,
        json={"semester": "2026-spring", "target_component": "total", "reason_text": "second pass"},
    )
    assert second.status_code == 200, second.text
    assert int(second.json()["id"]) != int(first.json()["id"])


def test_c2_score_appeal_can_reopen_after_reject(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    first = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_headers,
        json={"semester": "2026-fall", "target_component": "homework_avg", "reason_text": "need another look"},
    )
    assert first.status_code == 200, first.text

    closed = client.put(
        f"/api/scores/appeals/{first.json()['id']}",
        headers=teacher_headers,
        json={"teacher_response": "rejected once", "status": "rejected"},
    )
    assert closed.status_code == 200, closed.text

    second = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_headers,
        json={"semester": "2026-fall", "target_component": "homework_avg", "reason_text": "retry later"},
    )
    assert second.status_code == 200, second.text


def test_c3_score_appeal_response_marks_teacher_notification_as_handled(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])

    created = client.post(
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        headers=student_headers,
        json={"semester": "2026-summer", "target_component": "total", "reason_text": "notify teacher"},
    )
    assert created.status_code == 200, created.text
    appeal_id = int(created.json()["id"])
    before_title = ""
    before_content = ""

    db = SessionLocal()
    try:
        before = db.query(Notification).filter(Notification.related_score_appeal_id == appeal_id).all()
        assert len(before) == 1
        before_title = str(before[0].title or "")
        before_content = str(before[0].content or "")
    finally:
        db.close()

    updated = client.put(
        f"/api/scores/appeals/{appeal_id}",
        headers=teacher_headers,
        json={"teacher_response": "handled", "status": "resolved"},
    )
    assert updated.status_code == 200, updated.text

    db = SessionLocal()
    try:
        note = db.query(Notification).filter(Notification.related_score_appeal_id == appeal_id).one()
        assert str(note.title or "") != before_title or str(note.content or "") != before_content
    finally:
        db.close()


def test_c4_concurrent_duplicate_score_appeals_settle_to_one_pending_row(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    statuses: list[int] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            with TestClient(app) as thread_client:
                resp = thread_client.post(
                    f"/api/scores/appeals?subject_id={ctx['subject_id']}",
                    headers=student_headers,
                    json={"semester": "2026-concurrent", "target_component": "total", "reason_text": "same time"},
                )
                with lock:
                    statuses.append(resp.status_code)
        except Exception as exc:  # pragma: no cover
            with lock:
                errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert sorted(statuses) == [200, 400]

    db = SessionLocal()
    try:
        count = (
            db.query(ScoreGradeAppeal)
            .filter(
                ScoreGradeAppeal.subject_id == ctx["subject_id"],
                ScoreGradeAppeal.semester == "2026-concurrent",
                ScoreGradeAppeal.target_component == "total",
                ScoreGradeAppeal.status == "pending",
            )
            .count()
        )
        assert count == 1
    finally:
        db.close()


def test_c5_targeted_student_notification_stays_private_from_classmate(client: TestClient) -> None:
    ensure_admin()
    scenario = make_multi_student_scenario(2, auto_grading=False)
    course_meta = _subject_class_and_teacher(scenario["subject_id"])
    teacher_headers = login_api(client, scenario["teacher_username"], scenario["teacher_password"])
    student_a = scenario["students"][0]
    student_b = scenario["students"][1]
    student_a_headers = login_api(client, str(student_a["username"]), str(student_a["password"]))
    student_b_headers = login_api(client, str(student_b["username"]), str(student_b["password"]))

    created = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={
            "title": "private-a",
            "content": "only one student should see this",
            "class_id": course_meta["class_id"],
            "subject_id": scenario["subject_id"],
            "target_student_id": student_a["student_id"],
        },
    )
    assert created.status_code == 200, created.text
    note_id = int(created.json()["id"])

    visible_a = _notification_ids_for_user(client, student_a_headers, subject_id=scenario["subject_id"])
    visible_b = _notification_ids_for_user(client, student_b_headers, subject_id=scenario["subject_id"])
    assert note_id in visible_a
    assert note_id not in visible_b


def test_c6_mark_all_read_scopes_to_one_subject_only(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])

    db = SessionLocal()
    try:
        course = db.query(Subject).filter(Subject.id == ctx["subject_id"]).one()
        second_course = Subject(
            name=f"extra-course-{uuid.uuid4().hex[:6]}",
            teacher_id=course.teacher_id,
            class_id=course.class_id,
            course_type="required",
            status="active",
        )
        db.add(second_course)
        db.flush()
        student = db.query(Student).filter(Student.id == ctx["student_id"]).one()
        db.add(
            CourseEnrollment(
                subject_id=second_course.id,
                student_id=student.id,
                class_id=course.class_id,
                enrollment_type="required",
            )
        )
        db.commit()
        second_subject_id = int(second_course.id)
        class_id = int(course.class_id)
    finally:
        db.close()

    for title, subject_id in (("subject-one", ctx["subject_id"]), ("subject-two", second_subject_id)):
        resp = client.post(
            "/api/notifications",
            headers=teacher_headers,
            json={"title": title, "content": title, "class_id": class_id, "subject_id": subject_id},
        )
        assert resp.status_code == 200, resp.text

    before = client.get("/api/notifications/sync-status", headers=student_headers)
    assert before.status_code == 200, before.text
    assert before.json()["unread_count"] >= 2

    marked = client.post("/api/notifications/mark-all-read", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    assert marked.status_code == 200, marked.text

    subject_one = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": ctx["subject_id"]})
    subject_two = client.get("/api/notifications/sync-status", headers=student_headers, params={"subject_id": second_subject_id})
    assert subject_one.status_code == 200
    assert subject_two.status_code == 200
    assert subject_one.json()["unread_count"] == 0
    assert subject_two.json()["unread_count"] >= 1


def test_c7_concurrent_notification_read_paths_converge_to_one_row(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    class_id = _subject_class_and_teacher(ctx["subject_id"])["class_id"]

    created = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={"title": "read-race", "content": "race", "class_id": class_id, "subject_id": ctx["subject_id"]},
    )
    assert created.status_code == 200, created.text
    notification_id = int(created.json()["id"])
    errors: list[str] = []

    def mark_one() -> None:
        try:
            with TestClient(app) as thread_client:
                resp = thread_client.post(f"/api/notifications/{notification_id}/read", headers=student_headers)
                assert resp.status_code == 200, resp.text
        except Exception as exc:  # pragma: no cover
            errors.append(str(exc))

    def mark_all() -> None:
        try:
            with TestClient(app) as thread_client:
                resp = thread_client.post(
                    "/api/notifications/mark-all-read",
                    headers=student_headers,
                    params={"subject_id": ctx["subject_id"]},
                )
                assert resp.status_code == 200, resp.text
        except Exception as exc:  # pragma: no cover
            errors.append(str(exc))

    threads = [threading.Thread(target=mark_one), threading.Thread(target=mark_all)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors

    db = SessionLocal()
    try:
        rows = (
            db.query(NotificationRead)
            .filter(NotificationRead.notification_id == notification_id)
            .all()
        )
        assert len(rows) == 1
        assert bool(rows[0].is_read) is True
    finally:
        db.close()


def test_c7b_concurrent_dual_mark_all_read_no_integrity_errors(client: TestClient) -> None:
    """Two parallel mark-all-read calls must not race on unique (notification_id, user_id)."""
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    class_id = _subject_class_and_teacher(ctx["subject_id"])["class_id"]

    for i in range(3):
        created = client.post(
            "/api/notifications",
            headers=teacher_headers,
            json={
                "title": f"bulk-{i}",
                "content": "bulk",
                "class_id": class_id,
                "subject_id": ctx["subject_id"],
            },
        )
        assert created.status_code == 200, created.text

    errors: list[str] = []

    def mark_all() -> None:
        try:
            with TestClient(app) as thread_client:
                resp = thread_client.post(
                    "/api/notifications/mark-all-read",
                    headers=student_headers,
                    params={"subject_id": ctx["subject_id"]},
                )
                assert resp.status_code == 200, resp.text
        except Exception as exc:  # pragma: no cover
            errors.append(str(exc))

    threads = [threading.Thread(target=mark_all), threading.Thread(target=mark_all)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors

    sync = client.get(
        "/api/notifications/sync-status",
        headers=student_headers,
        params={"subject_id": ctx["subject_id"]},
    )
    assert sync.status_code == 200, sync.text
    assert sync.json()["unread_count"] == 0


def test_c8_deleting_notification_cleans_read_rows(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(auto_grading=False, course_llm_enabled=False)
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])
    class_id = _subject_class_and_teacher(ctx["subject_id"])["class_id"]

    created = client.post(
        "/api/notifications",
        headers=teacher_headers,
        json={"title": "cleanup", "content": "cleanup", "class_id": class_id, "subject_id": ctx["subject_id"]},
    )
    assert created.status_code == 200, created.text
    notification_id = int(created.json()["id"])
    assert client.post(f"/api/notifications/{notification_id}/read", headers=student_headers).status_code == 200

    deleted = client.delete(f"/api/notifications/{notification_id}", headers=teacher_headers)
    assert deleted.status_code == 200, deleted.text

    db = SessionLocal()
    try:
        assert db.query(Notification).filter(Notification.id == notification_id).count() == 0
        assert db.query(NotificationRead).filter(NotificationRead.notification_id == notification_id).count() == 0
    finally:
        db.close()


def test_c9_batch_set_class_flip_flop_keeps_single_required_enrollment(client: TestClient) -> None:
    ctx = _seed_class_move_context()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")

    move_to_b = client.post(
        "/api/users/batch-set-class",
        headers=admin_headers,
        json={"user_ids": [ctx["user_id"]], "class_id": ctx["class_b_id"]},
    )
    assert move_to_b.status_code == 200, move_to_b.text

    move_back = client.post(
        "/api/users/batch-set-class",
        headers=admin_headers,
        json={"user_ids": [ctx["user_id"]], "class_id": ctx["class_a_id"]},
    )
    assert move_back.status_code == 200, move_back.text

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == ctx["user_id"]).one()
        student = db.query(Student).filter(Student.id == ctx["student_id"]).one()
        enrollments = (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.student_id == ctx["student_id"])
            .all()
        )
        subject_ids = [int(row.subject_id) for row in enrollments]
        assert user.class_id == ctx["class_a_id"]
        assert student.class_id == ctx["class_a_id"]
        assert subject_ids.count(ctx["course_a_id"]) == 1
        assert ctx["course_b_id"] not in subject_ids
    finally:
        db.close()


def test_c10_batch_import_retry_keeps_one_student_and_one_required_enrollment(client: TestClient) -> None:
    ensure_admin()
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    uid = uuid.uuid4().hex[:8]
    student_no = f"batch_same_{uid}"

    db = SessionLocal()
    try:
        klass = Class(name=f"batch-class-{uid}", grade=2026)
        db.add(klass)
        db.flush()
        teacher = User(
            username=f"batch_teacher_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="Batch Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()
        course = Subject(name=f"batch-course-{uid}", teacher_id=teacher.id, class_id=klass.id, course_type="required", status="active")
        db.add(course)
        db.flush()
        db.add(SubjectClassLink(subject_id=course.id, class_id=klass.id, enrollment_mode="all_in_class"))
        db.commit()
        class_id = int(klass.id)
        course_id = int(course.id)
    finally:
        db.close()

    payload = {"students": [{"name": "Retry Student", "student_no": student_no, "gender": "male", "class_id": class_id}]}
    first = client.post("/api/students/batch", headers=admin_headers, json=payload)
    second = client.post("/api/students/batch", headers=admin_headers, json=payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["success"] == 1
    assert second.json()["success"] == 0

    db = SessionLocal()
    try:
        students = db.query(Student).filter(Student.student_no == student_no).all()
        assert len(students) == 1
        enrollments = (
            db.query(CourseEnrollment)
            .filter(CourseEnrollment.student_id == students[0].id, CourseEnrollment.subject_id == course_id)
            .all()
        )
        assert len(enrollments) == 1
    finally:
        db.close()


def test_c11_roster_enroll_after_batch_import_skips_existing_enrollment(client: TestClient) -> None:
    ensure_admin()
    ctx = _seed_class_move_context()
    teacher_username = None
    db = SessionLocal()
    try:
        teacher_username = db.query(User).filter(User.id == ctx["teacher_id"]).one().username
    finally:
        db.close()
    teacher_headers = login_api(client, teacher_username, "tp")
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    student_no = f"roster_imp_{uuid.uuid4().hex[:8]}"

    imported = client.post(
        "/api/students/batch",
        headers=admin_headers,
        json={"students": [{"name": "Roster Imported", "student_no": student_no, "gender": "female", "class_id": ctx["class_a_id"]}]},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["success"] == 1

    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.student_no == student_no).one()
        student_id = int(student.id)
    finally:
        db.close()

    roster = client.post(
        f"/api/subjects/{ctx['course_a_id']}/roster-enroll",
        headers=teacher_headers,
        json={"student_ids": [student_id]},
    )
    assert roster.status_code == 200, roster.text
    assert roster.json()["created"] == 0
    assert roster.json()["skipped_already_enrolled"] == 1


def test_c12_quota_recovery_keeps_failed_task_and_later_success(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework(daily_student_token_limit=500000)
    admin_headers = login_api(client, "pytest_admin", "pytest_admin_pass")
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])

    first_submit = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "first quota burn"},
    )
    assert first_submit.status_code == 200, first_submit.text
    first_task_id = _latest_task_id(ctx["homework_id"])

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(81.0, "first ok")),
    ):
        process_grading_task(first_task_id)

    lower = client.put(
        f"/api/llm-settings/admin/students/{ctx['student_id']}/quota-override",
        headers=admin_headers,
        json={"daily_tokens": 25},
    )
    assert lower.status_code == 200, lower.text

    second_submit = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "second should fail quota"},
    )
    assert second_submit.status_code == 200, second_submit.text
    second_task_id = _latest_task_id(ctx["homework_id"])
    process_grading_task(second_task_id)

    raise_cap = client.put(
        f"/api/llm-settings/admin/students/{ctx['student_id']}/quota-override",
        headers=admin_headers,
        json={"daily_tokens": 500000},
    )
    assert raise_cap.status_code == 200, raise_cap.text

    third_submit = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "third should recover"},
    )
    assert third_submit.status_code == 200, third_submit.text
    third_task_id = _latest_task_id(ctx["homework_id"])

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(92.0, "recovered")),
    ):
        process_grading_task(third_task_id)

    db = SessionLocal()
    try:
        second = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == second_task_id).one()
        third = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == third_task_id).one()
        assert second.status == "failed"
        assert second.error_code == "quota_exceeded_student"
        assert third.status == "success"
    finally:
        db.close()


def test_c13_disable_then_reenable_course_llm_preserves_failed_history_and_new_success(client: TestClient) -> None:
    ensure_admin()
    ctx = make_grading_course_with_homework()
    teacher_headers = login_api(client, ctx["teacher_username"], ctx["teacher_password"])
    student_headers = login_api(client, ctx["student_username"], ctx["student_password"])

    first_submit = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "before disable"},
    )
    assert first_submit.status_code == 200, first_submit.text
    first_task_id = _latest_task_id(ctx["homework_id"])

    disabled = client.put(
        f"/api/llm-settings/courses/{ctx['subject_id']}",
        headers=teacher_headers,
        json={"is_enabled": False, "teacher_prompt": "disabled", "endpoints": [{"preset_id": ctx["preset_id"], "priority": 1}]},
    )
    assert disabled.status_code == 200, disabled.text
    process_grading_task(first_task_id)

    enabled = client.put(
        f"/api/llm-settings/courses/{ctx['subject_id']}",
        headers=teacher_headers,
        json={"is_enabled": True, "teacher_prompt": "reenabled", "endpoints": [{"preset_id": ctx["preset_id"], "priority": 1}]},
    )
    assert enabled.status_code == 200, enabled.text

    second_submit = client.post(
        f"/api/homeworks/{ctx['homework_id']}/submission",
        headers=student_headers,
        json={"content": "after reenable"},
    )
    assert second_submit.status_code == 200, second_submit.text
    second_task_id = _latest_task_id(ctx["homework_id"])

    with mock.patch.object(
        httpx.Client,
        "post",
        lambda self, url, **kwargs: httpx.Response(200, json=json_llm_response(88.0, "ok after reenable")),
    ):
        process_grading_task(second_task_id)

    db = SessionLocal()
    try:
        first = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == first_task_id).one()
        second = db.query(HomeworkGradingTask).filter(HomeworkGradingTask.id == second_task_id).one()
        cfg = db.query(CourseLLMConfig).filter(CourseLLMConfig.subject_id == ctx["subject_id"]).one()
        assert first.status == "failed"
        assert second.status == "success"
        assert bool(cfg.is_enabled) is True
    finally:
        db.close()
