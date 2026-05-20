# Full school Playwright E2E runbook (`npm run test:e2e`)

## Purpose and audience

This document exists primarily for **LLM coding agents** and automation operators who must run **`apps/web/school`** → **`npm run test:e2e`** (full Playwright suite: all specs under `tests/e2e/web-school/`, typically **single-worker serial** per `playwright.config.cjs`). Humans may skim headings and commands; agents should read the failure triage sections before rewriting product code.

**Goal:** reduce wasted steps on environment gaps, seed/token mismatches, selector ambiguity in complex DOM, layout geometry traps, and **SQLite persistence effects** across hundreds of `resetE2eScenario()` calls.

**Implicit premise:** full-suite runs often mean **one backend process** plus a **file-backed SQLite database** reused for the entire CLI session. Many “single spec green, full suite red” outcomes are **state accumulation + harness ambiguity**, not necessarily broken business logic.

Cross-reference: [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md) (canonical numbered pitfalls), [pitfalls-playwright-and-e2e.md](pitfalls-playwright-and-e2e.md) (narrower Playwright route), [VALIDATION_WORKFLOW_AND_TOOLS.md](VALIDATION_WORKFLOW_AND_TOOLS.md), [FULL_VALIDATION_ENVIRONMENT_POLICY.md](FULL_VALIDATION_ENVIRONMENT_POLICY.md), [ENCODING_AND_MOJIBAKE_SAFETY.md](../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md).

Repo-local skill: [`../../skills/school-playwright-e2e/SKILL.md`](../../skills/school-playwright-e2e/SKILL.md)
for the condensed agent workflow when the full runbook is more detail than the
current task needs.

---

## Hard prerequisites (treat as blocking)

### Repository paths (placeholders)

- `<REPO_ROOT>` — git checkout root.
- `<ADMIN_PKG>` — `<REPO_ROOT>/apps/web/school` (the **only** directory that owns admin `package.json` for Playwright).
- `<E2E_SQLITE>` — file path derived from Playwright config (commonly `/tmp/playwright_e2e_<E2E_API_PORT>.sqlite` on Unix; see `apps/web/school/playwright.config.cjs`).

### Node / npm

Do **not** assume a minimal CI image ships Node. On Debian/Ubuntu-style agents:

```bash
sudo apt-get update
sudo apt-get install -y nodejs npm
```

Versions vary by distribution; they must satisfy `apps/web/school/package-lock.json` expectations for `npm ci`.

### Frontend install location

Run dependency install **inside** `<ADMIN_PKG>`, not only at `<REPO_ROOT>`:

```bash
cd <REPO_ROOT>/apps/web/school
npm ci
```

Anti-pattern: installing nothing under `<ADMIN_PKG>` then `npm run test:e2e` → `npm: command not found` or missing `@playwright/test` (see **Pitfall 48** in [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)).

### Playwright browsers

```bash
cd <REPO_ROOT>/apps/web/school
npx playwright install chromium
```

If the project config only targets Chromium, installing Chromium alone is usually sufficient.

### Maintained local screenshot workflow

For the homework list layout regression and similar teacher-facing screenshot
checks, use the maintained capture command instead of an ignored local helper:

```bash
cd <REPO_ROOT>/apps/web/school
npm run capture:homework-layout
```

What this does:

- starts the school backend and Vite frontend through the supported external
  runner path;
- calls `POST /api/e2e/dev/reset-scenario` with the current seed token;
- creates two teacher-homework rows sized to reproduce the wide rule-text +
  right-action-column layout pressure;
- logs in as the seeded teacher and captures `/homework`;
- writes the screenshot to `<REPO_ROOT>/pics/homework-layout-fixed.png` unless
  another output path is passed.

Local-output rule:

- `pics/` is for local image handoff and generated screenshots;
- files under `pics/` are normally not pushed to remotes unless the user
  explicitly asks for that.

For the student material-reader / course-catalog regression, use the maintained
student reading-page capture command:

```bash
cd <REPO_ROOT>/apps/web/school
npm run capture:student-material-reader
```

What this does:

- starts the school backend and Vite frontend through the supported external
  runner path;
- calls `POST /api/e2e/dev/reset-scenario` with the current seed token;
- uses the seeded reader-showcase course shape with chapter-linked homework,
  multiple chapter materials, uncategorized material, and uncategorized
  homework;
- logs in as the seeded student and captures `/materials/read/:id`;
- writes the screenshot to
  `<REPO_ROOT>/pics/student-material-reader-fixed.png` unless another output
  path is passed.

### Python backend invoked by `webServer`

Playwright `webServer` starts uvicorn. The interpreter must have **`requirements.txt`** installed:

```bash
cd <REPO_ROOT>
python3 -m pip install -r requirements.txt
```

Or set **`E2E_PYTHON=<path-to-venv-python>`** to a venv that already contains `uvicorn`, SQLAlchemy, etc. Symptom when wrong: webServer stderr shows **`No module named uvicorn`** (**Pitfall 11**).

Before launching Playwright through the managed `webServer`, run the repository
preflight from `<REPO_ROOT>`:

```bash
python ops/scripts/dev/playwright_preflight.py --json
```

On Windows, prefer the repository venv explicitly when it exists:

```powershell
.\.venv\Scripts\python.exe ops\scripts\dev\playwright_preflight.py --json
```

Treat failed checks for `e2e-python`, `backend-imports`, or
`password-hash-smoke` as environment blockers. The hash smoke protects the
`reset-scenario` seed path: `passlib==1.7.4` plus `bcrypt==5.0.0` can make seed
password hashing return `500`; restore the repository-compatible
`bcrypt==4.0.1` or otherwise prove the seed route works before debugging UI
selectors.

For release-like validation, prefer Python 3.11/3.12. Python 3.14 can be usable
for local SQLite-backed smoke only after compatible backend wheels are already
installed; the pinned `requirements.txt` set may not install unchanged because
some pins can lack Python-3.14 wheels or require local build tools.

### Seed token and CI semantics

Typical environment for a serious full run:

```bash
export CI=1
export E2E_PYTHON=/usr/bin/python3
export E2E_DEV_SEED_TOKEN=<same-value-as-backend>
```

The backend must have **`E2E_DEV_SEED_ENABLED=true`** and matching **`E2E_DEV_SEED_TOKEN`** (Playwright `globalSetup` and `tests/e2e/web-school/fixtures.cjs` call `POST /api/e2e/dev/reset-scenario` with header **`X-E2E-Seed-Token`**).

When **`E2E_DEV_REQUIRE_ADMIN_JWT`** is enabled on the API (default **`true`** for the subprocess spawned by `apps/web/school/playwright.config.cjs`), powerful `/api/e2e/dev/*` helpers (`mock-llm/configure`, `grading-state`, `process-grading`, `worker`, `mark-preset-validated`) also require an **admin Bearer**; **`fixtures.cjs`** refreshes it after each seed via **`e2e-seed-headers.cjs`**. See **Pitfall 55** in **`TEST_EXECUTION_PITFALLS.md`**.

If the token is missing or mismatched, many tests **skip** or **`resetE2eScenario` throws** — do not assume the SPA regressed.

---

## System shape: why failures chain

### Single-process backend + file SQLite

`playwright.config.cjs` sets `DATABASE_URL` to a **SQLite file** keyed by `E2E_API_PORT` (see config). Within **one** `npm run test:e2e` process:

- The database file **accumulates rows** across specs unless something deletes it.
- `POST /api/e2e/dev/reset-scenario` inserts **new** users/classes/courses every `beforeEach` in many specs.

If any uniqueness constraint collides (historically **`students.parent_code`** — see **Pitfall 52**), **`reset-scenario` returns 500**. Downstream tests then see bad `scenario.json`, wrong logins, empty tables — failures look unrelated.

### High-frequency `resetE2eScenario()`

When **`reset-scenario` fails once**, subsequent tests may operate on **stale `scenario.json`** or half-written DB state. Debugging strategy:

1. Stop asserting UI until **`POST /api/e2e/dev/reset-scenario` returns 200** consistently.
2. Read backend logs for **`IntegrityError`**, **`UNIQUE constraint`**.

---

## Pitfall catalog A–E (full-suite amplifiers)

### A — `students.parent_code` uniqueness vs seed entropy

**Symptom (backend):**

```text
sqlite3.IntegrityError: UNIQUE constraint failed: students.parent_code
```

**Symptom (Playwright):** `E2E seed failed (500)`, timeouts, “cannot find row”, blank shell.

**Concept:** `Student.parent_code` is **nullable unique**. If seed derives `parent_code` from too small a space (e.g. only 6 hex chars), repeated resets against a **persistent** SQLite file behave like a birthday paradox.

**Why single-file runs may pass:** fresh `<E2E_SQLITE>` or fewer resets.

**Fix (source-level):** ensure seed uses **high-entropy** codes (full suffix / UUID-derived), never aggressive truncation. **Pitfall 52** documents the repository fix path.

**Mitigation (environment-only):** delete `<E2E_SQLITE>` or point `DATABASE_URL` at a new path — useful to **confirm** collision hypothesis, not a substitute for code fixes.

### B — Element Plus selector ambiguity (“所属班级”, duplicate labels)

**Symptom:** wrong dropdown, no click effect, wrong API payload.

**Principle:** anchor **`getByRole('dialog', { name: /.../ })`** first, then scope `.el-form-item` / `.el-select`. Avoid page-wide `filter({ hasText: '所属班级' })` when the same literal appears in **table headers** and **dialogs**.

### C — Mobile sidebar geometry vs real CSS

`boundingBox()` width assertions can fail if `el-aside` keeps **min-width** or translation hides visually without collapsing layout width. Prefer **explicit CSS classes** for collapsed state over fragile inline-style substring selectors.

### D — `boundingBox()` over too many nodes

`locator('article.course-card')` may match **many** nodes (cached routes, hidden lists). Iterating all `nth(i)` → **timeout**.

**Pattern:** `locator(...).filter({ visible: true })`, cap **N** iterations (sampling), assert structural intent not exhaustive enumeration.

### E — Strict mode / overly broad `getByText(/LLM/)`

Multiple “LLM” strings on one page → strict violations. Anchor `.quota-card` or add **`data-testid`** in product when extending tests.

---

## Flaky in full-suite context

Do not immediately blame “browser randomness” when:

- Seed failed upstream (**reset 500**).
- Overlays/MessageBox from prior step still mounted.
- Data missing because **earlier spec** aborted DB seed.

**Triage order:**

1. Last successful **`reset-scenario`** / **`scenario.json`** freshness.
2. API status codes / backend traceback.
3. Locator scope / waits.
4. Only then suspect nondeterministic UI.

---

## Artifacts to collect on failure

- `<ADMIN_PKG>/test-results/**/error-context.md`
- `trace.zip` paths printed by Playwright
- Backend stdout: **`IntegrityError`**, SQLAlchemy tracebacks
- Manual `curl` / `fetch` to **`POST /api/e2e/dev/reset-scenario`** with **`X-E2E-Seed-Token`**

---

## Short execution checklist (no calendar estimates)

1. Node/npm present; **`npm ci`** in `<ADMIN_PKG>`.
2. **`npx playwright install chromium`**.
3. **`pip install -r requirements.txt`** on **`E2E_PYTHON`** interpreter.
4. Export **`CI`**, **`E2E_PYTHON`**, **`E2E_DEV_SEED_TOKEN`** aligned with backend env.
5. If investigating cumulative DB issues: try a **fresh** `<E2E_SQLITE>` path once as a control experiment.
6. On **`IntegrityError`**: fix seed/uniqueness — avoid mass product changes first.
7. Selectors: dialog name → form scope.
8. Geometry: visible + capped scans.
9. Text: narrow matchers / `data-testid`.

### Port / process hygiene (Pitfall 63)

`playwright.config.cjs` starts **two** `webServer` processes (API on `<E2E_API_HOST>:<E2E_API_PORT>`, Vite UI on `<E2E_UI_PORT>`). If a prior run was interrupted, **`node`** (Vite) or **`uvicorn`** may still listen; the next `npm run test:e2e` fails immediately with **`… is already used`** on **`8012`** or **`3012`** (placeholders; actual ports come from **`E2E_API_PORT`** / **`E2E_UI_PORT`**).

**Recover:** use **`lsof -i :3012`** and **`lsof -i :8012`** (when **`ss`** / **`fuser`** are absent on minimal images), then **`kill -9 <pid>`**.

**Alternative:** export **`PLAYWRIGHT_USE_EXTERNAL_SERVERS=1`** and launch API + UI yourself so ports are explicit.

### Header course switcher interactions (Pitfall 64)

`Layout.vue` uses **`el-dropdown` `trigger="hover"`** for **`data-testid="header-course-switch"`**. Tests that **`hover()`** then click menu text often flake with **element not visible / not stable** because Element Plus teleports the dropdown.

**Harness:** **`clickCourseSwitcherOption(page, courseLabel)`** in **`tests/e2e/web-school/future-advanced-coverage-helpers.cjs`** opens via **click**, anchors **`.course-dropdown-menu.filter({ visible: true })`**, then **`.click({ force: true })`** on **`.course-option`**. Avoid **`scrollIntoViewIfNeeded`** on poppers when animations fight stability.

### Shared mock-LLM cursor across specs (Pitfall 65)

In-memory mock profiles in **`e2e_dev.py`** advance on **every** **`POST .../mock-llm/<profile>/v1/chat/completions`**. Full-suite order plus discussion traffic can leave the cursor past your **`steps`** array; the handler then returns the default **`discuss_<suffix>:ok`** text instead of an expected Chinese comment.

**Spec pattern:** after asserting the **first** grading outcome, call **`configureMockLlm`** again with **only** the step(s) needed for the **next** grading wave (see **`e2e-homework-comment-cover-tier4.spec.js`** case **08**).

### `ElMessageBox` vs `el-dialog`, `el-select` visibility, roster, batch-class (Pitfalls 70–73)

Full-suite passes (May 2026) reinforced that **`ElMessageBox.confirm`** must not be driven by the same locators as large **`el-dialog`** course editors. The shared harness uses **`confirmElMessageBoxPrimary`** in **`tests/e2e/web-school/future-advanced-coverage-helpers.cjs`**.

Roster table selection for **从花名册进课** may require a prior admin **`DELETE /api/subjects/{id}/students/{studentId}`** so **`student_b`** is not already **已在课** after **`sync_course_enrollments`**.

**Batch调班** on **`/users`** with a large SQLite user count: scroll the target **`tr`**, assert **`users-open-batch-class`** is **enabled** before opening the dialog, then select the target class from a **visible** **`el-select-dropdown`**.

---

## Command reference

Full Playwright (school package):

```bash
cd <REPO_ROOT>/apps/web/school
CI=1 E2E_PYTHON=/usr/bin/python3 E2E_DEV_SEED_TOKEN=<seed> npm run test:e2e
```

Single spec (debug):

```bash
cd <REPO_ROOT>/apps/web/school
npx playwright test <spec-filename>.spec.js --project=chromium
```

Parent portal targeted spec through the external runner:

```bash
cd <REPO_ROOT>/apps/web/school
node scripts/playwright-external-runner.cjs e2e-parent-portal-hardening.spec.js --project=chromium
```

The external runner starts the school Vite app by default. It also starts the
parent portal Vite app when the spec name contains `parent-portal` or when
`E2E_PARENT_UI=1` is set. Override the parent port with
`E2E_PARENT_UI_PORT`; Playwright reads the resulting base URL from
`PLAYWRIGHT_PARENT_BASE_URL`.

Full pytest (separate from Playwright; complementary):

```bash
cd <REPO_ROOT>
COURSEEVAL_AUTO_PG_TESTS=1 python3 -m pytest tests/
```

See [FULL_VALIDATION_ENVIRONMENT_POLICY.md](FULL_VALIDATION_ENVIRONMENT_POLICY.md) for PostgreSQL provision and zero-skip expectations, and [DEVELOPMENT_AND_TESTING.md](DEVELOPMENT_AND_TESTING.md) only for the broader local testing handbook.
