# Test Suite Map

## Purpose

This document explains how the repository test suites are organized after the domain-oriented cleanup of the `tests/` tree.

It is intended for contributors and LLM coding agents who need to answer questions such as:

- which tests should be read first for a given feature,
- which suites are fast versus operationally fragile,
- which files are reusable helpers versus actual pytest entrypoints,
- which categories are most likely to fail because of environment issues rather than product regressions.

For concrete historical execution records, use the CSV tables in this directory. Those tables record per-target category, canonical command, last branch/commit, pass count, run count, and run-by-run results. [TEST_EXECUTION_LEDGER.md](TEST_EXECUTION_LEDGER.md) remains a stable Markdown entry point. This map answers **what exists and when to run it**; the ledger tables answer **what was actually run and what happened**.

## Top-Level Test Layout

  ```text
  tests/
    backend/                  focused backend pytest modules grouped by domain
    behavior/                 high-level multi-actor and workflow pytest suites
    postgres/                 PostgreSQL-only guards (skip unless Postgres: TEST_DATABASE_URL or COURSEEVAL_AUTO_PG_TESTS=1 after provision script)
    security/                 API authorization / abuse-edge regression (roles, tokens)
    e2e/web-school/            Playwright browser coverage for the school SPA
    frontend/                 lightweight frontend Node tests without backend/browser startup
    devtools/                 maintenance scripts that scan or rewrite test artifacts (not pytest-discovered; filenames must not start with `test_`)
    fixtures/                 static files used by tests
    scenarios/                shared scenario builders and stress helpers
    conftest.py               repository test environment defaults
  ```

### `tests/devtools/` (maintenance, not pytest discovery)

This subdirectory holds **repository-maintained utilities** that operate on files under `tests/` but are **not** pytest test modules.

Rules agents should follow:

- Filenames **must not** match `python_files = test_*.py` from [`pytest.ini`](../../pytest.ini), otherwise pytest will try to import them as tests.
- The redundancy auditor explicitly skips everything under `tests/devtools/` when classifying test inventory so the script does not count itself as coverage inventory noise.
- Prefer placing **deployment-facing** shell scripts in [`ops/scripts/`](../../ops/scripts/) instead of here; `tests/devtools/` is for analyzers, generators, and other tooling tightly coupled to the test corpus.

Current utilities:

- [`tests/devtools/audit_test_redundancy.py`](../../tests/devtools/audit_test_redundancy.py) — regenerates [`TEST_REDUNDANCY_AUDIT.md`](TEST_REDUNDANCY_AUDIT.md).
- [`tests/devtools/README.md`](../../tests/devtools/README.md) — short rules, commands, and cross-links for agents.

### `tests/frontend/` (Node-based frontend checks)

This subdirectory holds focused frontend tests that do not start FastAPI, Vite,
or a browser. Use it for shared utility contracts where full Playwright would
be too expensive or too environment-sensitive.

Current tests:

- [`tests/frontend/school/markdown_latex_and_clipboard.test.mjs`](../../tests/frontend/school/markdown_latex_and_clipboard.test.mjs) checks admin Markdown/LaTeX preprocessing, copy fallback behavior, and Playwright preflight JSON output.

Run from the repository root:

```bash
node --test tests/frontend/school/markdown_latex_and_clipboard.test.mjs
```

### Diff selector support files

The first-version diff-based validation selector uses a machine-readable target
registry:

- [`tests/TEST_SELECTION_TARGETS.json`](../../tests/TEST_SELECTION_TARGETS.json)

The executable selector lives outside `tests/` because it is a repository-wide
developer command:

- [`ops/scripts/dev/select_validation_targets.py`](../../ops/scripts/dev/select_validation_targets.py)
- [`ops/scripts/dev/validation_history.py`](../../ops/scripts/dev/validation_history.py)

The registry maps repository-relative changed paths to validation targets such
as focused backend pytest files, school frontend build, targeted Playwright, full
Playwright consideration, PostgreSQL package tests, and full PostgreSQL pytest.
It now also carries coverage tags, target review reasons, and high-blast-radius
fallback rules so selector output can distinguish `acceptable`, `needs_review`,
and `not_sufficient` non-full validation states. It complements, but does not
replace, the CSV execution ledger in this directory. The ledger
records observed executions; the registry recommends what to run next.

The executable runner for one target lives next to the selector:

- [`ops/scripts/dev/run_validation_target.py`](../../ops/scripts/dev/run_validation_target.py)
- [`ops/scripts/dev/run_validation_profile.py`](../../ops/scripts/dev/run_validation_profile.py)

The runner consumes the same registry, executes one target id, and writes local
artifacts under `.agent-run/logs/`. It also appends ignored JSONL history to
`.agent-run/validation-history.jsonl` so future selector runs can distinguish
fresh, stale, skipped, and blocked local evidence for the current changed-path
snapshot. For pytest targets, it adds ignored JUnit XML output when the command
does not already request one and records testcase-level totals and statuses in
the local artifacts. It intentionally does not update the committed ledger
automatically. Use it when a selector recommendation should be turned into a
local run record with stdout/stderr logs and a ledger snippet that can be
manually translated into CSV rows.

Failure triage should start with the pitfall lookup helper:

- [`ops/scripts/dev/search_pitfalls.py`](../../ops/scripts/dev/search_pitfalls.py)

Use it before classifying command/test/environment failures or changing product
code. It fuzzy-searches the pitfall Markdown, structured pitfall index,
troubleshooting notes, development testing guidance, and repo-local skills so
agents can reuse known mitigations instead of rediscovering them.

Registry commands should use portable command names where practical. The runner
normalizes `python` to the repository virtualenv when present, falls back to the
current interpreter, and maps `npm`/`npm.cmd` plus `npx`/`npx.cmd` to the
platform-appropriate executable. Plain `--dry-run` records the resolved plan
without environment checks; use `--dry-run --preflight` when the goal is to
prove that the selected tools are installed without executing the test command.

The profile runner provides a small orchestration layer over the target runner.
Its first profiles are `static` and `selector-recommended`. It defaults to
running only static/targeted targets and skips targets that require explicit
operator review unless `--include-review-targets` is passed.

When adding or moving test files, update this registry if the moved file should
influence future diff-based validation recommendations. If the selector output
has unmatched paths for a real source change, either add a registry rule or
choose a broader profile manually and document the reason.

CI workflow changes under `.github/workflows/` are currently mapped to static
text/tooling validation. That is enough for lightweight YAML and documentation
edits, but changes that materially alter cloud test scope should also be
reviewed against this map and the execution ledger so local and cloud validation
expectations do not drift. The lightweight GitHub Actions workflow keeps
selector tooling, backend quick pytest, admin build, and parent build as
separate jobs so infrastructure failures and product/test failures remain
distinct in PR status.

## Category Overview

### `tests/backend/`

This directory contains focused backend pytest modules. These tests usually exercise one domain at a time and are the best first stop when a code change is narrow.

Subgroups:

- `tests/backend/llm/`
  - LLM grading worker behavior
  - endpoint routing
  - quota logic
  - payload normalization
  - attachment format extraction
- `tests/backend/homework/`
  - homework lifecycle rules
  - submission limits
  - grading and appeal flows
  - markdown visibility behavior
  - homework vs course class integrity (`test_homework_course_class_integrity.py`)
- `tests/backend/courses/`
  - course access
  - roster versus course enrollment behavior
  - required versus elective rules
  - **`subject_class_links` regression:** `test_subject_multi_class_links.py`
  - **student course-catalog / elective self-enroll** must track **schoolwide elective** policy (`test_student_course_catalog_behavior.py`, `test_student_elective_catalog_and_quota.py`; updated 2026-05 when electives stopped mirroring `Subject.class_id`)
- `tests/backend/roster/`
  - roster enroll operations
  - batch class changes
  - student-user synchronization
  - import behavior
- `tests/backend/files/`
  - attachment serving and download authorization
  - upload compliance allow-list and sniffing (`test_attachment_upload_compliance.py`)
- `tests/backend/content_format/`
  - optional `content_format` / `body_format` persistence on homework, submissions, discussions, notifications

### HTTP client UX (school SPA)

See [HTTP client slow-response busy hint](../frontend/HTTP_CLIENT_SLOW_RESPONSE_BUSY_HINT.md) for the 3s “系统正忙，请等待。” message on `http` / `httpQuiet` / `httpPublic`.
- `tests/backend/scores/`
  - score composition and derived grading behavior
- `tests/backend/points/`
  - points routes and points-related permissions
- `tests/backend/system/`
  - production settings and environment constraints
- `tests/backend/e2e_dev/`
  - E2E seed helpers
  - demo course bootstrap behavior
  - LLM mock/reset support used by browser flows
- `tests/backend/integration/`
  - Cross-cutting API smoke tests that lock generic HTTP contracts (health, auth envelope, homework ACL, rubric redaction) — see `test_core_api_surface.py` and [TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md](TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md)
- `tests/backend/user_profile/`
  - profile and avatar flows
- `tests/backend/auth/`
  - forgot-password flow and admin notification content (`test_forgot_password_flow.py`)
  - public registration validation when `ALLOW_PUBLIC_REGISTRATION` is enabled (`test_public_registration_validation.py`)
- `tests/backend/learning_notes/`
  - learning-note visibility, owner-only mutation, course-bound vs all-authenticated public notes, note-local copied outline/resources, note discussion metadata, and attendance date parsing regressions that support the embedded teaching-calendar workflow (`test_learning_notes_api.py`)

### `tests/behavior/`

This directory contains higher-level pytest suites that combine multiple features, roles, or temporal phases in one scenario.

Typical characteristics:

- longer setup than focused backend tests,
- more cross-feature coupling,
- better at catching regressions in state convergence,
- harder to triage when they fail because one bug can surface deep into the scenario.

### `tests/e2e/web-school/`

This directory contains Playwright browser coverage for the school frontend.

These tests are the closest to a user-visible workflow because they exercise:

- backend startup,
- frontend startup,
- E2E seed/reset helpers,
- browser automation,
- UI-to-API convergence.

Additional targeted suite: **`e2e-discussion-cover-llm-tier3.spec.js`** — discussion LLM (`invoke_llm`), long reply preview (3 logical lines + expand), and course cover (API + UI). Run only that file with `npx playwright test e2e-discussion-cover-llm-tier3.spec.js` from `apps/web/school` when iterating on those features.

Another targeted suite: **`e2e-homework-comment-cover-tier4.spec.js`** (15 cases) — homework submission table **content/comment preview** truncation, **LLM grading** long comments + regrade + 429 recovery, **multi-role** API guards, and **course cover** flows (teacher/school UI + API). **Case 01** now expects **「详情」** to open the full-page review route (`/homework/:id/submissions/:submissionId`) and asserts the long teacher comment in `.review-comment-card` instead of a dialog. Run alone with `npx playwright test e2e-homework-comment-cover-tier4.spec.js` from `apps/web/school`.

Another targeted suite: **`e2e-homework-appeal-stale-tabs.spec.js`** (4 cases) — teacher stale-tab homework-appeal convergence on the full-page submission review route, including terminal reject-vs-resolve conflicts, terminal resolve-vs-reject conflicts, review-save interleave with appeal resolution, and reload/list-return checks that a terminal appeal detail no longer exposes stale actionable controls. Run alone with `node scripts/playwright-external-runner.cjs e2e-homework-appeal-stale-tabs.spec.js --project=chromium` from `apps/web/school`.

Another targeted suite: **`e2e-core-flows-smoke.spec.js`** — ten stability-focused journeys (invalid login stays on `/login`, student homework grid contains seeded title, teacher materials/notifications routes, admin user grid). Run alone with `npx playwright test e2e-core-flows-smoke.spec.js` from `apps/web/school`.

Another targeted suite: **`e2e-course-ui-markdown-reader.spec.js`** (12 cases) — **`subject_id` enrollment counts** surfaced via **学生管理** header (dashboard UI removed), **Markdown LaTeX demo** (scoped `MarkdownEditorPanel`), **sidebar** controls, **materials** layout + **MaterialRead** + discussion card, and historical **`/teaching-calendar`** deep-link coverage. Current product behavior redirects `/teaching-calendar` to **`/attendance`**; the teaching calendar is embedded inside the attendance page instead of appearing as a separate sidebar item, and no standalone `TeachingCalendarPage.vue` remains. Student sidebar remains flat (no 「课程学习」 parent — items match former children; regression: submenu title count `0`). Run alone with `npx playwright test e2e-course-ui-markdown-reader.spec.js` from `apps/web/school`.

Additive API-heavy tier after documentation alignment: **`e2e-docs-gap-tier15.spec.js`** — **`/api/discussions`** validation (`page_size`, scope mismatch, **`invoke_llm`** teacher acceptance), cross-class homework submission guards, orphan-course homework list for **class_teacher**, **`page_size`** discipline (**students** list **`le=1000`**), dual-gate mock LLM + **`process-grading`**, end-to-end mock grading drain, **`sync-status`** shape. Run alone with `npx playwright test e2e-docs-gap-tier15.spec.js` from `apps/web/school`.

Additive newer-surface tier: **`e2e-learning-notes-attendance-cover-tier20.spec.js`** (20 cases) — learning-note private/public visibility, all-authenticated public notes when `subject_id` is null, course-bound public notes, copied course outline/material snapshots, copied-note editing (`parent_id: null`, `chapter_id: null`, attachment clearing), note discussion metadata, `page_size` validation, learning-notes UI tabs/default-private dialog, student course-card cover visibility, `/teaching-calendar` redirect to embedded attendance calendar, and course/date-scoped attendance list behavior. Run alone with `npx playwright test e2e-learning-notes-attendance-cover-tier20.spec.js --project=chromium` from `apps/web/school`.

They also have the highest dependence on the local execution environment.

This directory also contains the **`future-advanced-coverage`** pair ? thirty higher-difficulty Playwright scenarios split across two files. They still run under the same Playwright package, but governance now classifies them as **explicit backlog debt** rather than routine maintained proof; see [VALIDATION_DEBT_REGISTRY.md](VALIDATION_DEBT_REGISTRY.md).

Files:

- `tests/e2e/web-school/future-advanced-coverage.spec.js` — scenarios **1–15**
- `tests/e2e/web-school/future-advanced-coverage-2.spec.js` — scenarios **16–30**

Helpers: `tests/e2e/web-school/future-advanced-coverage-helpers.cjs`

Runtime contract: same `apps/web/school/playwright.config.cjs`, `tests/e2e/web-school/global-setup.cjs`, `POST /api/e2e/dev/reset-scenario`, and `E2E_DEV_SEED_TOKEN` as other school E2E specs.

Targeted run from `apps/web/school`:

```bash
npx playwright test future-advanced-coverage.spec.js future-advanced-coverage-2.spec.js
```

#### Scenario index (`future-advanced-coverage*.spec.js`)

**Part I (`future-advanced-coverage.spec.js`)**

1. Student stale-tab homework resubmit after teacher hard review — one authoritative attempt history.
2. Teacher concurrent material chapter reorder from two tabs — one final chapter sequence.
3. Admin delete-class blocked while roster/course references exist.
4. Teacher LLM endpoint failover during async grading — one completed task, no orphan queue rows.
5. Student dual-tab score appeal — one pending appeal and one notification chain.
6. Admin batch user activation with stale filters — final active state matches API.
7. Student notification deep-link with corrupted `selected_course` — rebind to accessible course only.
8. Teacher concurrent max-submission edit vs student submit — cap enforcement after race.
9. Parent portal vs student web-school notification read-state isolation (per policy).
10. Teacher duplicate attendance save retries — one row per student/date.
11. Admin semester switch plus stale score composition tab — one valid composition.
12. Teacher points award vs student redemption race — consistent balance and ranking.
13. Student attachment replace after flaky upload — one surviving attachment reference.
14. Admin dual-tab system settings save — final branding consistent, no mixed fields.
15. Teacher targeted notification — privacy across student, classmate, admin, parent.

**Part II (`future-advanced-coverage-2.spec.js`)**

16. Teacher dual-tab material publish vs delete — one surviving material record.
17. Student stale homework detail after teacher unpublish — safe recovery.
18. Admin class rename during teacher session — labels update, course identity stable.
19. Per-course LLM policy change while worker processing — old vs new task config separation.
20. Student plus parent concurrent visibility after appeal reopen — permissions consistent.
21. Teacher rapid notification create/edit/delete — no duplicate unread counters on student dashboard.
22. Admin orphan user plus roster sync race — no duplicate student rows after reconcile.
23. Teacher score composition formula change while student scores open — one computed total everywhere.
24. Teacher materials attachment replace under flaky network — one downloadable file, no stale section ref.
25. Student stale elective selection after backend block — self-enroll affordance correct.
26. Teacher bulk attendance plus notification from parallel tabs — one batch, correct fanout.
27. Admin repeated demo-seed reset during session — safe re-login, no cross-scenario bleed.
28. Student avatar replace plus logout/login across tabs — one final avatar URL.
29. Teacher pinned notification reorder/unpin race — deterministic student list order.
30. Teacher stale grade-candidate page after manual override — obsolete candidate not resurrected.

### `tests/scenarios/`

This directory contains reusable helper modules rather than primary pytest discovery targets.

Current examples:

- `llm_scenario.py`
  - common login helpers
  - grading-course setup helpers
  - scenario factories reused by many backend and behavior tests
- `material_flow.py`
  - helper setup for material, chapter, and notification flows

Historical note (cleanup `2026-05-05`):

- the removed `llm_pressures.py` helper under `tests/scenarios/` was deleted after verification that **nothing imported it**
  (no test module, script, or documentation referenced its symbols). The repository already
  exercises heavy LLM scenarios through `tests/backend/llm/test_llm_stress_scenarios.py`,
  `test_llm_concurrency_scenarios.py`, and related behavior suites. If a future maintainer
  needs a dedicated pressure harness again, reintroduce it as an imported module with at least
  one pytest entrypoint or an explicit import from an existing test file so it cannot rot unseen.

Import paths:

- Prefer **`from tests.scenarios.llm_scenario import ...`** and
  **`from tests.scenarios.material_flow import ...`** in new code.
- Root-level compatibility stubs for `llm_scenario.py`, `material_flow.py`,
  and `llm_pressures.py` were removed in the same cleanup; older branches that still
  reference those paths must be updated when merged forward.

RAR attachment regression assets:

- Binary fixtures under **`tests/fixtures/llm_rar/`** (`unencrypted_nested_zip.rar`,
  `password_protected.rar`) supply archives for `tests/backend/llm/test_llm_attachment_formats.py`
  so those tests run **without** shelling out to the **`rar`** CLI at test time. Regeneration
  requires **`rar`** on `PATH` (same commands historically embedded in the test body); keep
  committed bytes UTF-8-clean and treat the directory as test assets, not runtime product data.

Another targeted suite: **`e2e-agent-followup-batch.spec.js`** (10 cases) — additive API/navigation checks (pagination boundaries, health, settings public, course entry). Run alone with `npx playwright test e2e-agent-followup-batch.spec.js` from `apps/web/school`.

Another additive hazard file: **`e2e-agent-hazard-tier-15.spec.js`** (15 cases) — API-only checks for authz edges, LLM admin vs student boundaries, parallel `mark-all-read`, and E2E dev seed header gates. Same globalSetup contract as `e2e-postgres-hazard-tier.spec.js`; run serially (Pitfall 41).

### Red-team E2E sample corpus

Targeted red-team browser attacks that need to be replayed by arbitrary sample
blocks live as one Playwright spec file per sample under
`tests/e2e/web-school/`. Keep this granularity: each file is independently
schedulable by WAI-VALID custom sample blocks, so future agents can compose
small concurrent regression sets without serial ad hoc E2E runs.

Current red-team sample files:

- `e2e-redteam-auth-login-me-failure-rollback.spec.js`: forces
  `/api/auth/login` to succeed and the following `/api/auth/me` bootstrap to
  fail, then verifies the browser returns to `/login` without leaving `token`,
  `user`, or `selected_course` in localStorage.
- `e2e-redteam-notification-same-context-tabs.spec.js`: logs the same student
  into two pages sharing one browser context and verifies a second-tab login
  does not invalidate the first tab or prevent notification badge convergence.
- `e2e-redteam-selected-course-cache-poison-badge.spec.js`: poisons
  `selected_course` with a cross-class `class_id` and verifies the student
  notification badge does not expand to another class broadcast.
- `e2e-redteam-parallel-login-context-isolation.spec.js`: logs five seeded
  actors into isolated browser contexts concurrently and checks role/token
  isolation.

Registered target:
`school.e2e.redteam_auth_notification_samples` runs these samples through the
foreground WAI-VALID supervisor with `self-organized-e2e-redteam`,
`concurrency=10`, and `regression_mode=light`. For ad hoc red-team regression,
compose the desired spec paths into a sample file or repeated `--sample`
arguments and use the same WAI-VALID custom block path; do not run a series of
these samples serially.

### Coverage gap addressed in May 2026 (notification header badge + sync-status)

Earlier Playwright suites exercised **`POST /api/notifications`** and list/mark-read flows extensively, but **did not systematically assert** the school SPA header surfaces documented in [NOTIFICATION_HEADER_AND_REALTIME_SYNC.md](../frontend/NOTIFICATION_HEADER_AND_REALTIME_SYNC.md):

- `data-testid="header-notification-badge"` (Element Plus badge content vs `sync-status.unread_count`),
- course-scoped unread when **`header-course-switch`** changes `selectedCourse` (maps to `subject_id` on `syncStatus`),
- convergence after **`window.dispatchEvent(new Event('focus'))`** (same hook as user returning to the tab — exercises `pollNotificationSync` without waiting `DEFAULT_NOTIFICATION_POLL_INTERVAL_MS`).

**New Playwright module (10 cases):** `tests/e2e/web-school/e2e-notification-header-sync-tier.spec.js`

**Deeper follow-up (24 cases):** `tests/e2e/web-school/e2e-notification-sync-deep-tier.spec.js` — admin global totals vs list, teacher explicit course switch before badge asserts, corrupt `selected_course` healing, concurrent publishes, cross-teacher isolation, mobile viewport, reload-based cold poll, delete race on `/notifications`, multi-class course badge isolation, admin-only global notification write scope, notification target-user denial, UI composer course/class scope coverage, and explicit target-clearing update semantics. Cases 23-24 prove `target_student_id: null` clears a stored target and updates the course-scoped badge, while a student-to-user target switch without clearing the old target is rejected. Run alone:

```bash
cd <REPO_ROOT>/apps/web/school
CI=1 E2E_PYTHON=<python-with-requirements> E2E_DEV_SEED_TOKEN=<seed> \
  npx playwright test e2e-notification-sync-deep-tier.spec.js --project=chromium
```

- Run from `<REPO_ROOT>/apps/web/school` (same `playwright.config.cjs` as other school E2E):

```bash
cd <REPO_ROOT>/apps/web/school
CI=1 E2E_PYTHON=<python-with-requirements> E2E_DEV_SEED_TOKEN=<seed> \
  npx playwright test e2e-notification-header-sync-tier.spec.js --project=chromium
```

**New behavior pytest module (10 cases):** `tests/behavior/test_notification_sync_api_edge_behavior.py`

- Stresses **HTTP contract alignment** between `GET /api/notifications` aggregates and `GET /api/notifications/sync-status`, plus concurrent writers/readers and **403** when a student passes a **foreign** `subject_id`.
- Uses the standard `tests/behavior/conftest.py` reset (SQLite by default); run:

```bash
cd <REPO_ROOT>
python3 -m pytest tests/behavior/test_notification_sync_api_edge_behavior.py -q
```

Operational notes for agents authoring similar specs live under **“Pitfall 50”** in [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md) (secondary-browser-tab login, disabled course-card affordances after `/courses`, badge vs API race windows).

### `tests/postgres/`

Small pytest package gated by dialect: when the effective engine is **not** PostgreSQL, tests **skip** at module level (set `TEST_DATABASE_URL`, or on Linux/macOS after `ops/scripts/dev/provision_postgres_pytest.sh` set **`COURSEEVAL_AUTO_PG_TESTS=1`** so `tests/conftest.py` auto-selects the standard throwaway URL). Use for `information_schema`, transactional visibility, and uniqueness smoke that SQLite does not model the same way. See `tests/postgres/conftest.py` plus `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md` for the PostgreSQL/zero-skip lane and `docs/testing/DEVELOPMENT_AND_TESTING.md` only for the broader harness handbook.

Files:

- `test_postgres_dialect_guards.py` — broad dialect and API smoke guards.
- `test_postgres_llm_schema_and_policy.py` — **LLM quota schema** guards (`llm_global_quota_policies`, `course_llm_configs` column set, preset FK `ON DELETE CASCADE`, `get_or_create_global_quota_policy` ORM read).
- `test_postgres_quota_api_and_constraints.py` — **HTTP + SQL hazard** module (admin `422` paths, auth edges, duplicate `course_llm_config_endpoints`, enrollment uniqueness, orphan FK attempts). Uses the shared `client` fixture from `tests/postgres/conftest.py` (PostgreSQL-only autouse reset).

### `tests/security/`

API-level **authorization and abuse-edge** regression tests (unauthenticated vs role boundaries, admin-only routes, cross-tenant homework/parent-code actions, invalid tokens). Uses the same DB reset contract as `tests/behavior/`. Run targeted: `python -m pytest tests/security/ -q`.

`tests/security/test_security_hardening_followup.py` is the additive hardening
file for high-risk authorization edges discovered during repository
normalization. As of May 2026 it includes the `class_teacher` read-vs-manage
boundary for teacher-owned visible courses:

- course update/delete/cover/roster management;
- material and homework creation;
- score writes, weights, grade schemes, and score-appeal responses;
- attendance writes and batch attendance;
- course notification publishing;
- discussion deletion and course-material chapter placement/reorder/homework
  links;
- parent-code revocation for foreign-class students that are only visible
  through a linked course;
- parent-code batch generation skipping class-linked foreign-class students;
- parent portal reads for scores/stats staying bound to the linked student, and
  homework/notification reads requiring matching `CourseEnrollment` for
  subject-scoped rows;
- parent-code rate limiting, expired-code semantics, regeneration/revocation
  lifecycle, and the distinction between regular `teacher` course-based
  parent-code management and `class_teacher` direct-class management;
- notification read-state authorization reusing list visibility, including
  hidden targeted notices, teacher-targeted notices, unenrolled elective
  notices, subject-scoped list/sync/mark-all-read excluding unrelated-class
  broadcasts, and mark-all-read creating rows only for visible notifications;
- global notification write scope, including rejecting teacher/class-teacher
  attempts to create or update into `subject_id IS NULL` plus
  `class_id IS NULL` while preserving admin global broadcast behavior;
- notification target-scope validation, including rejecting malformed
  `class_id=0` global writes, rejecting dual student/user targets, requiring
  targeted students to match the selected class/course enrollment, limiting
  non-admin `target_user_id` to the caller, preserving admin/self-target
  success cases, distinguishing omitted update fields from explicit `null`
  clears, requiring explicit old-target clearing when switching target type,
  and rejecting non-admin attempts to clear scope/target into a global notice;
- parent-code batch generation deduplicating repeated student ids before
  code rotation and preserving the direct-class-only class-teacher boundary;
- score-appeal second submission after resolved/rejected history keeping at
  most one pending appeal per component;
- dashboard subject statistics, rankings, trends, and subject analysis staying
  scoped to the requested subject;
- course LLM config management, including stale browser-selected-course cache
  attempts in the paired Playwright spec.

When adding a new course-owned mutation endpoint, add the backend assertion here
first. The paired browser-backed direct-API guard is
`tests/e2e/web-school/e2e-security-hardening-followup.spec.js`; keep that file
small and reserve it for high-value API edges that benefit from the managed
Playwright seed/login path. The paired spec currently also covers parent-code
read leakage for same-class unenrolled elective homework and notifications.

Parent SPA browser coverage lives in
`tests/e2e/web-school/e2e-parent-portal-hardening.spec.js`. It runs from the
school Playwright package but starts the parent Vite app through
`scripts/playwright-external-runner.cjs` when this spec name is passed. Run it
from `apps/web/school` with:

```bash
node scripts/playwright-external-runner.cjs e2e-parent-portal-hardening.spec.js --project=chromium
```

The parent portal spec covers successful binding, same-class unenrolled elective
homework/notification hiding, invalid-code login behavior, revoked-code
protected-route session cleanup, and isolation between student JWT
notification read-state and parent notification lists. It also covers clearing
stale local storage when an invalid login is attempted and when a protected
route sees a partial parent binding without `student_id`.

## Recommended Reading Order By Task

### If you are changing LLM logic

Read and run in this order:

1. `tests/scenarios/llm_scenario.py`
2. `tests/backend/llm/`
3. `tests/backend/homework/test_homework_llm_grading.py`
4. `tests/behavior/test_*llm*`
5. `tests/e2e/web-school/homework-llm-routing.spec.js`

### If you are changing course or roster behavior

Read and run in this order:

1. `tests/backend/courses/`
2. `tests/backend/roster/`
3. `tests/behavior/test_multi_actor_timeline_behavior.py`
4. `tests/e2e/web-school/roster-and-users.spec.js` — roster enroll + paste/file import dialogs + admin batch class + assertion that **用户管理** does **not** show 「文件导入学生用户」 (removed; roster import lives under **学生管理** only).

### If you are changing homework, notifications, or materials

Read and run in this order:

1. `tests/backend/homework/`
2. `tests/scenarios/material_flow.py`
3. `tests/behavior/test_material_chapters_notifications_homework_flow.py`
4. `tests/e2e/web-school/ui-homework-student-actions.spec.js`

## Which Tests Are Usually Easier To Pass

The easiest suites to keep green are usually the narrowly scoped backend tests in:

- `tests/backend/system/`
- `tests/backend/files/`
- `tests/backend/points/`
- smaller parts of `tests/backend/courses/`

Reasons:

- limited concurrency,
- fewer moving pieces,
- little or no browser/runtime orchestration,
- less dependence on long scenario setup.

## Which Tests Are Harder To Pass

The more difficult or fragile categories are usually:

### 1. Playwright browser E2E

Files under `tests/e2e/web-school/` are the hardest operationally because they depend on:

- backend boot,
- frontend boot,
- port availability,
- Playwright worker startup,
- seed/reset endpoints,
- browser-driver availability,
- timing across UI and API layers.

These tests are often the first place where Windows + PowerShell environment issues appear.

### 2. Behavior suites with multi-actor timelines

Examples from `tests/behavior/` are hard because they combine:

- multiple roles,
- staged mutations over time,
- read-state convergence,
- deduplication or reconciliation rules,
- a larger blast radius when one prerequisite silently diverges.

### 3. LLM concurrency and stress tests

Representative files include:

- `tests/backend/llm/test_llm_concurrency_scenarios.py`
- `tests/backend/llm/test_llm_stress_scenarios.py`

These are harder because they depend on:

- async or queue-backed behavior,
- retries and quota boundaries,
- ordering assumptions,
- state convergence after concurrent operations.

### 4. Seed/bootstrap-coupled backend tests

Files under `tests/backend/e2e_dev/` can be harder than normal unit-style backend tests because they touch:

- reset endpoints,
- demo seed data,
- startup assumptions,
- test-environment feature flags.

The module **`test_e2e_dev_api_hazard_tier.py`** adds fifteen **TestClient** checks that chain `reset-scenario` with cross-role HTTP calls (seed token gates, teacher vs student LLM quota routes, parallel `mark-all-read`, homework delete authz). It shares the same per-test DB reset pattern as `test_e2e_dev_seed.py`.

## Operational Advice

When a change is small, do not start with the hardest suites.

Prefer this escalation order:

1. relevant `tests/backend/<domain>/`
2. relevant `tests/behavior/`
3. one targeted Playwright spec
4. broader Playwright coverage if needed

If Playwright fails first, read [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md) before assuming the product is broken.

### Linux / CI agents

The same escalation order applies. Additional traps that showed up outside the original Windows-focused validation — managed Playwright `webServer` using a system Python without `uvicorn`, Element Plus message-box locale vs Chinese labels, strict-mode duplicate text matches, homework submit vs discussion `textarea` ordering, materials list `page_size` vs API `le=` limits — are recorded as Pitfalls 11–16 in [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md).
