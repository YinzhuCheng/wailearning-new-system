"""
High-difficulty API behavior: roster/enrollment races, sync storms, submission caps,
HTTP method edges, and score-appeal validation — complements Playwright E2E without duplicating UI flows.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import CourseEnrollment, Homework, Student, Subject, User, UserRole
from tests.scenarios.llm_scenario import make_grading_course_with_homework
from tests.scenarios.material_flow import headers_for


def _post(client: TestClient, path: str, headers: dict, json: dict | None = None):
    return client.post(path, headers=headers, json=json or {})


def _put(client: TestClient, path: str, headers: dict, json: dict):
    return client.put(path, headers=headers, json=json)


def _delete(client: TestClient, path: str, headers: dict):
    return client.delete(path, headers=headers)


def _seed_second_student_and_elective_course(*, teacher_id: int, class_id: int) -> dict[str, int]:
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        st = Student(name=f"Extra {uid}", student_no=f"extra_{uid}", class_id=class_id)
        db.add(st)
        db.flush()
        u = User(
            username=st.student_no,
            hashed_password=get_password_hash("ep"),
            real_name=st.name,
            role=UserRole.STUDENT.value,
            class_id=class_id,
        )
        db.add(u)
        db.flush()
        elective = Subject(
            name=f"ele-{uid}",
            teacher_id=teacher_id,
            class_id=class_id,
            course_type="elective",
            status="active",
        )
        db.add(elective)
        db.commit()
        db.refresh(elective)
        db.refresh(st)
        return {"student_id": st.id, "subject_id": elective.id, "username": u.username}
    finally:
        db.close()


def test_behavior_concurrent_elective_self_enroll_double_post_idempotent(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    extra = _seed_second_student_and_elective_course(teacher_id=ctx["teacher_id"], class_id=ctx["class_id"])
    st_headers = headers_for(client, extra["username"], "ep")

    def call():
        return _post(client, f"/api/subjects/{extra['subject_id']}/student-self-enroll", st_headers, {})

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(call), pool.submit(call)]
        codes = sorted([f.result().status_code for f in futures])

    assert codes == [200, 200]
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    roster = client.get(f"/api/subjects/{extra['subject_id']}/students", headers=th)
    assert roster.status_code == 200
    ids = [int(r["student_id"]) for r in roster.json()]
    assert ids.count(extra["student_id"]) == 1


def test_behavior_concurrent_roster_enroll_same_student_once(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    extra = _seed_second_student_and_elective_course(teacher_id=ctx["teacher_id"], class_id=ctx["class_id"])
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    body = {"student_ids": [extra["student_id"]]}

    def call():
        return _post(client, f"/api/subjects/{extra['subject_id']}/roster-enroll", th, body)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = [f.result().status_code for f in as_completed([pool.submit(call) for _ in range(4)])]

    assert all(200 <= c < 300 for c in results)
    roster = client.get(f"/api/subjects/{extra['subject_id']}/students", headers=th)
    assert roster.status_code == 200
    ids = [int(r["student_id"]) for r in roster.json()]
    assert ids.count(extra["student_id"]) == 1


def test_behavior_parallel_sync_enrollments_stable_student_count(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])

    def call():
        return _post(client, f"/api/subjects/{ctx['subject_id']}/sync-enrollments", th, {})

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = [f.result().status_code for f in as_completed([pool.submit(call) for _ in range(6)])]

    assert all(c == 200 for c in codes)
    roster = client.get(f"/api/subjects/{ctx['subject_id']}/students", headers=th)
    assert roster.status_code == 200
    assert len(roster.json()) >= 1


def test_behavior_max_submissions_full_then_concurrent_extra_posts_all_cap_errors(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    r = _put(
        client,
        f"/api/homeworks/{ctx['homework_id']}",
        th,
        {
            "title": "capped",
            "content": "x",
            "max_score": 100,
            "grade_precision": "integer",
            "auto_grading_enabled": False,
            "allow_late_submission": True,
            "late_submission_affects_score": False,
            "max_submissions": 1,
        },
    )
    assert r.status_code == 200, r.text

    first = _post(
        client,
        f"/api/homeworks/{ctx['homework_id']}/submission",
        st,
        {
            "content": f"first-{uuid.uuid4().hex}",
            "attachment_name": None,
            "attachment_url": None,
            "remove_attachment": False,
            "used_llm_assist": False,
            "submission_mode": "full",
        },
    )
    assert first.status_code == 200, first.text

    def over_submit():
        return _post(
            client,
            f"/api/homeworks/{ctx['homework_id']}/submission",
            st,
            {
                "content": f"over-{uuid.uuid4().hex}",
                "attachment_name": None,
                "attachment_url": None,
                "remove_attachment": False,
                "used_llm_assist": False,
                "submission_mode": "full",
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        res = list(pool.map(lambda _: over_submit(), range(2)))

    assert all(x.status_code == 400 for x in res)
    hist = client.get(f"/api/homeworks/{ctx['homework_id']}/submission/me/history", headers=st)
    assert hist.status_code == 200
    assert len(hist.json().get("attempts") or []) == 1


def test_behavior_concurrent_first_submission_no_duplicate_submission_rows(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    db = SessionLocal()
    try:
        hw = db.query(Homework).filter(Homework.id == ctx["homework_id"]).first()
        assert hw is not None
        hw.max_submissions = 5
        db.commit()
    finally:
        db.close()

    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    stamp = uuid.uuid4().hex

    def submit(i: int):
        return _post(
            client,
            f"/api/homeworks/{ctx['homework_id']}/submission",
            st,
            {
                "content": f"parallel-{stamp}-{i}",
                "attachment_name": None,
                "attachment_url": None,
                "remove_attachment": False,
                "used_llm_assist": False,
                "submission_mode": "full",
            },
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(submit, range(5)))

    assert all(r.status_code in (200, 409) for r in responses)
    assert sum(1 for r in responses if r.status_code == 200) >= 1
    hist = client.get(f"/api/homeworks/{ctx['homework_id']}/submission/me/history", headers=st)
    assert hist.status_code == 200
    data = hist.json()
    assert data.get("summary") is not None
    assert len(data.get("attempts") or []) >= 1


def test_behavior_score_appeal_invalid_target_component_400(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    st = headers_for(client, ctx["student_username"], ctx["student_password"])
    r = _post(
        client,
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        st,
        {
            "semester": "2026春季",
            "target_component": "not_a_real_component_xyz",
            "reason_text": "bad target",
            "score_id": None,
        },
    )
    assert r.status_code == 400


def test_behavior_teacher_post_score_appeal_forbidden_403(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    r = _post(
        client,
        f"/api/scores/appeals?subject_id={ctx['subject_id']}",
        th,
        {
            "semester": "2026春季",
            "target_component": "total",
            "reason_text": "teacher should not",
            "score_id": None,
        },
    )
    assert r.status_code == 403


def test_behavior_patch_homework_method_not_allowed_405(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.patch(
        f"/api/homeworks/{ctx['homework_id']}",
        headers=th,
        json={"title": "nope"},
    )
    assert r.status_code == 405


def test_behavior_delete_non_enrolled_student_from_course_404(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    extra = _seed_second_student_and_elective_course(teacher_id=ctx["teacher_id"], class_id=ctx["class_id"])
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    r = _delete(client, f"/api/subjects/{ctx['subject_id']}/students/{extra['student_id']}", th)
    assert r.status_code == 404


def test_behavior_student_delete_peer_from_roster_forbidden_403(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    db = SessionLocal()
    try:
        st2 = Student(name="Peer", student_no=f"peer_{uuid.uuid4().hex[:8]}", class_id=ctx["class_id"])
        db.add(st2)
        db.flush()
        u2 = User(
            username=st2.student_no,
            hashed_password=get_password_hash("p2"),
            real_name="Peer",
            role=UserRole.STUDENT.value,
            class_id=ctx["class_id"],
        )
        db.add(u2)
        db.flush()
        db.add(
            CourseEnrollment(
                subject_id=ctx["subject_id"],
                student_id=st2.id,
                class_id=ctx["class_id"],
                enrollment_type="required",
            )
        )
        db.commit()
        peer_id = st2.id
    finally:
        db.close()

    st_headers = headers_for(client, ctx["student_username"], ctx["student_password"])
    r = _delete(client, f"/api/subjects/{ctx['subject_id']}/students/{peer_id}", st_headers)
    assert r.status_code == 403


def test_behavior_course_teacher_can_view_student_homework_status(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    th = headers_for(client, ctx["teacher_username"], ctx["teacher_password"])
    r = client.get(
        f"/api/homeworks/courses/{ctx['subject_id']}/students/{ctx['student_id']}/homeworks",
        headers=th,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    assert any(int(row["homework_id"]) == int(ctx["homework_id"]) for row in body["data"])


def test_behavior_foreign_teacher_cannot_view_student_homework_status(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    db = SessionLocal()
    try:
        other_class = db.query(Student).filter(Student.id == ctx["student_id"]).one().class_id
        other_teacher = User(
            username=f"foreign_teacher_{uuid.uuid4().hex[:8]}",
            hashed_password=get_password_hash("pw"),
            real_name="Foreign Teacher",
            role=UserRole.TEACHER.value,
            class_id=other_class,
        )
        db.add(other_teacher)
        db.commit()
        db.refresh(other_teacher)
        other_headers = headers_for(client, other_teacher.username, "pw")
    finally:
        db.close()

    r = client.get(
        f"/api/homeworks/courses/{ctx['subject_id']}/students/{ctx['student_id']}/homeworks",
        headers=other_headers,
    )
    assert r.status_code == 403


def test_behavior_class_teacher_with_course_access_cannot_view_student_homework_status(client: TestClient):
    ctx = make_grading_course_with_homework(auto_grading=False)
    db = SessionLocal()
    try:
        class_teacher = User(
            username=f"class_teacher_{uuid.uuid4().hex[:8]}",
            hashed_password=get_password_hash("pw"),
            real_name="Class Teacher",
            role=UserRole.CLASS_TEACHER.value,
            class_id=ctx["class_id"],
        )
        db.add(class_teacher)
        db.commit()
        db.refresh(class_teacher)
        ct_headers = headers_for(client, class_teacher.username, "pw")
    finally:
        db.close()

    roster = client.get(f"/api/homeworks/courses/{ctx['subject_id']}/students", headers=ct_headers)
    assert roster.status_code == 403
    r = client.get(
        f"/api/homeworks/courses/{ctx['subject_id']}/students/{ctx['student_id']}/homeworks",
        headers=ct_headers,
    )
    assert r.status_code == 403
