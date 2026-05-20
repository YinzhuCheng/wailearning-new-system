"""Shared factories for LLM + homework API tests."""

from __future__ import annotations

import json as json_stdlib
import uuid

import httpx
from fastapi.testclient import TestClient

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import (
    Class,
    CourseEnrollment,
    CourseLLMConfig,
    CourseLLMConfigEndpoint,
    Homework,
    LLMEndpointPreset,
    LLMStudentTokenOverride,
    Student,
    Subject,
    SubjectClassLink,
    User,
    UserRole,
)


def login_api(client: TestClient, username: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def json_llm_response(score: float, comment: str) -> dict:
    payload = json_stdlib.dumps({"score": score, "comment": comment}, ensure_ascii=False)
    return {
        "choices": [{"message": {"content": payload}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def ensure_admin() -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "pytest_admin").first():
            db.add(
                User(
                    username="pytest_admin",
                    hashed_password=get_password_hash("pytest_admin_pass"),
                    real_name="Pytest Admin",
                    role=UserRole.ADMIN.value,
                )
            )
            db.commit()
    finally:
        db.close()


def make_grading_course_with_homework(
    *,
    auto_grading: bool = True,
    course_llm_enabled: bool = True,
    preset_max_retries: int = 2,
    daily_student_token_limit: int | None = None,
) -> dict:
    uid = uuid.uuid4().hex[:10]
    db = SessionLocal()
    try:
        klass = Class(name=f"pytest-class-{uid}", grade=2026)
        db.add(klass)
        db.flush()

        teacher = User(
            username=f"pytest_teacher_{uid}",
            hashed_password=get_password_hash("pytest_teacher_pass"),
            real_name="Pytest Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()

        stu_username = f"stu_{uid}"
        su = User(
            username=stu_username,
            hashed_password=get_password_hash("stu_pass"),
            real_name="Student One",
            role=UserRole.STUDENT.value,
            class_id=klass.id,
        )
        db.add(su)
        db.flush()

        stud = Student(name="Student One", student_no=stu_username, class_id=klass.id)
        db.add(stud)
        db.flush()

        course = Subject(name=f"pytest-course-{uid}", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.flush()
        db.add(SubjectClassLink(subject_id=course.id, class_id=klass.id, enrollment_mode="all_in_class"))

        db.add(
            CourseEnrollment(
                subject_id=course.id,
                student_id=stud.id,
                class_id=klass.id,
                enrollment_type="required",
            )
        )

        preset = LLMEndpointPreset(
            name=f"pytest-llm-preset-{uid}",
            base_url="https://api.virtual.test/v1/",
            api_key="sk-test",
            model_name="virtual",
            max_retries=preset_max_retries,
            initial_backoff_seconds=1,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        db.add(preset)
        db.flush()

        cfg = CourseLLMConfig(
            subject_id=course.id,
            is_enabled=course_llm_enabled,
            max_input_tokens=16000,
            max_output_tokens=1200,
        )
        db.add(cfg)
        db.flush()
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, preset_id=preset.id, priority=1))
        if daily_student_token_limit is not None:
            db.merge(LLMStudentTokenOverride(student_id=stud.id, daily_tokens=int(daily_student_token_limit)))

        hw = Homework(
            title="pytest homework",
            content="Do the thing.",
            class_id=klass.id,
            subject_id=course.id,
            max_score=100,
            auto_grading_enabled=auto_grading,
            created_by=teacher.id,
        )
        db.add(hw)
        db.commit()
        db.refresh(hw)
        return {
            "homework_id": hw.id,
            "preset_id": preset.id,
            "student_id": stud.id,
            "student_user_id": su.id,
            "teacher_id": teacher.id,
            "subject_id": course.id,
            "class_id": klass.id,
            "student_username": stu_username,
            "student_password": "stu_pass",
            "teacher_username": teacher.username,
            "teacher_password": "pytest_teacher_pass",
        }
    finally:
        db.close()


def make_multi_student_scenario(
    num_students: int,
    *,
    auto_grading: bool = True,
    daily_student_token_limit: int | None = None,
) -> dict:
    if num_students < 1:
        raise ValueError("num_students must be at least 1")
    uid = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        klass = Class(name=f"multi-{uid}", grade=2026)
        db.add(klass)
        db.flush()

        teacher = User(
            username=f"mt_teach_{uid}",
            hashed_password=get_password_hash("tp"),
            real_name="MT",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.flush()

        course = Subject(name=f"mc_{uid}", teacher_id=teacher.id, class_id=klass.id)
        db.add(course)
        db.flush()

        preset = LLMEndpointPreset(
            name=f"mp_{uid}",
            base_url="https://api.v.test/v1/",
            api_key="k",
            model_name="m",
            max_retries=0,
            is_active=True,
            supports_vision=True,
            validation_status="validated",
        )
        db.add(preset)
        db.flush()

        cfg = CourseLLMConfig(
            subject_id=course.id,
            is_enabled=True,
            max_input_tokens=16000,
            max_output_tokens=1200,
        )
        db.add(cfg)
        db.flush()
        db.add(CourseLLMConfigEndpoint(config_id=cfg.id, preset_id=preset.id, priority=1))

        hw = Homework(
            title="multi hw",
            content="c",
            class_id=klass.id,
            subject_id=course.id,
            max_score=100,
            auto_grading_enabled=auto_grading,
            created_by=teacher.id,
        )
        db.add(hw)
        db.flush()

        students: list[dict] = []
        for i in range(num_students):
            un = f"ms_{uid}_{i}"
            u = User(
                username=un,
                hashed_password=get_password_hash("p"),
                real_name=f"S{i}",
                role=UserRole.STUDENT.value,
                class_id=klass.id,
            )
            db.add(u)
            db.flush()
            st = Student(name=f"Name{i}", student_no=un, class_id=klass.id)
            db.add(st)
            db.flush()
            db.add(
                CourseEnrollment(
                    subject_id=course.id,
                    student_id=st.id,
                    class_id=klass.id,
                    enrollment_type="required",
                )
            )
            if daily_student_token_limit is not None:
                db.merge(LLMStudentTokenOverride(student_id=st.id, daily_tokens=int(daily_student_token_limit)))
            students.append(
                {
                    "username": un,
                    "password": "p",
                    "student_id": st.id,
                }
            )

        db.commit()
        db.refresh(hw)
        return {
            "homework_id": hw.id,
            "subject_id": course.id,
            "preset_id": preset.id,
            "teacher_username": teacher.username,
            "teacher_password": "tp",
            "students": students,
        }
    finally:
        db.close()


def patch_httpx_post(fn):
    from unittest import mock

    return mock.patch.object(httpx.Client, "post", fn)
