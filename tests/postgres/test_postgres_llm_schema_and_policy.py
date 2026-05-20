"""PostgreSQL-only checks for LLM quota schema: global policy table and course config shape.

Complements ``test_postgres_dialect_guards.py`` with assertions that are meaningless or
weaker on SQLite (information_schema, native types, FK delete rules). Skips unless the
test engine dialect is PostgreSQL (``TEST_DATABASE_URL``).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from apps.backend.courseeval_backend.db.database import SessionLocal, engine
from apps.backend.courseeval_backend.domains.llm.token_quota import get_or_create_global_quota_policy

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Set TEST_DATABASE_URL to a PostgreSQL URL to run PostgreSQL LLM schema tests",
)


def test_pg_llm_01_global_quota_policy_columns_exist():
    """Singleton policy row must expose admin-owned quota and estimation fields."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'llm_global_quota_policies'
                  AND column_name IN (
                      'id',
                      'default_daily_student_tokens',
                      'quota_timezone',
                      'estimated_chars_per_token',
                      'estimated_image_tokens',
                      'max_parallel_grading_tasks',
                      'updated_at'
                  )
                ORDER BY column_name
                """
            )
        ).fetchall()
        names = {r[0] for r in rows}
        assert names == {
            "default_daily_student_tokens",
            "estimated_chars_per_token",
            "estimated_image_tokens",
            "id",
            "max_parallel_grading_tasks",
            "quota_timezone",
            "updated_at",
        }
        by_name = {r[0]: r[1] for r in rows}
        assert by_name["estimated_chars_per_token"] in ("double precision", "real", "numeric")
        assert by_name["estimated_image_tokens"] in ("integer", "bigint")
        assert "timestamp" in by_name["updated_at"].lower()
    finally:
        db.close()


def test_pg_llm_02_course_llm_configs_has_behavior_columns_not_quota_policy_columns():
    """Course LLM row holds routing/prompt/token-boundary fields only (round-4 cleanup)."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'course_llm_configs'
                ORDER BY column_name
                """
            )
        ).fetchall()
        cols = {r[0] for r in rows}
        for need in (
            "id",
            "subject_id",
            "is_enabled",
            "response_language",
            "max_input_tokens",
            "max_output_tokens",
            "system_prompt",
            "teacher_prompt",
            "created_at",
            "updated_at",
        ):
            assert need in cols, f"missing expected column {need}"
        for legacy in (
            "quota_timezone",
            "estimated_chars_per_token",
            "estimated_image_tokens",
            "daily_student_token_limit",
            "daily_course_token_limit",
        ):
            assert legacy not in cols, f"legacy column {legacy} should not exist on course_llm_configs"
    finally:
        db.close()


def test_pg_llm_03_course_llm_config_endpoints_preset_fk_is_cascade():
    """Preset delete must drop course endpoint rows (production safety for preset lifecycle)."""
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT rc.delete_rule
                FROM information_schema.table_constraints tc
                JOIN information_schema.referential_constraints rc
                  ON rc.constraint_schema = tc.table_schema
                 AND rc.constraint_name = tc.constraint_name
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = 'course_llm_config_endpoints'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND tc.constraint_name = 'course_llm_config_endpoints_preset_id_fkey'
                """
            )
        ).fetchone()
        assert row is not None
        assert str(row[0]).upper() == "CASCADE"
    finally:
        db.close()


def test_pg_llm_04_student_token_overrides_unique_on_student_id():
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT c.conname
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public'
                  AND t.relname = 'llm_student_token_overrides'
                  AND c.contype = 'u'
                """
            )
        ).fetchall()
        names = [r[0] for r in row]
        assert names, "expected at least one UNIQUE constraint on llm_student_token_overrides"
        ddl = " ".join(names).lower()
        assert "student" in ddl
    finally:
        db.close()


def test_pg_llm_05_get_or_create_global_quota_policy_row_readable():
    """ORM path used at runtime must see the global policy row after schema reset."""
    db = SessionLocal()
    try:
        pol = get_or_create_global_quota_policy(db)
        assert pol.id == 1
        assert pol.default_daily_student_tokens is not None
        assert (pol.quota_timezone or "").strip()
        assert float(pol.estimated_chars_per_token or 0) > 0
        assert int(pol.estimated_image_tokens or 0) >= 1
        assert int(pol.max_parallel_grading_tasks or 0) >= 1
    finally:
        db.close()


def test_pg_llm_06_llm_token_usage_logs_subject_id_nullable_for_global_shape():
    """Usage logs keep subject_id for attribution; column must exist and be nullable."""
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT is_nullable FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'llm_token_usage_logs'
                  AND column_name = 'subject_id'
                """
            )
        ).fetchone()
        assert row is not None
        assert row[0] == "YES"
    finally:
        db.close()


def test_pg_llm_07_homework_grading_tasks_status_column_exists():
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT data_type FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'homework_grading_tasks'
                  AND column_name = 'status'
                """
            )
        ).fetchone()
        assert row is not None
        assert "char" in row[0].lower() or row[0] in ("text", "varchar", "character varying")
    finally:
        db.close()
