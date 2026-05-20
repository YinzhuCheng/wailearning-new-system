# Agent playbook — safe edits, tracing, and verification

**Audience:** LLM coding agents and maintainers who need procedural discipline, not only folder listings.

**Companion docs:** [`AGENTS.md`](../../AGENTS.md) (repo root), [`docs/README.md`](README.md) (hub), [`docs/reference/CODE_MAP_AND_ENTRYPOINTS.md`](../reference/CODE_MAP_AND_ENTRYPOINTS.md).

---

## 1. How to read this repository (order matters)

1. **Boundary:** [`architecture/REPOSITORY_STRUCTURE.md`](../architecture/REPOSITORY_STRUCTURE.md) — distinguishes git-tracked source from runtime dirs (`uploads/`, `.pytest_tmp/`, etc.).
2. **Capabilities:** [`architecture/SYSTEM_OVERVIEW.md`](../architecture/SYSTEM_OVERVIEW.md) — roles and route families (not every endpoint).
3. **Slices:** [`architecture/CORE_BUSINESS_FLOWS.md`](../architecture/CORE_BUSINESS_FLOWS.md) — homework + LLM + notifications vertical traces with code anchors.
4. **Config:** [`architecture/CONFIGURATION_REFERENCE.md`](../architecture/CONFIGURATION_REFERENCE.md) — every `Settings` field and major `VITE_*` vars.
5. **Tests:** [`testing/VALIDATION_WORKFLOW_AND_TOOLS.md`](../testing/VALIDATION_WORKFLOW_AND_TOOLS.md) + [`testing/TEST_EXECUTION_PITFALLS.md`](../testing/TEST_EXECUTION_PITFALLS.md), then [`testing/DEVELOPMENT_AND_TESTING.md`](../testing/DEVELOPMENT_AND_TESTING.md) for the broader harness handbook when needed.

Skipping step 1 causes agents to “fix” generated artifacts or propose forbidden package layouts.

---

## 1.1 Operational defaults for autonomous work

Use these defaults unless the user gives a narrower instruction for the current
task:

1. Read `AGENTS.md`, `docs/README.md`, and the task-scoped docs before editing.
   Use [`agent-startup-routing.md`](agent-startup-routing.md) when you need the
   full startup matrix rather than the procedural defaults in this file.
2. Execute ordinary repository reads, edits, validation discovery, and Git
   operations directly; ask only when an action is destructive,
   privacy-sensitive, or materially outside the task boundary.
3. On Windows PowerShell, use
   `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops/scripts/windows/invoke-safe-text-command.ps1`
   as the default repository entrypoint before inspection/editing. Only
   dot-source `ops/scripts/windows/set-utf8-session.ps1` directly when you
   intentionally need to mutate an already-trusted interactive shell.
4. Preserve documentation detail when it acts as process memory for future
   agents. Shorten only when the removed material is obsolete, contradictory, or
   duplicative enough to cause confusion.
5. Update committed docs in the same change set when behavior, permissions,
   configuration, routing, validation flow, or operational workflow changes.
6. Keep machine-specific evidence local under `.agent-run/`; use
   [`local-agent-workspace.md`](local-agent-workspace.md) for the workspace
   contract.
7. For repeated execution traps, prefer converting the lesson into a committed
   script, skill, selector rule, or pitfall entry rather than leaving it as
   ad hoc reasoning.
8. For recurring UI simulation or screenshot work, prefer a committed script
   over an ignored local helper. The maintained example is
   `apps/web/school/scripts/capture-homework-layout-runner.cjs`, which uses
   the supported school E2E startup path and writes local output under `pics/`.
9. Before committing, follow the closeout sequence in
   [`agent-closeout.md`](agent-closeout.md).

Related policy docs:

- [`agent-startup-routing.md`](agent-startup-routing.md)
- [`agent-closeout.md`](agent-closeout.md)
- [`../governance/repository-governance.md`](../governance/repository-governance.md)
- [`../governance/agent-update-log.md`](../governance/agent-update-log.md)
- [`local-agent-workspace.md`](local-agent-workspace.md)

---

## 2. Standard workflow for a feature touch

### 2.1 Locate the slice

| If the task mentions… | Start reading… |
|----------------------|----------------|
| HTTP shape / validation | `apps/backend/courseeval_backend/api/schemas.py` + relevant `api/routers/*.py` |
| Who can call an API | Router dependency (`get_current_user`) + `domains/courses/access.py` + `core/permissions.py` |
| Persistence | `db/models.py` + `bootstrap.py` (`ensure_schema_updates` if new columns) |
| Homework scoring display | `domains/llm/grading_result.py` (`resolve_effective_submission_score`) + `llm_grading.py` (`refresh_submission_summary`) + `api/routers/homework.py` serializers |
| LLM vendor calls | `domains/llm/` + `llm_grading.py` task processor |
| School UI | `apps/web/school/src/views/*.vue` + `apps/web/school/src/api/index.js` |
| Parent UI | `apps/web/parent/src/` |

### 2.2 Trace forward from UI click (homework example)

1. Vue view calls API helper in `apps/web/school/src/api/index.js` (axios instance `baseURL` = `/api` or `VITE_API_BASE_URL`).
2. FastAPI router under `apps/backend/courseeval_backend/api/routers/homework.py`.
3. Dependencies: DB session + current user; `ensure_course_access_http` or equivalent when course-scoped.
4. Services / domains: homework domain modules under `domains/homework/` (when logic extracted from router).
5. Tables: `homeworks`, `homework_submissions`, `homework_attempts`, `homework_score_candidates`, `homework_grading_tasks` — see [`reference/DATA_MODEL_ESSENTIALS.md`](../reference/DATA_MODEL_ESSENTIALS.md).
6. Async: new attempt may enqueue `HomeworkGradingTask`; worker thread drains queue — [`architecture/ASYNC_TASKS_AND_WORKERS.md`](../architecture/ASYNC_TASKS_AND_WORKERS.md).

### 2.3 Trace backward from DB symptom

1. Identify ORM model (`db/models.py`).
2. Find writes in routers/domains (grep model class name).
3. Check bootstrap defaults / demo seed (`domains/seed/demo.py`, `INIT_DEFAULT_DATA`).
4. Check tests mirroring feature (`tests/backend/**`).

---

## 3. Backend bootstrap ordering (do not reorder blindly)

**Source:** `apps/backend/courseeval_backend/main.py` `lifespan`.

Approximate sequence:

1. `Base.metadata.create_all(bind=engine)`
2. `ensure_schema_updates()` — additive migrations / compatibility DDL (`bootstrap.py`)
3. Normalization passes (`normalize_teacher_class_assignments`, semester catalog, subject-semester links)
4. `backfill_homework_grading_data(db)`
5. `reconcile_student_users_and_roster(db)`
6. Optional `seed_demo_course_bundle(db)` when `INIT_DEFAULT_DATA=true`, then roster reconcile again
7. After yield startup: optional `start_grading_worker()` when `ENABLE_LLM_GRADING_WORKER` and `LLM_GRADING_WORKER_LEADER`

**Agent implication:** schema repair functions must tolerate empty databases **and** legacy partially migrated databases. New helpers appended to `ensure_schema_updates()` should stay idempotent.

---

## 4. Testing playbook

### 4.1 Commands (verify locally after edits)

| Scope | Command |
|-------|---------|
| Single file | `python3 -m pytest path/to/test_file.py -q` |
| Backend subset | `python3 -m pytest tests/backend -q` |
| CI parity | `python -m pytest -q` with Python `3.11` (see [`ops/ci/pr-pipeline.yml`](../../ops/ci/pr-pipeline.yml)) |

**Interpreter:** Linux/macOS automation can lack `python` on PATH, so `python3`
may still be useful locally. The repository CI baseline itself is now Python
`3.11` plus the canonical `python -m ...` form.

### 4.2 Environment variables tests rely on

**Source:** `tests/conftest.py` (loaded automatically).

- Sets `DATABASE_URL` to `TEST_DATABASE_URL` **or** auto-selected Postgres when `COURSEEVAL_AUTO_PG_TESTS` matches **or** fallback SQLite file `<repo>/.pytest_tmp/test_<pid>.sqlite` by default, overridable with `PYTEST_SQLITE_BASENAME`.
- Forces `INIT_DEFAULT_DATA=false` during tests.
- Disables LLM worker by default (`TEST_ENABLE_LLM_GRADING_WORKER` overrides).

### 4.3 Playwright school E2E

```bash
cd apps/web/school
npm install
npm run test:e2e
```

Contract: [`testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`](../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md).

---

## 5. Documentation maintenance triggers

Update docs **in the same change set** when you:

| Change type | Docs |
|-------------|------|
| New/changed env var | `architecture/CONFIGURATION_REFERENCE.md`, possibly root `README.md` quick start |
| Router prefix / major flow | `architecture/SYSTEM_OVERVIEW.md`, `architecture/CORE_BUSINESS_FLOWS.md` |
| Demo seed behavior | `operations/ADMIN_BOOTSTRAP.md`, `product/LLM_HOMEWORK_GUIDE.md` demo sections |
| Test harness / pitfalls | `testing/VALIDATION_WORKFLOW_AND_TOOLS.md`, `testing/TEST_EXECUTION_PITFALLS.md`, `testing/DEVELOPMENT_AND_TESTING.md` |
| Known regressions / unclear ownership | `governance/known-issues-and-risks.md` |

---

## 6. When to stop and ask for human decision

Document as **“待人工确认”** in [`known-issues-and-risks.md`](../governance/known-issues-and-risks.md) when:

- Two implementations coexist and call sites disagree which is primary.
- External vendor behavior or deployment secrets are required to validate.
- Legal/compliance implications (PII logging, retention).

Agents must not invent certainty.

---

## 7. Anti-patterns (repeat offenders)

1. **Adding “shortcut” imports** that bypass `apps.backend.courseeval_backend` namespace.
2. **Changing demo seed** without updating `tests/backend/e2e_dev/test_demo_course_seed.py` expectations.
3. **Editing only school UI** for permission-sensitive actions — backend must reject unauthorized API calls.
4. **Assuming Redis/Celery** — LLM grading uses DB-backed tasks + in-process worker (`llm_grading.py`).
5. **Running destructive grep-replace** on Chinese copy without encoding hygiene (Windows).

---

## 8. Related operational docs

- Deploy layout: [`operations/DEPLOYMENT_AND_OPERATIONS.md`](../operations/DEPLOYMENT_AND_OPERATIONS.md)
- Bootstrap / admin seed: [`operations/ADMIN_BOOTSTRAP.md`](../operations/ADMIN_BOOTSTRAP.md)
- Symptom index: [`architecture/TROUBLESHOOTING.md`](../architecture/TROUBLESHOOTING.md)
