# Development and Testing

## Required Reading Before Running Commands

Do not start with ad hoc commands if you are new to this repository or returning after a break.

Read in this order first:

1. [../architecture/REPOSITORY_STRUCTURE.md](../architecture/REPOSITORY_STRUCTURE.md)
2. [../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md](../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md) if your shell is Windows + PowerShell or you may touch multilingual files
3. [TEST_SUITE_MAP.md](TEST_SUITE_MAP.md)
4. [TEST_REDUNDANCY_AUDIT.md](TEST_REDUNDANCY_AUDIT.md) if you are evaluating test cleanup or consolidation
5. [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)
6. the feature-specific document for the workflow you are about to touch

When the failure class is already obvious, start from the narrower pitfall
route before opening the full encyclopedia:

- [pitfalls-windows-and-encoding.md](pitfalls-windows-and-encoding.md)
- [pitfalls-playwright-and-e2e.md](pitfalls-playwright-and-e2e.md)
- [pitfalls-postgres-and-pytest.md](pitfalls-postgres-and-pytest.md)
- [pitfalls-ledger-and-selector-tooling.md](pitfalls-ledger-and-selector-tooling.md)

Why this is mandatory:

- the repository has strict package-boundary rules that are easy to misread if you only inspect paths
- Windows + PowerShell execution has known traps that can produce false test failures
- Windows + PowerShell sessions can also mis-render UTF-8 text; cleanup and documentation edits must follow [../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md](../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md) and the current repository-structure rules in [../architecture/REPOSITORY_STRUCTURE.md](../architecture/REPOSITORY_STRUCTURE.md)
- Playwright failures in this repository are often environment or process-management issues before they are product regressions
- local artifact directories can look like source or canonical output if you do not read the structure notes first
- cross-platform and cloud-automation runs can hit additional traps such as Element Plus locale behavior, Playwright selector ambiguity, API `page_size` limits, and stale ports; see [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md) for follow-up risk notes

## Local Development Setup

Before running commands, understand the repository boundary rules in [../architecture/REPOSITORY_STRUCTURE.md](../architecture/REPOSITORY_STRUCTURE.md). In particular:

- the canonical backend package lives in `apps/backend/courseeval_backend/`,
- the canonical backend import root is `apps.backend.courseeval_backend`,
- the root `conftest.py` is intentionally repository-scoped,
- Windows launcher scripts live in `../../ops/scripts/windows/`.

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn apps.backend.courseeval_backend.main:app --host 127.0.0.1 --port 8001 --reload
```

Optional Windows convenience launcher:

```bat
ops\scripts\windows\start-backend.bat
```

### Repository line-health metrics

Use the repository line-health script when you need a coarse, repeatable measure of how the repository is evolving across documentation, tests, and primary application code.

The script lives under `ops/scripts/dev/` because it is a repository-wide developer utility rather than a pytest module, deployment script, or app-local command:

```bash
python ops/scripts/dev/repo_line_health.py
python ops/scripts/dev/repo_line_health.py --json
python ops/scripts/dev/repo_line_health.py --details
```

Default behavior:

- uses `git ls-files` so local artifacts are excluded;
- counts text files only;
- skips binary files and undecodable files;
- reports total tracked text lines;
- reports "health" text lines excluding generated or lock files;
- reports required health categories: `documentation`, `test_code`, and `primary_source`;
- reports supporting categories such as `tooling`, `operations`, `configuration`, `application_support`, `generated_or_lock`, and `other`;
- emits Markdown by default and JSON when `--json` is passed;
- prints `<repo>` as the repository-root placeholder in JSON output rather than a local absolute path.

Interpretation guidance:

- `documentation` includes `docs/`, root `README.md`, root `AGENTS.md`, and Markdown/Text/RST files under app, ops, or tests folders.
- `test_code` includes `tests/backend/`, `tests/behavior/`, `tests/e2e/`, `tests/postgres/`, `tests/security/`, `tests/scenarios/`, plus repository pytest bootstrapping files.
- `primary_source` includes `apps/backend/courseeval_backend/`, `apps/web/school/src/`, and `apps/web/parent/src/`.
- `tooling` includes repository maintenance utilities such as `ops/scripts/` and `tests/devtools/`.
- `generated_or_lock` is separated so files such as `package-lock.json` do not distort the main health trend.

Do not use line counts as a quality score by themselves. They are a trend signal: a sudden test-code drop, documentation shrink, primary-source spike, or lockfile-heavy increase should prompt a closer diff review.

### Diff-based validation workflow

Use the focused validation handbook:

- [VALIDATION_WORKFLOW_AND_TOOLS.md](VALIDATION_WORKFLOW_AND_TOOLS.md)

That document is now the canonical source for:

- diff-based validation workflow
- selector, target runner, and profile runner behavior
- artifact and evidence rules
- local pytest SQLite guardrail
- validation sufficiency interpretation

### School frontend

```bash
cd apps/web/school
npm install
npm run dev
```

Optional Windows convenience launcher:

```bat
ops\scripts\windows\start-school-frontend.bat
```

### Parent portal

```bash
cd apps/web/parent
npm install
npm run dev
```

Optional Windows convenience launcher:

```bat
ops\scripts\windows\start-parent-frontend.bat
```

## Key Development Settings

The canonical list of **all** `Settings` fields, defaults, and related Vite variables is in [../architecture/CONFIGURATION_REFERENCE.md](../architecture/CONFIGURATION_REFERENCE.md) (kept in sync with [`apps/backend/courseeval_backend/core/config.py`](../../apps/backend/courseeval_backend/core/config.py)).

Quick reminders for developers running locally:

- Prefer `.env` at the repo root for backend variables (`Settings` reads `.env` with UTF-8 encoding).
- Never commit real secrets; placeholder defaults exist for local ergonomics but fail validation when `APP_ENV` is production or `REQUIRE_STRONG_SECRETS=true`.
- Frontend dev servers read `VITE_*` from `apps/web/school/` or `apps/web/parent/` — see CONFIGURATION_REFERENCE **Frontend dev** section.

Playwright-specific additions (not part of `Settings`):

- `PLAYWRIGHT_USE_EXTERNAL_SERVERS` — skip spawning managed uvicorn/vite when pointing at already-running servers.
- `E2E_API_PORT`, `E2E_UI_PORT` — defaults **8012** / **3012** inside `apps/web/school/playwright.config.cjs`.
- `E2E_PYTHON` — Python executable for the managed API subprocess.

Dual gate for `/api/e2e/dev/*` — see [E2E Seed and Environment](#e2e-seed-and-environment) below and CONFIGURATION_REFERENCE (`E2E_DEV_REQUIRE_ADMIN_JWT`).

## Test Layers

### CI reference (cloud pipelines)

This repository stores example Alibaba DevOps-style pipeline YAML under
[`ops/ci/pr-pipeline.yml`](../../ops/ci/pr-pipeline.yml) and sibling files. The
PR pipeline runs:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
```

The repository also has a lightweight GitHub Actions entrypoint at
[`../../.github/workflows/lightweight-validation.yml`](../../.github/workflows/lightweight-validation.yml).
It is intentionally a first cloud gate, not full validation. On pull requests it
runs selector/tooling checks, emits a diff-based validation recommendation,
runs quick backend `pytest`, and builds the school and parent frontends.

Current GitHub Actions scope:

- `Python selector tooling`: validates selector scripts and
  `tests/TEST_SELECTION_TARGETS.json`, runs
  `python -m unittest tests.backend.manual.test_validation_selector -v`,
  checks generated testing-governance docs and pitfall-index line sync, and
  uploads `validation-selection.json` for pull requests;
- `Backend quick pytest`: runs default quick backend `pytest`;
- `School frontend build`: runs `npm ci` plus `npm run build` for
  `apps/web/school`;
- `Parent frontend build`: runs `npm ci` plus `npm run build` for
  `apps/web/parent`.

Keep these jobs split. A selector/tooling failure means the validation
infrastructure itself is unreliable; a backend pytest or frontend build failure
means the product or test environment failed. Mixing them into one GitHub check
makes red-check triage slower and obscures ownership.

Current GitHub Actions non-goals:

- no PostgreSQL service container yet;
- no zero-skip backend guarantee;
- no RAR/unrar environment provisioning;
- no Playwright browser install or E2E run;
- no automated execution of selector-recommended broad/full targets.

Use this as the current compromise path: cloud catches cheap regressions and
records selector recommendations, while PostgreSQL-backed pytest, RAR-dependent
attachment coverage, and Playwright E2E remain local/manual or future
cloud-profile work.

### Remote CI wait policy

Do not make remote CI polling the default blocking path for development work.
After local, change-scoped validation has passed and the branch has been pushed,
confirm that the GitHub Actions run was created, record the commit/run context
in the handoff or task notes when useful, then continue with unrelated coding or
review work.

Wait synchronously for remote CI only when the result is the task itself or the
next local decision depends on it, for example:

- the user explicitly asked to fix red checks or verify a PR gate;
- a previous remote failure is being diagnosed from logs;
- the pushed fix changes CI, validation tooling, or a failing test path and the
  remote result proves whether the root cause was actually removed;
- the next code change would be different depending on the remote result.

If the run enters a long backend `pytest`, frontend build, Playwright, or future
PostgreSQL stage after the relevant failure point has passed, treat it as
asynchronous validation unless the user requested a full green wait. Report the
current run id, commit, and step, and return to productive work. If the remote
run later fails, resume from the new logs and fix that failure as a separate
iteration.

Agents on Linux should prefer **`python3`** invocations to match CI even when local README examples historically showed `python` for Windows-oriented quick starts.

### Backend `pytest`

Use backend tests for API logic, permission checks, grading behavior, and state-convergence rules.

```bash
python -m pytest
python -m pytest tests/behavior -q
```

Important directories:

- `tests/backend/`
- `tests/behavior/`
- `tests/scenarios/`

**Full regression parity:** SQLite-default pytest skips modules guarded for PostgreSQL dialect differences (`tests/postgres/*`). To eliminate those skips and exercise FK/schema paths closest to production, provision Postgres using `ops/scripts/dev/provision_postgres_pytest.sh`, export `TEST_DATABASE_URL` as printed by the script, then run `python3 -m pytest tests/`. See [TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md](TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md) Part I for the combined SQLite + Postgres + Playwright recipe and [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md) for container PostgreSQL start pitfalls (`pg_ctlcluster`, `policy-rc.d`).

Before concluding that a backend test failure is a product regression, review the temp-path, Windows, and environment notes in [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md).

For a domain-by-domain map of the backend suites, read [TEST_SUITE_MAP.md](TEST_SUITE_MAP.md).

### Frontend Playwright E2E

Use browser tests for login flows, stale-tab behavior, deep links, and UI-to-backend convergence.

```bash
cd apps/web/school
npx playwright install chromium
npm run test:e2e
```

The default config runs **all** spec files under `tests/e2e/web-school/` sequentially (`workers: 1`). A complete green run is ~300+ tests / ~15 minutes on a warm agent — budget wall-clock accordingly when iterating.

For environment variables, persistent SQLite behavior during long serial runs, selector strategy, and triage order when many specs fail together, read [FULL_PLAYWRIGHT_E2E_RUNBOOK.md](FULL_PLAYWRIGHT_E2E_RUNBOOK.md).

Key files:

- `apps/web/school/playwright.config.cjs`
- `tests/e2e/web-school/`
- `docs/testing/TEST_EXECUTION_PITFALLS.md`
- `tests/TEST_PROTECTION_RULES.json`

### Maintained local UI screenshot workflow

Use the committed homework-layout screenshot flow when you need a reproducible
teacher screenshot for the wide homework list layout:

```bash
cd apps/web/school
npm run capture:homework-layout
```

Contract:

- the command starts backend + frontend through the maintained external-runner
  path;
- it resets the E2E scenario, seeds two demo homework rows, opens `/homework`,
  and captures the page;
- default output is `<repo>/pics/homework-layout-fixed.png`;
- `pics/` is local-only by default and should not be pushed unless the user
  explicitly asks.

Use the committed student material-reader screenshot flow when you need a
reproducible student reading-page screenshot that proves student catalog entry,
chapter-linked actions, and uncategorized reader blocks:

```bash
cd apps/web/school
npm run capture:student-material-reader
```

Contract:

- the command starts backend + frontend through the maintained external-runner
  path;
- it resets the E2E scenario, opens a seeded `/materials/read/:id` page, and
  captures the student reader;
- default output is `<repo>/pics/student-material-reader-fixed.png`;
- `pics/` remains local-only by default unless the user explicitly asks to
  push screenshots.

Before running Playwright on Windows, read the pitfalls document first. Known false-failure causes include:

- `npm.ps1` execution-policy blocking,
- stale API or UI ports,
- hidden old processes serving the wrong app,
- sandbox `EPERM` during subprocess startup,
- readiness checks that accept the wrong HTTP response.

### Playwright advanced-coverage scenarios

In this branch, the pair below is already implemented as normal runnable Playwright coverage:

- `tests/e2e/web-school/future-advanced-coverage.spec.js`
- `tests/e2e/web-school/future-advanced-coverage-2.spec.js`

Shared helpers live in:

- `tests/e2e/web-school/future-advanced-coverage-helpers.cjs`

Scenario index (cases 1–30), verification commands, and interpretation notes are consolidated in [TEST_SUITE_MAP.md](TEST_SUITE_MAP.md) under the Playwright section — there is no separate env-gated “backlog” suite in this repository.

## E2E Seed and Environment

The repository includes an E2E-only reset API used by browser tests.

- Route family: `/api/e2e/...`
- Guarded by `E2E_DEV_SEED_ENABLED` and `E2E_DEV_SEED_TOKEN`
- Never enable this in production; additionally, `APP_ENV=production` forces `expose_e2e_dev_api()` to **false**, so every `/api/e2e/...` request returns **404** even if seed flags were mis-set (see `tests/backend/test_settings_e2e_router_gate.py`). The router remains registered for test-time toggles; access is blocked by a router-level dependency.

**Dual gate for powerful dev routes (mock LLM, grading pump, preset shortcuts)**

When `E2E_DEV_REQUIRE_ADMIN_JWT=true` (default in `apps/web/school/playwright.config.cjs` for the managed API subprocess), the following endpoints require **both** header `X-E2E-Seed-Token` **and** a valid **administrator** `Authorization: Bearer <jwt>`:

- `POST /api/e2e/dev/mock-llm/configure`
- `GET /api/e2e/dev/mock-llm/state`
- `GET /api/e2e/dev/grading-state`
- `POST /api/e2e/dev/process-grading`
- `POST /api/e2e/dev/worker`
- `POST /api/e2e/dev/mark-preset-validated`

`POST /api/e2e/dev/reset-scenario` remains **seed-token only** so automation can obtain credentials before any JWT exists.

Playwright (`tests/e2e/web-school/fixtures.cjs`, `global-setup.cjs`) calls `refreshE2eAdminBearer()` from `e2e-seed-headers.cjs` after each successful reset to store the seeded admin token in `process.env.E2E_DEV_ADMIN_BEARER` and merge it into shared `seedHeaders()` for specs that call powerful `/api/e2e/dev/*` routes.

To disable the admin JWT requirement (legacy tooling that only passes the seed header): set `E2E_DEV_REQUIRE_ADMIN_JWT=0` in the backend environment.

Playwright scenarios commonly use:

- `POST /api/e2e/dev/reset-scenario`
- a local API URL,
- a local frontend base URL,
- a local Playwright browser cache path on Windows.

## Windows Notes

This repository is actively used on Windows, so path and encoding discipline matters.

- For the default repository-safe Windows text workflow, start with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1
```

- If you intentionally need the UTF-8 session settings in the current
  interactive shell rather than the child-process wrapper, use:

```powershell
. .\ops\scripts\windows\set-utf8-session.ps1
```

- For byte-safe inspection and controlled text writes, use:

```powershell
python ops\scripts\dev\safe_show_text.py <path> --escape
python ops\scripts\dev\safe_write_text.py <path> --stdin --replace
python ops\scripts\dev\check_text_encoding.py <path>
```

- Prefer running `pytest` from the repository root.
- Prefer the repository virtual environment instead of a global Python.
- Keep documentation and scripted edits ASCII-first when possible.
- Avoid shell-side bulk rewriting of Chinese strings.
- Treat terminal-rendered Unicode as display-only until it is verified against file content or git diff.
- Do not treat local directories such as `frontend/`, `test-results/`, `.e2e-run/`, or `.pytest_tmp/` as source layout. They are local artifacts.
- For Playwright, explicitly set `PLAYWRIGHT_BROWSERS_PATH` when using a local browser cache.

Example command pattern for targeted Playwright runs:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH='C:\Users\<user>\AppData\Local\ms-playwright'
$env:E2E_API_URL='http://127.0.0.1:8012'
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3012'
$env:E2E_DEV_SEED_TOKEN='test-playwright-seed'
npm run test:e2e
```

Concrete safe-edit strategy for multilingual files in this repository:

- prefer editing through repository-aware patching instead of copying terminal-rendered Chinese text back into files
- do not trust PowerShell display output as the source of truth for non-ASCII content
- if a Chinese string must be changed, anchor the edit on surrounding ASCII structure (`data-testid`, route path, JSON key, Markdown heading, or code identifier) rather than on terminal-rendered mojibake
- after editing, verify via git diff and file-local context instead of trusting the console glyphs alone

For the detailed Windows safe-text workflow and helper semantics, use
[../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md](../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md)
as the canonical source.

## Current High-Value Regression Areas

These are the areas most worth testing when behavior changes:

- startup-time idempotency and backfill behavior,
- roster and class-move synchronization,
- required versus elective enrollment rules,
- homework submission history and max-submission limits,
- LLM routing, quota, retry, and regrade recovery,
- notification read-state convergence,
- grade and homework appeal deduplication,
- deep-link recovery when local course context is stale or missing.

## Complex Regression Coverage Added In This Repository

Recent behavior coverage includes scenarios such as:

- score-appeal reopen after resolve or reject,
- concurrent duplicate appeal submission settling to one pending row,
- targeted-student notification privacy,
- subject-scoped mark-all-read behavior,
- concurrent notification read-state convergence,
- batch class flip-flop preserving one required enrollment,
- batch import retry idempotency,
- quota exhaustion followed by recovery,
- disable-then-reenable LLM grading flows.

Browser note: `tests/e2e/web-school/e2e-discussion-cover-llm-tier3.spec.js` (15 cases) exercises **discussion LLM assistant**, **long-body preview/collapse**, and **course cover** flows against the seeded scenario; `POST /api/e2e/dev/reset-scenario` now seeds a per-run **`discussion_llm_profile`** plus an enabled course LLM row wired to the mock chat endpoint so discussion jobs can complete without manual admin setup.

Additional browser coverage: `tests/e2e/web-school/e2e-homework-comment-cover-tier4.spec.js` (15 cases) stresses **homework submissions list** `content_preview` / `comment_preview` ellipsis behavior (teacher UI uses stable `data-testid`s), **LLM auto-grade** long comments, **regrade** and **429-then-success** mock paths, concurrent teacher/student API interactions, and **course cover** uploads (teacher UI + admin POST + student-visible banners).

## Practical Testing Rules

- Assert authoritative business state before asserting visual transitions.
- Prefer stable identifiers and API-level validation over UI copy.
- Run the narrow failing test first, then the relevant suite, then the broader suite.
- Separate product bugs from environment mistakes such as working-directory or temp-path issues.
- If running on Windows + PowerShell, review `TEST_EXECUTION_PITFALLS.md` before assuming Playwright or pytest failures are product regressions.

### Incremental lessons from higher-difficulty browser/API suites (May 2026)

When extending Playwright or threaded pytest coverage, the friction usually clusters around contract mismatches, router redirects by role, SQLite races, and Playwright locator ambiguity. Read the later pitfall entries in [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md) before debugging failures that look like flaky UI but are actually environment or selector-discipline issues.

Further test-authoring lessons from the tier-4 stress E2E pass are recorded in the same document, including `apiBase` mismatches, JSON encoding mistakes, schema `ge=` limits, homework title DOM-vs-API mismatches, password-change token capture, and attachment ACL issues. A subsequent full `pytest` plus full school Playwright pass on a Linux agent added notes about MessageBox accessibility, duplicate course-title rows, disabled-force click mistakes, `waitForResponse` races, password button labels, and Vite `goto` races. A later pitfall-guard follow-up added delete-list UI-vs-API truth and per-route `page_size` lessons.

### Recommendations for new test samples (E2E and API)

- **Confirm the contract first**: path, verb, query-vs-body shape, and Pydantic bounds should align with `apps/backend/courseeval_backend/api/routers/*.py` and `apps/backend/courseeval_backend/api/schemas.py`, and should mirror the admin client in `apps/web/school/src/api` when in doubt.
- **Assert server state before UI**: use `page.request`, shared `apiGetJson`, or `expect.poll` on an API predicate, then reload or widen locators for the UI.
- **Prefer stable hooks**: `data-testid`, course context helpers such as `enterSeededRequiredCourse`, and explicit `waitForResponse` registration before clicks are safer, especially for Element Plus dialogs and batch actions.
- **Concurrency**: prefer API-only parallel storms when the UI disables controls; avoid `Promise.all` on clicks that may be no-ops when disabled (see Pitfall 22).
- **Conditional scenarios**: if a test needs two movable material chapters, a parent code, or a class-teacher seed, use `test.skip` with a clear reason when the seed layout does not support it, and document the assumption in the spec comment.
- **Playwright environment contract**: default managed E2E in this branch starts the API on `8012` and the school UI on `3012`, uses `PLAYWRIGHT_USE_EXTERNAL_SERVERS` to opt out of managed servers, and accepts `E2E_PYTHON` plus `E2E_USE_REAL_WORKER` for backend-process control; keep docs and CI commands aligned with `apps/web/school/playwright.config.cjs`.
- **Regression placement**: put **API contract and idempotency** checks in `pytest` where possible; reserve Playwright for routing, visibility, and multi-tab behavior that HTTP tests cannot see.

### Sample hygiene: overlap, redundancy, and refinement targets

This is judgment for maintainers, not an automatic delete list:

- **`tests/e2e/web-school/e2e-tier4-stress-backlog.spec.js`** and the **`future-advanced-coverage*.spec.js`** family can overlap conceptually (multi-role, LLM, notifications). They are tracked in [VALIDATION_DEBT_REGISTRY.md](VALIDATION_DEBT_REGISTRY.md) so backlog-style coverage is not mistaken for routine maintained proof. When adding scenarios, check for an existing spec that already proves the same **invariant**; extend or parameterize before copying a full new test.
- Older E2E that still rely on `toBeHidden` on Element Plus dialogs alone are more fragile than patterns that confirm success via network response, navigation, and table-row state. Prefer aligning those tests with the authoritative-state-first rule rather than deleting them outright.
- **`TEST_REDUNDANCY_AUDIT.md`** remains the formal gate for safe deletes; the audit's protected list intentionally keeps high-difficulty files, so do not clean up stress specs without reading that policy.

### May 2026: lessons from a full `pytest` + full school Playwright run (Linux agent)

These notes **add** to the bullets above; they do not replace the redundancy audit or protection rules.

**Further recommendations when authoring new samples**

- **MessageBox and locale**: treat delete and confirm flows as overlay-plus-confirm-button problems first.
- **Student course pages**: any test that drives **选课/退选** must scope to the **catalog table** and wait for **enabled** action buttons; see Pitfalls **33–34**.
- **Network pairing**: for idempotent POSTs that return quickly, pair **`waitForResponse` with `click`** atomically; see Pitfall **35**.
- **Personal settings**: match the **exact** primary action label (`更新密码`) for password flows; see Pitfall **36**.
- **Login helpers shared across specs**: harden `goto('/login')` against Vite navigation races; see Pitfall **37**. Any new shared helper should follow the same pattern.
- **Admin `/users` table**: `el-table` inner layout can make raw `.el-table__body` visibility checks misleading; prefer waiting for a known toolbar `data-testid` such as `users-open-create` plus a row-or-cell locator scoped to the user table, or poll the API if the scenario allows.

**Samples that were misleading or easy to mis-maintain (refine in place, not necessarily delete)**

- **`e2e-scenario-resilience.spec.js` elective dual-context cases** historically used **unscoped** `tr:has-text(courseName)` and **`button.first()`** — wrong target and silent **`force`** on disabled **退选**. The fix is **scoping + enabled waits**; other files that copy the old pattern should be aligned when touched.
- **Tier-4 password test** using **`/密码/`** on the personal-settings page was **too broad**; prefer explicit labels or testids.
- **Overlap** between **`e2e-tier4-stress-backlog.spec.js`**, **`e2e-scenario-resilience.spec.js`**, and **`future-advanced-coverage*.spec.js`** remains: before adding a new case, grep for the same **invariant** (enroll idempotency, token invalidation, mark-all-read). Parameterize or extend an existing spec when the setup cost is high, and keep the debt-registry classification aligned when a suite is promoted or trimmed.
- **Redundancy**: still governed by [TEST_REDUNDANCY_AUDIT.md](TEST_REDUNDANCY_AUDIT.md); the audit's merge-only candidates are review prompts, not an automatic delete list.

### May 2026 (second pass): pitfall-guard batch specs and `page_size` discipline

- A second small Playwright file **`tests/e2e/web-school/e2e-pitfall-guard-rails-batch2.spec.js`** was added to widen **`page_size` 422** coverage across **logs**, **points**, **parent scores/homework**, **homework submissions**, and **students** where router-specific `le` limits differ. Run it alone with:
  - `npx playwright test e2e-pitfall-guard-rails-batch2.spec.js`
- When adding more list-endpoint tests, **parameterize `(path, max_page_size)`** from code or a tiny shared table in the spec; avoid magic `200` unless you confirmed `le` for that router.
- **`e2e-pitfall-guard-rails.spec.js`** (15 cases) and **batch2** (10 cases) overlap conceptually with **`e2e-cross-cutting-tier3.spec.js`** HTTP-edge tests; new edges should **extend** batch2 or tier3, not fork a third file, unless the invariant is genuinely new.

## Pitfalls index (fast lookup)

The exhaustive narrative lives in [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md). Use this table to jump when triaging failures.

| Topic | Pitfall ids / keywords | Notes |
|-------|-------------------------|-------|
| Ports already bound (`3012`, `8012`, `8001`) | **63**, stale `node`/`uvicorn` | Kill stray listeners before full Playwright runs. |
| Course switcher / Element Plus dropdown flakiness | **64**, `clickCourseSwitcherOption`, hover-trigger menus | Prefer helpers over raw `.hover()` when CI is unstable. |
| Mock LLM profile cursor drift across scenarios | **65**, `configureMockLlm` after setup steps | Reset mock steps before multi-phase grading assertions. |
| Material chapter reorder contract (`ordered_chapter_ids`, POST vs PUT) | **66**, `material-chapters` API | Align tests with router verb + payload; seed needs ≥2 movable chapters. |
| Responsive layout regression timeouts (`boundingBox` sampling) | **67**, large `el-table` / many cards | Cap locator iteration for viewport proofs. |
| Large `users` table + Element Plus forms (`el-select`, batch move) | **68**, API-first setup | Prefer `page.request` / shared API helpers over flaky UI for bulk actions in long suites. |
| Enrollment / cross-class homework expectations vs `prepare_student_course_context`, unknown `page_size` query keys | **69** | See pitfalls doc — do not assume `student_b` lacks required enrollment; validate `Query(le=...)` on the actual router. |
| `ElMessageBox.confirm` vs large `el-dialog`, stacked overlays | **70**, `confirmElMessageBoxPrimary` | Delete/batch confirms — click `.el-message-box` primary, not generic dialog filters. |
| Many `.el-select-dropdown` nodes stay hidden (teleported poppers) | **71**, visible filter / API setup | Prefer **`POST /api/subjects`** when testing delete/list invariants, not form picker ergonomics. |
| Roster-enroll UI needs **`student_b`** **未在课** | **72**, admin `DELETE .../subjects/{id}/students/{sid}` first | Required-course sync may already enroll class roster. |
| Batch调班 on huge **`/users`** table | **73**, scroll row, wait **`users-open-batch-class` enabled** | Optional **`filterable`** input may not exist — option click still works. |
| School frontend build fails with `vite: not found` | **74**, missing `node_modules` under `apps/web/school` | Run `npm ci` before `npm run build` on fresh agents. |
| Playwright runner installed but Chromium missing | **75**, `Executable doesn't exist`, `playwright install` | Run `npx playwright install chromium` before targeted E2E. |
| Discussion Markdown demo / preview expectation drift | **76**, `discussion-markdown-preview`, `查看 Markdown + LaTeX 示例` | Demo is collapsed by default; assert preview or click toggle first. |
| Wrapper-based dual-scroll refactor broke Vue template structure | **77**, `Element is missing end tag` | Recount preserved scroll-container tags and run `npm run build` immediately. |
| Student login route reads ORM user after logging commit | **78**, `DetachedInstanceError`, expired `User` state | Cache role/class before log commit or re-query user before student-specific repair. |
| Legacy pytest module imports `main.py` too early | **79**, `table already exists`, `no such table` during isolated runs | Import `main.app` lazily inside fixtures after DB reset setup. |
| Isolated admin discussion smoke can fail inside login logging, not route logic | **80**, `operation_logs.user_id`, `ensure_admin()` | Prefer stable teacher-route regression plus helper-level admin entitlement proof. |
| `SECRET_KEY` / `REQUIRE_STRONG_SECRETS` startup failures | **57** | Weak secrets rejected when strong validation is on — see [CONFIGURATION_REFERENCE.md](../architecture/CONFIGURATION_REFERENCE.md). |

When adding a **new** recurring failure mode, append it to `TEST_EXECUTION_PITFALLS.md` first, then add one row here so agents discover it without rereading the entire pitfalls file every time.

## After Documentation Updates

For documentation-only work, full test runs are not always necessary. For changes that also touch behavior, prefer:

```bash
python -m pytest tests/behavior -q
```

and then any targeted Playwright spec that covers the affected workflow.

### Cross-platform and CI smoke expectations

### Full-suite environment policy: do not accept missing-dependency skips as final evidence

Use the focused heavy-validation policy handbook:

- [FULL_VALIDATION_ENVIRONMENT_POLICY.md](FULL_VALIDATION_ENVIRONMENT_POLICY.md)

That document is now the canonical source for:

- full-suite environment policy
- PostgreSQL zero-skip guidance
- RAR attachment environment policy
- release-grade prerequisites
- long PostgreSQL / cloud-agent environment notes

### Agent triage notes (incremental, May 2026): pitfalls, sample hygiene, residual risk

This subsection records lessons from a focused repair pass (pytest + Playwright + PostgreSQL smoke). It **adds** to earlier guidance; it does not replace [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md).

#### A. Pitfalls encountered (test-operator / harness side) and how to avoid them

- **Playwright `webServer` + Python:** Managed E2E must use the **repository `.venv`** (or `E2E_PYTHON`) so `uvicorn` sees project deps — see Pitfall 11 in [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md).
- **Element Plus roster-enroll table:** Do not use `click({ force: true })` on **selection checkboxes** then `force` the primary button; selection may not update, the submit stays **disabled**, and `waitForResponse` times out with **no POST**. Prefer a normal checkbox click, then **`expect(btn-roster-enroll-submit).toBeEnabled()`** before pairing `waitForResponse` with submit — see Pitfall 40.
- **Concurrent discussion list assertions:** The API orders by **`(created_at, id)`**. On PostgreSQL, **serial `id` order can diverge** from insert wall-clock order under concurrent threads; asserting **sorted ids alone** can false-fail. Assert **lexicographic order of `(created_at, id)`** or match the API contract explicitly.
- **`metadata.drop_all()` on PostgreSQL:** FKs declared with SQLAlchemy **`use_alter=True`** may produce **unnamed** constraints and break `drop_all` during test resets. The suite uses **`tests/db_reset.py`** (`DROP SCHEMA public CASCADE` for non-SQLite) — keep new DB resets aligned with that helper when using Postgres.
- **Parallel pytest + single `TEST_DATABASE_URL`:** Two processes resetting the same Postgres schema cause **nondeterministic failures**. Run **one** full-suite Postgres job at a time per database.

**Preferred toolchain for serious regression (principle):** install **`unrar`** (for RAR attachment regression tests) and run **`pytest` with `TEST_DATABASE_URL` pointing at PostgreSQL** so dialect-specific guards (e.g. `information_schema`, transactional visibility, uniqueness behavior) execute instead of skipping. SQLite remains the default fast loop for everyday edits.

#### B. Guidance for future test samples; redundancy and refinement

- **Confirm HTTP contracts before scripting:** Path, verb, query vs body, and **`Query(..., le=)`** bounds must match routers — copy-pasting `page_size=200` across routes causes false reds when one route allows **1000** (students) and another **100** (logs). Prefer a **small shared table** `(path, max_page_size)` in specs or grep routers once.
- **Prefer stable hooks:** `data-testid`, seeded scenario helpers (`enterSeededRequiredCourse`), and API-first assertions before fragile UI copy.
- **Overlap without deleting:** `e2e-pitfall-guard-rails*.spec.js`, `e2e-cross-cutting-tier*.spec.js`, and `future-advanced-coverage*.spec.js` intentionally overlap on invariants (pagination, auth). Before adding a file, **grep for the same invariant**; extend or parameterize rather than fork a fourth parallel guard file unless the scenario is genuinely new.
- **Admin sidebar labels (LLM triage):** As of the `2026-05` navigation consolidation in `apps/web/school/src/views/Layout.vue`, the student root entry **我的课程** was renamed **选课与进度** (route `/courses` unchanged). E2E that assert visible Chinese text for the old label may need to target **选课与进度** or rely on `page.goto('/courses')` / `data-testid` instead of menu title strings.
- **Samples that deserve refinement when touched:** Very broad Playwright regexes (e.g. `/密码/` on settings), **`textarea:first()`** on homework submit (discussion vs submission — use `homework-submit-content`), and **unscoped `tr:has-text(course)`** on **我的课程** (catalog vs cards — scope to `.elective-catalog-card`).
- **Automated redundancy policy:** Deletions still go through [TEST_REDUNDANCY_AUDIT.md](TEST_REDUNDANCY_AUDIT.md) and `tests/TEST_PROTECTION_RULES.json`; overlap is a **review signal**, not an automatic delete list.

#### C. Residual product / architecture concerns (from tests, not a confirmed bug list)

- **Startup and lifespan coupling:** Heavy bootstrap (schema repair, reconciliation, optional worker) increases **order-dependent** and **environment-sensitive** failure modes; failures often present as **health/E2E boot** issues rather than the edited feature.
- **Notification read-state under concurrency:** Dual-tab mark-all-read remains a **high flake/risk** surface; distinguish **API truth** vs **UI convergence** under automation.
- **SQLite vs PostgreSQL semantics:** Transaction boundaries, uniqueness timing, and **`SERIAL`** vs SQLite autoincrement can diverge; Postgres-only paths deserve **periodic** CI or manual smoke with `TEST_DATABASE_URL`.
- **Large orchestration modules (`llm_grading`, heavy routers):** Fixes in one branch of grading or roster flows can **couple** unexpectedly — prefer **narrow pytest** for extracted helpers when refactoring.

**New focused suites (additive):**

- `tests/postgres/test_postgres_dialect_guards.py` — dialect and transactional guards that **skip on SQLite** unless `TEST_DATABASE_URL` is PostgreSQL (see `tests/postgres/conftest.py`).
- `tests/postgres/test_postgres_llm_schema_and_policy.py` — LLM **schema shape** guards (`information_schema`, FK `ON DELETE CASCADE`, nullable attribution columns).
- `tests/postgres/test_postgres_quota_api_and_constraints.py` — fifteen **HTTP + SQL** hazard checks for quota policy, course LLM boundaries, uniqueness, and FK violations.
- `tests/e2e/web-school/e2e-agent-followup-batch.spec.js` — ten API/navigation checks complementary to pitfall rails.
- `tests/e2e/web-school/e2e-notification-header-sync-tier.spec.js` — ten **UI + API** checks for **`header-notification-badge`**, **`header-course-switch`** scoped **`sync-status`**, dropdown label convergence, and dual-tab polling (see [NOTIFICATION_HEADER_AND_REALTIME_SYNC.md](../frontend/NOTIFICATION_HEADER_AND_REALTIME_SYNC.md), **Pitfall 50** in [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)).
- `tests/e2e/web-school/e2e-notification-sync-deep-tier.spec.js` — fifteen **follow-up** checks (admin global sync vs list, teacher course-switch discipline, localStorage poison + reload paths, concurrent POST storms, cross-teacher isolation, alien `subject_id` **403**, mobile viewport, delete-under-navigation stress).
- `tests/behavior/test_notification_sync_api_edge_behavior.py` — ten **pytest** checks aligning **`GET /api/notifications`** aggregates with **`GET /api/notifications/sync-status`**, concurrent publishes/reads, and student **403** on inaccessible **`subject_id`** (depends on notifications router using **`ensure_course_access_http`** — documented in the same notification doc).
- `tests/e2e/web-school/e2e-postgres-hazard-tier.spec.js` — fifteen **API + UI** checks for global quota vs course LLM (see subsection **4** above for commands).
- `tests/e2e/web-school/e2e-agent-hazard-tier-15.spec.js` — fifteen **API-only** Playwright checks (pagination `422` boundaries, LLM admin vs student, parallel `mark-all-read`, E2E seed header gates, `forgot-password` empty username, registration disabled). Same seed contract as other web-school E2E; run **serially** (Pitfall 41).
- `tests/backend/e2e_dev/test_e2e_dev_api_hazard_tier.py` — fifteen **pytest + TestClient** checks against `/api/e2e/dev/*` and cross-actor HTTP edges using the same DB reset as `test_e2e_dev_seed.py` (no Playwright; fast in CI when `E2E_DEV_SEED_ENABLED` is toggled per test).
- `tests/security/test_security_regression.py` — twenty API security-boundary checks (admin vs teacher vs student, unauthenticated paths, invalid JWT).
- `ops/scripts/dev/provision_postgres_pytest.sh` — idempotent **throwaway PostgreSQL** role+database for zero-skip full `pytest` (see Cross-platform smoke expectations above and **Pitfall 45** in [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)).

Security hardening follow-up files added during repository normalization:

- `tests/security/test_security_hardening_followup.py` - additive backend
  security checks for recently discovered authorization gaps. The current
  high-risk block proves that class-linked `class_teacher` course visibility
  does not imply assigned-teacher management authority over subjects, roster
  operations, materials, homework, scores, attendance, notifications, or course
  LLM config.
- `tests/e2e/web-school/e2e-security-hardening-followup.spec.js` - small
  browser-backed direct-API slice for the highest-value security hardening
  cases. Use `node scripts/playwright-external-runner.cjs
  e2e-security-hardening-followup.spec.js --project=chromium` from
  `<repo>/apps/web/school`; keep this file narrower than the backend security
  suite.

#### D. Agent hazard pass (additive, May 2026): new tests, pitfalls observed, worries, coverage gaps

This subsection documents a follow-up **hazard-tier** pass that added **15 Playwright API tests** and **15 pytest E2E-dev API tests** (see file list under “New focused suites”). It is written primarily for LLM agents that need searchable, exhaustive context; humans may skim headings.

##### D1. Commands used to validate the new modules

```bash
# Fast pytest module (resets DB per test via e2e_dev fixtures; ~20s typical)
cd <REPO_ROOT>
python3 -m pytest tests/backend/e2e_dev/test_e2e_dev_api_hazard_tier.py -q

# Playwright file (requires globalSetup + E2E_DEV_SEED_TOKEN; run alone — Pitfall 41)
cd <REPO_ROOT>/apps/web/school
CI=1 E2E_PYTHON=<REPO_ROOT>/.venv/bin/python npx playwright test e2e-agent-hazard-tier-15.spec.js --project=chromium
```

##### D2. Pitfalls encountered while authoring these tests (concrete)

1. **Discussion list `page_size` vs FastAPI `Query(le=...)`:** `GET /api/discussions` declares `page_size: Optional[int] = Query(None, ge=1, le=100)`. Values **above 100** therefore return **422** before the handler’s internal clamp (`_resolve_page_size` maps into `[MIN_PAGE_SIZE, MAX_PAGE_SIZE]`). A hazard test that expected “HTTP 200 + clamped page_size” for `page_size=200` would be **wrong** for this router — the correct high-difficulty assertion on the allowed branch is `page_size=100` → **200 OK** with `page_size <= 50` in the JSON body. This mirrors the general rule in subsection **B**: always grep the router for `Query(..., le=)` before scripting pagination edge cases.

2. **`httpx` / Starlette deprecation when using `TestClient.post(..., data=bytes)`:** Passing raw form bytes via the `data=` parameter on `TestClient` can trigger `DeprecationWarning: Use 'content=<...>' to upload raw bytes`. Prefer `content=body.encode("utf-8")` with `Content-Type: application/x-www-form-urlencoded` for OAuth2-style login in pytest (fixed in `test_e2e_dev_api_hazard_tier.py::_login_form`).

3. **E2E seed token header is mandatory for every `/api/e2e/dev/*` call:** Even when `E2E_DEV_SEED_ENABLED` is true in tests, omitting `X-E2E-Seed-Token` must yield **403** (not 404) on guarded dev routes — this is part of the contract validated by `test_hz03` and the Playwright case `08`.

4. **Student quota endpoints are student-only:** Teachers receive **403** on `/api/llm-settings/courses/student-quotas` and `/api/llm-settings/courses/student-quota/{subject_id}` — do not assume instructors can “inspect student quota for debugging” without an explicit admin/teacher API (the hazard tests encode the current contract).

5. **Parallel `mark-all-read`:** After the server-side upsert hardening (Round-4 continuation), issuing **two concurrent** `POST /api/notifications/mark-all-read` from the same student token should both return **200** and leave `sync-status.unread_count === 0`. If either request fails with `IntegrityError` in logs, that is a **regression** in the batch upsert path, not a flake.

6. **Playwright scripts must match real admin LLM quota routes:** An early draft of `e2e-agent-hazard-tier-15.spec.js` called `POST /api/llm-settings/admin/quota-overrides/students`, which **does not exist** (HTTP **404**). The repository exposes **`PUT /api/llm-settings/admin/students/{student_id}/quota-override`** for a single student and **`POST /api/llm-settings/admin/quota-overrides/bulk`** for scoped bulk updates (`LLMQuotaBulkOverrideRequest`). Before writing E2E against admin quota mutations, run `rg "quota-override" apps/backend/courseeval_backend/api/routers/llm_settings.py` and copy the exact path + verb from the router.

##### D3. “Worries” from this pass (planning signals, not confirmed defects)

- **Playwright-only API tests still depend on globalSetup:** If `E2E_DEV_SEED_TOKEN` is missing, the entire describe block skips — CI must export the token for hazard-tier Playwright files the same way as `e2e-postgres-hazard-tier.spec.js`.
- **pytest `TestClient` + full app import:** The `tests/backend/e2e_dev/*` modules import `main:app` after `tests/conftest.py` sets `DATABASE_URL`. If a future refactor moves engine creation **before** env setup, imports could fail with empty URL errors — keep `tests/conftest.py` at the top of the pytest plugin order (repository root `conftest.py` is Windows-only temp hacks; `tests/conftest.py` owns `DATABASE_URL`).
- **Public registration test (`hz10` Playwright):** When `ALLOW_PUBLIC_REGISTRATION` is false (default), `POST /api/auth/register` returns **403**. If an environment enables public registration for experiments, the same test accepts **400** (validation) as an alternate success class — agents should not treat “400 vs 403” as a product regression without reading `settings.ALLOW_PUBLIC_REGISTRATION`.

##### D4. Coverage gaps explicitly *not* closed by these 30 tests

- **Parent portal** and **mobile viewport** hazard coverage remain thin; new tests target admin/teacher/student API edges on the **admin-seeded** scenario only.
- **Real SMTP / password reset email** flows are not exercised (`forgot-password` only checks empty username returns a safe 200 message).
- **Multi-worker Gunicorn** LLM worker leader election, wall-clock stale reclaim, and cross-process file locking are not represented in Playwright or the 15-pytest dev module.
- **Production `APP_ENV`** cannot be covered by the dev-seed tests; production gating remains documented in subsection **2d** (`expose_e2e_dev_api`, router dependency).

## Test Cleanup Policy

If you are considering deleting or consolidating tests, do not start from ad hoc judgment.

Read and use:

- [TEST_REDUNDANCY_AUDIT.md](TEST_REDUNDANCY_AUDIT.md)
- `tests/devtools/audit_test_redundancy.py`
- `tests/TEST_PROTECTION_RULES.json`

Policy:

- high-difficulty and high-value tests are protected first,
- exact duplicates may be considered for removal only when they are outside the protection policy,
- same-file duplicates should usually be parameterized rather than deleted,
- overlap candidates should be reviewed manually before any deletion is proposed.
