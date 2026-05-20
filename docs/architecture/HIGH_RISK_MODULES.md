# High-Risk Modules

## Purpose

This document expands the short high-risk list kept in `AGENTS.md`.

Use it when a task touches modules with broad authorization, bootstrap,
grading, or E2E-surface impact and you need a fuller trace plan than the root
agent contract should carry.

## High-Risk Areas

### `apps/backend/courseeval_backend/llm_grading.py`

Risk surface:

- quota accounting;
- retries and task failure classification;
- attachment extraction handoff;
- effective-score aggregation;
- in-process worker orchestration.

Route with:

- `docs/product/LLM_HOMEWORK_GUIDE.md`
- `docs/architecture/ASYNC_TASKS_AND_WORKERS.md`
- `skills/postgres-release-validation/SKILL.md` for release-quality DB
  confidence.

### `apps/backend/courseeval_backend/domains/courses/access.py`

Risk surface:

- course visibility for every role;
- enrollment-driven access checks;
- class-linked versus instructor-linked access behavior;
- permission-sensitive subject-scoped reads.

Route with:

- `docs/reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md`
- `skills/permission-audit/SKILL.md`
- `tests/security/`

### `apps/backend/courseeval_backend/bootstrap.py` and `main.py` lifespan

Risk surface:

- startup ordering;
- compatibility DDL and schema repair;
- roster normalization;
- demo seed entrypoints;
- worker startup timing.

Route with:

- `docs/operations/ADMIN_BOOTSTRAP.md`
- `docs/architecture/CORE_BUSINESS_FLOWS.md`
- `skills/data-migration-audit/SKILL.md`

### `apps/backend/courseeval_backend/api/routers/e2e_dev.py`

Risk surface:

- powerful reset and seed helpers;
- mock LLM and grading-control endpoints;
- dual-gate seed-token/admin-JWT exposure rules;
- production exposure boundary.

Route with:

- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`
- `skills/seed-surface-hardening/SKILL.md`
- `skills/school-playwright-e2e/SKILL.md`

### `apps/backend/courseeval_backend/api/routers/homework.py`

Risk surface:

- role-dependent serialization;
- submission and review permissions;
- redaction rules for student versus staff;
- grading-queue and appeal interactions.

Route with:

- `docs/architecture/CORE_BUSINESS_FLOWS.md`
- `docs/product/LLM_HOMEWORK_GUIDE.md`
- `skills/api-surface-audit/SKILL.md`

## Related Files

- `AGENTS.md`
- `docs/governance/high-risk-path-metadata.json`
- `docs/architecture/CORE_BUSINESS_FLOWS.md`
- `docs/reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md`
- `docs/operations/ADMIN_BOOTSTRAP.md`
- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`
