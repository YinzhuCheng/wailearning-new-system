---
name: boundary-governance
description: Use when clarifying CourseEval feature, module, permission, data-flow, import, and ownership boundaries; identifying large files, mixed responsibilities, duplicate implementations, cross-layer imports, naming drift, or safe file splits/moves that reduce agent context load without breaking behavior.
---

# Boundary Governance

## Goal

Reduce context explosion for future feature work. Make ownership and data flow
clear enough that a small change does not require reading unrelated modules.

## Layer Role

This is a horizontal boundary skill. Use it to identify ownership drift,
mixed responsibilities, large files, and unsafe imports. When a finding belongs
to a specialized risk domain, route to the richer skill rather than expanding
this checklist.

## Workflow

1. Read `AGENTS.md`, `docs/README.md`, `docs/architecture/BACKEND_PACKAGE_STRUCTURE.md`,
   `docs/reference/CODE_MAP_AND_ENTRYPOINTS.md`, and task-specific product docs.
2. Run:
   `python ops/scripts/dev/check_boundary_governance.py --details`.
   When `api/schemas.py` is a candidate for splitting, also run:
   `python ops/scripts/dev/inventory_api_schemas.py --fail-on-missing-imports`.
3. Classify findings:
   - low-risk: pure helper extraction, documentation or agent-map clarification, import path
     cleanup with direct tests;
   - medium-risk: moving domain helpers already isolated by tests;
   - high-risk: router splits, startup/bootstrap changes, permission helpers,
     schema/DDL, worker orchestration, cross-role behavior.
4. Apply only low-risk changes in a general governance round. Record medium/high
   risks in docs with file paths, why they matter, and recommended validation.
5. When moving code, update imports, tests, scripts, docs links, `AGENTS.md`,
   and validation target metadata in the same change.
6. Route specialized risks:
   - authorization or course access: `skills/permission-audit/SKILL.md`;
   - route/client contract: `skills/api-surface-audit/SKILL.md`;
   - frontend request/response drift:
     `skills/frontend-backend-contract-audit/SKILL.md`;
   - schema, bootstrap, or data repair:
     `skills/data-migration-audit/SKILL.md`;
   - seed/E2E dev surface: `skills/seed-surface-hardening/SKILL.md`.

## Boundary Rules

- Keep `apps.backend.courseeval_backend` as the only backend import root.
- Routers own HTTP shape and orchestration; domain packages own reusable
  business rules; `core/` owns cross-domain primitives only.
- `api/schemas.py` is a high-blast-radius schema barrel. Do not split it during
  a broad governance pass. First inventory direct imports, domain buckets,
  schema references, and `model_rebuild()` calls with
  `ops/scripts/dev/inventory_api_schemas.py`; then split behind a dedicated
  validation matrix.
- Frontend hiding is not authorization. Backend route/domain checks must enforce
  sensitive behavior.
- Prefer the richer specialized skill or guard script when it overlaps this
  skill. Keep this skill focused on boundary discovery and safe routing.
- Prefer a documented follow-up over a risky split without focused tests.

## Current Large-File Interpretation

As of the May 2026 repository-normalization closeout, current high-value
backend candidates are `llm_grading.py`, `api/routers/homework.py`,
`domains/seed/demo.py`, `bootstrap.py`, and dedicated `api/schemas.py`
schema-boundary rounds. `api/routers/subjects.py` is below the backend router
threshold after helper extraction and should be treated as an accepted HTTP/auth
orchestration boundary unless new reusable course logic accumulates there.

Large admin Vue views remain UI-boundary candidates, but split them only with a
frontend build and targeted Playwright evidence in scope.

## Checks

```powershell
python ops/scripts/dev/check_boundary_governance.py --details
python ops/scripts/dev/inventory_api_schemas.py --fail-on-missing-imports
python ops/scripts/dev/check_api_surface_governance.py
python ops/scripts/dev/check_schema_governance.py
python ops/scripts/dev/select_validation_targets.py --worktree
```
