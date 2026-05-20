---
name: school-playwright-e2e
description: Use this when running, debugging, or documenting CourseEval school Playwright E2E. Triggers include targeted spec runs, full admin browser validation, external-runner usage, seed/reset troubleshooting, port/process cleanup, and converting a repeatable browser workflow into durable repo guidance.
---

# School Playwright E2E

## Purpose

Run CourseEval school Playwright with the repository's supported workflow instead
of ad hoc browser commands. Prefer the repo's external runner for real runs so
API/UI startup and teardown stay owned by one process.

This skill should route through the narrowest current Playwright docs first,
instead of defaulting to the full testing handbook for every browser task.

## Workflow

1. Read:
   - `docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`
   - `docs/testing/pitfalls-playwright-and-e2e.md`
   - `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
2. If the run is being treated as full-suite, zero-skip, or release-grade,
   also read:
   - `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`
3. Confirm school package dependencies and browsers exist in
   `apps/web/school/`.
4. For a real targeted run, prefer the external runner from the school package:
   `node scripts/playwright-external-runner.cjs <spec>.spec.js --project=chromium`
5. Use `tests/e2e/web-school/fixtures.cjs` and
   `future-advanced-coverage-helpers.cjs` patterns before inventing new seed,
   login, or API helper flows.
6. If the browser scenario needs complex state, create it through seeded API
   helpers first, then assert the browser-visible outcome.
7. Record whether a failure came from product behavior, seed/reset, browser
   startup, stale ports, or teardown/cleanup.
8. Run external-runner commands serially when using the default ports/database.
   Parallel default runners can make Vite switch away from port 3012 while
   Playwright still navigates to 3012, and can lock the shared SQLite database.
9. When running more than one Playwright spec as a validation series, prefer a
   WAI-VALID self-organized custom block instead of serial ad hoc commands.
   WAI-VALID assigns isolated API/UI ports and SQLite state per spec, so the
   default custom-block concurrency is `10` unless resource pressure requires a
   documented lower value.

## Document Routing Rules

- Use `FULL_PLAYWRIGHT_E2E_RUNBOOK.md` as the canonical source for the full
  school Playwright environment contract.
- Use `pitfalls-playwright-and-e2e.md` as the first pitfall route when the
  failure shape is clearly browser/harness/UI-flow related.
- Use `VALIDATION_WORKFLOW_AND_TOOLS.md` for selector, target, and profile
  behavior when deciding how much Playwright to run.
- Use `FULL_VALIDATION_ENVIRONMENT_POLICY.md` only when the browser work is part
  of a full-suite / release-grade validation claim.
- Use `TEST_EXECUTION_PITFALLS.md` as the mixed-surface fallback, not the first
  read in every Playwright task.

## Commands

```powershell
cd apps/web/school
npm.cmd ci
npx.cmd playwright install chromium
cd ..\..
python ops/scripts/dev/playwright_preflight.py --json
cd apps/web/school
node scripts/playwright-external-runner.cjs roster-and-users.spec.js --project=chromium
node scripts/playwright-external-runner.cjs
```

## Guardrails

- Prefer `node scripts/playwright-external-runner.cjs ...` over managed
  `npx playwright test ...` for non-trivial local runs.
- Keep `E2E_DEV_SEED_TOKEN`, `E2E_API_URL`, and `PLAYWRIGHT_BASE_URL`
  consistent with the runner flow; do not hand-roll mixed startup modes.
- Do not start two `npm.cmd run test:e2e:external -- ...` commands in parallel
  on the default ports. If parallelism is required, assign distinct
  `E2E_API_PORT`, `E2E_UI_PORT`, and database paths per process.
- WAI-VALID custom blocks are the supported parallel Playwright path because
  they provide per-shard API/UI port isolation and supervised timeout handling.
- Reuse fixture helpers before adding bespoke login or seed code.
- For API-heavy browser scenarios, assert the API-side precondition before
  blaming a missing UI row.
- Treat spawn errors, missing browsers, stale ports, or teardown timeouts as
  harness signals first.
- Do not claim selector recommendations or partial browser smoke as release-grade
  browser coverage without following the full-validation policy lane.

## Related Files

- `apps/web/school/scripts/playwright-external-runner.cjs`
- `apps/web/school/playwright.config.cjs`
- `tests/e2e/web-school/fixtures.cjs`
- `tests/e2e/web-school/future-advanced-coverage-helpers.cjs`
- `docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`
- `docs/testing/pitfalls-playwright-and-e2e.md`
- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`
- `docs/testing/TEST_EXECUTION_PITFALLS.md`
