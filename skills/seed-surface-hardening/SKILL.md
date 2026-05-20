---
name: seed-surface-hardening
description: Use this when changing or reviewing CourseEval demo seed, /api/e2e/dev routes, INIT_DEFAULT_DATA, first-admin bootstrap, seed tokens, public registration toggles, or other powerful local/test-only startup surfaces.
---

# Seed Surface Hardening

## Purpose

Keep powerful demo, seed, reset, and first-run surfaces useful for local
development and E2E automation without widening production behavior.

## Workflow

1. Read `docs/operations/ADMIN_BOOTSTRAP.md`,
   `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`,
   `docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`, and
   `docs/reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md`.
2. Classify the surface: first-admin bootstrap, demo data seed,
   `/api/e2e/dev/*`, mock LLM controls, grading pump, public registration, or
   local Playwright reset.
3. Confirm production behavior in code, not only docs. For `/api/e2e/dev/*`,
   production must return 404 unless `expose_e2e_dev_api()` is true.
4. Preserve dual gates for powerful E2E dev routes: seed token plus admin JWT
   when `E2E_DEV_REQUIRE_ADMIN_JWT=true`.
5. Add backend TestClient coverage for route gates before relying on
   Playwright.
6. Keep real tokens, local database paths, generated seed logs, and machine
   details out of committed files.

## Commands

```powershell
rg -n "E2E_DEV|INIT_DEFAULT_DATA|INIT_ADMIN|ALLOW_PUBLIC_REGISTRATION|expose_e2e_dev_api|reset-scenario|mock-llm|process-grading" apps/backend/courseeval_backend tests
.venv\Scripts\python.exe -m pytest tests\backend\e2e_dev -q
.venv\Scripts\python.exe -m pytest tests\backend\test_settings_e2e_router_gate.py -q
.venv\Scripts\python.exe ops\scripts\dev\select_validation_targets.py --worktree
```

## Guardrails

- Do not make E2E/dev routes reachable in production.
- Do not weaken seed-token or admin-JWT requirements without a security review
  and tests.
- Do not conflate first-admin bootstrap with demo data seeding.
- Do not store plaintext operational credentials in repository notes; use env
  vars and reset scripts.

## Related Files

- `apps/backend/courseeval_backend/api/routers/e2e_dev.py`
- `apps/backend/courseeval_backend/core/config.py`
- `apps/backend/courseeval_backend/domains/seed/demo.py`
- `apps/backend/courseeval_backend/bootstrap.py`
- `tests/backend/e2e_dev/`
- `tests/backend/test_settings_e2e_router_gate.py`
- `docs/operations/ADMIN_BOOTSTRAP.md`
