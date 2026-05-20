---
name: frontend-backend-contract-audit
description: Use this when reviewing or changing CourseEval frontend/backend contracts such as pagination bounds, query parameters, request bodies, response shapes, timeouts, bulk inputs, upload limits, or Vue API-client assumptions.
---

# Frontend Backend Contract Audit

## Purpose

Prevent UI and API drift. Frontend code must respect FastAPI route contracts for
path, method, query/body shape, validation bounds, authorization, and response
fields.

## Workflow

1. Identify the frontend caller, usually under `apps/web/school/src/` or
   `apps/web/parent/src/`.
2. Find the matching backend router in
   `apps/backend/courseeval_backend/api/routers/`.
3. Compare method, path, query parameter names, `Query(..., ge=..., le=...)`
   bounds, request schema, and response schema.
4. For list endpoints, verify `page_size` or `limit` values against the exact
   router. Do not reuse a bound from another route.
5. Add a focused API test for backend validation and, when the issue is
   browser-visible, a targeted frontend or Playwright test.
6. Update docs or selector rules if the contract is recurring or high-risk.

## Commands

```powershell
rg -n "page_size|limit|api\\.|axios|fetch\\(" apps/web/school/src apps/web/parent/src
rg -n "Query\\(|page_size|limit|@router" apps/backend/courseeval_backend/api/routers
.venv\Scripts\python.exe ops\scripts\dev\select_validation_targets.py --worktree
```

## Guardrails

- Frontend hiding is not validation or authorization.
- A route returning HTTP 422 for out-of-bound query values is often correct;
  check the declared `Query(le=...)` before changing tests.
- For bulk operations, verify both frontend request sizes and backend caps.
- Prefer shared frontend helpers for paged fetches when the backend contract is
  common; avoid hard-coded magic values copied across pages.

## Related Files

- `apps/web/school/src/api/index.js`
- `apps/web/parent/src/api/index.js`
- `apps/backend/courseeval_backend/api/routers/`
- `apps/backend/courseeval_backend/api/schemas.py`
- `tests/e2e/web-school/e2e-pitfall-guard-rails-batch2.spec.js`
- `docs/testing/TEST_EXECUTION_PITFALLS.md`
