---
name: data-migration-audit
description: Use this when changing CourseEval SQLAlchemy models, bootstrap.ensure_schema_updates compatibility DDL, student identity migration helpers, seed data repair, or deployment/bootstrap docs that affect schema upgrades.
---

# Data Migration Audit

## Purpose

Keep CourseEval schema and data-repair work honest while the repository has no
Alembic migration tree. Current compatibility DDL lives in
`apps/backend/courseeval_backend/bootstrap.py::ensure_schema_updates()`.

This skill should route agents quickly to the current schema truth, bootstrap
truth, and validation truth instead of treating all schema-adjacent changes as
one flat migration checklist.

## When to Use

Use this before changing:

- `apps/backend/courseeval_backend/db/models.py`
- `apps/backend/courseeval_backend/bootstrap.py`
- student identity audit/repair helpers under `domains/roster/` or
  `ops/scripts/dev/*student_identity*.py`
- deployment/bootstrap docs that mention schema repair or first-run data
- tests touching PostgreSQL, `tests/db_reset.py`, or migration prechecks

## Inputs

- Current diff and intended changed files.
- The affected ORM tables, columns, constraints, and compatibility reads.
- Whether the change is greenfield-only, legacy-database repair, or data
  mutation.

## Workflow

1. Read:
   - `docs/reference/DATA_MODEL_ESSENTIALS.md`
   - `docs/operations/ADMIN_BOOTSTRAP.md`
   - `docs/governance/known-issues-and-risks.md`
   - `docs/architecture/BACKEND_PACKAGE_STRUCTURE.md` when a boundary split may
     affect schema/bootstrap ownership
2. Compare `db/models.py` with `bootstrap.ensure_schema_updates()`.
3. For new columns/tables used by existing deployments, add idempotent DDL to
   `ensure_schema_updates()` or document why `create_all` is sufficient.
4. For student identity changes, run audit before repair; do not restore
   username/student-number guessing as normal feature behavior.
5. Route to `roster-identity-repair-playbook` when the core task is really
   student identity / `users.student_id` / roster drift repair rather than
   general schema-governance work.
6. Use the focused validation docs to decide whether the evidence claim is an
   everyday targeted validation result or a full release-grade schema claim.
7. For destructive cleanup or fallback removal, document migration evidence,
   rollback boundary, and validation before deleting compatibility code.
8. Update docs and selector targets in the same change set.

## Document Routing Rules

- Use `DATA_MODEL_ESSENTIALS.md` as the canonical source for current model and
  table-shape truth.
- Use `ADMIN_BOOTSTRAP.md` as the canonical source for startup/bootstrap and
  demo-seed sequencing.
- Use `known-issues-and-risks.md` for active schema-governance risks,
  historical traps, and unresolved migration concerns.
- Use `VALIDATION_WORKFLOW_AND_TOOLS.md` for selector/runner/profile behavior.
- Use `FULL_VALIDATION_ENVIRONMENT_POLICY.md` when the claim is zero-skip,
  PostgreSQL-backed, or release-grade rather than an everyday targeted check.
- Use `roster-identity-repair-playbook` when the real task is identity repair
  workflow rather than general schema governance.

## Commands

```powershell
python ops/scripts/dev/check_schema_governance.py
python ops/scripts/dev/select_validation_targets.py --worktree
python ops/scripts/dev/run_validation_target.py static.schema_governance --timeout-seconds 120
.\.venv\Scripts\python.exe -m pytest tests\backend\roster\test_student_identity_audit.py -q
.\.venv\Scripts\python.exe -m pytest tests\postgres -q
```

## Checks

- `check_schema_governance.py` passes.
- New persisted fields have either model+DDL parity or a documented greenfield
  reason.
- Audit/repair commands are read-only by default unless explicitly applying a
  repair.
- PostgreSQL-required validation is either run or explicitly deferred as an
  environment-dependent broad/full target.
- Schema claims, bootstrap claims, and identity-repair claims should be
  classified separately instead of folded into one vague migration note.

## Failure Handling

- If static governance fails, fix the missing model/DDL/doc anchor before
  claiming migration readiness.
- If local SQLite is noisy, run `pytest_sqlite_guard.py` before deleting the
  shared test database.
- If Postgres is unavailable, record the validation blocker and do not claim
  zero-skip or production-aligned schema validation.

## Related Files

- `apps/backend/courseeval_backend/db/models.py`
- `apps/backend/courseeval_backend/bootstrap.py`
- `docs/reference/DATA_MODEL_ESSENTIALS.md`
- `docs/operations/ADMIN_BOOTSTRAP.md`
- `docs/governance/known-issues-and-risks.md`
- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`
- `ops/scripts/dev/check_schema_governance.py`
- `ops/scripts/dev/audit_student_identity.py`
- `ops/scripts/dev/repair_student_identity.py`
- `skills/roster-identity-repair-playbook/SKILL.md`
