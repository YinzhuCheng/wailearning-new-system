# Agent Startup Routing

## Purpose

This document holds the detailed startup routing that used to make the root
`AGENTS.md` file too long for its entrypoint role.

Use it when:

- starting a non-trivial repository task after reading `AGENTS.md`;
- deciding which docs or skills to open next;
- locating high-risk boundaries before tracing or editing;
- choosing grep anchors, validation entrypoints, or CI references.

`AGENTS.md` remains the startup contract. This file is the detailed routing
surface it points to.

## Startup Workflow

1. Read `AGENTS.md`.
2. Read [`docs/README.md`](../README.md).
3. Read
   [`docs/governance/repository-governance.md`](../governance/repository-governance.md).
4. Open the task-specific docs listed in `docs/README.md` under
   **Mandatory reading by task**.
5. If this machine already has local continuation artifacts, read the
   task-relevant files under `.agent-run/`, especially `.agent-run/plan/` when
   a local execution plan exists for the task.
6. If the task is non-trivial, route into the appropriate skill from
   [`skills/README.md`](../../skills/README.md) before planning edits.

Execution entrypoints such as Windows safe-text launching, failure triage,
validation, and CI routing now live in
[`agent-execution-entrypoints.md`](agent-execution-entrypoints.md).

## Task Routing

Use the nearest authoritative doc or skill for the task type:

| Task type | Read first | Skill | Validate first |
|----------|------------|-------|----------------|
| Docs, links, entrypoint wording, or governance-doc edits | [`../governance/repository-governance.md`](../governance/repository-governance.md) | [`../../skills/docs-governance/SKILL.md`](../../skills/docs-governance/SKILL.md) | `static.docs_governance` |
| Module boundaries, permission/data-flow boundaries, or low-risk extractions | [`../reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md`](../reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md) | [`../../skills/boundary-governance/SKILL.md`](../../skills/boundary-governance/SKILL.md) | `static.boundary_governance` |
| Repository/path/layout changes | [`../architecture/REPOSITORY_STRUCTURE.md`](../architecture/REPOSITORY_STRUCTURE.md) | [`../../skills/structure-governance/SKILL.md`](../../skills/structure-governance/SKILL.md) | `static.structure_governance` |
| Repo-wide governance, naming/path drift, entrypoint cleanup | [`../governance/repository-governance.md`](../governance/repository-governance.md) | [`../../skills/repository-normalization/SKILL.md`](../../skills/repository-normalization/SKILL.md) | `check_repository_normalization.py` |
| Backend/API contract changes | [`../architecture/SYSTEM_OVERVIEW.md`](../architecture/SYSTEM_OVERVIEW.md) | [`../../skills/api-surface-audit/SKILL.md`](../../skills/api-surface-audit/SKILL.md) | `static.api_surface_governance` |
| Permissions/course access/sensitive role behavior | [`../reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md`](../reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md) | [`../../skills/permission-audit/SKILL.md`](../../skills/permission-audit/SKILL.md) | `security.api_regression` |
| Schema/bootstrap/student identity | [`../operations/ADMIN_BOOTSTRAP.md`](../operations/ADMIN_BOOTSTRAP.md) | [`../../skills/data-migration-audit/SKILL.md`](../../skills/data-migration-audit/SKILL.md) / [`../../skills/roster-identity-repair-playbook/SKILL.md`](../../skills/roster-identity-repair-playbook/SKILL.md) | `static.schema_governance` |
| School Playwright or browser-harness work | [`../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`](../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md) | [`../../skills/school-playwright-e2e/SKILL.md`](../../skills/school-playwright-e2e/SKILL.md) | `frontend.school.build` plus the nearest `school.e2e.*` target |
| Local pytest/Playwright/SQLite/process failures | [`../testing/TEST_EXECUTION_PITFALLS.md`](../testing/TEST_EXECUTION_PITFALLS.md) or the matching topic route | [`../../skills/local-test-triage/SKILL.md`](../../skills/local-test-triage/SKILL.md) | `static.local_test_guardrails` when the issue is harness-shaped |
| Validation target choice and evidence | [`../testing/VALIDATION_WORKFLOW_AND_TOOLS.md`](../testing/VALIDATION_WORKFLOW_AND_TOOLS.md) | [`../../skills/validation-selection/SKILL.md`](../../skills/validation-selection/SKILL.md) / [`../../skills/validation-ledger-maintenance/SKILL.md`](../../skills/validation-ledger-maintenance/SKILL.md) | `static.validation_selector` |
| Parallel validation supervision, slot refill, live progress monitoring | [`../testing/VALIDATION_WORKFLOW_AND_TOOLS.md`](../testing/VALIDATION_WORKFLOW_AND_TOOLS.md) and [`../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`](../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md) | [`../../skills/parallel-validation-orchestration/SKILL.md`](../../skills/parallel-validation-orchestration/SKILL.md) | `static.validation_selector` plus the block-specific runtime target |
| Multi-round phased execution with plan re-read, closeout, and local commit discipline | [`../governance/repository-governance.md`](../governance/repository-governance.md) and [`agent-closeout.md`](agent-closeout.md) | [`../../skills/round-plan-discipline/SKILL.md`](../../skills/round-plan-discipline/SKILL.md) | the validation entrypoint for the current round's actual change surface |
| Deployment/ops/runtime config | [`../operations/DEPLOYMENT_AND_OPERATIONS.md`](../operations/DEPLOYMENT_AND_OPERATIONS.md) | [`../../skills/deployment-governance/SKILL.md`](../../skills/deployment-governance/SKILL.md) | `static.operator_scripts_governance` when operator scripts or templates move |
| Full skill catalog and layering | [`../../skills/README.md`](../../skills/README.md) | route from there | use the routed validation entrypoint |

## High-Risk Areas

Trace these with a focused plan before editing:

1. `apps/backend/courseeval_backend/llm_grading.py`
2. `apps/backend/courseeval_backend/domains/courses/access.py`
3. `apps/backend/courseeval_backend/bootstrap.py` and
   `apps/backend/courseeval_backend/main.py` lifespan
4. `apps/backend/courseeval_backend/api/routers/e2e_dev.py`
5. `apps/backend/courseeval_backend/api/routers/homework.py`

Use
[`../architecture/HIGH_RISK_MODULES.md`](../architecture/HIGH_RISK_MODULES.md)
for the expanded explanations and related docs/skills.

## Fast Grep Map

Use this short map as the first jump only:

| Intent | Start grep |
|--------|------------|
| Course access and visibility | `get_accessible_courses_query`, `ensure_course_access_http`, `prepare_student_course_context` |
| Homework serialization and effective score | `_serialize_homework`, `_serialize_submission`, `resolve_effective_submission_score`, `effective_score_note_zh` |
| Grading queue and worker | `HomeworkGradingTask`, `queue_grading_task`, `process_next_grading_task`, `_WorkerManager`, `start_grading_worker` |
| Quota policy | `precheck_quota`, `reserve_quota_tokens`, `LLMGlobalQuotaPolicy` |
| Demo seed and E2E reset | `seed_demo_course_bundle`, `INIT_DEFAULT_DATA`, `expose_e2e_dev_api`, `E2E_DEV_SEED_ENABLED` |
| Schema repair | `ensure_schema_updates`, `bootstrap.py` |

Use
[`../reference/CODE_MAP_AND_ENTRYPOINTS.md`](../reference/CODE_MAP_AND_ENTRYPOINTS.md)
for the full file-level map and extended grep surface.

Use [`agent-execution-entrypoints.md`](agent-execution-entrypoints.md) for:

- Windows safe-text entry
- failure triage entry
- validation entry
- CI entrypoints
