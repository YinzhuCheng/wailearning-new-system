# Test Execution Pitfalls

## Purpose

This document records pitfalls encountered while executing the repository test suites on Windows + PowerShell during the repository-structure refactor completed on May 1, 2026. The focus here is the tester environment, test runner behavior, and execution workflow friction, not product-code bugs.

Later passes (same overall repository layout) added Linux / CI / cloud-agent notes and Playwright selector pitfalls discovered while fixing false failures. Those additions are additive: they do not replace the Windows-focused guidance above.

This file is meant to save future test operators from rediscovering the same issues.

For the repository-wide policy on Unicode-safe editing and for the current mojibake hotspot audit, also read:

- [ENCODING_AND_MOJIBAKE_SAFETY.md](../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md)

## Topic Routes

`TEST_EXECUTION_PITFALLS.md` remains the **primary execution encyclopedia**
for historical pitfall entries, mixed-surface narratives, and the structured
`pitfall-index.csv` linkage. Some canonical pitfall clusters now live in the
topic docs below. Use the topic routes when you already know the failure class
and want the narrower canonical surface before diving back into the full
encyclopedia.

- [pitfalls-windows-and-encoding.md](pitfalls-windows-and-encoding.md)
  for PowerShell, UTF-8, local shell, and machine-local text/tooling hazards.
- [pitfalls-playwright-and-e2e.md](pitfalls-playwright-and-e2e.md)
  for Playwright harness, Vite/webServer, E2E ports, selector races, and UI
  authoring traps.
- [pitfalls-postgres-and-pytest.md](pitfalls-postgres-and-pytest.md)
  for PostgreSQL provisioning, dialect differences, SQLite vs PostgreSQL test
  semantics, and full-suite environment gates.
- [pitfalls-ledger-and-selector-tooling.md](pitfalls-ledger-and-selector-tooling.md)
  for validation-selector, CSV ledger, update-log, private-path scan, and
  append-tooling pitfalls.

Use the topic docs as routers and as canonical homes for clusters already
migrated there. Record new pitfall details in the most specific canonical
location:

- use this file for new mixed-surface or not-yet-migrated entries;
- use the matching topic doc when that cluster already lives there.

## Read This Before Running Tests

If you are about to run tests, especially as an LLM coding agent on Windows + PowerShell, check these first:

1. Use the repository `.venv`, not a global Python.
2. Treat `npm.ps1` as suspect; prefer `npm.cmd` or `npx.cmd` when PowerShell policy is restrictive.
3. Assume stale backend or frontend processes may still own your intended ports.
4. Do not trust "a port responds" as proof that the correct app is serving.
5. For Playwright, prefer isolated ports and explicit external-server startup when a run matters.
6. If pytest fails before test bodies execute, inspect temp-path behavior before blaming product code.
7. Do not copy Chinese text from PowerShell output back into tracked files.
8. On Linux or in CI, if Playwright starts the API via `webServer`, confirm the command uses the repository `.venv` interpreter (or `E2E_PYTHON`), not a bare `python3` without project dependencies (see Pitfall 11).

If you skip this checklist, you may spend time debugging the shell, temp directories, old background processes, or port collisions instead of the repository itself.

## Fuzzy Pitfall Lookup Before Failure Triage

Before classifying any command, test, Playwright, PostgreSQL, encoding, port,
process, selector, or local-environment failure, search the pitfall memory. Do
this before changing product code or deciding whether the failure is product,
test-contract, harness, or environment.

Use the repository helper from the repo root:

```powershell
python ops\scripts\dev\search_pitfalls.py "initdb restricted token error code 87 postgres"
python ops\scripts\dev\search_pitfalls.py "playwright grep no tests found"
python ops\scripts\dev\search_pitfalls.py "QueuePool course card timeout"
```

The helper searches:

- this Markdown pitfall file;
- `docs/testing/pitfall-index.csv`;
- `docs/architecture/TROUBLESHOOTING.md`;
- `docs/testing/DEVELOPMENT_AND_TESTING.md`;
- repo-local `skills/*/SKILL.md`.

Fuzzy lookup strategy:

1. Search the exact error text first, including numeric error codes.
2. Search the command or tool name (`pytest`, `playwright`, `initdb`,
   `postgres`, `npm.cmd`, `selector`, `encoding`, etc.).
3. Search the affected subsystem or harness (`parent portal`, `notification`,
   `e2e`, `sqlite`, `QueuePool`, `localStorage`, `TEST_DATABASE_URL`).
4. Search aliases and near terms. Examples: `pg` and `postgres`; `e2e` and
   `playwright`; `utf8`, `utf-8`, and `mojibake`.
5. Inspect both the structured index hit and the surrounding Markdown or skill
   guidance before acting.

Interpretation rules:

- A search hit is a lead, not a verdict. Confirm that the root cause and
  mitigation match the current failure before reusing it.
- If an existing pitfall matches, record the observed run or validation result
  in the relevant ledger; do not create duplicate pitfall entries.
- Add a new pitfall only when the root cause, trigger condition, or mitigation
  is genuinely new.
- If the search returns no useful hits, document the failed lookup in your
  reasoning, classify the failure from primary evidence, and add a pitfall if
  the trap is repeatable.

## Recording New Pitfalls

When a failure reveals a genuinely new repeatable trap, record it in the same
change set.

Use this flow:

1. Search first with `search_pitfalls.py`.
2. Add or update the Markdown explanation in the most specific canonical
   pitfall document.
3. Add one matching row to `docs/testing/pitfall-index.csv`.
4. Keep the durable mitigation in the most specific live location: this file, a
   guardrail script, a selector/runner rule, or a repo-local skill.

Structured index fields:

- `pitfall_sequence`
- `source_commit_sha`
- `document_path`
- `heading`
- `category`
- `status`
- `notes`

Sequence rules:

- new pitfalls use increasing positive integers;
- legacy Markdown-only pitfalls may remain `pitfall_sequence=0` with
  `source_commit_sha=Null`;
- use the most recent committed hash at the time the new pitfall is recorded as
  `source_commit_sha`.

Use [`../../skills/local-test-triage/SKILL.md`](../../skills/local-test-triage/SKILL.md)
when the main problem is failure classification rather than authoring the
pitfall entry itself.

## Windows, encoding, and local shell notes

Detailed Windows / PowerShell / UTF-8 / temp-path execution narratives have
been moved to
[pitfalls-windows-and-encoding.md](pitfalls-windows-and-encoding.md).

This includes:

- the scope of the original Windows session;
- PowerShell mojibake and safe UTF-8 helper usage;
- `npm.ps1` execution-policy issues;
- sandbox `EPERM` child-process startup failures;
- stale readiness and old-process contamination;
- pytest temp-directory behavior on Windows;
- background process lifetime differences;
- Node module resolution after test moves;
- `git` index-lock / execution-permission issues.
## Playwright, E2E, and browser-authoring notes

Detailed Playwright / E2E / selector / browser-authoring narratives for the
first Linux-cloud session and the early strict-mode/browser-contract pitfalls
have been moved to
[pitfalls-playwright-and-e2e.md](pitfalls-playwright-and-e2e.md).

This includes:

- the additional Linux / cloud-agent session note;
- Pitfalls 11-16 around managed `webServer`, locale, duplicate selectors,
  wrong textareas, `page_size`, and startup reconciliation drift;
- early browser-authoring extensions that are easier to route from the narrower
  Playwright topic doc.
## Remaining unease after advanced E2E and behavior passes (May 2026)

These are not documented as solved product defects; they are **risk surfaces** that stayed uncomfortable while authoring higher-difficulty tests:

- **Notification mark-all-read vs UI**: server semantics can be correct while the UI remains temporarily ambiguous under concurrency; treating API responses as authoritative remains mandatory.
- **SQLite concurrency**: even after idempotent inserts, **lost updates** remain possible for counters updated via ORM read-modify-write; concurrent increment paths may need SQL-level atomic updates.
- **Router-driven redirects**: admin accounts skip student-facing navigation assumptions; tests must mirror **actual role routing**, not an idealized “open any path” model.
- **`expect.poll` footguns**: returning `undefined`/`null` can prevent predicate satisfaction until timeout; ensure the predicate returns a definite boolean or use assertions inside the callback carefully.

## Pitfall 17: school SPA router redirects hide student routes until course context exists

### Symptom

Playwright navigates to `/points-display`, `/homework`, `/notifications`, etc., but lands elsewhere or never reaches the expected shell controls until timeouts.

### Why it happens

The school SPA `router.beforeEach` redirects **admin users** away from many paths students use, and **students** may be forced through `/courses` until `selectedCourse` / enrollment context is resolved.

### Recommendation

For student flows that depend on a seeded course, call the same **`enterSeededRequiredCourse`** helper used by other specs **before** asserting pages that assume teaching/student course context.

### Extension (May 2026): read-only list routes may mutate roster/user linkage

`GET /api/students`, `GET /api/students/{id}`, and admin `GET /api/users` invoke `reconcile_student_users_and_roster()` followed by `Session.commit()` before returning JSON. This intentionally heals drift between roster rows and student login accounts when staff merely **open** the Students or Users admin pages.

Implications for tests:

- Specs that relied on “no `User` exists yet for this `Student` until an explicit POST” can become flaky after navigation triggers reconciliation.
- Prefer asserting **final product state** after navigation (or seed fixtures that already satisfy reconciliation) rather than assuming stale orphan roster rows persist across GETs.

### Extension (May 2026): elective courses no longer mirror `Subject.class_id`

Product change: electives clear `subjects.class_id` and remove `Subject.class_id == klass` predicates from demo seeds / student enrollment guards.

Playwright / API tests that assumed:

- `GET /subjects/elective-catalog` filters `WHERE subject.class_id IS NOT NULL`, or
- self-enroll endpoints rejected courses without `class_id`, or
- demo elective lookup queried `(name, teacher_id, class_id)`

need updating to match `domains/courses/access.py` + `api/routers/subjects.py`. Backend regression coverage lives in `tests/backend/courses/test_subject_multi_class_links.py`.

## Pitfall 18: Playwright strict mode with multiple tables (`getByRole('table')`)

### Symptom

`expect(page.getByRole('table')).toBeVisible()` fails with strict-mode violations or resolves the wrong table (layout chrome vs-data tables).

### Recommendation

Scope locators: `page.locator('.ranking-card').getByRole('table').first()` (or another stable ancestor), rather than the page-global role query.

## Pitfall 19: student course-catalog enrollment flags (`is_enrolled`, not legacy JSON guesses)

### Symptom

Assertions like `row.enrolled` always fail even though the UI shows enrollment; API responses look “wrong”.

### Why it happens

The student catalog schema exposes **`is_enrolled`** (see `StudentCourseCatalogItem`). Older informal field names are misleading.

### Recommendation

Assert **`is_enrolled`** / documented schema fields, not ad hoc property names copied from other payloads.

## Pitfall 20: user updates use `PUT`, not `PATCH`

### Symptom

E2E sends `PATCH /api/users/{id}` expecting `{ is_active: false }`; nothing changes and downstream bearer validation assertions fail.

### Recommendation

Match the backend route family (`PUT /api/users/{id}` for updates in this repository) when scripting admin changes.

## Pitfall 21: `POST /api/notifications/mark-all-read` takes `subject_id` as a query parameter

### Symptom

Posting JSON `{ subject_id: ... }` to `mark-all-read` silently behaves like “no filter” or fails validation expectations.

### Recommendation

Mirror the SPA client: **`POST /api/notifications/mark-all-read?subject_id=<id>`** (FastAPI `Optional[int]` query params).

## Pitfall 22: clicking disabled “mark all read” can stall `Promise.all`

### Symptom

An E2E runs until the **suite timeout** with no obvious failure until you notice Playwright waiting forever on a click.

### Why it happens

The notifications UI disables “全部标为已读” when `unreadCount === 0`. Putting `click()` inside `Promise.all` alongside API racing calls may block indefinitely.

### Recommendation

Prefer API-only storms for concurrency scenarios, or guard clicks with enabled checks; do not parallelize unconditional UI clicks with uncertain disabled state.

## Pitfall 23: homework submission success copy varies (`作业已提交` vs “已保存”)

### Symptom

Assertions waiting only for `/已保存/` miss Element Plus success toasts.

### Recommendation

Allow multiple known success patterns consistent with `HomeworkSubmission.vue` (`作业已提交`, etc.).

## Pitfall 24: SQLite `UNIQUE` on first-create paths vs lost updates on counters

### Symptom A — inserts

Concurrent first-time inserts into uniqueness-constrained rows (examples encountered while extending coverage: `homework_submissions`, `student_points`) surface **`IntegrityError`** under parallel requests.

### What helps

Treat duplicate-key as “already exists”, rollback, reload the row, and continue; homework submission creation paths adopted this pattern during stress testing.

### Symptom B — updates

Concurrent “read balance → add → write” increments lose totals even without duplicate inserts.

### What helps

Prefer **single-statement SQL increments** (`UPDATE ... SET total_points = total_points + :delta`) for hot counters instead of ORM read-modify-write in parallel threads.

## Pitfall 25: helper `fetch` / `fetchRaw` double-prefixes the API base URL

### Symptom

`TypeError: Failed to parse URL` or URLs like `http://127.0.0.1:8012http://127.0.0.1:8012/api/...`.

### Why it happens

A helper already prefixes `apiBase()`, but the test passes a **full absolute URL** as the path argument.

### How to avoid (test side)

- Pass **path-only** strings to shared helpers (`/api/...`), **or**
- Teach the helper to treat `http://` / `https://` prefixes as already-absolute and skip concatenation.

## Pitfall 26: `fetchRaw`-style helpers and JSON bodies — avoid double encoding

### Symptom

Backend `500` / `AttributeError` (for example attendance batch) because the route receives a **string** where it expects a parsed object.

### Why it happens

The test passes `JSON.stringify(body)` while the helper also sets `Content-Type: application/json` and may stringify again, or the server assumes `dict` and calls `.get` on a string.

### How to avoid (test side)

- Pass a **plain object** as the body and let one layer perform `JSON.stringify`.
- If you must send raw bytes, match what the backend route declares (form vs JSON).

## Pitfall 27: asserting fields that the API response model does not expose

### Symptom

`expect.poll` never succeeds: the test checks `homework_title` (or similar) on a payload that only includes **`HomeworkSubmissionHistoryResponse`** fields (`summary`, `attempts`), not the parent homework row.

### How to avoid (test side)

- Before writing polls, confirm field names against **`apps/backend/courseeval_backend/api/schemas.py`** or a sample `GET` in Swagger/OpenAPI.
- For “title updated” convergence, prefer **`GET /api/homeworks/{id}`** (or the list endpoint) for the homework record, not the submission history response.

## Pitfall 28: Pydantic validation limits are easy to violate in scripted payloads

### Symptom

`422` on appeals, LLM course settings, or other endpoints when the test uses too-short strings or token counts below `ge=...`.

### Examples encountered

- Appeal `reason_text` minimum length (validators strip and enforce a floor).
- `max_input_tokens` / `max_output_tokens` on course LLM config have **minimums** (for example 1000) — values chosen only to “stress” the worker may be **invalid for the schema**.

### How to avoid (test side)

- Read the schema / router for **`Field(ge=...)`** and custom validators before choosing edge values.
- Separate “invalid on purpose” cases (expect 422) from “happy path” cases.

## Pitfall 29: UI title vs API title — heading selectors may not match the DOM

### Symptom

API polls green, but `getByRole('heading', { name })` times out on the homework submit page.

### How to avoid (test side)

- After authoritative API state is correct, **`reload`** the page and assert **`body` text** or a broader title locator (`h1`, `h2`, `.page-title`) with `filter({ hasText })`, not only `heading` role, unless you verified the component’s a11y tree.

## Pitfall 30: password-change + token invalidation tests must capture the old token first

### Symptom

The test obtains a **new** token after the UI already changed the password, then expects `401` — receives `200` because the new token is valid.

### How to avoid (test side)

- Call `obtainAccessToken(...)` **before** any UI action that changes credentials.
- After UI submit, **poll** `GET /api/auth/me` with the **old** token until `401` (or a short wait for commit), because UI “success” can race the DB update.

## Pitfall 31: attachment download tests must respect how the server authorizes URLs

### Symptom

`404` or `403` when `GET`ting a file right after `POST /api/files/upload`: the bytes exist on disk but **no row** references the URL yet (name-based download resolves candidates via DB paths like homework, materials, notifications, **and** user avatar).

### How to avoid (test side)

- For “download works” coverage, either **link** the file the way production does (homework submission, material, **or** `POST /api/auth/me/avatar`), **or** assert the documented behavior for orphan uploads.
- When building a path for `fetch`, handle **relative** `attachment_url` values (`/api/files/...`) — do not assume `new URL(fileUrl)` without a base when the server returns a path-only URL.

## Pitfall 32: Element Plus `ElMessageBox.confirm` title is not always the dialog’s accessible name

### Symptom

Playwright waits forever on `getByRole('dialog', { name: /删除课程/ })` or the confirm button inside it, while the UI visibly shows the delete confirmation.

### Why it matters

MessageBox markup and locale wiring do not guarantee that the **title string** is exposed as the dialog’s **accessible name** in every Element Plus version or configuration.

### How to avoid (test side)

- Prefer targeting the overlay that contains the primary action, for example `page.getByRole('dialog').filter({ has: page.getByRole('button', { name: /^(确定|OK)$/ }) })`, then click **确定/OK** inside that dialog (same pattern as advanced coverage specs).

## Pitfall 33: Student “我的课程” page shows the same course title twice (catalog table vs course cards)

### Symptom

`page.locator('tr').filter({ hasText: courseName })` or `row.getByRole('button').first()` clicks **刷新目录** or hits the wrong row; API polls never reach the expected enroll/drop state.

### Why it happens

`MyCourses.vue` renders the **elective catalog** in a table and also lists **active courses** as cards below. The same `name` can appear in both regions; the first `tr` match or the first button in a row may not be **选课/退选**.

### How to avoid (test side)

- Scope locators to the catalog card only, e.g. `.elective-catalog-card` + `.el-table__body tbody tr`, then click **`getByRole('button', { name: '选课' })`** or **`'退选'`** explicitly — never `row.getByRole('button').first()`.

## Pitfall 34: `click({ force: true })` on a disabled Element Plus button is a silent no-op

### Symptom

Dual-tab elective enroll/drop tests time out on `expect.poll` even though the test “clicked” 退选/选课.

### Why it happens

In `MyCourses.vue`, **退选** stays `:disabled` until local `courses` includes the elective (`isElectiveEnrollment`). Catalog `is_enrolled` can be true while the button is still disabled for a short window. **`force: true` does not enable a disabled control.**

### How to avoid (test side)

- **`await expect(button).toBeEnabled({ timeout: … })`** before `click()` (without `force`), or assert API-side state first and reload the page if you intentionally need a cold DOM.

## Pitfall 35: `waitForResponse` registered after `click()` misses a fast 200

### Symptom

`TimeoutError` waiting for `POST …/roster-enroll` even though the UI closed the dialog and enrollment succeeded.

### Why it happens

The response can complete before Playwright attaches the listener.

### How to avoid (test side)

- Start **`page.waitForResponse(...)`** and **`click()`** in the same **`Promise.all([...])`**, or use **`expect.poll`** on API state instead of relying on a single network event.

## Pitfall 36: Over-broad `getByRole('button', { name: /密码/ })` matches the wrong control

### Symptom

Password-change / token-invalidation specs never call `POST /api/auth/change-password` or behave randomly.

### Why it happens

Section headers and other controls can match a loose `/密码/` regex; the real submit control on `PersonalSettings.vue` is **`更新密码`**.

### How to avoid (test side)

- Prefer **exact** button labels from the Vue template (`更新密码`) or `data-testid` if one is added later.

## Pitfall 37: Vite `webServer` + repeated `goto('/login')` — navigation interrupted or `net::ERR_ABORTED`

### Symptom

`page.goto('/login')` throws **interrupted by another navigation** or **`net::ERR_ABORTED`**, or `page.evaluate` fails with **Execution context was destroyed**, often after a long E2E run or when the dev server reloads.

### How to avoid (test side)

- Use **`waitUntil: 'domcontentloaded'`** (not only `load`) for login hops, **retry** `goto` on the errors above, and treat **`goto` + `localStorage.clear`** as best-effort if the page navigates mid-call.
- Before starting a new Playwright process, ensure **no stray `node`/`vite`/`chrome`** holds `E2E_UI_PORT` / `E2E_API_PORT` when `reuseExistingServer` is false — otherwise `webServer` fails to bind and the suite misleads you into “app” failures.

## Pitfall 38: Admin delete-course UI assertion races the subjects table refresh

### Symptom

`DELETE /api/subjects/{id}` returns **200**, but `getByTestId('subjects-delete-{id}')` still exists for tens of seconds — `toHaveCount(0)` times out.

### Why it happens

The list row is driven by client state; **`loadCourses()`** (or equivalent) may lag behind the successful API delete, especially under Vite dev + SQLite E2E load.

### How to avoid (test side)

- After a successful delete response, **`expect.poll` on `GET /api/subjects`** until the id disappears, then **`page.goto('/subjects')`** (or wait for an explicit table reload) before asserting row-level UI.

## Pitfall 39: `page_size` upper bounds differ by route — do not assume `le=100` everywhere

### Symptom

A test expects **`422`** for `page_size=200` on **`/api/students`**, but receives **200** — because that list allows **`le=1000`**.

### Why it matters

Copy-pasting “`page_size=200` means 422” from homework/materials/notifications tests will create **false failures** on routes with different `Query(..., le=...)`.

### How to avoid (test side)

- Read the **`Query(..., le=)`** on the FastAPI handler (or grep `page_size` in `apps/backend/courseeval_backend/api/routers/`) before picking an out-of-range value. Prefer **`page_size = max_allowed + 1`** per route family.

## Pitfall 40: `force: true` on Element Plus table row checkboxes can skip selection state

### Symptom

`page.waitForResponse` for `POST .../roster-enroll` times out (up to 120s) on `Subjects.vue` “从花名册进课” even though the dialog and row are visible.

### Why it happens

`btn-roster-enroll-submit` stays **disabled** until `rosterEnrollSelection` is non-empty selection from `el-table` **selection-change**. A forced click on the row checkbox can fail to run the same code path as a normal user click, so no row is selected, the primary button remains disabled, and a second **`click({ force: true })` on the disabled button** is a no-op—no network request, endless wait for response.

### How to avoid (test side)

- Click the table selection checkbox **without** `force: true` (or use the table’s public selection API if you add one in the app for tests only).
- **`await expect(getByTestId('btn-roster-enroll-submit')).toBeEnabled()`** before pairing `waitForResponse` with submit.
- If you need `force` on the submit click, do not use it on the checkbox first; re-read Pitfall 34 for disabled-control semantics.

## Proven Command Patterns

### Backend full suite

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests -rs -q
```

### Playwright test discovery

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH='C:\Users\<user>\AppData\Local\ms-playwright'
& 'C:\Program Files\nodejs\npx.cmd' playwright test --list
```

### Windows-safe Node package invocation

```powershell
& 'C:\Program Files\nodejs\npm.cmd' run test:e2e
& 'C:\Program Files\nodejs\npx.cmd' playwright test
```

## Recommended Execution Order for Future Full Validation

1. Confirm no stale backend/frontend processes are occupying the intended ports.
2. Use the repository `.venv` explicitly for backend commands **and** for any Playwright-managed API process when using `webServer` (see Pitfall 11).
3. Run backend `pytest` first, because it is cheaper and exposes import/path regressions quickly.
4. For Playwright on Windows, prefer isolated ports and explicit external-server startup.
5. Require UI root `200` before starting browser tests.
6. If Playwright fails with `EPERM`, retry outside the restricted sandbox before concluding the suite is broken.
7. If a single concurrency scenario fails after a long mostly-green run, rerun that one case in isolation before treating it as a deterministic regression.
8. On Linux/CI, if the browser suite fails to boot the API, verify `uvicorn` runs under the project venv before assuming application regressions.

## PostgreSQL, SQLite, and full-suite environment notes

Detailed PostgreSQL provisioning, SQL dialect, full-suite dependency, and
PostgreSQL-aligned UI/UX audit notes have been moved to
[pitfalls-postgres-and-pytest.md](pitfalls-postgres-and-pytest.md).

This includes:

- the PostgreSQL-aligned Windows audit field notes;
- the Windows local-binary, initdb, and throwaway-cluster lessons;
- Linux `policy-rc.d` / cluster-start behavior;
- full-suite dependency and zero-skip environment guidance.
## Additional Playwright invocation and runtime notes

Detailed frontend-package invocation, Playwright project-discovery, local Node
module-resolution, and early runtime-port contention notes have been moved to
[pitfalls-playwright-and-e2e.md](pitfalls-playwright-and-e2e.md).

This includes:

- frontend build and Playwright invocation directory pitfalls;
- local screenshot-script module-resolution notes;
- Pitfall 41 around `ECONNRESET` on default E2E ports.
### Pitfalls 42-46: PostgreSQL and pytest environment semantics

Detailed PostgreSQL SQL, ORM, skip-policy, and pytest bootstrap narratives for
Pitfalls 42-46 have been moved to
[pitfalls-postgres-and-pytest.md](pitfalls-postgres-and-pytest.md).
### Pitfall 47: `GET /api/homework` is not the student homework list — the plural router is `/api/homeworks`

### Symptom

A hazard or E2E test expects **HTTP 422** (or a JSON list) from:

```text
GET /api/homework?page=1&page_size=200
```

but receives **404** or an HTML error page, so pagination validation never runs.

### Context

`apps/backend/courseeval_backend/api/routers/homework.py` registers `APIRouter(prefix="/api/homeworks", ...)`. There is no first-class list route at `/api/homework` in this branch.

### Fix

Use **`/api/homeworks`** for list queries. Re-run `rg "APIRouter\\(prefix=" apps/backend/courseeval_backend/api/routers/homework.py` before freezing URL literals in new tests.

### Interpretation

This is a **test contract bug** (wrong path), not evidence that FastAPI removed validation for oversized `page_size`.

### Pitfall 48: `npm: command not found` blocks Playwright E2E even when pytest is green

### Symptom

```text
npm: command not found
```

when attempting:

```bash
cd <REPO_ROOT>/apps/web/school
npx playwright test e2e-agent-hazard-tier-2-15.spec.js
```

### Context

Cloud CI images optimized for Python may omit Node.js entirely. The repository’s Playwright specs live under `<REPO_ROOT>/tests/e2e/web-school/` but execute via **`apps/web/school/playwright.config.cjs`**, which requires **`npm ci`** / **`npm install`** inside **`apps/web/school`** before **`npx playwright`** exists.

### Fix

**Preferred (portable):** Install a supported **Node.js + npm** from your OS or from **https://nodejs.org** (LTS), then:

```bash
cd <REPO_ROOT>/apps/web/school
npm ci
npx playwright install chromium
```

**Debian/Ubuntu without `nvm` / upstream tarball:** Use distribution packages when the image is Python-first and blocks custom installers:

```bash
sudo apt-get update
sudo apt-get install -y nodejs npm
cd <REPO_ROOT>/apps/web/school
npm ci
npx playwright install chromium
```

On Ubuntu **24.04** this commonly provides **Node 18.x** and **npm 9.x**, which satisfies the admin `package.json` lockfile in this repository. If `npm ci` fails with an engine mismatch, upgrade Node via NodeSource or official binaries — document the failure in CI logs rather than pinning unsupported ranges in `package.json` without maintainer review.

**Playwright backend process:** `playwright.config.cjs` defaults `E2E_PYTHON` to `<REPO_ROOT>/.venv/bin/python` when that path exists; otherwise **`python3`**. If **`uvicorn` is missing** from the system `python3`, either create `.venv` + `pip install -r requirements.txt` or set **`E2E_PYTHON=/path/to/python-with-deps`** explicitly (observed working: **`E2E_PYTHON=/usr/bin/python3`** after `pip install -r requirements.txt` on the same machine).

### Interpretation

**pytest-only CI** can stay green while **Playwright never runs** — track Node availability separately from Python bootstrap (**Pitfall 46**). **`npm: command not found`** is resolved by **any** compliant Node toolchain, including **`apt-get install nodejs npm`** on Debian-derived agents.

### Pitfall 49: Student sidebar label rename broke brittle Playwright text assertions

### Symptom

Playwright fails with strict-mode or timeout when locating sidebar links:

```text
getByRole('link', { name: '我的课程' })
```

### Context

The school SPA (`apps/web/school/src/views/Layout.vue`) grouped student navigation under **`课程学习`** until May 2026; the first child was renamed from **我的课程** to **选课与进度** (route `/courses` unchanged). **Current behavior:** the 「课程学习」 shell was **removed** — student links are **flat** top-level `el-menu-item` rows (same labels/paths as before). Older specs that hard-coded **我的课程** or assumed a parent expand step before **课程通知** will fail.

### Fix

Prefer **`page.goto('/courses')`**, **`enterSeededRequiredCourse`** from `tests/e2e/web-school/fixtures.cjs`, or role selectors anchored on `.elective-catalog-card`. If you must click the sidebar, match **`选课与进度`** / **`课程通知`** as **top-level** `menuitem` names or use stable **`data-testid`** hooks if added later.

### Interpretation

This is usually a **test harness expectation drift**, not a routing regression — verify with `router.beforeEach` guards and direct navigation before rewriting product copy back to the old label.

### Pitfall 50: Notification header badge E2E — disabled course card clicks, hover-only dropdowns, badge/API races

### Symptom

Playwright scenarios around **`data-testid="header-notification-badge"`** time out on **`进入课程|查看课程`** with **`element is not enabled`**, or assertions fail when relying on **duplicate** avatar-dropdown notification entries (removed in favor of **sidebar `课程通知`** — update specs accordingly), or the badge digit **lags** `GET /api/notifications/sync-status` by one poll.

### Context

- **`enterSeededRequiredCourse`** (`tests/e2e/web-school/fixtures.cjs`) clicks the course-card primary button. After a student visits **`/courses`**, the UI may keep that button **disabled** until client enrollment reconciliation catches up — **re-clicking the card is unsafe** for routing-edge specs.
- Element Plus **`hover()`** on **`header-user-menu`** remains timing-sensitive; prefer **`click()`** on triggers when a dropdown must open. Notification routing assertions should use **sidebar** **`getByRole('menuitem', { name: /课程通知/ })`** (student menu) rather than a removed duplicate dropdown row.
- **`Layout.vue`** updates **`headerUnreadCount`** from **`pollNotificationSync`** (route watcher + focus handler). Parallel **`fetch`** writes from the test can advance **`sync-status`** **before** the next **`pollNotificationSync`** completes — **`expect.poll`** pairing badge text with **`sync-status`** avoids flaky strict equality.

### Fix

- For **“return from `/courses` with fresh unread”** scenarios, **`page.goto('/course-home')`** after **`window.dispatchEvent(new Event('focus'))`** rather than calling **`enterSeededRequiredCourse`** twice.
- To verify navigation to **`/notifications`**, use the **sidebar** notification item (see **`e2e-notification-header-sync-tier.spec.js`** case **09**) instead of avatar-dropdown-only flows.
- After multi-step API mutations (two **`POST /api/notifications`**, **`POST .../read`**), use **`expect.poll`** until **`badge digit === sync.unread_count`**.

### Interpretation

These failures showed up while authoring **`tests/e2e/web-school/e2e-notification-header-sync-tier.spec.js`** on a Linux agent with **`npm`** installed via **`apt-get install nodejs npm`** (see **Pitfall 48**). They are **harness timing / selector** issues unless **`sync-status`** itself diverges from list totals — in that case prefer **`tests/behavior/test_notification_sync_api_edge_behavior.py`** to isolate HTTP contracts first.

### Pitfall 51: Teacher dashboard default course may not be the seeded required course

### Symptom

Playwright asserts **`badge digit === sync-status(...?subject_id=<course_required_id>)`** after **`page.goto('/students')`** (historically **`/dashboard`** before the SPA dashboard removal) but the badge stays **0** or matches a **different** subject.

### Context

**`ensureSelectedCourse`** picks **`rankTeachingCourses`** order (semester + id), not necessarily **`E2E必修课_<suffix>`**. **`notificationSyncParams`** uses **`selectedCourse.id`**, so the layout polls **`sync-status`** for whatever course is selected — which may **not** be `course_required_id` from the seed JSON.

### Fix

Before comparing UI to API for **`course_required_id`**, open **`header-course-switch`** with **`click()`** and select the **`.course-option`** row whose **heading text** matches the seeded required course name.

### Interpretation

Documented while authoring **`tests/e2e/web-school/e2e-notification-sync-deep-tier.spec.js`** case **02**.

### Pitfall 52: Full Playwright suite + persistent SQLite — `students.parent_code` UNIQUE collisions on `reset-scenario`

### Symptom

Backend log:

```text
sqlite3.IntegrityError: UNIQUE constraint failed: students.parent_code
```

Playwright / `fixtures.cjs`:

```text
E2E seed failed (500): Internal Server Error
```

Follow-on failures: timeouts on `page.goto`, missing table rows, logins that succeed but show empty shells — **not obviously “notification UI broke”**.

### Context

- School Playwright uses a **file-backed SQLite** URL (see `apps/web/school/playwright.config.cjs`; Unix placeholder pattern like `/tmp/playwright_e2e_<port>.sqlite`).
- **`POST /api/e2e/dev/reset-scenario`** runs in many specs’ **`beforeEach`** hooks.
- `Student.parent_code` is **`unique=True`** in `apps/backend/courseeval_backend/db/models.py`.
- If seed assigns **`parent_code`** from a **small** derived space (historically a short prefix of `suffix`), repeated inserts into the **same** SQLite file across a long full-suite run increase collision probability (“birthday paradox” vs leftover rows).

Short targeted runs often pass because the DB file is young or resets are fewer.

### Fix

- **Product / seed fix (preferred):** derive **`parent_code`** from a high-entropy
  token that still matches the parent SPA input contract. The parent login input
  currently has `maxlength=8`, so the E2E seed handler in
  `apps/backend/courseeval_backend/api/routers/e2e_dev.py` uses
  **`P{suffix[:7].upper()}`** where **`suffix`** is
  **`uuid.uuid4().hex[:10]`**. This keeps the code at exactly 8 characters for
  the browser while retaining enough space for persistent SQLite full-suite
  runs.
- **Operator mitigation (diagnostic only):** delete the Playwright SQLite file at `<E2E_SQLITE>` or change **`E2E_API_PORT`** so a fresh file is used — confirms collision vs logic regression; **do not** rely on this instead of seed entropy in CI.

### Interpretation

See also **§ Key pitfall A** in [FULL_PLAYWRIGHT_E2E_RUNBOOK.md](FULL_PLAYWRIGHT_E2E_RUNBOOK.md).

### Pitfall: parent SPA truncates overlong E2E parent codes before verification

The parent portal login input enforces `maxlength=8`. If the E2E seed returns a
longer `parent_code`, the browser truncates it before calling
`/api/parent/verify/{parent_code}`. API-only tests can still pass because they
send the full code directly, but real parent SPA tests stay on `/login` after
the verify request returns `valid: false`.

Mitigation:

- Keep seeded parent codes exactly 8 characters unless the parent SPA contract
  changes.
- When debugging parent portal login failures, compare the code in
  `scenario.json` with the network request URL, not only the backend seed
  response.
- Run the parent SPA browser spec after changing E2E seed parent-code logic;
  direct API coverage is insufficient for this contract.

### Pitfall: PowerShell splits nested pytest `-k` expressions inside ledger append commands

When appending a test-execution ledger row from Windows PowerShell, a command
string that itself contains a pytest `-k` boolean expression can be split before
`append_run_ledger.py` receives it. For example, trying to pass a literal
command containing:

```powershell
-k "hard61 or hard62 or hard63"
```

can surface as an argparse error from the ledger helper:

```text
append_run_ledger.py: error: unrecognized arguments: or hard62 or hard63 ...
```

This is a shell quoting pitfall in the ledger append step, not evidence that the
observed pytest run failed. Mitigation:

- Prefer recording a selector target command without inline `-k` when that is
  faithful enough for the ledger.
- If the exact observed command matters, append the CSV row through a
  structured CSV writer or a small repo script that receives JSON/stdin instead
  of trying to nest the pytest expression through multiple PowerShell quoting
  layers.
- Do not spend time re-running the already observed pytest target only to work
  around the ledger quoting issue; record the original result and keep the
  quoting failure itself as a pitfall.

### Pitfall 53: Avatar oversized PNG body hits format validation before the 2 MB guard

### Symptom

`tests/backend/user_profile/test_profile_and_avatar.py::test_avatar_oversized_rejected_and_orphan_not_left_on_disk` expects HTTP **400** with **`Avatar image must be 2 MB or smaller`** (English substring **`2 MB`**). Instead the API returns generic attachment validation text such as **`图片文件无法通过校验…`** when the uploaded bytes are not a valid PNG image.

### Context

`/api/auth/me/avatar` ultimately calls **`save_attachment`**, which runs **`assert_attachment_format_compliant`** before persisting. A synthetic **`huge.png`** payload of **`0xFF` repeated bytes** fails PNG validation **before** `upload_my_avatar` can compare **`size > MAX_AVATAR_BYTES`**.

### Fix

In **`apps/backend/courseeval_backend/api/routers/auth.py`**, read the **`UploadFile`** bytes first and reject **`len(content) > MAX_AVATAR_BYTES`** immediately. Pass bytes into **`save_attachment(..., preloaded=content)`** so oversized rejects happen **without** writing to disk and **without** entering format validation for oversize junk payloads.

### Interpretation

This is a **route-ordering** regression guard: size limits for avatars must precede generic attachment sniffing when the upload route shares **`save_attachment`**.

### Pitfall 54: Markdown discussion collapsed preview flattened newlines (tier-3 **`...`** ellipsis specs broke)

### Symptom

Playwright **`e2e-discussion-cover-llm-tier3.spec.js`** expects **`discussion-row__text`** to contain **`...`** when more than three logical lines exist. Instead the UI showed all lines separated by spaces with **no** ellipsis.

### Context

**`collapsedBodyPreview`** in **`CourseDiscussionPanel.vue`** treated non-plain bodies by replacing **`\n`** with spaces before applying only a **240-character** cap. That bypassed **`previewText()` / `lineSegmentsFromBody()`**, which implement the intended **three logical-line** preview model (including counting **`![](...)`** and **`<img>`** as lines).

### Fix

For markdown bodies, when **`isTruncated(body)`** is true, render **`previewText(body)`** (same helper chain as plain text). Keep expanded rows stable by wrapping both collapsed text and **`PlainOrMarkdownBlock`** inside a persistent **`.discussion-row__text`** container so Playwright locators survive expand/collapse.

### Interpretation

Full-suite runs surfaced this because discussion specs execute late and depend on DOM structure + ellipsis semantics staying aligned with **`PREVIEW_LINE_LIMIT`**.

### Pitfall 55: Powerful `/api/e2e/dev/*` routes now expect admin Bearer when `E2E_DEV_REQUIRE_ADMIN_JWT` is true

### Symptom

Playwright or curl calls return **403** with detail mentioning **`administrator Bearer`** when hitting:

- `/api/e2e/dev/mock-llm/configure`
- `/api/e2e/dev/grading-state`
- `/api/e2e/dev/process-grading`
- `/api/e2e/dev/worker`
- `/api/e2e/dev/mark-preset-validated`

even though **`X-E2E-Seed-Token`** is correct.

### Context

The seed token alone proves possession of a shared CI secret; it does **not** prove an interactive admin session. When **`settings.E2E_DEV_REQUIRE_ADMIN_JWT`** is **true**, selected routes require **`Authorization: Bearer <admin JWT>`** in addition to the seed header. **`reset-scenario`** stays seed-only so **`globalSetup`** can run before any login.

Playwright stores the post-reset admin token in **`process.env.E2E_DEV_ADMIN_BEARER`** via **`tests/e2e/web-school/e2e-seed-headers.cjs`** (`refreshE2eAdminBearer`). Specs that duplicate **`seedHeaders()`** locally must either import **`seedHeaders`** from **`e2e-seed-headers.cjs`** or duplicate the merge logic.

### Fix

- Managed Playwright: rely on **`fixtures.cjs`** / **`global-setup.cjs`** (they refresh the bearer after each seed).
- External API without Playwright env: login as seeded **`admin`** from **`scenario.json`** and pass **`Authorization`** with **`POST /api/e2e/dev/*`** calls.
- Opt out only for intentional legacy scripts: **`E2E_DEV_REQUIRE_ADMIN_JWT=false`** on the backend process.

### Interpretation

This pitfall appeared while closing **P0 E2E exposure** findings: misconfigured non-production hosts previously allowed powerful actions with only a static seed header.

### Pitfall 57: Default `SECRET_KEY` placeholder remains valid unless production or `REQUIRE_STRONG_SECRETS`

### Symptom

Operators expect **`SECRET_KEY=change-me-in-production`** to fail fast in **all** environments; instead the app starts when **`APP_ENV`** is not production-style **and** **`REQUIRE_STRONG_SECRETS`** is **false** (the default), because **`reject_weak_secrets_in_production`** only forces strong secrets when **`REQUIRE_STRONG_SECRETS` or production APP_ENV**.

### Context

Changing **`REQUIRE_STRONG_SECRETS`** default to **`true`** breaks **`from apps.backend.courseeval_backend.core.config import settings`** for processes that have **no** `.env` and rely on code defaults — pytest/conftest sets **`SECRET_KEY`** explicitly, but bare **`python -m uvicorn`** without env would crash unless operators create secrets first.

### Fix

Deployments must set **`APP_ENV=production`** (or **`REQUIRE_STRONG_SECRETS=true`**) **and** supply **`SECRET_KEY`** / **`DATABASE_URL`** per **`docs/operations/DEPLOYMENT_AND_OPERATIONS.md`**. Treat **`change-me-in-production`** as invalid anywhere tokens matter.

### Interpretation

This documents **P0 weak-default-key** risk without silently breaking developer **`import settings`** ergonomics.

### Pitfall 56: Attachment download by basename — ambiguous collision returns **400** (not 403)

### Symptom

`GET /api/files/download/<stored_basename>` returns **400** with text about passing **`attachment_url`**, where the same lesson previously returned **403** (“Ambiguous attachment reference…”).

### Context

Multiple logical **`attachment_url`** rows can reference the same on-disk name. Returning **403** misclassified “caller knows basename but DB has multiple logical URLs” as purely forbidden; **400** invites passing the canonical **`attachment_url`** query parameter to disambiguate after ACL checks.

### Fix

Clients that deep-link **`/api/files/download/{name}`** without a query parameter must tolerate **400** when collisions exist; prefer **`GET /api/files/download?attachment_url=...`** (already supported) or pass **`?attachment_url=`** on the basename route.

### Interpretation

**`tests/backend/files/test_files_attachment_download.py`** still expects **200** when the teacher has access and either there is a single matching URL or paths coincide.

### Pitfall 58: `ensure_course_access` raised `ValueError` inside FastAPI routes (500 instead of 404)

### Symptom

Calling course-scoped endpoints with a non-existent **`subject_id`** returned **500 Internal Server Error** because **`ensure_course_access`** calls **`get_course_or_404`**, which raises **`ValueError("Course not found.")`** — uncaught in many routers.

### Context

Only some handlers wrapped **`try/except ValueError`**. Others assumed **`ensure_course_access`** only raised **`PermissionError`**.

### Fix

**`ensure_course_access_http`** (in **`apps/backend/courseeval_backend/domains/courses/access.py`**) now maps **`ValueError`** to HTTP **404** and **`PermissionError`** to **403**. Route modules were migrated to call **`ensure_course_access_http`** instead of **`ensure_course_access`** for HTTP endpoints (**`homework.py`**, **`scores.py`**, **`attendance.py`**, **`dashboard.py`**, **`subjects.py`**, **`llm_settings.py`**, **`files.py`** attachment ACL helper).

### Interpretation

Regression guard: unknown course IDs must never surface as **500** for authenticated callers.

### Pitfall 59: Homework **`class_id`** vs course **`Subject.class_id`** mismatch

### Symptom

Corrupt rows where **`Homework.class_id`** references class A but **`Homework.subject_id`** points at a **`Subject`** owned by class B caused confusing auth: **`ensure_course_access`** could return **404** (“course not in accessible list”) after the user already passed class-level homework checks.

### Context

Multi-column inconsistency is an administrator/data-import defect; students should not see **404** suggesting “wrong roster” when the real issue is inconsistent homework wiring.

### Fix

**`_ensure_homework_access`** compares **`Subject.class_id`** to **`Homework.class_id`** when both are set and returns **403** with an explicit **data integrity** message before calling **`ensure_course_access_http`**.

### Interpretation

Covered by **`tests/backend/homework/test_homework_course_class_integrity.py`** (admin sees integrity **403**; student is blocked **403**).

### Pitfall 60: `POST /api/auth/forgot-password` spam and throttle semantics

### Symptom

Repeated forgot-password requests for the same username flood **`notifications`** rows for administrators; scripted clients can also hammer the endpoint from one IP.

### Context

The endpoint intentionally returns the **same generic message** for missing accounts (anti-enumeration). Throttling must therefore avoid leaking “account exists” via different HTTP codes — skipped work still returns the canonical success body.

### Fix

- **`FORGOT_PASSWORD_USERNAME_COOLDOWN_SECONDS`** (default **600**): suppresses a **new** admin notification if another **`password_reset_request`** notification for the same titled user was created within the window. A **`operation_logs`** row with **`result=cooldown`** records the skip (no notification row).
- **`FORGOT_PASSWORD_MAX_REQUESTS_PER_IP_PER_HOUR`** (default **40**): counts **`operation_logs`** rows with **`action=forgot_password_request`** per IP in the rolling hour; when over budget, skip notification creation and log **`result=rate_limited`**.

Disable by setting **`FORGOT_PASSWORD_USERNAME_COOLDOWN_SECONDS=0`** and/or **`FORGOT_PASSWORD_MAX_REQUESTS_PER_IP_PER_HOUR=0`** (zero disables that gate).

### Interpretation

**`tests/backend/auth/test_forgot_password_flow.py`** still expects the first successful path unchanged; add parallel tests if you tighten defaults further.

### Pitfall 61: Public registration with invented **`class_id`**

### Symptom

With **`ALLOW_PUBLIC_REGISTRATION=true`**, **`POST /api/auth/register`** accepted arbitrary **`class_id`** values, creating student accounts pointing at non-existent **`classes`** rows (orphan **`users.class_id`**).

### Fix

When **`PUBLIC_REGISTRATION_VALIDATE_CLASS_EXISTS`** is **true** (default), **`register`** queries **`classes`** and returns **400** with **`Invalid class_id: class does not exist.`** if missing.

### Interpretation

**`tests/backend/auth/test_public_registration_validation.py`** asserts rejection for a synthetic ID; **`tests/backend/courses/test_student_course_roster_behavior.py::test_public_register_student_then_roster_same_username_gets_enrollments`** still uses a real class from the scenario.

### Pitfall 62: Student LLM quota GET endpoint creating **`CourseLLMConfig`** rows

### Symptom

**`GET /api/llm-settings/courses/student-quota/{subject_id}`** called **`ensure_course_llm_config`**, which inserts **`course_llm_configs`** and may sync template endpoints — an unintended **write** side effect for a read-only quota view.

### Fix

After **`ensure_course_access_http`**, build usage via **`get_student_quota_usage_snapshot(db, None, student_id=..., subject_id=...)`** (extended signature in **`domains/llm/quota.py`**) without initializing course LLM config.

**`GET /api/llm-settings/courses/student-quotas`** no longer calls **`ensure_course_llm_config`** per enrollment row (read-only aggregation).

### Interpretation

Teachers still invoke **`ensure_course_llm_config`** through **`GET/PUT /api/llm-settings/courses/{subject_id}`** when editing LLM settings — that path intentionally creates/configures rows.

### Pitfall 63: Stale `node` / `uvicorn` on default E2E ports after interrupted full run

### Symptom

`npm run test:e2e` aborts before tests start:

```text
Error: http://127.0.0.1:3012/ is already used
Error: http://127.0.0.1:8012/api/health is already used
```

### Context

Playwright `webServer` in **`apps/web/school/playwright.config.cjs`** tries to bind **Vite** and **uvicorn**. A killed CLI may leave the child **`node`** (Vite) or Python server alive; **`fuser`** may be missing in the image.

### Fix

**`lsof -i :<E2E_UI_PORT>`** and **`lsof -i :<E2E_API_PORT>`** then **`kill -9`**, or use **`PLAYWRIGHT_USE_EXTERNAL_SERVERS=1`** and manage processes explicitly.

### Interpretation

This is an **operator / environment** failure, not a test assertion failure. Documented in [FULL_PLAYWRIGHT_E2E_RUNBOOK.md](FULL_PLAYWRIGHT_E2E_RUNBOOK.md) as runbook **Pitfall 63** (mirrors this pitfall number for cross-linking).

### Pitfall 64: `header-course-switch` — hover-based Element Plus dropdown vs Playwright click

### Symptom

**`e2e-notification-header-sync-tier.spec.js`** / **`e2e-notification-sync-deep-tier.spec.js`**: timeout on **`.course-dropdown-menu`** click — “element is not visible / not stable”.

### Context

**`el-dropdown` `trigger="hover"`** + teleported menu: **`hover()` + getByText** on nested **`<strong>`** is fragile; **`scrollIntoViewIfNeeded`** on an animating popper can block until test timeout.

### Fix

**`clickCourseSwitcherOption`** in **`tests/e2e/web-school/future-advanced-coverage-helpers.cjs`**: click **切换课程**, visible **`.course-dropdown-menu`**, **force** click **`.course-option`**.

### Pitfall 65: Mock LLM `discuss_<suffix>` profile cursor drift in full Playwright run

### Symptom

**`e2e-homework-comment-cover-tier4.spec.js`** case **08** — **`expect.poll` on `comment_preview`** never contains **`复`**, value stays **`discuss_<hex>:ok`**.

### Context

**`/api/e2e/dev/mock-llm/<profile>/v1/chat/completions`** advances a **per-profile cursor** in **`e2e_dev.py`**. Other specs (discussion LLM, validation) and ordering can exhaust **`steps`** so the handler falls back to default **`{profile}:ok`**.

### Fix

After the first graded comment is confirmed, **`configureMockLlm`** again with **only** the step intended for the **regrade** attempt.

### Interpretation

Same numbered narrative as **FULL_PLAYWRIGHT_E2E_RUNBOOK.md** sections **Pitfall 64–65** (course switcher vs mock cursor).

### Pitfall 66: Tier-4 chapter reorder — wrong HTTP verb / payload vs tree shape

### Symptom

**`tests/e2e/web-school/e2e-tier4-stress-backlog.spec.js`** case **13**: **`movable.length >= 2`** fails at **1**, or reorder returns **405/422** after fixing counts.

### Context

1. **`GET /api/material-chapters/tree`** returns a **nested** tree. Filtering **`tree.nodes`** only counts **root-level** rows. A single extra **`CourseMaterialChapter`** inserted as a **child** under another chapter still yields **one** movable root sibling alongside **未分类**.
2. Reorder is **`POST /api/material-chapters/reorder?subject_id=...`** with JSON **`{ parent_id: null, ordered_chapter_ids: [...] }`** — not **`PUT`**, and not **`chapter_ids`** (see **`material_chapters.py`**).

### Fix

- Seed **two non-uncategorized root chapters** (`parent_id=None`) for the required course in **`e2e_dev.py`** so **`nodes.filter(!is_uncategorized)`** has **≥ 2** entries at the root.
- Call **`apiPostJson`** with **`ordered_chapter_ids`**, matching the SPA client (**`apps/web/school/src/api/index.js`** → **`reorderChapters`**).

### Interpretation

When authoring chapter reorder specs, align with **`CourseMaterialChapterReorderRequest`** in **`apps/backend/.../schemas.py`** and prefer **`flattenChapterTree`** from **`future-advanced-coverage-helpers.cjs`** if you must include nested chapters.

### Pitfall 67: Responsive E2E — **`boundingBox()`** over huge **`catalog-mobile-item`** lists times out

### Symptom

**`ui-responsive-layout-regression.spec.js`** — **`mobile course cards and catalog cards stay inside a 390px viewport`** exceeds **120s** while **`waiting for locator('.catalog-mobile-item').nth(N)`** with **N** in the hundreds.

### Context

The elective catalog can return **many** rows in smoke databases. **`expectLocatorBoxesWithinViewport`** previously iterated **every** match; each **`boundingBox()`** forces layout work — **O(n)** becomes prohibitive.

### Fix

Cap sampled rows (**first `maxItems`**) and rely on **`expectNoPageHorizontalOverflow`** for the global **`scrollWidth`** invariant.

### Pitfall 68: Users-page **`tbody tr`** + **`batch-set-class`** UI vs accumulated SQLite user rows

### Symptom

**`e2e-scenario-resilience.spec.js`** (`student mid-session class migration`, `stale roster dialog…`) times out on **`expect(tr).toBeVisible`** or on **`batch-class`** dropdown option clicks after many full Playwright runs against the **same file-backed SQLite** (`<E2E_SQLITE>` in **`FULL_PLAYWRIGHT_E2E_RUNBOOK.md`**).

### Context

**`/users`** loads **all** users (`GET /api/users` returns `query.all()`). **`reset-scenario`** does not truncate unrelated historical rows; **local E2E user counts grow**. **`getByRole('row', { name: … })`** on **`el-table`** can also miss when the accessible **name** does not include the username column text.

### Fix

- Prefer **`POST /api/users/batch-set-class`** from the test harness when the scenario only needs **authoritative class migration + enrollment sync**, not **batch-class dialog UX**.
- When asserting presence on **`Users.vue`**, use **`locator('tbody tr').filter({ hasText: username })`** instead of **`getByRole('row', { name: regex })`**.
- **`boundary: admin creates a new student`** now creates via **`POST /api/users`** then verifies the **table row** — avoids **`el-select`** teleport edge cases under heavy lists.

### Pitfall 69: E2E assertions vs **`prepare_student_course_context`** and inconsistent **`page_size`** caps across routers

### Symptom

Authoring **`tests/e2e/web-school/e2e-docs-gap-tier15.spec.js`** (or similar API-heavy specs):

1. **`student_b`** “not enrolled in required course” — **`GET /api/homeworks/{id}/submission/me`** unexpectedly returns **200** because **`prepare_student_course_context`** + **`sync_student_course_enrollments`** auto-create **`CourseEnrollment`** for **all** students in the class when the required-course sync runs — **待人工确认** whether treating every roster student as implicitly enrolled is intended product-wise.

2. Cross-class homework submission expectation **`404`** from **`_resolve_student_for_user`** sometimes yields **`403`** instead because **`_ensure_homework_access`** runs **`ensure_course_access_http`** first; students enrolled only elsewhere hit **`PermissionError`** (**403**) before roster mismatch (**404**).

3. **`GET /api/scores/appeals`** has **no `page_size` query parameter** — FastAPI ignores unknown query keys; **`page_size=5000`** returns **200** with the router's fixed **`limit(200)`** behavior. Tests that expect **422** from oversized **`page_size`** must target a route that actually declares **`Query(..., le=...)`** (for example **`GET /api/students`** uses **`le=1000`**).

4. Same-class students may **`GET /api/points/students/{other_student_id}`** without **403** when both share a **`class_id`** — privacy expectations must not assume “student cannot read peer points” unless product explicitly forbids it (**待人工确认**).

### Fix

- Prefer **explicit cross-class homework rows** (admin-created **`Homework`** with **`class_id`** / **`subject_id`** pointing at **`course_other_teacher_id`** + **`class_id_2`**) when testing “wrong class” submission denial.
- Accept **`[403, 404]`** where course-access vs roster-order differs.
- Validate pagination bounds only against routers that validate **`page_size`** in **`Query`** — grep **`apps/backend/courseeval_backend/api/routers/*.py`** before writing **`422`** expectations.

### Interpretation

Documentation that says “enrollment must exist” should mention **class-wide required-course sync** on student requests, or new readers (and agents) will mis-design tests and false-positive “bugs”.

### Pitfall 70: **`ElMessageBox.confirm`** vs **`el-dialog`** — wrong overlay target after long SQLite runs

### Symptom

**`tests/e2e/web-school/e2e-pitfall-guard-rails.spec.js`** case **01**, **`e2e-scenario-boundary-dynamic-complex.spec.js`** delete path, **`future-advanced-coverage.spec.js`** case **3**, **`e2e-scenario-resilience.spec.js`** batch-class paths:

- `waitForResponse` on **`DELETE /api/subjects/:id`** times out,
- or `getByRole('dialog').filter({ has: button OK })` clicks the **wrong** overlay,
- or Playwright waits until **test timeout** (~300s) while the **MessageBox** never receives the intended click.

### Context

Element Plus **`ElMessageBox.confirm`** renders a **teleported** small modal with class **`el-message-box`**, not the same accessibility tree as large **`el-dialog`** course forms. After hundreds of seeds, **multiple** hidden `.el-select-dropdown` nodes and **stacked** overlays can exist; targeting **“last dialog”** is ambiguous.

### Fix

Use a **MessageBox-scoped** primary button:

- helper **`confirmElMessageBoxPrimary`** in **`tests/e2e/web-school/future-advanced-coverage-helpers.cjs`** — waits for **`.el-message-box`** then clicks **`.el-message-box__btns .el-button--primary`**.

### Interpretation

Do not assert delete flows by title **`删除课程`** alone — pair **network** assertions with the **MessageBox** button actually wired to **`ElMessageBox.confirm`**.

### Pitfall 71: **`el-select-dropdown`** — many nodes stay **`hidden`** in DOM; prefer **visible** scoping

### Symptom

**`e2e-scenario-boundary-dynamic-complex.spec.js`** — `clickSelectOptionByLabel` waits forever on **`.el-select-dropdown.last()`** where the last node is **always hidden** (teleported popper retain).

### Fix

Use **`.filter({ visible: true })`**, wait for **visible** popper after opening the trigger, or **avoid UI selects entirely** for setup — e.g. **`POST /api/subjects`** with **`SubjectCreate`** for course rows when the test goal is **delete / list consistency**, not **form layout**.

### Pitfall 72: Roster-enroll UI assumes **`student_b`** is **not** already in the required course

### Symptom

**`roster-and-users.spec.js`** — checkbox stays disabled / no **`POST .../roster-enroll`**.

### Context

**`sync_course_enrollments`** (bootstrap + course writes) can enroll **all** class roster students into **required** courses. **`student_b`** is often already **`已在课`**, and **`el-table`** selection is **`selectable: row => !row._enrolled`**.

### Fix

Before opening **从花名册进课**, **`DELETE /api/subjects/{course_required_id}/students/{student_row_id}`** as admin (ignore **404**) so the row returns to **未在课** for the UI assertion.

### Pitfall 73: **Batch调班** — enable **`users-open-batch-class`** before open; optional filter on **`filterable`** `el-select`

### Symptom

**`dialog-batch-class`** never appears — **`users-open-batch-class`** stays disabled because **no row selected** in a huge **`/users`** table.

### Fix

**`scrollIntoViewIfNeeded`** on the **`tr`**, then **`expect(users-open-batch-class).toBeEnabled`**, then open dialog; pick target class via **visible** dropdown + **`getByRole('option')`** (filter input is **optional** — may not exist in all EP builds).

### Pitfall 74: `npm run build` in `apps/web/school` can fail with `vite: not found` on fresh agents

### Symptom

```text
> courseeval-school@1.0.0 build
> vite build

sh: 1: vite: not found
```

### Context

The repository stores the school SPA lockfile under **`<REPO_ROOT>/apps/web/school/package-lock.json`**, but fresh cloud agents and Python-first CI images often start with **no `node_modules/` directory**. In that state, `npm run build` launches the package script correctly but fails because the local Vite binary from `devDependencies` is missing.

This surfaced during a discussion-editor repair pass: the code change itself was valid, but the first build failed before Vite executed.

### Fix

From **`<REPO_ROOT>/apps/web/school`**:

```bash
npm ci
npm run build
```

If the image lacks Node/npm entirely, first read **Pitfall 48**. Do **not** treat `vite: not found` as evidence that the Vite config or source imports are broken.

### Interpretation

This is **frontend dependency bootstrap debt**, not a product regression in the edited Vue files.

### Pitfall 75: Playwright browsers may be missing even after `npm ci`

### Symptom

```text
browserType.launch: Executable doesn't exist at .../chromium_headless_shell-.../chrome-headless-shell
Looks like Playwright was just installed or updated.
Please run: npx playwright install
```

### Context

Installing **`@playwright/test`** via `npm ci` provides the runner but **not necessarily the browser binaries**. On blank Linux agents, the first targeted E2E may therefore fail only after the managed backend and Vite startup have already succeeded, which can mislead operators into suspecting the app boot sequence.

### Fix

From **`<REPO_ROOT>/apps/web/school`**:

```bash
npx playwright install chromium
npx playwright test <spec> --project=chromium
```

If disk budgets or custom browser caches matter, also align `PLAYWRIGHT_BROWSERS_PATH` with your runner policy.

### Interpretation

This is **browser-runtime bootstrap debt**. When the error explicitly says the executable does not exist, do not debug selectors, routes, or API startup first.

### Pitfall 76: Discussion Markdown demo is intentionally collapsed by default; target preview or click the toggle first

### Symptom

Older Playwright expectations fail after opening a discussion composer:

```text
expect(getByTestId('markdown-latex-demo-render')).toBeVisible()
Received: 0 matching elements
```

or the test verifies a posted short Markdown reply and sees raw source / plain text instead of a rendered `.katex` node because it was written against the pre-fix DOM behavior.

### Context

`CourseDiscussionPanel.vue` changed in May 2026 so the long fixed example is **hidden behind** **`查看 Markdown + LaTeX 示例`** until the user asks for it. At the same time, Markdown authoring gained a dedicated **`discussion-markdown-preview`** live preview region, and short published rows now render through `PlainOrMarkdownBlock` immediately instead of waiting for an expand action that short rows never expose.

### Fix

- For the example card, assert the **toggle button** first, then click it before expecting **`markdown-latex-demo-render`**.
- For authoring feedback, assert **`data-testid="discussion-markdown-preview"`** (for example, wait for `.katex` inside it after typing).
- For published output, scope to the specific **`.discussion-row`** and assert a rendered `.katex` node on short Markdown posts.

Reference regression guard:

- `tests/e2e/web-school/e2e-course-ui-markdown-reader.spec.js`
  - `material detail discussion keeps demo collapsed by default, shows live preview, and renders posted KaTeX`

### Interpretation

This is mostly **test expectation drift** caused by a deliberate UX change, not a regression in the discussion feature.

### Pitfall 77: wrapper-based dual-scroll refactors can leave Vue templates with a missing closing tag

### Symptom

`npm run build` fails quickly with a Vue SFC parse error such as:

```text
[vite:vue] src/views/Attendance.vue (...): Element is missing end tag.
```

### Context

This surfaced while adding a synchronized **top horizontal scrollbar** above an
existing bottom-only wide-surface scroll area. The affected page
(`apps/web/school/src/views/Attendance.vue`) already had:

```text
<div class="sheet-scroll">
  <div class="attendance-grid">...</div>
</div>
```

Wrapping that block in a new `DualHorizontalScroll` component introduced one more
container level. During the first edit, the explicit `.sheet-scroll` closing
`</div>` was accidentally dropped, so the SFC parser reached `</DualHorizontalScroll>`
while one inner `div` was still open.

### Fix

When wrapping an existing wide table/grid in a new scroll shell:

1. count the original container boundaries first;
2. preserve the **existing real scroll target** (`.sheet-scroll`, `.table-wrapper`,
   etc.);
3. add the wrapper **around** that target rather than half-replacing it;
4. run `npm run build` immediately after the structural edit.

For the specific attendance failure, restoring the missing `</div>` for
`.sheet-scroll` resolved the build.

### Interpretation

This is a **template-structure regression** introduced during refactor, not a
runtime bug in the scrolling logic itself. Build-first validation is the fastest
way to catch it.

### Pitfall 78: Student login flows can trip ORM state expiry if post-login code reads `user.role` after logging commits

### Symptom

A targeted student registration/login test fails inside `/api/auth/login` with a stack resembling:

```text
DetachedInstanceError / expired scalar load on User
```

or a loader trace triggered at the branch that decides whether to run
student-specific post-login context repair.

### Context

`auth.py::login` historically did:

1. query `user`,
2. build the JWT,
3. call `LogService.log_login(...)`,
4. **then** branch on `user.role` / `user.class_id`.

`LogService.log_login` commits the shared session. On some student-login test
paths, that commit can expire the ORM instance before the later role/class read,
turning a normal student login into a session-state failure unrelated to
credentials or quota logic.

### Fix

Cache the values needed for post-login branching **before** calling the logging
helper, or re-query the `User` row by id after the logging commit before calling
student-only repair such as `prepare_student_course_context(...)`.

This repository now follows that rule in `apps/backend/courseeval_backend/api/routers/auth.py`.

### Interpretation

This is a **session-lifecycle pitfall** in route implementation, not evidence
that public registration or student quota binding itself is broken.

### Pitfall 79: Some legacy pytest modules are fragile when `main.py` is imported at module load before DB reset helpers

### Symptom

A narrowly targeted pytest invocation against one module can fail during
collection or fixture setup with errors such as:

```text
table users already exists
no such table: llm_endpoint_presets
no such table: course_llm_configs
```

### Context

Certain older backend test modules import `apps.backend.courseeval_backend.main`
at module load time. In this repository, `main.py` still calls:

```text
Base.metadata.create_all(bind=engine)
```

when `APP_ENV != production`.

If that import happens before the test's own reset helper has re-established the
expected schema lifecycle, isolated single-module runs can observe a different
DDL order from the steady-state suite and surface "already exists" or "missing
table" errors that are really test-harness sequencing issues.

### Fix

- Prefer client fixtures that import `main.app` **inside** the fixture after the
  module's reset/autouse setup has run.
- For new focused regression files, reuse the shared `tests.db_reset.reset_test_database_schema()`
  pattern and avoid extra module-level side effects when a local fixture can
  import the app lazily.
- When triaging a new single-file failure, separate:
  1. business-logic regression,
  2. ORM/session bug,
  3. test harness import/DDL ordering.

### Interpretation

This is a **test authoring / collection-order pitfall**. Do not infer a product
schema regression solely from these errors until you confirm the module's import
order and reset strategy.

### Pitfall 80: Isolated admin-discussion smoke tests can be noisier than teacher-path tests under legacy helper / session setup

### Symptom

A narrowly scoped behavior test that:

1. creates a course/student scenario,
2. calls `ensure_admin()`,
3. logs in as `pytest_admin`,
4. then exercises `/api/discussions` with `invoke_llm=true`

can fail inside the **login logging** path with an `IntegrityError` around
`operation_logs.user_id` rather than around the actual discussion feature.

### Context

This showed up during a discussion-LLM permission expansion pass. The product
change itself was "teachers/admins may invoke discussion LLM", but one isolated
admin API smoke path was less stable than:

- the teacher-path route regression, and
- the lower-level helper regression proving that admin is part of the
  quota-exempt role set.

The likely cause cluster is legacy helper/session/test-app lifecycle interaction,
not the discussion serializer or route guard directly.

### Fix

When a new admin discussion regression becomes noisy under isolated SQLite test
setup:

- keep one stable **teacher route** regression for `invoke_llm=true` acceptance;
- keep a focused **helper-level** regression for the admin quota-exempt role
  decision;
- if an admin route assertion is still required, build the admin user inside the
  same fixture/app lifecycle as the target scenario instead of depending on a
  broader shared helper whose session timing may differ.

### Interpretation

This is primarily a **test-harness stability** issue. It should not, by itself,
be read as evidence that admin discussion-LLM permission is broken once the
teacher route and quota-exempt helper regressions are green.

### Pitfall 81: PowerShell `python` may be system Python without pytest even when repo `.venv` exists

### Symptom

Running a focused pytest command from the repository root fails immediately:

```text
<system-python>: No module named pytest
```

### Context

On Windows, `python` can resolve to a system interpreter even when the repository has a populated `.venv`. This surfaced while adding the learning-note / attendance-cover test tier: `python -m pytest tests/backend/learning_notes/test_learning_notes_api.py -q` failed before collection, while `<repo>/.venv/Scripts/python.exe -m pytest ...` ran the target module successfully.

### Fix

Use the repository virtualenv explicitly for targeted backend validation:

```powershell
<repo>\.venv\Scripts\python.exe -m pytest tests\backend\learning_notes\test_learning_notes_api.py -q
```

Do not rewrite imports or pytest configuration to fix a missing `pytest` package on the wrong interpreter. This is the Windows-specific variant of Pitfall 46.

### Pitfall 82: Learning-note copied resources and chapters require `model_fields_set` to distinguish omitted vs explicit `null`

### Symptom

Tests or UI flows that try to freely edit a copied learning note cannot detach a resource from a copied chapter or promote a copied child chapter back to the note root. Payloads like these appear accepted but do not change the relationship:

```json
{ "chapter_id": null }
{ "parent_id": null }
{ "attachment_url": null }
```

### Cause

The first implementation used `if payload.chapter_id is not None` / `if payload.parent_id is not None` / `if payload.attachment_url is not None`. That pattern treats an explicitly supplied JSON `null` exactly like an omitted field, so owner edits cannot clear nullable relationships or attachment references.

### Fix

Use Pydantic v2 `payload.model_fields_set` for nullable update fields:

```text
if "chapter_id" in payload.model_fields_set: ...
if "parent_id" in payload.model_fields_set: ...
if "attachment_url" in payload.model_fields_set: ...
```

Regression coverage:

- `tests/backend/learning_notes/test_learning_notes_api.py`
- `tests/e2e/web-school/e2e-learning-notes-attendance-cover-tier20.spec.js`

### Pitfall 83: Attendance single-create and date filters must parse `YYYY-MM-DD`, not pass raw strings to SQLite `DateTime`

### Symptom

`POST /api/attendance` returns **500** on SQLite when the request body uses the same date format emitted by the attendance page date picker / teaching-calendar flow:

```json
{ "date": "2026-05-07" }
```

The backend stack includes:

```text
SQLite DateTime type only accepts Python datetime and date objects as input.
```

A follow-up list request with `start_date=2026-05-07&end_date=2026-05-07` can also return **422** if the route parameters are typed as `datetime` directly, because Pydantic expects a datetime separator.

### Cause

Batch attendance routes already parsed incoming date strings before insert, but the single-create route wrote the raw Pydantic string into the ORM model. List/statistics filters also let FastAPI parse query dates as `datetime`, which rejects date-only values that the UI naturally sends.

### Fix

Centralize attendance date parsing in the router:

- single-create converts `YYYY-MM-DD` or ISO datetime strings to `datetime` before querying/inserting;
- list/class-stat/student-stat query boundaries accept string params and normalize date-only values to start/end of day;
- invalid date strings return **400** instead of leaking database exceptions.

Regression coverage:

- `tests/backend/learning_notes/test_learning_notes_api.py::test_ln11_attendance_single_create_parses_iso_date_string_for_sqlite`
- `tests/e2e/web-school/e2e-learning-notes-attendance-cover-tier20.spec.js` case 20

### Pitfall 84: Course-cover E2E should assert the enrolled course card, not assume catalog thumbnail placement

### Symptom

After setting `subjects.cover_image_url`, an E2E assertion for `data-testid="course-catalog-cover-thumb"` times out, while the active enrolled course card correctly renders `data-testid="course-card-cover"`.

### Context

`MyCourses.vue` renders two different student surfaces:

- the schoolwide catalog table (`course-catalog-cover-thumb`);
- the student's active/completed course cards (`course-card-cover`).

Depending on current catalog filters, enrollment state, table virtualization, and route timing, a test that only wants to verify "students can see a selected course's cover" should target the active course card for the seeded course.

### Fix

Scope the locator to the exact `article.course-card` whose heading is the seeded course title, then assert `course-card-cover` inside that card. Keep separate catalog-thumbnail tests for catalog-specific behavior if that surface is the product target.

### Pitfall 85: Multi-class notification E2E must link the course before publishing second-class broadcasts

Symptom:

```text
POST /api/notifications failed 403: You can only publish notifications for accessible classes.
```

Context:

The notification header deep-tier tests intentionally exercise a required
course that spans two administrative classes. A normal teacher is allowed to
publish a class broadcast for another class only after the course has a
`subject_class_links` row for that class. Merely choosing `class_id_2` from the
seed scenario does not make the class accessible for course notification
publishing.

Fix:

Before publishing a `subject_id = null` broadcast to the second class in a
multi-class notification E2E, update the course with both class links, for
example through `PUT /api/subjects/{course_id}` with:

```json
{
  "class_links": [
    { "class_id": "<class_id_1>", "enrollment_mode": "all_in_class" },
    { "class_id": "<class_id_2>", "enrollment_mode": "all_in_class" }
  ]
}
```

Then publish the second-class broadcast and assert student/class-teacher
visibility separately from assigned-teacher/admin visibility.

Interpretation:

This is a test setup pitfall. A 403 before linking the course is expected
authorization behavior, not evidence that notification visibility or the header
badge regressed.

### Pitfall 86: Header course-switcher tests should use API-returned course names

Symptom:

Playwright cannot find the intended `.course-option` even though the course is
visible in the selector menu. The failed selector may show a mojibake-looking
Chinese course label copied from terminal output.

Context:

Windows PowerShell can display valid UTF-8 Chinese as mojibake. If a test
hard-codes a rendered terminal label such as a seeded course name, the locator
literal can diverge from the actual browser DOM text.

Fix:

When a Playwright test needs to select a seeded course in
`header-course-switch`, obtain the current course name from `GET /api/subjects`
using the same role token, then pass that exact string to the course-switcher
helper. Avoid copying multilingual labels from shell output into selectors.

Interpretation:

This is a selector-authoring and encoding pitfall, not a product routing
regression. Keep the API-derived name pattern for future course-switcher tests,
especially around notification badge convergence.

### Pitfall: system-wide student quota totals are repeated on course attribution rows

Symptom:

```text
assert used_b1 == used_b0
E       assert 10 == 0
```

Context:

A behavior test submitted homework in course A, then read the
`/api/llm-settings/courses/student-quotas` summary and expected the course B row
to keep `student_used_tokens_today` unchanged.

Cause:

After quota consolidation, `student_used_tokens_today` is the student's
system-wide daily LLM usage total. It is intentionally repeated on every course
row so each row can show the same daily pool context. The per-course field is
`course_used_tokens_today`; that field is the attribution value that should stay
unchanged for a course that did not receive new usage.

Fix:

When testing the post-consolidation model, assert both sides explicitly:

```text
course A row student_used_tokens_today == course B row student_used_tokens_today
course A row course_used_tokens_today increased
course B row course_used_tokens_today did not change
```

Interpretation:

This failure is not evidence that course attribution broke. It is evidence that
the old per-course-pool mental model leaked into a test assertion.

### Pitfall: Element Plus switch test id may be on the wrapper, not the role element

Symptom:

```text
expect(locator).toHaveAttribute("aria-checked", "false")
Received: ""
locator resolved to <div class="el-switch" data-testid="...">...</div>
```

Cause:

Element Plus can render the `data-testid` on the switch wrapper while the
actual accessible switch state lives on the nested element with `role="switch"`.
The wrapper is useful for clicking, but it may not carry `aria-checked`.

Fix:

Click the stable test id if that is the most convenient target, then assert on
the role locator inside the same dialog or component:

```text
const enableSwitch = dialog.getByRole('switch')
await page.getByTestId('llm-course-enable').click()
await expect(enableSwitch).toHaveAttribute('aria-checked', 'false')
```

Interpretation:

This is a selector issue in the test, not evidence that the UI failed to toggle.

### Pitfall: parallel Playwright commands can reset local E2E backend fetches

Symptom:

```text
TypeError: fetch failed
[cause]: Error: read ECONNRESET
```

Another observed symptom when the commands are the repository external runner
instead of raw Playwright:

```text
Port 3012 is in use, trying another one...
page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:3012/login
sqlite3.OperationalError: database is locked
```

Context:

Two separate Playwright CLI commands were started at the same time from
`<repo>/apps/web/school`, both using the default school Playwright config or both
using `node scripts/playwright-external-runner.cjs`.

Relevant config shape:

```text
E2E_API_PORT defaults to 8012
E2E_UI_PORT defaults to 3012
DATABASE_URL defaults to a temp SQLite file keyed by E2E_API_PORT
webServer starts FastAPI at http://127.0.0.1:8012
webServer starts Vite at http://127.0.0.1:3012
```

Cause:

The two CLI processes share the same default local ports and temp SQLite file.
One process can reset/restart/tear down the backend while the other process is
performing a Node-side `fetch(...)` against the local API. The resulting error
is a local backend/webServer connection reset. It is not evidence of Codex
platform high demand, and it is not evidence that a real external LLM provider
was called.

With the external runner, Vite may notice that the default UI port is occupied
and auto-bind to the next available port. The test process can still be
configured with `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3012`, so page navigation
then fails against the original port even though Vite printed a usable
`http://127.0.0.1:3013/` URL. A second runner can also collide with the same
SQLite database during FastAPI startup / schema repair, surfacing as
`database is locked`. Treat both as the same orchestration class: two local E2E
owners are trying to manage one default environment.

How to identify the target:

For the school Playwright config, helper `apiBase()` resolves to:

```text
http://127.0.0.1:<E2E_API_PORT>
```

The affected LLM hard-scenario tests create presets with mock base URLs such as:

```text
http://127.0.0.1:<E2E_API_PORT>/api/e2e/dev/mock-llm/<profile>/v1/
```

Therefore a `fetch failed` in those helpers should first be investigated as a
local backend/webServer issue unless the stack trace or preset data shows a
non-localhost URL.

Fix:

Prefer one Playwright CLI process at a time when using the default local
webServer config. If parallel CLI processes are required, give each process its
own ports and isolated database, for example:

```text
E2E_API_PORT=8013 E2E_UI_PORT=3013 npx playwright test ...
E2E_API_PORT=8014 E2E_UI_PORT=3014 npx playwright test ...
```

On Windows PowerShell use separate `$env:` assignments in the same command
session before invoking Playwright. Keep `NO_PROXY=localhost,127.0.0.1,::1` when
a local HTTP proxy is configured so localhost E2E traffic does not leave the
machine.

For `npm.cmd run test:e2e:external -- ...`, do not launch two such commands in
parallel on the default ports. Run targeted specs serially, or explicitly export
a distinct `E2E_API_PORT`, `E2E_UI_PORT`, and database path for each runner
process if parallelism is truly required.

Interpretation:

If the same test passes when rerun serially with the same code and local mock
LLM endpoint, treat the earlier `ECONNRESET` as local E2E orchestration
contention rather than product behavior. The same interpretation applies to
the `3012` refused / `database is locked` pair after a parallel external-runner
attempt.

### Pitfall: outbound dependency commands may need the local VPN proxy

On this workstation, outbound dependency and repository commands can fail even
when the network is usable through the local VPN proxy. Typical affected
commands include:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd install
npx.cmd playwright install chromium
git fetch
```

Observed symptoms include socket permission errors, DNS/connection failures, or
package managers reporting no matching package versions because they could not
reach the index. Before recording the environment as offline, retry with the
local HTTP proxy:

```powershell
$env:HTTP_PROXY='http://127.0.0.1:7897'
$env:HTTPS_PROXY='http://127.0.0.1:7897'
$env:ALL_PROXY='http://127.0.0.1:7897'
$env:NO_PROXY='localhost,127.0.0.1,::1'
```

For npm, prefer environment variables first; if the process still ignores them,
use a one-command scoped config rather than writing global npm state:

```powershell
npm.cmd --proxy=http://127.0.0.1:7897 --https-proxy=http://127.0.0.1:7897 install
```

Interpretation:

- `NO_PROXY` is mandatory for local Playwright/FastAPI/Vite/PostgreSQL traffic;
- do not commit machine-specific proxy logs or user-profile paths;
- local helper tools used to make these retries work, such as copied RAR
  extractors, local PostgreSQL binaries, virtualenvs, browser caches, and
  generated logs, must stay under ignored paths such as `.agent-run/`,
  `.e2e-run/`, `.venv/`, or `node_modules/`;
- ignored local bootstrap scripts under `.agent-run/` may set this proxy by
  default for this workstation;
- if the proxy retry also fails, record both attempts and the exact failure mode
  before treating the command as blocked.

- It does not claim the product code is bug-free.
- It does not claim all Windows environments need the exact same workarounds.
- It does not claim the sandbox restrictions seen here will match CI or a developer's normal terminal.
- It does not claim Linux agents exhibit only the Linux-specific pitfalls above; many Windows pitfalls (ports, readiness, flake in long suites) still apply cross-platform.

It records what actually happened during validation sessions (starting with the May 1, 2026 Windows-focused pass, extended by later Linux/CI observations) so the next operator can start from firmer ground.

## Demo seed and `DEFAULT_LLM_API_KEY` bootstrap (pytest / cloud agents, 2026-05)

### Symptom

After tightening `_ensure_default_llm_endpoint_preset()` so empty `DEFAULT_LLM_API_KEY` installs create a **pending** preset instead of a falsely `validated` row, `tests/backend/e2e_dev/test_demo_course_seed.py::test_demo_seed_creates_teacher_students_course_homework` initially failed with `CourseLLMConfigEndpoint` count `0` for the demo required course.

### Cause

`domains/seed/demo.py::_first_validated_preset_for_demo_course` originally returned only presets that were already **validated and active**. Local pytest databases produced via `ensure_schema_updates()` therefore had **no** eligible preset whenever outbound LLM validation was impossible (no API key, sandbox network blocked), so `_ensure_demo_subject_llm_binding` skipped inserting endpoints even though a bootstrap preset row existed.

### Fix pattern (implemented in product code)

The demo helper now **falls back** to the bootstrap preset named `"gpt-5.4"` even when it is still `pending`, documenting that automatic grading remains unreliable until an operator validates or supplies credentials. This restores deterministic pytest expectations while preserving honest validation semantics for keyed deployments.

### Operational note

When running integration tests that **do** set `DEFAULT_LLM_API_KEY` against a real vendor, expect startup latency and possible failures if the remote API blocks the runner egress (`<repository-root>/.venv/bin/python` path placeholder). Prefer mocking vendor HTTP for CI instead of live keys.

### Secondary pitfall observed during the same change set

While validating `tests/backend/homework/test_markdown_homework_visibility_and_llm.py`, the environment initially lacked project dependencies (`ModuleNotFoundError: pydantic_settings`). Resolution path: install from `<repository-root>/requirements.txt` using the repository virtualenv interpreter, not the bare system `python3`.

## Homework effective-score aggregates + intentional clock surgery (pytest, 2026-05)

### Symptom

While authoring `tests/backend/homework/test_effective_homework_score_aggregate.py`, an integration scenario needed one attempt visibly on-time and another late with ``counts_toward_final_score=false``, yet both submissions originate through `POST /api/homeworks/{id}/submission`, which timestamps attempts at request handling time.

### Cause

HTTP submission logic derives lateness from wall-clock `submitted_at` compared to `homework.due_date`. Pure API sequencing cannot fabricate a chronology where attempt two is materially late while keeping deterministic grading mocks unless ORM rows are adjusted after inserts.

### Fix pattern used in tests

The scenario commits explicit SQLAlchemy updates on `HomeworkAttempt.submitted_at`, `HomeworkAttempt.is_late`, and `HomeworkAttempt.counts_toward_final_score` after each mocked grading cycle so eligibility mirrors classroom expectations without a time-traveling HTTP client.

### Interpretation for agents

When extending homework lifecycle tests, prefer surgical row mutation over rewriting routers; altering `_is_late_attempt` solely for tests would poison production semantics.

## Persistent pytest SQLite file + metadata registration (`tests/conftest.py`, 2026-05)

### Symptom

Pytest runs fail early inside `apps.backend.courseeval_backend.bootstrap.ensure_schema_updates()` with `sqlite3.OperationalError: no such table: course_llm_configs` (or other core tables) immediately after `tests.db_reset.reset_test_database_schema()` reports success.

Alternatively, mass `UNIQUE constraint failed: users.username` errors appear when executing many tests sequentially against the default file-backed SQLite URL.

### Contributing factors (non-exhaustive)

1. **Shared database file:** `tests/conftest.py` defaults to `sqlite:///<repo>/.pytest_tmp/test.sqlite` when Postgres test URLs are not configured. Interrupted runs can leave the file half-migrated.
2. **SQLAlchemy metadata registration timing:** `Base.metadata.create_all()` only creates tables for mapped classes that were **imported** before `create_all` runs. Most tests import `main` or models early, but exotic collection orders or utility-only imports could historically skip mappings.
3. **Parallel pytest without isolated `TEST_DATABASE_URL`:** multiple processes writing one sqlite file guarantees corruption-like failures.

### Product-side mitigation (implemented in `tests/db_reset.py`, 2026-05)

`reset_test_database_schema()` now imports `apps.backend.courseeval_backend.db.models` **before** `metadata.drop_all` / `create_all`, guaranteeing mapper registration even when a test file only imported `db.database` + `main` without touching ORM classes directly. This removes the systematic `no such table: course_llm_configs` failure mode during `ensure_schema_updates()` on cold SQLite schemas.

Corrupted shared sqlite files and parallel writers remain hazards — keep the deletion playbook below.

### Mitigation playbook

1. Run `python ops/scripts/dev/pytest_sqlite_guard.py` from the repository root.
   The command is read-only; it reports active pytest processes and the shared
   SQLite file state without deleting anything.
2. Stop all pytest processes touching the repo if the guardrail reports
   `status=warn`.
3. Delete `<repository-root>/.pytest_tmp/test.sqlite` (path placeholder: adjust if `PYTEST_DEBUG_TEMPROOT` overrides temp behavior on Windows).
4. Re-run a **single** failing test file with `python3 -m pytest path/to/test.py -q`.
5. If failures persist, force Postgres throwaway DB via `TEST_DATABASE_URL` (see `ops/scripts/dev/provision_postgres_pytest.sh` mention in `tests/conftest.py`).

### Evidence note

A minimal control script that imports `apps.backend.courseeval_backend.db.models` before `create_all` succeeded on a fresh sqlite path.

## Demo seed strings containing LaTeX (`domains/seed/demo.py`, pytest / agents, 2026-05)

### Symptom

While adding the **初等概率论** elective bundle, early drafts stored teacher-only rubrics or reference answers in plain triple-quoted Python strings containing fragments like `\frac{...}{...}` or `\times`. Runtime strings showed corrupted LaTeX (missing backslashes, unexpected tabs) or `SyntaxError` / deprecation warnings depending on Python version.

### Cause

Standard Python string literals treat `\f` as a form-feed escape, `\t` as tab, and similar sequences eat backslashes needed for LaTeX. Multiline **non-raw** strings also mishandle `\Omega`-style sequences when authors forget to double-escape.

### Fix pattern

- Prefer **`r"""..."""` raw triple-quoted strings** for any demo copy meant to include LaTeX backslashes handed to Markdown/KaTeX clients.
- For prefilled student markdown bodies that need real paragraph breaks, use multiline raw triple quotes in the source file instead of embedding the two-character sequence `\` + `n` inside a one-line `r"..."` literal (those store a literal backslash-n, not a newline).

### Interpretation for agents

Treat `domains/seed/demo.py` as **data-heavy**: run `python3 -m py_compile apps/backend/courseeval_backend/domains/seed/demo.py` after edits and inspect a seeded row in SQLite/Postgres if unsure whether content round-tripped correctly.

## Linux agent: PostgreSQL apt install vs systemd-less containers (`policy-rc.d`, 2026-05)

### Symptom

After `apt-get install postgresql`, `pg_isready` still fails and `tests/postgres/*` remain skipped even when `provision_postgres_pytest.sh` succeeds at SQL provisioning time — or apt prints `invoke-rc.d: policy-rc.d denied execution of start`.

### Cause

Minimal CI/agent images ship `policy-rc.d` hooks that **block** maintainer scripts from auto-starting services. PostgreSQL files exist but the daemon never listens on `5432`.

### Fix pattern

```bash
sudo pg_ctlcluster 16 main start   # substitute cluster version from `pg_lsclusters`
pg_isready -h 127.0.0.1 -p 5432
```

Then run `bash ops/scripts/dev/provision_postgres_pytest.sh` (requires `sudo -u postgres psql`).

### Interpretation

Always distinguish **“installed”** from **“listening”**. Full-suite verification that removes Postgres skips must export `TEST_DATABASE_URL` **before** importing `tests.conftest` side effects (pytest handles this automatically when the env var is set in the shell wrapping pytest).

## Full-suite dependency: `unrar` for LLM attachment extraction tests

`tests/backend/llm/test_llm_attachment_formats.py` calls `_require_rar_extractor()` which skips when neither `unrar`, `unrar-free`, nor compatible libarchive-backed `tar` / `bsdtar` exists on `PATH`. Installing `unrar` via apt or providing a compatible `tar` removes the skip without weakening assertions.

## Windows full-suite dependency provisioning: do not leave environment skips unexercised

### Symptom

A full-suite validation attempt can appear "mostly green" while important tests did not actually execute:

- RAR attachment tests skip because no `unrar` / `unrar-free` exists on `PATH`.
- PostgreSQL-only tests skip because `TEST_DATABASE_URL` is unset or no local PostgreSQL listener exists.
- Playwright tests abort before browser assertions because Node, Chromium, or subprocess spawning is unavailable.

### Policy

For a result described as a full validation, do not accept those skips as final evidence. Install or provision the missing environment and rerun the affected target at least once. It is fine to keep a fast-loop SQLite profile or a targeted smoke profile, but the ledger must clearly distinguish it from a complete environment-backed run.

Committed documentation must use placeholders such as `<repo>`, `<local-postgres-bin>`, `<local-postgres-data>`, `<local-browser-cache>`, and `<artifact-dir>`. Real local paths, user names, browser cache paths, downloaded archive paths, and service logs belong in an ignored `.e2e-run/` note.

### Windows RAR extractor notes from the 2026-05-07 session

The Windows host did not have `unrar`, `unrar-free`, or `rar` on `PATH`. Attempts to install `unrar` through a system package manager failed because the package manager's system directories were locked or not writable from the automation shell. That should be documented as environment bootstrap debt, not as a product bug.

Downloading RARLAB's Windows installer-style executable is not equivalent to installing a command-line `unrar` for automated tests. In this session, trying to treat that executable as `unrar` caused test execution to hang before product assertions. Do not rely on installer executables as CLI extractors unless you have verified `unrar` command semantics with a small archive.

The repository now accepts a libarchive-backed `tar` / `bsdtar` executable as a RAR extraction fallback when `unrar` and `unrar-free` are absent. This is useful on Windows where `tar.exe` may be present even when package-manager installation is blocked. Validate with:

```powershell
.venv\Scripts\python.exe -m pytest tests\backend\llm\test_llm_attachment_formats.py -q
```

### Windows `tar.exe` temp-directory ACL notes

During the fallback implementation, `tar.exe -xf <archive> -C <temp-dir> <member>` failed against some `tempfile.mkdtemp(...)` directories and left directories that Git could not enumerate (`Permission denied` warnings for `rar-one-*`). The working pattern was to create the per-member extraction directory explicitly with `Path(tempfile.gettempdir()) / f"rar-one-{uuid}"` plus `Path.mkdir(...)`, then remove it with `shutil.rmtree(..., ignore_errors=True)`.

If local `rar-one-*` directories remain after interrupted runs, treat them as local artifacts. Remove them only after verifying the resolved path is inside the intended temp/artifact area. Do not commit them and do not list their machine-specific absolute paths in committed docs.

### Windows PostgreSQL local-binary notes from the 2026-05-07 session

When the host lacks a PostgreSQL service, Docker, `psql`, or `pg_ctl` on `PATH`, an official PostgreSQL Windows binary archive under an ignored local artifact directory can be enough for a throwaway test database. Keep the archive, extracted binaries, data directory, and logs out of Git.

Known Windows friction:

- `initdb.exe` may finish writing a usable data directory but still print restricted-token errors at the end.
- `pg_ctl.exe start` can fail with restricted-token errors even when direct `postgres.exe -D <data-dir> -h 127.0.0.1 -p <port>` works.
- A background `postgres.exe` started by one automation command may not stay alive for the next tool call in this sandboxed environment. Prefer a single orchestrator command/script that starts PostgreSQL, waits for readiness, creates the test role/database, runs pytest, and then stops the process.
- PowerShell `Start-Process` cannot redirect stdout and stderr to the same file; use separate log files.
- If an interrupted orchestrator kills PostgreSQL during startup or recovery, the data directory can retain a stale `postmaster.pid` or enter crash recovery. For full-suite validation, a fresh throwaway data directory is often cheaper than trying to reason about the partially started one.

### Windows PostgreSQL validation on Python 3.14: old `psycopg2-binary` pins can be the real blocker

During the repository-normalization cleanup validation, `tests/postgres` was
initially blocked even after a local PostgreSQL binary runtime was available.
The repository virtualenv used Python 3.14, while `requirements.txt` still
listed `psycopg2-binary==2.9.9`. That version has no Python 3.14 wheel, so pip
fell back to a source build and failed at link time.

The working fix was to install and pin a Python-3.14-capable wheel:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade "psycopg2-binary>=2.9.12"
.\.venv\Scripts\python.exe -c "import psycopg2; print(psycopg2.__version__)"
```

This is environment bootstrap, not product behavior. Do not spend time
rewriting database code until the selected interpreter can import `psycopg2`.

Related dependency lesson: a local `.venv` may contain newer compatible wheels
than the committed pins. If `pip show` proves the environment works only because
newer wheels are installed, update `requirements.txt` in the same round so the
next operator can reproduce the validation environment.

### Windows PostgreSQL `initdb.exe` may require the approved execution context

In the same session, running `initdb.exe` from the default automation sandbox
failed immediately with:

```text
initdb: error: could not create restricted token: error code 87
```

The identical command succeeded when rerun in an approved non-restricted
PowerShell context. The successful pattern was:

1. create a fresh data directory under an ignored artifact root;
2. run `initdb.exe -D <artifact-dir>/data -U postgres --auth=trust --encoding=UTF8 --locale=C`;
3. start `postgres.exe` directly on a loopback-only local port;
4. create the throwaway role/database;
5. export `TEST_DATABASE_URL`;
6. run `.\.venv\Scripts\python.exe -m pytest tests\postgres -q`;
7. stop the process in a `finally` block.

Do not commit the orchestrator, database directory, logs, or local port. The
committed skill/documentation should describe the pattern with placeholders such
as `<local-postgres-bin>`, `<artifact-dir>`, and `<local-port>`.

### Chocolatey and official downloads are not the only path to Postgres validation

The same Windows host had Chocolatey installed, but `choco install python312`
failed because system Chocolatey directories and package locks under
`C:\ProgramData\chocolatey` were not writable from the automation shell. A
direct official Python installer download also timed out through the available
network path. Neither failure meant PostgreSQL validation was impossible.

Before declaring Postgres validation blocked:

- inspect the repository `.venv` and package versions with `pip show`;
- try a Python-3.14-compatible `psycopg2-binary` wheel when the interpreter is
  Python 3.14;
- prefer local PostgreSQL binaries and a throwaway database under ignored
  artifacts over system service installation when the task only needs tests.

### Windows PostgreSQL reused data directory can fail crash recovery before pytest starts

During a follow-up cleanup validation on `cursor/discussion-avatar-chat-ui-921d`, a local-only PowerShell orchestrator first reused a data directory from a previously interrupted PostgreSQL attempt. The server began crash recovery, repeatedly reported that the database system was still starting up to `pg_isready`, and then exited before readiness with:

```text
could not signal for checkpoint: Operation not permitted
```

This happened before pytest could connect to the database. Treat this as a local PostgreSQL runtime/data-directory recovery failure, not as evidence that `tests/postgres` failed.

The successful local pattern was:

1. keep the orchestrator under `<repo>/.e2e-run/`;
2. create a fresh throwaway data directory for each validation attempt, for example `<artifact-dir>/postgres-package-tests/data-<timestamp>`;
3. run `initdb` into that fresh directory;
4. tolerate the known Windows restricted-token and locale/text-search warnings when `PG_VERSION` and the cluster files were created successfully;
5. start `postgres.exe` directly with `-D <fresh-data-dir> -h 127.0.0.1 -p <local-port>`;
6. create the throwaway role/database;
7. set `TEST_DATABASE_URL`;
8. run pytest;
9. stop the process in the orchestrator `finally` block.

Do not copy the real data directory, log path, local port, or user profile into committed docs. Put those in `.e2e-run/local-private-paths.md`.

### PostgreSQL full pytest can expose stale roster-sync test expectations

A PostgreSQL-backed full pytest run on `cursor/discussion-avatar-chat-ui-921d` initially showed early failure markers and later timed out before a final summary. A focused rerun identified three failures in:

```text
tests/backend/courses/test_student_course_roster_behavior.py
```

The failing expectations were older than the current product behavior. They assumed that a student-role `User` with a `class_id` but no matching same-class `Student` roster row would continue to see no required course and would not be able to submit course homework. Current code intentionally calls `prepare_student_course_context(...)` during student login/course access. That helper can:

- create or repair the same-class roster row through `sync_student_roster_from_user_accounts(...)`;
- then call `sync_student_course_enrollments(...)`;
- then expose required courses for that class and allow homework submission when the repaired roster/enrollment is authoritative.

For tests around this area:

- assert the final repaired product state when the scenario is a normal same-class student account;
- use explicit cross-class data, enrollment blocks, or intentionally conflicting roster rows when the intended invariant is denial;
- do not assert "no roster row means no course forever" unless the product rule changes;
- keep route-denial tests separate from login-time repair tests so failures diagnose the right invariant.

This is a test semantics pitfall, not a reason to remove the login-time repair behavior.

### Ledger interpretation

Record environment failures and interruptions in
[`test-execution-runs.csv`](test-execution-runs.csv):

- increment `run_count` in `test-execution-targets.csv` for started validation attempts that were blocked or interrupted;
- increment `pass_count` only for actual passed test runs;
- record whether a skip was eliminated by provisioning the missing condition;
- store exact local paths and downloaded tool locations only in ignored `.e2e-run/` handoff notes.

## Stale documentation paths after removing root `tools/` (2026-05)

### Symptom

Agents or humans follow bookmarks pointing at `tools/testing/audit_test_redundancy.py` and conclude the file vanished or the clone is incomplete.

### Actual location

The test redundancy auditor now lives at `tests/devtools/audit_test_redundancy.py`.

### Verification

Run `rg 'tools/testing' -g '*.{py,yml,yaml,sh,bat,cjs,js,json}'` from the repository root after any structural pass; it should return **no** matches for executable/config surfaces once migrations are complete. Markdown narrative (including this section) may still cite the legacy path when teaching the pitfall.

### Pitfall during validation

If you only move the script but forget to skip `tests/devtools/` inside the auditor’s inventory walk, the generated `TEST_REDUNDANCY_AUDIT.md` may include spurious “uncategorized-python” rows for the utility itself. This pass adds an explicit `rel_path.startswith("tests/devtools/")` guard.

## Learning notes and attendance/calendar implementation pitfalls (2026-05)

### Pitfall: old doc path memory for code maps

During the learning-notes / attendance-calendar pass, an agent-side memory pointed at an old `architecture/` location for `CODE_MAP_AND_ENTRYPOINTS.md`. The actual current file is:

```text
<repo-root>/docs/reference/CODE_MAP_AND_ENTRYPOINTS.md
```

Fix: use `docs/README.md` as the documentation hub and prefer `rg "CODE_MAP_AND_ENTRYPOINTS"` over guessing a folder.

### Pitfall: `LLMQuotaReservation` cannot be reused for learning-note assistant replies by inventing a dummy job id

Course discussion quota rows currently attach to discussion/homework job tables. A learning-note discussion entry id is **not** a valid `discussion_llm_jobs.id`, so inserting quota/reservation rows with a dummy note discussion id would violate foreign-key expectations or silently corrupt attribution semantics.

Current product code therefore gates learning-note assistant replies through course access and course LLM config, but does not claim quota parity. A future implementation should add a note-specific LLM job table or generalize the quota attribution schema before recording learning-note token usage.

### Pitfall: patching multilingual demo seed with Chinese context can miss anchors

`domains/seed/demo.py` is data-heavy and contains many Chinese strings. A patch that matched nearby rendered Chinese text failed because PowerShell display and exact file bytes did not line up. The successful approach used ASCII anchors such as `_DEMO_PASSWORD`, `_HOMEWORK_TITLE`, and `link_row`.

Fix pattern: for multilingual files, use ASCII identifiers/path names as patch anchors, then run `py_compile` immediately.

Additional example from the richer demo-content pass:

- Replacing the old three-level `_seed_demo_material_chapters(...)` implementation by matching its Chinese-containing docstring initially failed. The reliable patch matched only the ASCII function definition `def _seed_demo_material_chapters` and the next ASCII function boundary, then replaced the function body with helper functions.
- Replacing `_DEMO_PREFILL_BODIES` by matching the old Chinese homework body text also failed. The reliable patch anchored on `_DEMO_PREFILL_STUDENT_NOS` and the following ASCII boundary `def _seed_prefilled_submissions_for_homework`.
- Do not treat either failure as evidence that the tracked file is corrupt. In this repository, PowerShell rendering may display valid UTF-8 Chinese as mojibake, while `apply_patch` still writes valid UTF-8 when given a precise byte-level context.
- For future seed-data edits, prefer this order: introduce new constants near ASCII identifiers, replace call signatures by ASCII function names, compile with `.venv\Scripts\python.exe -m py_compile apps\backend\courseeval_backend\domains\seed\demo.py`, then run the focused demo seed tests.

### Pitfall: Vite build can succeed while terminal output looks mojibake

`npm.cmd run build` rendered some chunk output and Chinese-adjacent console text through the Windows terminal encoding, but the Vue SFC source still compiled as UTF-8 and `rg` showed correct file content. Do not copy build output strings back into source. Use build success/failure as the syntax signal and inspect file diffs for content changes.

### Pitfall: targeted Playwright validation can fail before product code runs when subprocess spawning is blocked

During the standalone teaching-calendar wrapper cleanup, the targeted command below failed immediately in the default sandbox:

```powershell
npx.cmd playwright test e2e-course-ui-markdown-reader.spec.js --project=chromium
```

Observed symptom:

```text
Error: spawn EPERM
```

Interpretation:

- this failure happened before the browser test could start the managed backend/frontend subprocesses;
- it is an execution-environment permission failure, not evidence that `/teaching-calendar` redirect behavior or the attendance page is broken;
- the correct next step is to retry the same command outside the restricted sandbox or with an approved execution context, then evaluate any real Playwright assertion failures separately.

Agent workflow rule:

1. First run fast static checks such as `git diff --check` and `npm.cmd run build` from the school frontend package to catch syntax/import regressions.
2. If the targeted Playwright command fails with `spawn EPERM`, do not rewrite selectors or route code based on that result.
3. Record the blocked command and the exact high-level failure (`spawn EPERM`) in this pitfalls document.
4. Keep local absolute paths, user profile names, browser cache paths, or other machine-identifying details in an ignored local note under `.e2e-run/`, not in committed documentation.

### Pitfall: Playwright managed `webServer` can fail when the repository `.venv` is a stale junction

On Windows worktrees, `<repo>/.venv` may be a junction or symlink to another
local checkout. If that target directory is later deleted or moved, the admin
Playwright config still tries to start the managed FastAPI server with:

```text
<repo>/.venv/Scripts/python.exe -m uvicorn apps.backend.courseeval_backend.main:app ...
```

The targeted Playwright command may then fail after the sandbox `spawn EPERM`
issue is resolved, before any browser assertion runs:

```powershell
npx.cmd playwright test e2e-course-ui-markdown-reader.spec.js --project=chromium
```

Observed symptom:

```text
Error: Process from config.webServer was not able to start. Exit code: 1
[WebServer] The system cannot find the path specified.
```

Interpretation:

- this is a local Playwright environment/bootstrap failure, not evidence that
  the changed UI behavior is broken;
- the school Playwright config defaults `E2E_PYTHON` to
  `<repo>/.venv/Scripts/python.exe` on Windows;
- a system Python without `uvicorn`, `fastapi`, and `sqlalchemy` is not a valid
  replacement unless project dependencies were installed into that interpreter;
- real junction targets, browser cache locations, and user-profile paths belong
  only in ignored local notes under `.agent-run/`.

Preflight before rerunning Playwright:

```powershell
python ops\scripts\dev\playwright_preflight.py
python ops\scripts\dev\playwright_preflight.py --json
```

Use `--include-private-paths` only for local ignored handoff notes:

```powershell
python ops\scripts\dev\playwright_preflight.py --include-private-paths
```

Fix patterns:

1. recreate the repository virtual environment and install requirements;
2. or set `E2E_PYTHON=<python-with-project-dependencies>` before invoking
   Playwright;
3. or start backend/frontend manually, verify health, and run Playwright with
   `PLAYWRIGHT_USE_EXTERNAL_SERVERS=1`;
4. rerun the same targeted Playwright command only after the preflight no longer
   reports missing backend Python dependencies.

Do not edit Playwright selectors, Vue components, or route code based solely on
this `webServer` bootstrap failure.

### Pitfall: Playwright managed `webServer` can hang during Windows teardown after all tests report `ok`

On the Windows `cursor/beautify-ui` branch, targeted school Playwright specs
reported every browser test body as `ok`, but the outer CLI process did not exit
before the local timeout. This is not a passing validation result.

Confirmed evidence from a focused rerun with Playwright webServer debug enabled:

```text
ok 1 ... material detail discussion keeps demo collapsed ...
pw:webserver Terminating the WebServer
```

The command then hung before logging `Terminated the WebServer`. Port checks
after timeout showed no listener on `8012` or `3012`, which points at the
Playwright managed-server cleanup wait path rather than a UI assertion failure.
Disabling the real grading worker with `E2E_USE_REAL_WORKER=false` did not make
the managed `webServer` command exit reliably.

Fix/workaround now available for local Windows validation:

```powershell
cd apps\web\school
$env:E2E_USE_REAL_WORKER='false'
npm.cmd run test:e2e:external -- e2e-course-ui-markdown-reader.spec.js --project=chromium
```

`test:e2e:external` runs `scripts/playwright-external-runner.cjs`. The runner
starts the FastAPI API and Vite UI itself, waits for health checks, invokes
Playwright with `PLAYWRIGHT_USE_EXTERNAL_SERVERS=true`, and then kills only the
processes it started with a bounded cleanup path.

Observed successful reruns:

- `npm.cmd run test:e2e:external -- e2e-course-ui-markdown-reader.spec.js --project=chromium`
  exited `0` with `12 passed (54.2s)`.
- `npm.cmd run test:e2e:external -- e2e-discussion-cover-llm-tier3.spec.js --project=chromium`
  exited `0` with `15 passed (1.2m)`.
- Post-run checks found no remaining listeners on ports `8012` or `3012`.

Additional guardrail: if using Playwright's own `DEBUG=pw:webserver`, ensure the
backend child process does not inherit `DEBUG=pw:webserver` as its application
`DEBUG` setting. The school Playwright config now forces managed server child
environments to `DEBUG=false` for that reason.

Do not rewrite UI selectors or business code based solely on this cleanup hang.
Use the external runner when a true local Windows pass/fail exit status is
needed.

### Pitfall: Playwright preflight must cover seed-time backend dependencies, not only uvicorn startup

The managed school Playwright path can pass a shallow `uvicorn` import check and
still fail before the first browser assertion when `globalSetup` calls
`POST /api/e2e/dev/reset-scenario`.

Observed cluster on the Windows `cursor/discussion-avatar-chat-ui-921d` branch:

- the host only exposed Python 3.14, while the pinned `requirements.txt`
  includes packages with known Python-3.14 install friction
  (`pydantic==2.5.3` via `pydantic-core==2.14.6`, and
  `psycopg2-binary==2.9.9` source-build risk without `pg_config`);
- a locally smoke-capable Python 3.14 `.venv` was possible only after installing
  compatible wheels, so "requirements installed" and "current venv works" were
  not the same claim;
- `bcrypt==5.0.0` with `passlib==1.7.4` caused the E2E seed password hashing
  path to return `500`, even though the backend process itself had started;
- the failed seed left the default file-backed Playwright SQLite database in the
  temp directory, which can confuse the next diagnostic pass if the operator
  assumes every rerun starts from a clean database.

Fix pattern now encoded in `ops/scripts/dev/playwright_preflight.py`:

```powershell
.\.venv\Scripts\python.exe ops\scripts\dev\playwright_preflight.py --json
```

The preflight must check:

- the selected `E2E_PYTHON` exists and can run;
- Python version details are visible, with Python 3.14 recorded as local-smoke
  usable only when dependencies are already installed;
- known Python-3.14 requirement pins are surfaced in the JSON detail;
- backend modules needed by startup and seed routes import successfully
  (`uvicorn`, `fastapi`, `sqlalchemy`, `pydantic`, `pydantic_settings`, `jose`,
  `passlib`, `multipart`, `httpx`);
- `passlib` can hash a bcrypt password, catching the `bcrypt==5.0.0` /
  `passlib==1.7.4` seed-500 class before Playwright launches;
- the default Playwright SQLite file for `E2E_API_PORT` is visible in output so
  a half-initialized local artifact is not mistaken for product state.

Interpretation rule:

- Missing Python, missing imports, or failing bcrypt smoke is a blocking
  environment failure for managed Playwright.
- Python 3.14 pin friction and an existing local SQLite file are diagnostic
  details for local smoke, not automatic product failures. Use Python 3.11/3.12
  for release-like validation, or document that the run used a specially
  populated Python 3.14 environment.

### Pitfall: execution ledgers become misleading if they only record green runs

The structured execution ledger lives at:

```text
<repo-root>/docs/testing/test-execution-targets.csv
<repo-root>/docs/testing/test-execution-runs.csv
```

`TEST_EXECUTION_LEDGER.md` is only the stable Markdown entry point. The CSV
tables are meant to help agents avoid reflexively rerunning every suite when a
narrow change only touches known surfaces. The ledger becomes actively harmful
if failed, blocked, timed-out, skipped, or interrupted validation attempts are
omitted from `run_count` and the append-only run table.

Fix pattern:

- record every observed validation attempt that was started for a target, including blocked Playwright runs and environment failures;
- increment `run_count` for blocked/failed/timed-out/interrupted/skipped attempts;
- increment `pass_count` only for `result=passed`;
- keep committed command rows repository-relative (`<repo>`, `<repo>/apps/web/school`, `<python-with-requirements>`);
- put machine-specific paths, user profile names, browser cache paths, local database files, and exact private working directories in `.e2e-run/local-private-paths.md` or another ignored `.e2e-run/` note;
- do not backfill historical pass counts from memory or branch names.

Interpretation:

Use the ledger as a test-selection aid, not as a substitute for touched-file analysis. A high pass count for a target does not prove the target can be skipped after relevant code changes. Conversely, a blocked run should not be treated as a product failure without reading the environment details in this pitfalls document.

### Pitfall: line-count health scripts must not count local artifacts

The repository line-health script lives at:

```text
<repo-root>/ops/scripts/dev/repo_line_health.py
```

The first implementation deliberately uses `git ls-files` by default. A naive recursive filesystem walk would count `.venv/`, `node_modules/`, `apps/web/*/dist/`, `.e2e-run/`, Playwright reports, local sqlite files, upload directories, and other machine-local artifacts. That would make the reported "repository size" mostly a measure of local environment churn, not source evolution.

Fix pattern:

- use tracked files as the default metric source;
- keep an explicit `--include-untracked` mode only for diagnostics, and still skip obvious artifact directories;
- split `generated_or_lock` from normal application and documentation categories so lockfile churn does not look like feature-code growth;
- print `<repo>` in machine-readable output instead of an absolute repository path;
- keep any machine-specific path notes in `.e2e-run/`, not in committed metric output.

During development of the script, remember that a newly added metrics script or documentation file is not part of `git ls-files` until it is staged. If you need the line-health output to represent the exact intended commit, stage the new tracked files first, then rerun the command before recording the ledger row.

Interpretation:

Line counts are trend indicators, not quality metrics. A larger documentation count can be healthy in this repository because documentation is agent-facing operating context. A smaller test count can be healthy after deduplication only if the redundancy audit or equivalent evidence explains why coverage was preserved.

### Pitfall: learning-note public visibility is not the same as "must bind a course"

The first implementation of learning notes treated `visibility="course"` as literally course-only and rejected public notes where `subject_id` was null. That no longer matches the product rule: a public note with a course is same-course-visible, while a public note without a course is visible to every authenticated user.

Implementation consequence:

- Do not restore a validator like `Public course-visible notes must be associated with a course`.
- Public list queries without a course filter must include both `subject_id IS NULL` notes and course-bound notes for ids returned by `get_accessible_course_ids(...)`.
- Public list queries with a concrete `subject_id` still call `ensure_course_access_http(...)` and filter to that course only, so a course-specific view does not unexpectedly mix in all-authenticated notes.
- Update payload handling must distinguish "field omitted" from `"subject_id": null`; otherwise a user cannot clear a note's course binding and publish it to all authenticated users.

Verification pattern: after editing `api/routers/learning_notes.py`, run targeted Python compilation and grep for the obsolete validator/error text before claiming the visibility semantics are fixed.

### Pitfall: subject-scoped teacher access must not be blocked by an empty class-id set first

The recurring regression pattern in this repository is:

1. a teacher legitimately owns a course through `Subject.teacher_id`;
2. the route also computes `get_accessible_class_ids(...)`;
3. the code rejects the request because the derived class-id set is empty or does not contain the record's `class_id`;
4. the request never reaches `ensure_course_access_http(subject_id, ...)`, even though that course access check would have allowed the teacher.

This broke multiple surfaces during the repository-normalization line:

- basename attachment download in `api/routers/files.py`;
- homework batch late-submission and batch regrade flows in `api/routers/homework.py`;
- attendance create/list/update/batch flows in `api/routers/attendance.py`.

Safe rule:

- for records that already carry a meaningful `subject_id`, check course access first with `ensure_course_access_http(...)`;
- use class-id filtering only for records that are truly class-scoped and have no course context;
- do not treat an empty `get_accessible_class_ids(...)` result as an automatic teacher denial when the route is fundamentally course-owned.

Verification pattern:

- seed a `teacher` user with `Subject.teacher_id = teacher.id` and `Subject.class_id = <class>`;
- do **not** rely on `subject_class_links` or teacher `user.class_id` unless the scenario is explicitly class-scoped;
- confirm that teacher-owned subject operations still work for attachments, homework batch operations, and attendance writes after the change.

### Pitfall: visible course access is not course management permission

The mirror-image regression is treating a `class_teacher` who can see a course
through `subject_class_links` as if they can manage that course. That was a real
bug across several repository-normalization hardening rounds.

Observed failure pattern:

1. `class_teacher` has `user.class_id = class A`.
2. A course is linked to class A, so `ensure_course_access_http(...)` succeeds.
3. The course is actually owned by another teacher through `Subject.teacher_id`.
4. A mutation endpoint uses only role membership plus course visibility.
5. The `class_teacher` can mutate another teacher's course-owned records.

Routes that have already been hardened after this bug pattern:

- `api/routers/subjects.py`: update/delete, cover upload, sync-enrollments,
  roster-enroll, enrollment-type update, and student removal.
- `api/routers/materials.py`: course material creation.
- `api/routers/homework.py`: course homework creation.
- `api/routers/scores.py`: score creation/update/delete, batch score import,
  exam weights, grade schemes, and score-appeal responses.
- `api/routers/attendance.py`: course attendance create/update/delete plus
  batch and class-batch variants.
- `api/routers/notifications.py`: course notification publish/update when
  `subject_id` is set.
- `api/routers/llm_settings.py`: course LLM config `GET` and `PUT`.

Safe rule:

- Use `ensure_course_access_http(...)` for visibility and read/list access.
- Add `is_course_instructor(...)` or a route-local wrapper for any
  course-owned mutation.
- Do not assume `class_teacher` plus class-linked course visibility equals
  assigned-teacher authority.

Verification pattern:

- seed a course whose `Subject.teacher_id` belongs to a teacher;
- link that course to a class teacher's class via `subject_class_links`;
- login as the class teacher and attempt the write directly over HTTP;
- assert **403** and verify the target row did not change.

Canonical regression files:

- `tests/security/test_security_hardening_followup.py`
- `tests/e2e/web-school/e2e-security-hardening-followup.spec.js`

The May 2026 ledger rows around `security.api_regression` document the observed
red-to-green sequence. Extend the same tests before adding a new route that can
write course-owned data.

### Pitfall: patching mojibake-rendered exception strings can corrupt Python syntax

Windows PowerShell can display UTF-8 Chinese exception strings as mojibake. If
an agent copies the displayed text into an `apply_patch` hunk, the patch may
replace only part of the original string or introduce mismatched quotes. During
this hardening round, a route-level permission detail string in
`apps/backend/courseeval_backend/api/routers/parent.py` was temporarily turned
into an unterminated Python string, and `py_compile` caught the syntax error.

Mitigation:

- Treat terminal-rendered non-ASCII as display-only. Verify bytes, use an
  escaped UTF-8 view, or patch around ASCII anchors before editing multilingual
  source.
- Prefer ASCII for backend exception details when the text is not user-facing or
  is already inconsistent with localized UI copy.
- If a line is syntactically corrupted and `apply_patch` cannot reliably match
  the rendered bytes, replace the smallest complete syntactic unit and
  immediately run `python -m py_compile` on the touched file.
- Record the incident in `docs/testing/pitfall-index.csv` and keep
  the mitigation close to the encoding guidance instead of leaving it as only a
  chat transcript note.

## Ledger and selector tooling notes

Detailed selector, ledger, update-log, and private-path-scan pitfalls have
been moved to
[pitfalls-ledger-and-selector-tooling.md](pitfalls-ledger-and-selector-tooling.md).

This includes:

- validation-target `ledger_id` drift,
- school Playwright external-runner target rules,
- external-runner API readiness timing,
- Playwright grep over-selection,
- array matcher containment confusion,
- private-path scanner self-matches,
- BOM-sensitive update-log and CSV ledger pitfalls.
