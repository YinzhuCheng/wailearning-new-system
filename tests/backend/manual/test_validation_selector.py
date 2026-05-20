from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SELECTOR = REPO_ROOT / "ops" / "scripts" / "dev" / "select_validation_targets.py"
sys.path.insert(0, str(REPO_ROOT / "ops" / "scripts" / "dev"))
from lint_validation_registry import lint_registry  # noqa: E402
from check_api_surface_governance import check_api_surface_governance  # noqa: E402
from check_ci_baselines import check_ci_baselines  # noqa: E402
from check_operator_scripts import check_scripts as check_operator_scripts  # noqa: E402
from check_validation_policy_gate import evaluate_policy_gate  # noqa: E402
from check_validation_capabilities import build_capabilities, evaluate_target_capabilities  # noqa: E402
from check_validation_debt_registry import check_validation_debt_registry  # noqa: E402
from check_validation_lane_budgets import evaluate_budget, load_budgets  # noqa: E402
from check_high_risk_path_metadata import check_high_risk_path_metadata  # noqa: E402
from check_repo_skills import check_repo_skills  # noqa: E402
from check_schema_governance import check_schema_governance  # noqa: E402
from sync_testing_governance_docs import check_docs as check_testing_governance_docs  # noqa: E402
from sync_pitfall_index_lines import main as sync_pitfall_index_main  # noqa: E402
from pytest_sqlite_guard import build_report, is_pytest_process  # noqa: E402
from search_pitfalls import build_corpus, search_blocks  # noqa: E402
from select_validation_targets import parse_ledger  # noqa: E402
from validation_history import changed_paths_signature  # noqa: E402
from wai_valid_build_custom_args import (  # noqa: E402
    DEFAULT_CONCURRENCY as CUSTOM_BLOCK_DEFAULT_CONCURRENCY,
    build_args as build_custom_block_args,
)
from wai_valid_supervisor import (  # noqa: E402
    DEFAULT_CONCURRENCY as SUPERVISOR_DEFAULT_CONCURRENCY,
    classify_tasks,
    infer_block_name_from_path,
    load_sample_file,
    playwright_spec_arg,
)
from run_validation_target import (
    RESULT_BLOCKED,
    expand_command_placeholders,
    infer_failure_class,
    parse_junit_xml,
    resolve_command_argv,
    target_needs_playwright_preflight,
    with_pytest_junitxml,
)  # noqa: E402


def run_selector(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SELECTOR), "--repo-root", str(REPO_ROOT), *args, "--json"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return json.loads(result.stdout)


def run_validation_target(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "ops" / "scripts" / "dev" / "run_validation_target.py"),
            "--repo-root",
            str(REPO_ROOT),
            *args,
        ],
        cwd=REPO_ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_validation_profile(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "ops" / "scripts" / "dev" / "run_validation_profile.py"),
            "--repo-root",
            str(REPO_ROOT),
            *args,
        ],
        cwd=REPO_ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def recommendation_ids(payload: dict) -> set[str]:
    return {item["id"] for item in payload["recommendations"]}


def recommendation(payload: dict, target_id: str) -> dict:
    for item in payload["recommendations"]:
        if item["id"] == target_id:
            return item
    raise AssertionError(f"{target_id} not recommended; got {recommendation_ids(payload)}")


def required_target_ids(payload: dict, bucket: str) -> set[str]:
    return {
        item["id"]
        for item in payload.get("required_validation", {}).get(bucket, [])
    }


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


class ValidationSelectorTests(unittest.TestCase):
    def test_learning_notes_backend_path_selects_precise_backend_and_playwright_targets(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/api/routers/learning_notes.py")

        ids = recommendation_ids(payload)
        self.assertIn("backend.learning_notes.api", ids)
        self.assertIn("school.e2e.learning_notes_attendance_cover_tier20", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["unmatched_paths"], [])
        self.assertEqual(payload["non_full_validation"]["status"], "needs_review")

        backend_target = recommendation(payload, "backend.learning_notes.api")
        self.assertEqual(backend_target["history_status"], "stale")
        self.assertTrue(
            any(
                reason in backend_target["history_reason"]
                for reason in ("changed-path snapshot", "target trigger changed in current diff")
            ),
            backend_target["history_reason"],
        )
        self.assertIn("learning-notes", backend_target["coverage_tags"])

    def test_unmapped_backend_source_escalates_to_full_postgres(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/unknown_new_module.py")

        self.assertEqual(recommendation_ids(payload), {"full.pytest.postgres"})
        self.assertEqual(payload["non_full_validation"]["status"], "not_sufficient")
        self.assertIn("full validation target", payload["non_full_validation"]["reason"])
        target = recommendation(payload, "full.pytest.postgres")
        self.assertEqual(target["history_status"], "stale")
        self.assertTrue(
            any(reason in target["history_reason"] for reason in ("fallback", "different changed-path snapshot")),
            target["history_reason"],
        )

    def test_admin_homework_view_selects_build_and_homework_playwright_target(self):
        payload = run_selector("--paths", "apps/web/school/src/views/HomeworkSubmissions.vue")

        ids = recommendation_ids(payload)
        self.assertIn("frontend.school.build", ids)
        self.assertIn("school.e2e.homework_comment_cover_tier4", ids)
        self.assertNotIn("school.e2e.full", ids)
        self.assertEqual(payload["unmatched_paths"], [])

        e2e_target = recommendation(payload, "school.e2e.homework_comment_cover_tier4")
        self.assertTrue(e2e_target["requires_review_reason"])
        self.assertIn("homework", e2e_target["coverage_tags"])
        self.assertIn("frontend.school.build", required_target_ids(payload, "required_targets"))
        self.assertIn("school.e2e.homework_comment_cover_tier4", required_target_ids(payload, "optional_targets"))

    def test_playwright_harness_selects_full_playwright_and_marks_non_full_insufficient(self):
        payload = run_selector("--paths", "tests/e2e/web-school/global-setup.cjs")

        ids = recommendation_ids(payload)
        self.assertIn("school.e2e.full", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "not_sufficient")
        self.assertIn("school.e2e.full", payload["non_full_validation"]["reason"])
        self.assertIn("school.e2e.full", required_target_ids(payload, "required_review_targets"))

    def test_docs_only_change_is_static_and_non_full_acceptable_after_running_targets(self):
        payload = run_selector("--paths", "docs/testing/TEST_SUITE_MAP.md")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.validation_selector", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_repo_local_skill_change_is_static_text_governance(self):
        payload = run_selector("--paths", "skills/validation-selection/SKILL.md")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.repo_local_skills", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_repo_local_skill_script_change_is_static_skill_governance(self):
        payload = run_selector("--paths", "skills/security-redteam-iteration/scripts/suggest_next_ids.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.repo_local_skills", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_local_test_guard_change_is_static_selector_governance(self):
        payload = run_selector("--paths", "ops/scripts/dev/pytest_sqlite_guard.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.local_test_guardrails", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_pitfall_search_change_is_static_selector_governance(self):
        payload = run_selector("--paths", "ops/scripts/dev/search_pitfalls.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.validation_selector", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_schema_governance_change_selects_schema_static_target(self):
        payload = run_selector("--paths", "ops/scripts/dev/check_schema_governance.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.schema_governance", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_api_surface_governance_change_selects_api_static_target(self):
        payload = run_selector("--paths", "ops/scripts/dev/check_api_surface_governance.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.api_surface_governance", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_docs_governance_change_selects_docs_static_target(self):
        payload = run_selector("--paths", "ops/scripts/dev/check_docs_governance.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.docs_governance", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_boundary_governance_skill_change_selects_boundary_static_target(self):
        payload = run_selector("--paths", "skills/boundary-governance/SKILL.md")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.repo_local_skills", ids)
        self.assertIn("static.boundary_governance", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_api_schema_inventory_change_selects_boundary_static_target(self):
        payload = run_selector("--paths", "ops/scripts/dev/inventory_api_schemas.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.boundary_governance", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_schema_defs_change_selects_schema_targets_without_full_fallback(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/api/schema_defs/appearance.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.api_surface_governance", ids)
        self.assertIn("static.boundary_governance", ids)
        self.assertIn("backend.user_profile.appearance_styles", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_notification_schema_defs_change_selects_notification_behavior_target(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/api/schema_defs/notifications.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.api_surface_governance", ids)
        self.assertIn("static.boundary_governance", ids)
        self.assertIn("behavior.notifications.sync_api_edge", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_files_schema_defs_change_selects_file_attachment_target(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/api/schema_defs/files.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.api_surface_governance", ids)
        self.assertIn("static.boundary_governance", ids)
        self.assertIn("backend.files.attachment_api", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_manual_script_api_coverage_change_selects_manual_api_target(self):
        payload = run_selector("--paths", "tests/backend/manual/test_manual_script_api_coverage.py")

        ids = recommendation_ids(payload)
        self.assertIn("backend.manual_script_api_coverage", ids)
        self.assertEqual(payload["unmatched_paths"], [])

    def test_structure_governance_doc_change_selects_structure_static_target(self):
        payload = run_selector("--paths", "docs/architecture/REPOSITORY_STRUCTURE.md")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.docs_governance", ids)
        self.assertIn("static.structure_governance", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_init_db_sql_maps_to_static_encoding_target(self):
        payload = run_selector("--paths", "ops/scripts/init_db.sql")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.operator_scripts_governance", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_operator_script_change_selects_static_governance_target(self):
        payload = run_selector("--paths", "ops/scripts/deploy_frontend.sh")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.operator_scripts_governance", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

        target = recommendation(payload, "static.operator_scripts_governance")
        self.assertEqual(target["risk"], "static")
        self.assertIn("operator-scripts", target["coverage_tags"])

    def test_ci_workflow_change_selects_ci_baseline_static_target(self):
        payload = run_selector("--paths", ".github/workflows/lightweight-validation.yml")

        ids = recommendation_ids(payload)
        self.assertIn("static.encoding_text_tools", ids)
        self.assertIn("static.ci_baseline_governance", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

        target = recommendation(payload, "static.ci_baseline_governance")
        self.assertEqual(target["risk"], "static")
        self.assertIn("ci-baselines", target["coverage_tags"])
        self.assertEqual(target["policy_requirement"], "required")

    def test_security_sensitive_path_recommends_security_and_full_postgres_context(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/core/auth.py")

        ids = recommendation_ids(payload)
        self.assertIn("security.api_regression", ids)
        self.assertIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "not_sufficient")
        self.assertIn("security.api_regression", required_target_ids(payload, "required_review_targets"))
        self.assertIn("full.pytest.postgres", required_target_ids(payload, "required_review_targets"))
        security = recommendation(payload, "security.api_regression")
        self.assertEqual(security["risk"], "broad")
        self.assertIn("security", security["coverage_tags"])

    def test_score_dashboard_routes_select_precise_course_scope_target(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/api/routers/scores.py")

        ids = recommendation_ids(payload)
        self.assertIn("backend.scores.dashboard_course_scope", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["unmatched_paths"], [])

        target = recommendation(payload, "backend.scores.dashboard_course_scope")
        self.assertEqual(target["risk"], "targeted")
        self.assertIn("course-access", target["coverage_tags"])

    def test_core_api_surface_selects_score_dashboard_target(self):
        payload = run_selector("--paths", "tests/backend/integration/test_core_api_surface.py")

        ids = recommendation_ids(payload)
        self.assertIn("backend.scores.dashboard_course_scope", ids)
        self.assertEqual(payload["unmatched_paths"], [])

    def test_dashboard_schema_defs_change_selects_score_dashboard_target(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/api/schema_defs/dashboard.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.api_surface_governance", ids)
        self.assertIn("static.boundary_governance", ids)
        self.assertIn("backend.scores.dashboard_course_scope", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_roster_schema_defs_change_selects_roster_target(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/api/schema_defs/roster.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.api_surface_governance", ids)
        self.assertIn("static.boundary_governance", ids)
        self.assertIn("backend.roster.student_user_api_sync", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_course_metadata_helper_selects_course_roster_target(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/domains/courses/metadata.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.boundary_governance", ids)
        self.assertIn("backend.courses.student_course_roster_behavior", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_course_class_links_helper_selects_course_roster_target(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/domains/courses/class_links.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.boundary_governance", ids)
        self.assertIn("backend.courses.student_course_roster_behavior", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_course_enrollment_helper_selects_course_roster_target(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/domains/courses/enrollment.py")

        ids = recommendation_ids(payload)
        self.assertIn("static.boundary_governance", ids)
        self.assertIn("backend.courses.student_course_roster_behavior", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_demo_seed_helper_change_selects_demo_course_seed_target(self):
        payload = run_selector(
            "--paths",
            "apps/backend/courseeval_backend/domains/seed/demo_users.py",
            "apps/backend/courseeval_backend/domains/seed/demo_courses.py",
        )

        ids = recommendation_ids(payload)
        self.assertIn("static.boundary_governance", ids)
        self.assertIn("backend.e2e_dev.demo_course_seed", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["non_full_validation"]["status"], "acceptable")
        self.assertEqual(payload["unmatched_paths"], [])

    def test_llm_grading_prompt_helper_selects_homework_llm_target(self):
        payload = run_selector(
            "--paths",
            "apps/backend/courseeval_backend/domains/llm/grading_prompt.py",
            "apps/backend/courseeval_backend/domains/llm/grading_result.py",
        )

        ids = recommendation_ids(payload)
        self.assertIn("static.boundary_governance", ids)
        self.assertIn("backend.homework.llm_grading", ids)
        self.assertIn("behavior.homework_lifecycle_llm", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["unmatched_paths"], [])

    def test_homework_serialization_helper_selects_homework_llm_target(self):
        payload = run_selector(
            "--paths",
            "apps/backend/courseeval_backend/domains/homework/serialization.py",
            "apps/backend/courseeval_backend/domains/homework/submission_rules.py",
        )

        ids = recommendation_ids(payload)
        self.assertIn("static.boundary_governance", ids)
        self.assertIn("backend.homework.llm_grading", ids)
        self.assertIn("behavior.homework_lifecycle_llm", ids)
        self.assertNotIn("full.pytest.postgres", ids)
        self.assertEqual(payload["unmatched_paths"], [])

    def test_discussion_router_prefers_pytest_hazard_tier_before_api_heavy_playwright(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/api/routers/discussions.py")

        ids = recommendation_ids(payload)
        self.assertIn("backend.e2e_dev.api_hazard_tier", ids)
        self.assertIn("school.e2e.discussion_cover_llm_tier3", ids)
        self.assertNotIn("school.e2e.docs_gap_tier15", ids)

    def test_runner_dry_run_writes_redacted_run_record(self):
        history_path = ".agent-run/test-selector-history-dry-run.jsonl"
        result = run_validation_target("static.validation_selector", "--dry-run", "--history", history_path)
        payload = json.loads(result.stdout)

        self.assertEqual(payload["target_id"], "static.validation_selector")
        self.assertEqual(payload["result"], "skipped")
        self.assertTrue(payload["private_paths_redacted"])
        self.assertTrue(payload["artifact_dir"].startswith("<repo>/.agent-run/logs/"))
        self.assertEqual(payload["history"], f"<repo>/{history_path}")
        run_json = REPO_ROOT / payload["artifact_dir"].replace("<repo>/", "") / "run.json"
        self.assertTrue(run_json.exists())
        history_jsonl = REPO_ROOT / history_path
        self.assertTrue(history_jsonl.exists())
        last_history = json.loads(history_jsonl.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(last_history["target_id"], "static.validation_selector")
        self.assertEqual(last_history["result"], "skipped")
        self.assertTrue(last_history["private_paths_redacted"])

    def test_runner_dry_run_does_not_preflight_missing_runtime_tools(self):
        result = run_validation_target(
            "frontend.school.build",
            "--dry-run",
            "--history",
            ".agent-run/test-selector-history-dry-run-no-preflight.jsonl",
        )
        payload = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["result"], "skipped")
        self.assertEqual(payload["failure_class"], None)
        self.assertEqual(payload["commands"][0]["result"], "skipped")

    def test_runner_preflight_turns_dry_run_into_environment_check(self):
        result = run_validation_target(
            "frontend.school.build",
            "--dry-run",
            "--preflight",
            "--history",
            ".agent-run/test-selector-history-dry-run-preflight.jsonl",
            check=False,
        )
        payload = json.loads(result.stdout)

        if result.returncode == 0:
            self.assertEqual(payload["result"], "skipped")
        else:
            self.assertEqual(result.returncode, 2)
            self.assertEqual(payload["result"], "blocked")
            self.assertEqual(payload["failure_class"], "environment")
            self.assertIn("capability_report", payload)

    def test_runner_uses_explicit_changed_paths_for_history_attribution(self):
        history_path = ".agent-run/test-selector-history-explicit-paths.jsonl"
        changed_paths = [
            {"status": "M", "path": "docs/testing/TEST_SUITE_MAP.md"},
            {"status": "??", "path": "notes/new-note.md"},
        ]
        result = run_validation_target(
            "static.validation_selector",
            "--dry-run",
            "--history",
            history_path,
            "--changed-paths-json",
            json.dumps(changed_paths),
        )
        payload = json.loads(result.stdout)

        history_jsonl = REPO_ROOT / history_path
        last_history = json.loads(history_jsonl.read_text(encoding="utf-8").splitlines()[-1])

        self.assertEqual(payload["result"], "skipped")
        self.assertEqual(last_history["changed_paths"], changed_paths)
        self.assertEqual(last_history["changed_paths_signature"], changed_paths_signature(changed_paths))
        self.assertIn("explicitly provided changed-path snapshot", payload["notes"])

    def test_runner_blocks_missing_pytest_as_environment_not_product_failure(self):
        write_json(
            REPO_ROOT / ".agent-run/test-selector-missing-module-registry.json",
            {
                "targets": [
                    {
                        "id": "static.missing_module_probe",
                        "category": "static-check",
                        "risk": "static",
                        "working_directory": ".",
                        "commands": [
                            {
                                "label": "missing module",
                                "argv": [
                                    "python",
                                    "-m",
                                    "module_that_should_not_exist_for_runner_probe",
                                ],
                            }
                        ],
                        "triggers": {"paths": [], "globs": []},
                        "ledger_id": None,
                    }
                ]
            },
        )
        result = run_validation_target(
            "static.missing_module_probe",
            "--registry",
            ".agent-run/test-selector-missing-module-registry.json",
            "--artifact-root",
            ".agent-run/test-selector-runner-logs",
            "--history",
            ".agent-run/test-selector-history-blocked.jsonl",
            check=False,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["result"], "blocked")
        self.assertEqual(payload["failure_class"], "environment")
        self.assertIn("module", payload["summary"].lower())

    def test_runner_detects_playwright_targets_for_preflight(self):
        self.assertTrue(target_needs_playwright_preflight({"category": "school-playwright"}))
        self.assertFalse(target_needs_playwright_preflight({"category": "backend-pytest"}))

    def test_validation_capability_report_includes_playwright_postgres_rar_and_text_safety(self):
        report = build_capabilities(REPO_ROOT, include_private=False)
        capability_names = {item["name"] for item in report["capabilities"]}

        self.assertIn("playwright-managed", capability_names)
        self.assertIn("postgres-test-env", capability_names)
        self.assertIn("rar-extraction", capability_names)
        self.assertIn("text-safety", capability_names)

    def test_validation_capability_evaluation_maps_postgres_target_to_postgres_capability(self):
        report = build_capabilities(REPO_ROOT, include_private=False)
        target = {
            "id": "full.pytest.postgres",
            "category": "full-suite",
            "required_capabilities": ["postgres-test-env"],
        }

        evaluated = evaluate_target_capabilities(report, target)

        self.assertEqual([item["name"] for item in evaluated], ["postgres-test-env"])

    def test_runner_classifies_spawn_eperm_as_environment_block(self):
        from run_validation_target import run_command

        artifact_dir = REPO_ROOT / ".agent-run/test-selector-spawn-eperm"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        script = artifact_dir / "spawn_eperm.py"
        stdout_path = artifact_dir / "stdout.log"
        stderr_path = artifact_dir / "stderr.log"
        script.write_text("print('Error: spawn EPERM')\nraise SystemExit(1)\n", encoding="utf-8")

        result, failure_class, return_code, _duration = run_command(
            [sys.executable, str(script)],
            REPO_ROOT,
            30,
            stdout_path,
            stderr_path,
        )

        self.assertEqual(result, RESULT_BLOCKED)
        self.assertEqual(failure_class, "environment")
        self.assertEqual(return_code, 1)

    def test_failure_classification_marks_port_collision_as_environment(self):
        failure_class = infer_failure_class(
            ["python", "-m", "uvicorn"],
            "ERROR: [Errno 10048] Only one usage of each socket address is normally permitted\n",
        )

        self.assertEqual(failure_class, "environment")

    def test_failure_classification_marks_missing_playwright_browser_as_environment(self):
        failure_class = infer_failure_class(
            ["npx.cmd", "playwright", "test"],
            "browser executable doesn't exist at C:\\cache\\chromium\nPlease run the following command to download new browsers: npx playwright install\n",
        )

        self.assertEqual(failure_class, "environment")

    def test_failure_classification_marks_missing_python_module_as_environment(self):
        failure_class = infer_failure_class(
            ["python", "-m", "pytest"],
            "Traceback...\nModuleNotFoundError: No module named 'uvicorn'\n",
        )

        self.assertEqual(failure_class, "environment")

    def test_failure_classification_leaves_assertion_failures_as_product(self):
        failure_class = infer_failure_class(
            ["python", "-m", "pytest"],
            "E   AssertionError: expected 200 but got 500\n1 failed, 3 passed\n",
        )

        self.assertEqual(failure_class, "product")

    def test_runner_adds_pytest_junitxml_argument_when_missing(self):
        output_path = REPO_ROOT / ".agent-run/test-selector-junit.xml"
        argv = [sys.executable, "-m", "pytest", "tests/backend/manual/test_validation_selector.py", "-q"]

        updated = with_pytest_junitxml(argv, output_path)

        self.assertEqual(updated[:-1], argv)
        self.assertEqual(updated[-1], f"--junitxml={output_path}")

    def test_wai_valid_infers_security_block_for_security_paths(self):
        self.assertEqual(
            infer_block_name_from_path("tests/security/test_security_regression.py"),
            "security",
        )

    def test_wai_valid_classifies_security_file_as_security_pytest_task(self):
        tasks = classify_tasks(
            ["tests/security/test_security_regression.py::test_sec01_unauthenticated_users_list_returns_401"],
            "auto",
            postgres_base_port=15460,
        )

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].kind, "pytest")
        self.assertEqual(tasks[0].block, "security")
        self.assertEqual(
            tasks[0].source_path,
            "tests/security/test_security_regression.py::test_sec01_unauthenticated_users_list_returns_401",
        )

    def test_wai_valid_sample_file_loads_text_samples(self):
        sample_file = REPO_ROOT / ".agent-run/test-custom-wai-valid-samples.txt"
        sample_file.parent.mkdir(parents=True, exist_ok=True)
        sample_file.write_text(
            "\n".join(
                [
                    "# comment",
                    "tests/backend/manual/test_validation_selector.py::ValidationSelectorTests::test_wai_valid_infers_security_block_for_security_paths",
                    "",
                    "validation-target:static.validation_selector",
                ]
            ),
            encoding="utf-8",
        )

        self.assertEqual(
            load_sample_file(str(sample_file)),
            [
                "tests/backend/manual/test_validation_selector.py::ValidationSelectorTests::test_wai_valid_infers_security_block_for_security_paths",
                "validation-target:static.validation_selector",
            ],
        )

    def test_wai_valid_custom_block_args_keep_default_concurrency_10(self):
        payload = build_custom_block_args(
            run_id="sample-regression",
            block="self-organized-light-regression",
            concurrency=CUSTOM_BLOCK_DEFAULT_CONCURRENCY,
            regression_mode="light",
            samples_files=["C:/tmp/samples.txt"],
            samples=[],
        )

        self.assertEqual(SUPERVISOR_DEFAULT_CONCURRENCY, 10)
        self.assertEqual(CUSTOM_BLOCK_DEFAULT_CONCURRENCY, 10)
        self.assertIn("--no-console-report", payload)
        self.assertIn("--concurrency", payload)
        self.assertEqual(payload[payload.index("--concurrency") + 1], "10")
        self.assertIn("--samples-file", payload)

    def test_wai_valid_classifies_playwright_line_sample_as_playwright_task(self):
        target = "tests/e2e/web-school/e2e-scenario-resilience.spec.js:647"
        tasks = classify_tasks([target], "self-organized-e2e", postgres_base_port=15460)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].kind, "playwright")
        self.assertEqual(tasks[0].block, "self-organized-e2e")
        self.assertEqual(tasks[0].source_path, target)
        self.assertEqual(playwright_spec_arg(target), "e2e-scenario-resilience.spec.js:647")

    def test_runner_normalizes_cross_platform_command_names(self):
        npm_argv, _npm_notes = resolve_command_argv(REPO_ROOT, ["npm", "run", "build"])
        npx_cmd_argv, _npx_notes = resolve_command_argv(REPO_ROOT, ["npx.cmd", "playwright", "test"])
        python_argv, _python_notes = resolve_command_argv(REPO_ROOT, ["python", "-m", "py_compile"])

        expected_npm = "npm.cmd" if sys.platform.startswith("win") else "npm"
        expected_npx = "npx.cmd" if sys.platform.startswith("win") else "npx"
        expected_python = REPO_ROOT / ".venv" / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")
        if not expected_python.exists():
            expected_python = Path(sys.executable)
        self.assertEqual(npm_argv[0], expected_npm)
        self.assertEqual(npx_cmd_argv[0], expected_npx)
        self.assertEqual(Path(python_argv[0]).resolve(), expected_python.resolve())

    def test_runner_expands_changed_text_files_placeholder(self):
        changed_paths = [
            {"status": "M", "path": "docs/README.md"},
            {"status": "M", "path": ".env.production"},
            {"status": "M", "path": "apps/web/school/src/assets/logo.png"},
            {"status": "D", "path": "docs/deleted.md"},
        ]

        expanded, notes = expand_command_placeholders(
            REPO_ROOT,
            ["python", "ops/scripts/dev/check_text_encoding.py", "--skip-if-empty", "<changed-text-files>"],
            changed_paths,
        )

        self.assertIn("docs/README.md", expanded)
        self.assertIn(".env.production", expanded)
        self.assertNotIn("apps/web/school/src/assets/logo.png", expanded)
        self.assertNotIn("docs/deleted.md", expanded)
        self.assertIn("expanded <changed-text-files> to 2 file(s)", notes)

    def test_encoding_scan_skip_if_empty_prevents_accidental_full_repo_scan(self):
        result = subprocess.run(
            [sys.executable, "ops/scripts/dev/check_text_encoding.py", "--skip-if-empty"],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertIn("scanned=0", result.stdout)
        self.assertIn("skipped=empty-input", result.stdout)

    def test_runner_parses_junit_xml_testcase_results(self):
        path = REPO_ROOT / ".agent-run/test-selector-sample-junit.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="sample" tests="3" failures="1" errors="0" skipped="1">
  <testcase classname="tests.sample" name="test_passes" file="tests/sample.py" time="0.1" />
  <testcase classname="tests.sample" name="test_fails" file="tests/sample.py" time="0.2">
    <failure message="boom" />
  </testcase>
  <testcase classname="tests.sample" name="test_skips" file="tests/sample.py" time="0.0">
    <skipped message="skip" />
  </testcase>
</testsuite>
""",
            encoding="utf-8",
        )

        parsed = parse_junit_xml(path, REPO_ROOT)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["tests"], 3)
        self.assertEqual(parsed["passed"], 1)
        self.assertEqual(parsed["failures"], 1)
        self.assertEqual(parsed["skipped"], 1)
        self.assertEqual([case["status"] for case in parsed["cases"]], ["passed", "failed", "skipped"])

    def test_runner_redacts_absolute_junit_case_paths(self):
        path = REPO_ROOT / ".agent-run/test-selector-absolute-junit.xml"
        case_path = REPO_ROOT / "tests" / "sample.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="sample" tests="1" failures="0" errors="0" skipped="0">
  <testcase classname="tests.sample" name="test_passes" file="{case_path}" time="0.1" />
</testsuite>
""",
            encoding="utf-8",
        )

        parsed = parse_junit_xml(path, REPO_ROOT)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["cases"][0]["file"], "<repo>/tests/sample.py")

    def test_profile_static_dry_run_executes_static_validation_target(self):
        result = run_validation_profile(
            "static",
            "--dry-run",
            "--history",
            ".agent-run/test-selector-profile-static-history.jsonl",
        )
        payload = json.loads(result.stdout)

        self.assertEqual(payload["profile"], "static")
        self.assertEqual(payload["result"], "passed")
        self.assertEqual([run["target_id"] for run in payload["target_runs"]], ["static.validation_selector"])
        self.assertEqual(payload["target_runs"][0]["result"], "skipped")

    def test_profile_selector_recommended_skips_review_targets_by_default(self):
        result = run_validation_profile(
            "selector-recommended",
            "--paths",
            "apps/web/school/src/views/HomeworkSubmissions.vue",
            "--dry-run",
            "--history",
            ".agent-run/test-selector-profile-recommended-history.jsonl",
        )
        payload = json.loads(result.stdout)
        runs_by_id = {run["target_id"]: run for run in payload["target_runs"]}

        self.assertEqual(payload["profile"], "selector-recommended")
        self.assertEqual(payload["result"], "passed_with_deferred_review")
        self.assertIn("frontend.school.build", runs_by_id)
        self.assertEqual(runs_by_id["frontend.school.build"]["action"], "executed")
        self.assertIn("school.e2e.homework_comment_cover_tier4", runs_by_id)
        self.assertEqual(runs_by_id["school.e2e.homework_comment_cover_tier4"]["action"], "skipped")
        self.assertIn("requires operator review", runs_by_id["school.e2e.homework_comment_cover_tier4"]["reason"])
        deferred_ids = [item["target_id"] for item in payload["deferred_targets"]]
        self.assertIn("school.e2e.homework_comment_cover_tier4", deferred_ids)
        self.assertIn("school.e2e.homework_appeal_stale_tabs", deferred_ids)
        self.assertEqual(
            payload["selection"]["required_validation"]["required_targets"][0]["id"],
            "frontend.school.build",
        )

    def test_profile_forwards_selector_changed_paths_to_target_history(self):
        history_path = ".agent-run/test-selector-profile-forward-history.jsonl"
        changed_path = "apps/web/school/src/views/HomeworkSubmissions.vue"
        result = run_validation_profile(
            "selector-recommended",
            "--paths",
            changed_path,
            "--dry-run",
            "--history",
            history_path,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["result"], "passed_with_deferred_review")

        history_jsonl = REPO_ROOT / history_path
        entries = [json.loads(line) for line in history_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
        build_entry = next(entry for entry in entries if entry["target_id"] == "frontend.school.build")

        self.assertEqual(build_entry["changed_paths"], [{"status": "M", "path": changed_path}])
        self.assertEqual(
            build_entry["changed_paths_signature"],
            changed_paths_signature([{"status": "M", "path": changed_path}]),
        )

    def test_selector_uses_matching_structured_history_as_fresh_evidence(self):
        changed_path = "docs/testing/TEST_SUITE_MAP.md"
        history_path = ".agent-run/test-selector-structured-history.jsonl"
        changed_paths = [{"status": "M", "path": changed_path}]
        record = {
            "schema_version": 1,
            "target_id": "static.validation_selector",
            "result": "passed",
            "failure_class": None,
            "branch": "test",
            "commit": "abc1234",
            "ended_at": "2026-05-08T00:00:00Z",
            "artifact_dir": "<repo>/.agent-run/logs/test",
            "changed_paths": changed_paths,
            "changed_paths_signature": changed_paths_signature(changed_paths),
            "private_paths_redacted": True,
        }
        path = REPO_ROOT / history_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

        payload = run_selector("--paths", changed_path, "--history", history_path)

        target = recommendation(payload, "static.validation_selector")
        self.assertEqual(target["history_status"], "fresh")
        self.assertIn("latest structured run passed", target["history_reason"])
        self.assertEqual(target["structured_history"]["commit"], "abc1234")

    def test_registry_lint_passes_for_repository_registry(self):
        issues = lint_registry(
            REPO_ROOT,
            "tests/TEST_SELECTION_TARGETS.json",
            "docs/testing/test-execution-targets.csv",
        )

        self.assertEqual(issues, [])

    def test_testing_governance_generated_docs_are_in_sync(self):
        self.assertEqual(check_testing_governance_docs(REPO_ROOT), [])

    def test_pitfall_index_line_sync_check_passes_for_repository_docs(self):
        self.assertEqual(sync_pitfall_index_main(["--repo-root", str(REPO_ROOT), "--check"]), 0)

    def test_validation_debt_registry_check_passes_for_repository_registry(self):
        self.assertEqual(
            check_validation_debt_registry(
                REPO_ROOT,
                "docs/testing/validation-debt-registry.csv",
                "tests/TEST_SELECTION_TARGETS.json",
            ),
            [],
        )

    def test_validation_lane_budget_config_accepts_repository_lane(self):
        budgets = load_budgets(REPO_ROOT / "docs/testing/validation-lane-budgets.json")
        issues = evaluate_budget(
            "backend-quick-pytest",
            budgets["lanes"]["backend-quick-pytest"],
            {
                "tests": 10,
                "failures": 0,
                "errors": 0,
                "skipped": 2,
                "passed": 8,
                "deselected": 0,
                "xfailed": 0,
                "xpassed": 0,
            },
        )
        self.assertEqual(issues, [])

    def test_high_risk_path_metadata_check_passes_for_repository_metadata(self):
        self.assertEqual(
            check_high_risk_path_metadata(
                REPO_ROOT,
                "docs/governance/high-risk-path-metadata.json",
                "tests/TEST_SELECTION_TARGETS.json",
            ),
            [],
        )

    def test_selector_reports_matched_high_risk_path_metadata(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/db/models.py")

        matched = payload["matched_high_risk_paths"]
        self.assertTrue(any(item["path"] == "apps/backend/courseeval_backend/db/" for item in matched), matched)

    def test_operator_script_governance_check_passes_for_repository_scripts(self):
        self.assertEqual(check_operator_scripts(REPO_ROOT), [])

    def test_ci_baseline_governance_check_passes_for_repository_ci_contract(self):
        self.assertEqual(check_ci_baselines(REPO_ROOT), [])

    def test_ci_baseline_governance_check_detects_python_version_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(REPO_ROOT / ".github", root / ".github")
            shutil.copytree(REPO_ROOT / "ops", root / "ops")
            branch_pipeline = root / "ops/ci/branch-pipeline.yml"
            text = branch_pipeline.read_text(encoding="utf-8")
            branch_pipeline.write_text(text.replace("pythonVersion: '3.11'", "pythonVersion: '3.9'"), encoding="utf-8")

            issues = check_ci_baselines(root)

        self.assertIn(
            "ops/ci/branch-pipeline.yml: must use pythonVersion '3.11'",
            issues,
        )

    def test_validation_policy_gate_passes_when_required_classes_are_available(self):
        payload = run_selector("--paths", ".github/workflows/lightweight-validation.yml")

        issues = evaluate_policy_gate(
            payload,
            {"static-check", "backend-pytest", "behavior-pytest", "security-pytest", "frontend-build", "frontend-node-test"},
        )

        self.assertEqual(issues, [])

    def test_validation_policy_gate_fails_when_required_review_class_is_unavailable(self):
        payload = run_selector("--paths", "apps/backend/courseeval_backend/core/auth.py")

        issues = evaluate_policy_gate(
            payload,
            {"static-check", "backend-pytest", "behavior-pytest", "security-pytest", "frontend-build", "frontend-node-test"},
        )

        self.assertTrue(any("full.pytest.postgres" in issue and "full-suite" in issue for issue in issues), issues)

    def test_operator_script_governance_check_detects_frontend_backend_restart_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(REPO_ROOT / "ops", root / "ops")
            deploy_frontend = root / "ops/scripts/deploy_frontend.sh"
            text = deploy_frontend.read_text(encoding="utf-8")
            deploy_frontend.write_text(text + "\nsystemctl restart courseeval-backend.service\n", encoding="utf-8")

            issues = check_operator_scripts(root)

        self.assertIn(
            "ops/scripts/deploy_frontend.sh: frontend-only deploy must not restart the backend service",
            issues,
        )

    def test_repo_local_skill_check_passes_for_repository_skills(self):
        self.assertEqual(check_repo_skills(REPO_ROOT), [])

    def test_repo_local_skill_check_detects_todo_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "skills/sample-skill"
            skill_dir.mkdir(parents=True)
            write_text(
                skill_dir / "SKILL.md",
                "---\nname: sample-skill\ndescription: Use this for a realistic sample skill validation case.\n---\n\nTODO\n",
            )
            write_text(
                skill_dir / "agents/openai.yaml",
                'interface:\n  display_name: "Sample Skill"\n  short_description: "Sample skill metadata."\n  default_prompt: "Use this sample skill."\n',
            )

            issues = check_repo_skills(root)

        self.assertIn("skills/sample-skill/SKILL.md: contains TODO placeholder", issues)

    def test_repo_local_skill_check_detects_missing_skill_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "skills/sample-skill"
            skill_dir.mkdir(parents=True)
            write_text(
                skill_dir / "SKILL.md",
                (
                    "---\n"
                    "name: sample-skill\n"
                    "description: Use this for a realistic sample skill validation case.\n"
                    "---\n\n"
                    "Use `skills/missing-skill/SKILL.md` when needed.\n"
                ),
            )
            write_text(
                skill_dir / "agents/openai.yaml",
                'interface:\n  display_name: "Sample Skill"\n  short_description: "Sample skill metadata."\n  default_prompt: "Use this sample skill."\n',
            )

            issues = check_repo_skills(root)

        self.assertIn(
            "skills/sample-skill/SKILL.md: missing referenced skill `skills/missing-skill/SKILL.md`",
            issues,
        )

    def test_search_pitfalls_finds_postgres_restricted_token_guidance(self):
        blocks = build_corpus(REPO_ROOT, context_lines=1)
        hits = search_blocks("initdb restricted token error code 87 postgres", blocks, limit=8)

        self.assertTrue(hits)
        rendered = "\n".join(f"{hit.path}:{hit.line}:{hit.title}:{hit.snippet}" for hit in hits)
        self.assertIn("postgres-release-validation", rendered)
        self.assertIn("restricted", rendered.lower())

    def test_search_pitfalls_finds_playwright_grep_pitfall(self):
        blocks = build_corpus(REPO_ROOT, context_lines=1)
        hits = search_blocks("playwright grep describe text no tests found", blocks, limit=8)

        self.assertTrue(hits)
        rendered = "\n".join(f"{hit.path}:{hit.line}:{hit.title}:{hit.snippet}" for hit in hits)
        self.assertIn("Playwright grep", rendered)

    def test_schema_governance_check_passes_for_repository_schema_contract(self):
        self.assertEqual(check_schema_governance(REPO_ROOT), [])

    def test_api_surface_governance_check_passes_for_repository_api_contract(self):
        self.assertEqual(check_api_surface_governance(REPO_ROOT), [])

    def test_pytest_sqlite_guard_detects_pytest_command_but_not_current_process(self):
        self.assertTrue(
            is_pytest_process(
                {"pid": "999", "name": "python.exe", "command": "python -m pytest tests -q"},
                current_pid=123,
            )
        )
        self.assertFalse(
            is_pytest_process(
                {"pid": "123", "name": "python.exe", "command": "python ops/scripts/dev/pytest_sqlite_guard.py"},
                current_pid=123,
            )
        )

    def test_selector_parses_csv_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(
                root / "docs/testing/test-execution-targets.csv",
                "\n".join(
                    [
                        "test_id,last_branch,last_commit,last_result,last_run_date,pass_count,run_count",
                        "static.sample,test-branch,abc1234,passed,2026-05-10,2,3",
                        "",
                    ]
                ),
            )

            parsed = parse_ledger(root, "docs/testing/test-execution-targets.csv")

        self.assertEqual(parsed["static.sample"]["last_result"], "passed")
        self.assertEqual(parsed["static.sample"]["pass_count"], "2")

    def test_registry_lint_accepts_csv_ledger_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "docs/testing/test-execution-targets.csv", "test_id\nstatic.sample\n")
            write_json(
                root / "tests/TEST_SELECTION_TARGETS.json",
                {
                    "targets": [
                        {
                            "id": "static.sample",
                            "category": "static-check",
                            "risk": "static",
                            "working_directory": ".",
                            "commands": [{"label": "ok", "argv": ["python", "--version"]}],
                            "triggers": {"paths": [], "globs": []},
                            "ledger_id": "static.sample",
                        }
                    ],
                    "fallback_rules": [],
                },
            )

            issues = lint_registry(root, "tests/TEST_SELECTION_TARGETS.json", "docs/testing/test-execution-targets.csv")

        self.assertEqual(issues, [])

    def test_registry_lint_rejects_null_ledger_id_when_target_has_committed_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "docs/testing/test-execution-targets.csv", "test_id\nschool.e2e.sample\n")
            write_json(
                root / "tests/TEST_SELECTION_TARGETS.json",
                {
                    "targets": [
                        {
                            "id": "school.e2e.sample",
                            "category": "school-playwright",
                            "risk": "targeted",
                            "working_directory": ".",
                            "commands": [{"label": "ok", "argv": ["npx.cmd", "playwright", "test", "sample.spec.js"]}],
                            "triggers": {"paths": [], "globs": []},
                            "ledger_id": None,
                        }
                    ],
                    "fallback_rules": [],
                },
            )

            issues = lint_registry(root, "tests/TEST_SELECTION_TARGETS.json", "docs/testing/test-execution-targets.csv")

        self.assertIn("school.e2e.sample: target has a committed ledger row but ledger_id is null", issues)

    def test_registry_lint_rejects_mismatched_ledger_id_when_target_has_own_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "docs/testing/test-execution-targets.csv", "test_id\nschool.e2e.sample\nother.target\n")
            write_json(
                root / "tests/TEST_SELECTION_TARGETS.json",
                {
                    "targets": [
                        {
                            "id": "school.e2e.sample",
                            "category": "school-playwright",
                            "risk": "targeted",
                            "working_directory": ".",
                            "commands": [{"label": "ok", "argv": ["npx.cmd", "playwright", "test", "sample.spec.js"]}],
                            "triggers": {"paths": [], "globs": []},
                            "ledger_id": "other.target",
                        }
                    ],
                    "fallback_rules": [],
                },
            )

            issues = lint_registry(root, "tests/TEST_SELECTION_TARGETS.json", "docs/testing/test-execution-targets.csv")

        self.assertIn(
            "school.e2e.sample: target has its own committed ledger row but ledger_id points elsewhere: other.target",
            issues,
        )
        self.assertIn(
            "school.e2e.sample: ledger_id must match target id unless an explicit alias mechanism is added: other.target",
            issues,
        )

    def test_registry_lint_rejects_mismatched_ledger_id_even_without_own_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "docs/testing/test-execution-targets.csv", "test_id\nother.target\n")
            write_json(
                root / "tests/TEST_SELECTION_TARGETS.json",
                {
                    "targets": [
                        {
                            "id": "behavior.sample",
                            "category": "behavior-pytest",
                            "risk": "targeted",
                            "working_directory": ".",
                            "commands": [{"label": "ok", "argv": ["python", "--version"]}],
                            "triggers": {"paths": [], "globs": []},
                            "ledger_id": "other.target",
                        }
                    ],
                    "fallback_rules": [],
                },
            )

            issues = lint_registry(root, "tests/TEST_SELECTION_TARGETS.json", "docs/testing/test-execution-targets.csv")

        self.assertIn(
            "behavior.sample: ledger_id must match target id unless an explicit alias mechanism is added: other.target",
            issues,
        )

    def test_registry_lint_accepts_external_runner_playwright_spec_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "apps/web/school/scripts/playwright-external-runner.cjs", "// runner\n")
            write_text(root / "tests/e2e/web-school/sample.spec.js", "test('ok', () => {})\n")
            write_text(root / "docs/testing/test-execution-targets.csv", "test_id\n")
            write_json(
                root / "tests/TEST_SELECTION_TARGETS.json",
                {
                    "targets": [
                        {
                            "id": "school.e2e.sample",
                            "category": "school-playwright",
                            "risk": "targeted",
                            "working_directory": "apps/web/school",
                            "commands": [
                                {
                                    "label": "playwright",
                                    "argv": ["node", "scripts/playwright-external-runner.cjs", "sample.spec.js", "--project=chromium"],
                                }
                            ],
                            "triggers": {"paths": [], "globs": []},
                            "ledger_id": None,
                        }
                    ],
                    "fallback_rules": [],
                },
            )

            issues = lint_registry(root, "tests/TEST_SELECTION_TARGETS.json", "docs/testing/test-execution-targets.csv")

        self.assertEqual(issues, [])

    def test_registry_lint_rejects_missing_external_runner_playwright_spec_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "apps/web/school/scripts/playwright-external-runner.cjs", "// runner\n")
            write_text(root / "docs/testing/test-execution-targets.csv", "test_id\n")
            write_json(
                root / "tests/TEST_SELECTION_TARGETS.json",
                {
                    "targets": [
                        {
                            "id": "school.e2e.sample",
                            "category": "school-playwright",
                            "risk": "targeted",
                            "working_directory": "apps/web/school",
                            "commands": [
                                {
                                    "label": "playwright",
                                    "argv": ["node", "scripts/playwright-external-runner.cjs", "missing.spec.js", "--project=chromium"],
                                }
                            ],
                            "triggers": {"paths": [], "globs": []},
                            "ledger_id": None,
                        }
                    ],
                    "fallback_rules": [],
                },
            )

            issues = lint_registry(root, "tests/TEST_SELECTION_TARGETS.json", "docs/testing/test-execution-targets.csv")

        self.assertIn(
            "school.e2e.sample: referenced Playwright file does not exist: tests/e2e/web-school/missing.spec.js",
            issues,
        )

    def test_repository_school_playwright_targets_use_supported_runners(self):
        registry = json.loads((REPO_ROOT / "tests/TEST_SELECTION_TARGETS.json").read_text(encoding="utf-8"))
        targets = [target for target in registry["targets"] if target.get("category") == "school-playwright"]

        self.assertGreater(len(targets), 0)
        for target in targets:
            argv = target["commands"][0]["argv"]
            if argv[:2] == ["node", "scripts/playwright-external-runner.cjs"]:
                continue
            self.assertEqual(
                argv[:2],
                [".venv/Scripts/python.exe", "ops/scripts/dev/wai_valid_supervisor.py"],
                target["id"],
            )
            self.assertIn("--sample", argv, target["id"])
            self.assertIn("--concurrency", argv, target["id"])

    def test_repository_full_playwright_target_uses_external_runner(self):
        registry = json.loads((REPO_ROOT / "tests/TEST_SELECTION_TARGETS.json").read_text(encoding="utf-8"))
        targets = {target["id"]: target for target in registry["targets"]}

        argv = targets["school.e2e.full"]["commands"][0]["argv"]
        self.assertEqual(argv, ["node", "scripts/playwright-external-runner.cjs"])

    def test_pytest_sqlite_guard_directory_scan_collects_pid_named_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_dir = root / ".pytest_tmp"
            sqlite_dir.mkdir(parents=True)
            (sqlite_dir / "test_100.sqlite").write_text("a", encoding="utf-8")
            (sqlite_dir / "test_200.sqlite").write_text("b", encoding="utf-8")

            report = build_report(root, sqlite_dir)

        self.assertEqual(report["sqlite"]["mode"], "directory-scan")
        self.assertEqual(report["sqlite"]["candidate_count"], 2)
        self.assertEqual(
            {Path(item["path"]).name for item in report["sqlite"]["candidates"]},
            {"test_100.sqlite", "test_200.sqlite"},
        )

    def test_pytest_sqlite_guard_compat_scan_finds_pid_named_candidate_without_legacy_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_dir = root / ".pytest_tmp"
            sqlite_dir.mkdir(parents=True)
            compat_path = sqlite_dir / "test.sqlite"
            (sqlite_dir / "test_321.sqlite").write_text("x", encoding="utf-8")

            report = build_report(root, compat_path)

        self.assertEqual(report["sqlite"]["mode"], "compat-scan")
        self.assertEqual(report["sqlite"]["candidate_count"], 1)
        self.assertEqual(Path(report["sqlite"]["candidates"][0]["path"]).name, "test_321.sqlite")

    def test_registry_lint_rejects_unknown_fallback_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "docs/testing/TEST_EXECUTION_LEDGER.md", "")
            write_json(
                root / "tests/TEST_SELECTION_TARGETS.json",
                {
                    "targets": [
                        {
                            "id": "static.sample",
                            "category": "static-check",
                            "risk": "static",
                            "working_directory": ".",
                            "commands": [{"label": "ok", "argv": ["python", "--version"]}],
                            "triggers": {"paths": [], "globs": []},
                            "ledger_id": None,
                        }
                    ],
                    "fallback_rules": [
                        {
                            "id": "broken",
                            "if_any_path_matches": ["README.md"],
                            "recommend": ["missing.target"],
                        }
                    ],
                },
            )

            issues = lint_registry(root, "tests/TEST_SELECTION_TARGETS.json", "docs/testing/TEST_EXECUTION_LEDGER.md")

        self.assertIn("broken: recommend references unknown target id: missing.target", issues)

    def test_registry_lint_rejects_missing_literal_trigger_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "docs/testing/TEST_EXECUTION_LEDGER.md", "")
            write_json(
                root / "tests/TEST_SELECTION_TARGETS.json",
                {
                    "targets": [
                        {
                            "id": "backend.sample",
                            "category": "backend-pytest",
                            "risk": "targeted",
                            "working_directory": ".",
                            "commands": [{"label": "pytest", "argv": ["python", "-m", "pytest", "tests/test_sample.py"]}],
                            "triggers": {"paths": ["apps/backend/missing.py"], "globs": []},
                            "ledger_id": None,
                        }
                    ],
                    "fallback_rules": [],
                },
            )

            issues = lint_registry(root, "tests/TEST_SELECTION_TARGETS.json", "docs/testing/TEST_EXECUTION_LEDGER.md")

        self.assertIn("backend.sample: trigger path does not exist: apps/backend/missing.py", issues)

    def test_registry_lint_rejects_missing_playwright_spec_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "apps/web/school/package.json", "{}\n")
            write_text(root / "docs/testing/TEST_EXECUTION_LEDGER.md", "")
            write_json(
                root / "tests/TEST_SELECTION_TARGETS.json",
                {
                    "targets": [
                        {
                            "id": "school.e2e.sample",
                            "category": "school-playwright",
                            "risk": "targeted",
                            "working_directory": "apps/web/school",
                            "commands": [
                                {
                                    "label": "playwright",
                                    "argv": ["npx.cmd", "playwright", "test", "missing.spec.js", "--project=chromium"],
                                }
                            ],
                            "triggers": {"paths": [], "globs": []},
                            "ledger_id": None,
                        }
                    ],
                    "fallback_rules": [],
                },
            )

            issues = lint_registry(root, "tests/TEST_SELECTION_TARGETS.json", "docs/testing/TEST_EXECUTION_LEDGER.md")

        self.assertIn(
            "school.e2e.sample: referenced Playwright file does not exist: tests/e2e/web-school/missing.spec.js",
            issues,
        )

    def test_registry_lint_rejects_missing_ledger_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "docs/testing/TEST_EXECUTION_LEDGER.md", "### Test ID: `other.target`\n")
            write_json(
                root / "tests/TEST_SELECTION_TARGETS.json",
                {
                    "targets": [
                        {
                            "id": "static.sample",
                            "category": "static-check",
                            "risk": "static",
                            "working_directory": ".",
                            "commands": [{"label": "ok", "argv": ["python", "--version"]}],
                            "triggers": {"paths": [], "globs": []},
                            "ledger_id": "static.sample",
                        }
                    ],
                    "fallback_rules": [],
                },
            )

            issues = lint_registry(root, "tests/TEST_SELECTION_TARGETS.json", "docs/testing/TEST_EXECUTION_LEDGER.md")

        self.assertIn("static.sample: ledger_id not found in ledger: static.sample", issues)

    def test_selector_marks_structured_history_stale_for_different_diff_signature(self):
        changed_path = "docs/testing/TEST_SUITE_MAP.md"
        history_path = ".agent-run/test-selector-structured-history-stale.jsonl"
        recorded_paths = [{"status": "M", "path": "ops/scripts/dev/select_validation_targets.py"}]
        record = {
            "schema_version": 1,
            "target_id": "static.validation_selector",
            "result": "passed",
            "failure_class": None,
            "branch": "test",
            "commit": "abc1234",
            "ended_at": "2026-05-08T00:00:00Z",
            "artifact_dir": "<repo>/.agent-run/logs/test",
            "changed_paths": recorded_paths,
            "changed_paths_signature": changed_paths_signature(recorded_paths),
            "private_paths_redacted": True,
        }
        path = REPO_ROOT / history_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

        payload = run_selector("--paths", changed_path, "--history", history_path)

        target = recommendation(payload, "static.validation_selector")
        self.assertEqual(target["history_status"], "stale")
        self.assertIn("different changed-path snapshot", target["history_reason"])

                                        
if __name__ == "__main__":
    unittest.main()
