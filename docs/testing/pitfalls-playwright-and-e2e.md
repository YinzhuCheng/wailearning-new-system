# Playwright And E2E Pitfalls

## Purpose

Use this route when the failure shape suggests:

- Playwright worker, browser, or webServer startup issues;
- Vite / backend managed-server problems;
- E2E port collisions;
- brittle selectors, overlay targeting, dropdown timing, or badge/UI race
  assertions;
- seeded browser-scenario setup drift.

This file is a **route, summary, and canonical home** for the Playwright and
E2E pitfall clusters that have already been migrated here. Historical entries
that have not been moved yet still remain in
[TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md).

## Start Here

1. Run:

   ```powershell
   python ops\scripts\dev\search_pitfalls.py "<exact Playwright error or UI symptom>"
   ```

2. Open:
   [FULL_PLAYWRIGHT_E2E_RUNBOOK.md](FULL_PLAYWRIGHT_E2E_RUNBOOK.md)
3. If the failure may still be local-environment shaped, route through:
   [../../skills/local-test-triage/SKILL.md](../../skills/local-test-triage/SKILL.md)

## Primary Pitfall Clusters

| Cluster | Start with |
|---------|------------|
| managed webServer, wrong Python, project discovery | Pitfalls 4, 11, 41, frontend/playwright invocation directory pitfalls |
| browser/runtime bootstrap | Pitfalls 48 and 75 |
| selector strict mode / duplicate UI affordances | Pitfalls 13, 18, 29, 32-40 |
| notification / course-switcher / mobile race behavior | Pitfalls 49-50, 63-71 |
| parent portal E2E contract | parent SPA truncation pitfall, Pitfall 127 in `pitfall-index.csv` |
| external runner / readiness timing | Pitfalls 88 and Playwright external-runner readiness sections |

## Key Pitfalls

- **Pitfall 11**: Playwright `webServer` on Linux may use `python3` without
  project dependencies.
- **Pitfall 41**: `read ECONNRESET` / `fetch failed` on default E2E ports is
  usually harness contention, not remote provider failure.
- **Pitfalls 13 / 18 / 32-40**: strict-mode duplication, wrong dialog target,
  disabled controls, and route/query expectation drift are frequent UI
  authoring traps.
- **Pitfall 48**: `npm: command not found` blocks Playwright even when pytest
  is green.
- **Pitfall 50**: notification header badge tests are especially sensitive to
  disabled course-card clicks, hover-only dropdowns, and badge/API race
  windows.
- **Pitfalls 63-75**: stale listeners, hover dropdowns, mock cursor drift,
  chapter reorder contracts, responsive timeout patterns, and missing browser
  binaries dominate long-suite browser failures.

## Recommended Commands

```bash
cd <repo>/apps/web/school
npm ci
npx playwright install chromium
npx playwright test --list
```

For routing or selector drift, also inspect:

- [TEST_SUITE_MAP.md](TEST_SUITE_MAP.md)
- [../frontend/NOTIFICATION_HEADER_AND_REALTIME_SYNC.md](../frontend/NOTIFICATION_HEADER_AND_REALTIME_SYNC.md)

For a maintained local screenshot workflow tied to the school E2E startup
contract, use:

```bash
cd <repo>/apps/web/school
npm run capture:homework-layout
```

This command writes to `<repo>/pics/homework-layout-fixed.png` by default and
keeps the output local unless the user explicitly asks to push it.

## Related Files

- [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)
- [FULL_PLAYWRIGHT_E2E_RUNBOOK.md](FULL_PLAYWRIGHT_E2E_RUNBOOK.md)
- [TEST_SUITE_MAP.md](TEST_SUITE_MAP.md)
- [../../skills/school-playwright-e2e/SKILL.md](../../skills/school-playwright-e2e/SKILL.md)

## Detailed migrated entries

### Additional session (Linux / cloud agent, May 2026)

This session used Linux bash, the repository `.venv` for pytest,
system-packaged Node/npm where needed, and Playwright driven from
`apps/web/school` (`npm run test:e2e`). Pitfalls 11–16 below come from that
pass. They complement, rather than contradict, the Windows-focused items.

### Pitfall 11: Playwright `webServer` on Linux uses `python3` without project packages

#### Symptom

Playwright fails immediately when starting the API, with stderr similar to:

- `No module named uvicorn`

#### Why it happens

The Playwright config may spawn the backend with the system `python3`. That
interpreter often does not have `requirements.txt` installed, while the
repository expects a local virtual environment.

#### What worked

- Point the API command at `.venv/bin/python` when that path exists, or set
  `E2E_PYTHON` to an interpreter that has backend dependencies installed.

#### Relationship to other guidance

This is the same operational idea as checklist item 1 ("use the repository
`.venv`"), but it applies specifically to who starts uvicorn when tests use
managed `webServer`.

### Pitfall 12: Element Plus default locale vs Chinese button labels in tests

#### Symptom

A test waits for `getByRole('button', { name: '确定' })` or `关闭`, but
Playwright reports strict-mode violations or timeouts. The dialog may show
**OK** / **Cancel**, or the header close button may expose a different
accessible name.

#### Why it matters

Without registering a Chinese locale for Element Plus, `ElMessageBox.confirm`
and similar components follow English defaults even when surrounding UI copy is
Chinese.

#### Safe handling strategy

- Register Element Plus `zh-cn` (or match tests to the actual accessible names
  rendered in your locale), or use narrow selectors.

### Pitfall 13: Playwright strict mode and duplicate text matches

#### Symptom

`expect(locator).toBeVisible()` fails with strict-mode violation: one locator
resolved to two or more elements.

#### Recommendation

Prefer:

- role-based locators
- scoped locators
- or `data-testid` hooks

#### Extensions

- duplicate `data-testid` values inside one overlay
- Element Plus `el-radio-button` intercepting clicks on the native radio input
- `MaterialRead` title vs chapter navigation ordering
- sidebar `default-active` vs nested routes
- homework detail page is a full route, not a dialog
- teacher dashboard route removal and redirect expectations

### Pitfall 14: `textarea:first()` on the homework submit page is often the wrong control

#### Symptom

Submission-related E2E polls the API forever: attempt count stays `0`, or
`POST /api/homeworks/{id}/submission` never fires as expected.

#### Why it happens

The homework submit view renders `CourseDiscussionPanel` above the homework
submission form. `page.locator('textarea').first()` fills the discussion draft,
not `homework-submit-content`.

#### Recommendation

Target the homework body field explicitly, for example
`getByTestId('homework-submit-content')`.

### Pitfall 15: client `page_size` larger than the API allows

#### Symptom

The materials UI shows an empty table even though seeded data exists, or E2E
cannot find a known material title.

#### Why it happens

List endpoints validate `page_size` with an upper bound (for example `le=100`).
A client request with `page_size=200` may return `422`; the UI may not surface
the validation error clearly.

#### Recommendation

Keep client requests aligned with FastAPI/Pydantic limits. When debugging empty
lists, inspect network responses for 422 before assuming seed or routing bugs.

### Pitfall 16: duplicate `course_enrollments` rows during startup reconciliation (often seen with SQLite)

#### Symptom

Backend crashes during application lifespan or pytest/E2E startup with unique
constraint failures on `course_enrollments.subject_id, student_id`.

#### Interpretation

Multiple reconciliation paths can attempt to insert the same enrollment for the
same student and course. SQLite may surface the race more readily during
startup batches.

#### What worked in practice

Defensive idempotency at insert time so startup reconciliation does not abort
the whole process.


## Additional migrated Playwright blocks

## Frontend Build And Playwright Invocation Directory Pitfalls

This subsection records command-invocation mistakes encountered while adding a
focused UI outline guard. The product code was not the root cause; the failures
came from running the right tools from the wrong directory or outside the test
configuration boundary.

### Pitfall: root-level `npm.cmd run build` can fail with missing `package.json`

Symptom:

```text
npm error enoent Could not read package.json
npm error path <repo>/package.json
```

Cause:

The school frontend package lives under:

```text
<repo>/apps/web/school
```

The repository root is not the frontend package root and does not own the
school SPA `package.json`.

Fix:

Run the build from the frontend app directory:

```text
cd <repo>/apps/web/school
npm.cmd run build
```

Interpretation:

Do not treat this failure as a dependency install failure or a Vite failure.
It is a working-directory failure. Re-run from the frontend package before
changing code, reinstalling packages, or editing build configuration.

### Pitfall: Playwright project names disappear when running from the spec directory

Symptom:

```text
Error: Project(s) "chromium" not found. Available projects: ""
```

Cause:

The Playwright config for the school SPA is in:

```text
<repo>/apps/web/school/playwright.config.cjs
```

Running `npx.cmd playwright test ... --project=chromium` from
`<repo>/tests/e2e/web-school` can fail to load that config. Without the config,
the CLI does not know about the `chromium` project.

Fix:

Run maintained school Playwright specs from:

```text
<repo>/apps/web/school
```

Use the configured test file name relative to the configured `testDir`, for
example:

```text
npx.cmd playwright test ui-homework-history-outline-regression.spec.js --project=chromium
```

Interpretation:

This is not evidence that Chromium is missing. It means the command did not
load the project configuration.

### Pitfall: path arguments outside configured `testDir` may report "No tests found"

Symptom:

```text
Error: No tests found.
Make sure that arguments are regular expressions matching test files.
```

Cause:

The school Playwright config sets:

```text
testDir: ../../../tests/e2e/web-school
```

Passing a path outside that directory, such as an ignored local script under
`<artifact-dir>`, does not necessarily behave like a one-off arbitrary spec
runner. The config still scopes discovery around its `testDir`.

Fix:

For maintained tests, keep the spec under `<repo>/tests/e2e/web-school` and run
it by filename from `<repo>/apps/web/school`.

For local screenshot experiments, prefer a committed maintained script when the
workflow is likely to recur. The current example is
`apps/web/school/scripts/capture-homework-layout-runner.cjs`.

Only fall back to one-off local helpers when the scenario is truly disposable.

Interpretation:

Do not expand `testDir` just to run a local screenshot helper. Keep ignored
artifacts ignored and keep maintained test discovery narrow.

### Pitfall: local Node screenshot scripts may not inherit Playwright config module resolution

Symptom:

```text
Error: Cannot find module '@playwright/test'
Require stack:
- <repo>/tests/e2e/web-school/fixtures.cjs
- <artifact-dir>/...
```

Cause:

The school Playwright config prepends the frontend `node_modules` directory to
`NODE_PATH` and calls `Module._initPaths()` before running tests. A direct local
Node script does not inherit that setup unless it recreates it.

Fix:

For local-only scripts, add the equivalent setup before importing E2E helpers:

```javascript
const Module = require('module')
const schoolNodeModules = '<repo>/apps/web/school/node_modules'
process.env.NODE_PATH = [schoolNodeModules, process.env.NODE_PATH].filter(Boolean).join(path.delimiter)
Module._initPaths()
```

Use placeholder paths in committed docs. Put real absolute paths only in ignored
local notes.

Interpretation:

This failure does not mean `@playwright/test` is missing from the frontend app.
It means the direct script skipped the configuration bootstrap that normally
makes the package visible to shared E2E helpers.

## What This Document Does Not Claim

It does not claim SQLite and PostgreSQL accept the same SQL text for every ad hoc query embedded in tests.

### Pitfall 41: Playwright `read ECONNRESET` / `TypeError: fetch failed` with default E2E ports

Symptom:

```text
TypeError: fetch failed
[cause]: Error: read ECONNRESET
```

Context:

School Playwright defaults commonly bind the backend to `http://127.0.0.1:8012` and the SPA to
`http://127.0.0.1:3012`. Mock LLM traffic stays on-loopback under paths such as
`/api/e2e/dev/mock-llm/<profile>/v1/`. This is **not** an external provider outage.

Cause:

Two or more Playwright CLI processes (or stray `uvicorn` / `vite` processes) can race the same
fixed ports. The browser then hits a half-dead server, a wrong process, or a torn-down connection,
which surfaces as `ECONNRESET` rather than a clear HTTP error.

Fix:

- Run narrow E2E greps **serially** (one `npx playwright test ...` at a time).
- Before blaming product code, check for duplicate listeners on `8012` / `3012` (or whatever
  `E2E_API_PORT` / `PLAYWRIGHT_BASE_URL` you configured).
- When you must parallelize automation, assign **distinct** backend and frontend ports per job and
  isolate databases.

Interpretation:

This failure pattern is usually harness contention, not Codex rate limits and not remote LLM API
instability.
