"""Fifteen high-difficulty API checks against the seeded E2E dev surface (auth, seed gates, LLM dev helpers).

Reuses the same DB reset contract as ``test_e2e_dev_seed.py`` so each test starts from a clean schema.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.core.config import settings
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.main import app
from apps.backend.courseeval_backend.db.models import Homework, User, UserRole


@pytest.fixture(autouse=True)
def _reset_e2e_settings():
    yield
    settings.E2E_DEV_SEED_ENABLED = False
    settings.E2E_DEV_SEED_TOKEN = ""
    if hasattr(settings, "E2E_DEV_REQUIRE_ADMIN_JWT"):
        settings.E2E_DEV_REQUIRE_ADMIN_JWT = False


@pytest.fixture(autouse=True)
def _reset_db():
    from tests.db_reset import reset_test_database_schema

    reset_test_database_schema()
    from apps.backend.courseeval_backend.bootstrap import ensure_schema_updates

    ensure_schema_updates()
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "adm").first():
            db.add(
                User(
                    username="adm",
                    hashed_password=get_password_hash("a"),
                    real_name="Admin",
                    role=UserRole.ADMIN.value,
                )
            )
            db.commit()
    finally:
        db.close()
    yield
    SessionLocal().close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_SEED = "hazard-tier-e2e-dev-token"


def _enable_seed() -> None:
    settings.E2E_DEV_SEED_ENABLED = True
    settings.E2E_DEV_SEED_TOKEN = _SEED


def _seed_headers() -> dict[str, str]:
    return {"X-E2E-Seed-Token": _SEED}


def _admin_headers(client: TestClient) -> dict[str, str]:
    body = f"username=adm&password=a"
    lr = client.post(
        "/api/auth/login",
        content=body.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert lr.status_code == 200, lr.text
    tok = lr.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _powerful_e2e_headers(client: TestClient) -> dict[str, str]:
    """Seed token + admin JWT when E2E_DEV_REQUIRE_ADMIN_JWT is enabled."""
    return {**_seed_headers(), **_admin_headers(client)}


def _reset_scenario(client: TestClient) -> dict:
    _enable_seed()
    r = client.post("/api/e2e/dev/reset-scenario", headers=_seed_headers())
    assert r.status_code == 200, r.text
    return r.json()


def _login_form(client: TestClient, username: str, password: str) -> str:
    body = f"username={username}&password={password}"
    lr = client.post(
        "/api/auth/login",
        content=body.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert lr.status_code == 200, lr.text
    return lr.json()["access_token"]


def test_hz01_reset_scenario_returns_stable_id_bundle(client: TestClient) -> None:
    s = _reset_scenario(client)
    for key in (
        "suffix",
        "course_required_id",
        "homework_id",
        "material_discussion_id",
        "class_id_1",
        "student_plain",
    ):
        assert key in s
    assert int(s["course_required_id"]) > 0
    assert int(s["homework_id"]) > 0


def test_hz01b_reset_scenario_binds_seeded_student_accounts_for_roster_actions(client: TestClient) -> None:
    s = _reset_scenario(client)
    admin_tok = _login_form(client, s["admin"]["username"], s["password_admin"])

    users = client.get("/api/users", headers={"Authorization": f"Bearer {admin_tok}"})
    assert users.status_code == 200, users.text
    users_by_name = {row["username"]: row for row in users.json()}
    for key in ("student_plain", "student_drop", "student_b"):
        seeded = s[key]
        row = users_by_name[seeded["username"]]
        assert int(row["student_id"]) == int(seeded["student_row_id"])
        assert int(row["id"]) == int(seeded["student_user_id"])

    teacher_tok = _login_form(client, s["teacher_own"]["username"], s["password_teacher_student"])
    roster = client.get(
        f"/api/subjects/{s['course_required_id']}/students",
        headers={"Authorization": f"Bearer {teacher_tok}"},
    )
    assert roster.status_code == 200, roster.text
    by_student_id = {int(row["student_id"]): row for row in roster.json()}
    plain = s["student_plain"]
    assert int(by_student_id[int(plain["student_row_id"])]["student_user_id"]) == int(plain["student_user_id"])


def test_hz02_reset_scenario_rejects_wrong_seed_token(client: TestClient) -> None:
    _enable_seed()
    r = client.post("/api/e2e/dev/reset-scenario", headers={"X-E2E-Seed-Token": "not-the-token"})
    assert r.status_code == 403


def test_hz03_reset_scenario_rejects_missing_seed_header(client: TestClient) -> None:
    _enable_seed()
    r = client.post("/api/e2e/dev/reset-scenario")
    assert r.status_code == 403


def test_hz04_mock_llm_configure_rejects_wrong_seed(client: TestClient) -> None:
    _enable_seed()
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True
    r = client.post(
        "/api/e2e/dev/mock-llm/configure",
        headers={"X-E2E-Seed-Token": "wrong"},
        json={"profiles": {"p": {"steps": [{"kind": "ok", "score": 1.0, "comment": "x"}]}}},
    )
    assert r.status_code == 403


def test_hz05_mock_llm_configure_profiles_roundtrip_state(client: TestClient) -> None:
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True
    _reset_scenario(client)
    cfg = client.post(
        "/api/e2e/dev/mock-llm/configure",
        headers=_powerful_e2e_headers(client),
        json={"profiles": {"hz_prof": {"steps": [{"kind": "ok", "score": 77.0, "comment": "hz"}], "repeat_last": True}}},
    )
    assert cfg.status_code == 200, cfg.text
    st = client.get("/api/e2e/dev/mock-llm/state", headers=_powerful_e2e_headers(client))
    assert st.status_code == 200, st.text
    assert "hz_prof" in st.json().get("profiles", {})


def test_hz06_grading_state_requires_valid_seed(client: TestClient) -> None:
    _enable_seed()
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True
    r = client.get("/api/e2e/dev/grading-state", headers={"X-E2E-Seed-Token": "nope"})
    assert r.status_code == 403


def test_hz07_process_grading_requires_valid_seed(client: TestClient) -> None:
    _enable_seed()
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True
    r = client.post(
        "/api/e2e/dev/process-grading",
        headers={"X-E2E-Seed-Token": "nope"},
        json={"max_tasks": 1},
    )
    assert r.status_code == 403


def test_hz08_worker_status_payload_shape_when_disabled(client: TestClient) -> None:
    _reset_scenario(client)
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True
    r = client.post("/api/e2e/dev/worker", headers=_powerful_e2e_headers(client), json={"action": "status"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert "running" in body


def test_hz09_mark_preset_validated_rejects_non_int_preset_id(client: TestClient) -> None:
    _reset_scenario(client)
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True
    r = client.post(
        "/api/e2e/dev/mark-preset-validated",
        headers=_powerful_e2e_headers(client),
        json={"preset_id": "not-an-int"},
    )
    assert r.status_code == 400


def test_hz10_mark_preset_validated_returns_404_for_unknown_preset(client: TestClient) -> None:
    _reset_scenario(client)
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True
    r = client.post(
        "/api/e2e/dev/mark-preset-validated",
        headers=_powerful_e2e_headers(client),
        json={"preset_id": 999_999_999},
    )
    assert r.status_code == 404


def test_hz11_teacher_forbidden_student_quotas_summary(client: TestClient) -> None:
    s = _reset_scenario(client)
    tok = _login_form(client, s["teacher_own"]["username"], s["password_teacher_student"])
    r = client.get("/api/llm-settings/courses/student-quotas", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_hz12_teacher_forbidden_student_quota_per_course(client: TestClient) -> None:
    s = _reset_scenario(client)
    tok = _login_form(client, s["teacher_own"]["username"], s["password_teacher_student"])
    sid = int(s["course_required_id"])
    r = client.get(f"/api/llm-settings/courses/student-quota/{sid}", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_hz13_other_teacher_cannot_delete_foreign_homework(client: TestClient) -> None:
    s = _reset_scenario(client)
    tok = _login_form(client, s["teacher_other"]["username"], s["password_teacher_student"])
    hid = int(s["homework_id"])
    r = client.delete(f"/api/homeworks/{hid}", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code in (403, 404)


def test_hz14_student_mark_all_read_clears_unread_for_course(client: TestClient) -> None:
    s = _reset_scenario(client)
    st_tok = _login_form(client, s["student_plain"]["username"], s["password_teacher_student"])
    th_tok = _login_form(client, s["teacher_own"]["username"], s["password_teacher_student"])
    subj = int(s["course_required_id"])
    cls = int(s["class_id_1"])
    created = client.post(
        "/api/notifications",
        headers={"Authorization": f"Bearer {th_tok}", "Content-Type": "application/json"},
        json={
            "title": "hazard-tier",
            "content": "body",
            "class_id": cls,
            "subject_id": subj,
        },
    )
    assert created.status_code == 200, created.text
    nid = int(created.json()["id"])
    assert client.post(f"/api/notifications/{nid}/read", headers={"Authorization": f"Bearer {st_tok}"}).status_code == 200
    created2 = client.post(
        "/api/notifications",
        headers={"Authorization": f"Bearer {th_tok}", "Content-Type": "application/json"},
        json={"title": "hazard-tier-2", "content": "b2", "class_id": cls, "subject_id": subj},
    )
    assert created2.status_code == 200, created2.text
    assert (
        client.post(
            "/api/notifications/mark-all-read",
            headers={"Authorization": f"Bearer {st_tok}"},
            params={"subject_id": subj},
        ).status_code
        == 200
    )
    sync = client.get(
        "/api/notifications/sync-status",
        headers={"Authorization": f"Bearer {st_tok}"},
        params={"subject_id": subj},
    )
    assert sync.status_code == 200, sync.text
    assert int(sync.json().get("unread_count") or 0) == 0


def test_hz15_discussion_list_clamps_page_size_above_user_max(client: TestClient) -> None:
    """``page_size`` above ``Query(..., le=100)`` is invalid; at ``le=100`` the handler clamps to [5,50]."""
    s = _reset_scenario(client)
    tok = _login_form(client, s["student_plain"]["username"], s["password_teacher_student"])
    mid = int(s["material_discussion_id"])
    subj = int(s["course_required_id"])
    cls = int(s["class_id_1"])
    path = (
        f"/api/discussions?target_type=material&target_id={mid}"
        f"&subject_id={subj}&class_id={cls}&page=1&page_size=100"
    )
    r = client.get(path, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert int(body.get("page_size") or 0) <= 50


def test_hz16_powerful_e2e_requires_admin_jwt_when_dual_gate_enabled(client: TestClient) -> None:
    """Dual gate: valid seed alone is insufficient for mock-llm/configure when REQUIRE_ADMIN_JWT is on."""
    _enable_seed()
    settings.E2E_DEV_REQUIRE_ADMIN_JWT = True
    r = client.post(
        "/api/e2e/dev/mock-llm/configure",
        headers=_seed_headers(),
        json={"profiles": {"no_auth": {"steps": [{"kind": "ok", "score": 1.0, "comment": "x"}], "repeat_last": True}}},
    )
    assert r.status_code == 403


def test_hz17_discussion_list_rejects_page_size_above_query_limit(client: TestClient) -> None:
    s = _reset_scenario(client)
    tok = _login_form(client, s["teacher_own"]["username"], s["password_teacher_student"])
    hid = int(s["homework_id"])
    subj = int(s["course_required_id"])
    cls = int(s["class_id_1"])
    r = client.get(
        "/api/discussions",
        headers={"Authorization": f"Bearer {tok}"},
        params={
            "target_type": "homework",
            "target_id": hid,
            "subject_id": subj,
            "class_id": cls,
            "page": 1,
            "page_size": 200,
        },
    )
    assert r.status_code == 422


def test_hz18_discussion_list_rejects_homework_class_id_mismatch(client: TestClient) -> None:
    s = _reset_scenario(client)
    tok = _login_form(client, s["teacher_own"]["username"], s["password_teacher_student"])
    hid = int(s["homework_id"])
    subj = int(s["course_required_id"])
    wrong_class = int(s["class_id_2"])
    r = client.get(
        "/api/discussions",
        headers={"Authorization": f"Bearer {tok}"},
        params={
            "target_type": "homework",
            "target_id": hid,
            "subject_id": subj,
            "class_id": wrong_class,
            "page": 1,
        },
    )
    assert r.status_code == 400


def test_hz19_student_cannot_access_foreign_homework_submission_me(client: TestClient) -> None:
    s = _reset_scenario(client)
    student_tok = _login_form(client, s["student_plain"]["username"], s["password_teacher_student"])
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.username == s["admin"]["username"]).first()
        assert admin_user is not None
        hw = Homework(
            title=f"hz19-foreign-{s['suffix']}",
            content="cross-class probe",
            class_id=int(s["class_id_2"]),
            subject_id=int(s["course_other_teacher_id"]),
            max_score=100,
            auto_grading_enabled=False,
            created_by=int(admin_user.id),
        )
        db.add(hw)
        db.commit()
        db.refresh(hw)
        foreign_homework_id = int(hw.id)
    finally:
        db.close()

    r = client.get(
        f"/api/homeworks/{foreign_homework_id}/submission/me",
        headers={"Authorization": f"Bearer {student_tok}"},
    )
    assert r.status_code in (403, 404)


def test_hz20_homework_list_rejects_page_size_above_100(client: TestClient) -> None:
    s = _reset_scenario(client)
    tok = _login_form(client, s["teacher_own"]["username"], s["password_teacher_student"])
    r = client.get(
        "/api/homeworks",
        headers={"Authorization": f"Bearer {tok}"},
        params={"subject_id": int(s["course_required_id"]), "page": 1, "page_size": 500},
    )
    assert r.status_code == 422


def test_hz21_materials_list_rejects_page_size_above_100_for_teacher_and_student(client: TestClient) -> None:
    s = _reset_scenario(client)
    subj = int(s["course_required_id"])
    for username in (s["teacher_own"]["username"], s["student_plain"]["username"]):
        password = s["password_teacher_student"]
        tok = _login_form(client, username, password)
        r = client.get(
            "/api/materials",
            headers={"Authorization": f"Bearer {tok}"},
            params={"subject_id": subj, "page": 1, "page_size": 250},
        )
        assert r.status_code == 422


def test_hz22_students_list_rejects_page_size_above_1000_for_admin(client: TestClient) -> None:
    s = _reset_scenario(client)
    tok = _login_form(client, s["admin"]["username"], s["password_admin"])
    r = client.get(
        "/api/students",
        headers={"Authorization": f"Bearer {tok}"},
        params={"page": 1, "page_size": 5000},
    )
    assert r.status_code == 422


def test_hz23_class_teacher_cannot_list_homework_for_orphan_subject(client: TestClient) -> None:
    s = _reset_scenario(client)
    tok = _login_form(client, s["class_teacher"]["username"], s["password_teacher_student"])
    r = client.get(
        "/api/homeworks",
        headers={"Authorization": f"Bearer {tok}"},
        params={"subject_id": int(s["course_orphan_id"]), "page": 1, "page_size": 20},
    )
    assert r.status_code in (403, 404)
