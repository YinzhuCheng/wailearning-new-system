---
name: api-surface-audit
description: Use this when changing CourseEval FastAPI routers, route prefixes, frontend API clients, OpenAPI/API documentation, parent-code endpoints, E2E dev API routes, or API regression tests.
---

# API Surface Audit

## Purpose

Keep CourseEval's backend routers, frontend API clients, docs, and validation
targets aligned. This skill is for API contract changes; it does not replace a
full OpenAPI export.

This skill should route agents to the current API-surface truth quickly:
router shape, schema shape, client usage, permission boundary, and the right
validation lane for contract changes.

## When to Use

Use this before changing:

- `apps/backend/courseeval_backend/api/routers/*.py`
- `apps/backend/courseeval_backend/main.py`
- `apps/backend/courseeval_backend/api/schemas.py`
- `apps/web/school/src/api/index.js`
- `apps/web/parent/src/api/index.js`
- API route docs, parent-code docs, E2E dev API docs, or API regression tests

## Inputs

- Changed router/client/schema paths.
- Intended route family, HTTP method, request/query/body shape, and response
  model.
- Affected roles: admin, teacher, class teacher, student, parent-code caller, or
  E2E seed client.

## Workflow

1. Read:
   - `docs/reference/CODE_MAP_AND_ENTRYPOINTS.md`
   - `docs/reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md`
   - `docs/architecture/SYSTEM_OVERVIEW.md`
   - the affected feature doc
2. Open the backend router and `api/schemas.py` before trusting frontend helper
   names or older docs.
3. Confirm route prefix, method, query-vs-body shape, response model, and
   permission dependency in the router.
4. If the admin or parent SPA calls the route, update the matching API helper in
   the same change set.
5. If route semantics changed, update docs and selector targets together.
6. Route to `frontend-backend-contract-audit` when the real issue is a narrow
   request/response contract such as pagination bounds, request body shape, or
   response field usage rather than a broader route-family or router-surface
   change.
7. Use `VALIDATION_WORKFLOW_AND_TOOLS.md` to choose the right selector/runner
   lane instead of treating the older broad testing handbook as the first
   validation source.
8. Prefer pytest/API regression for contract changes; reserve Playwright for
   browser routing, visibility, or multi-tab behavior.

## Document Routing Rules

- Use `docs/reference/CODE_MAP_AND_ENTRYPOINTS.md` for where routers, clients,
  and schema surfaces live.
- Use `docs/reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md` when the route
  change might really be a permission-boundary problem.
- Use `docs/architecture/SYSTEM_OVERVIEW.md` for route-family and capability
  context.
- Use `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md` for selector, target, and
  profile behavior.
- Use `frontend-backend-contract-audit` when the problem is really a focused
  frontend/backend request contract issue, not a broader API surface audit.

## Commands

```powershell
python ops/scripts/dev/check_api_surface_governance.py
python ops/scripts/dev/select_validation_targets.py --worktree
python ops/scripts/dev/run_validation_target.py static.api_surface_governance --timeout-seconds 120
python ops/scripts/dev/run_validation_target.py security.api_regression --timeout-seconds 120
```

## Checks

- `check_api_surface_governance.py` passes.
- Changed route families are represented in selector targets or explicitly
  escalated to a broader target.
- Frontend helper URLs do not invent singular/plural paths that routers do not
  expose.
- Authorization-sensitive changes have backend tests, not only hidden UI
  buttons.
- Route-family drift, client drift, and permission-boundary drift should be
  classified separately instead of folded into one vague “API issue”.

## Failure Handling

- If the static guardrail fails, fix the router/client/doc anchor before
  claiming API surface alignment.
- If the right API target is missing, add a selector rule or document why broad
  validation is required.
- If OpenAPI export is needed but not implemented, record that as a known gap;
  do not hand-write a pretend complete API reference.

## Related Files

- `apps/backend/courseeval_backend/main.py`
- `apps/backend/courseeval_backend/api/routers/`
- `apps/backend/courseeval_backend/api/schemas.py`
- `apps/web/school/src/api/index.js`
- `apps/web/parent/src/api/index.js`
- `docs/architecture/SYSTEM_OVERVIEW.md`
- `docs/reference/CODE_MAP_AND_ENTRYPOINTS.md`
- `docs/reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md`
- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `ops/scripts/dev/check_api_surface_governance.py`
- `tests/TEST_SELECTION_TARGETS.json`
- `skills/frontend-backend-contract-audit/SKILL.md`
