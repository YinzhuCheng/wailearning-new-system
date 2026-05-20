# Known issues, risks, and “待人工确认” backlog

This document lists **implementation-backed hazards** and **open questions**. It is **not** a duplicate of all pitfalls in [`testing/TEST_EXECUTION_PITFALLS.md`](../testing/TEST_EXECUTION_PITFALLS.md); that file remains the deep execution encyclopedia. Entries here prioritize **ownership ambiguity** and **agent traps**.

---

## 1. Queue / worker architecture assumptions

| Issue | Detail |
|-------|--------|
| No Celery/Redis grading queue | LLM grading uses SQL rows (`homework_grading_tasks`) + in-process worker (`llm_grading.py`). Agents searching for `celery` or `redis` queue config will find none by design. |

See [`architecture/ASYNC_TASKS_AND_WORKERS.md`](../architecture/ASYNC_TASKS_AND_WORKERS.md).

---

## 2. Documentation vs package naming drift

| Issue | Detail |
|-------|--------|
| Legacy npm identifiers | Admin `package.json` may still show historical package names (`courseeval-school`) while README branding is CourseEval — cosmetic unless publishing packages. |
| External bookmarks to removed `tools/testing/` | Narrative docs may still **mention** the old path when explaining migrations; actionable code/config must not reference it. Canonical utility location: `tests/devtools/audit_test_redundancy.py`. |

---

## 3. pytest / SQLite harness hazards (observed agent environment)

### 3.1 Persistent pytest SQLite artifacts under `.pytest_tmp/`

**Mechanism:** `tests/conftest.py` sets `DATABASE_URL` to a **repo-local per-process SQLite file** such as `.pytest_tmp/test_<pid>.sqlite` when Postgres URL is not forced.

**Risk:** Interrupted runs or partially applied DDL can leave one or more local SQLite artifacts in a state where later tests fail with missing tables or FK errors until the affected file is deleted. The per-process naming reduces accidental cross-process sharing, but stale artifacts can still mislead local reruns.

**Mitigation documented:** run `python ops/scripts/dev/pytest_sqlite_guard.py`
first, stop any active pytest process it reports, then delete
the reported `<repo-root>/.pytest_tmp/test*.sqlite` artifact when bizarre
`no such table` errors appear after supposedly resetting schema. The guardrail
is read-only; it does not kill processes or delete files.

### 3.2 `ensure_schema_updates()` vs empty/partial metadata — mitigated (2026-05)

**Historical symptom:** `pytest` occasionally failed at `ensure_schema_updates()` with `sqlite3.OperationalError: no such table: course_llm_configs` immediately after `tests.db_reset.reset_test_database_schema()`.

**Root cause:** `reset_test_database_schema()` invoked `Base.metadata.create_all()` before guaranteed ORM mapper registration when test modules imported only `db.database` + `main` without pulling `db.models`.

**Fix:** `tests/db_reset.py` now imports `apps.backend.courseeval_backend.db.models` at the beginning of `reset_test_database_schema()`.

**Residual risks:** corrupted `.pytest_tmp/test*.sqlite` files or callers that override the basename back to a shared path still require deletion / isolation when suspected.

---

## 4. Demo seed security posture

`INIT_DEFAULT_DATA=true` creates predictable accounts (`teacher`, `teacher_pro`, `stu*`) — **never** enable on production internet-facing installs without rotation policy. Documented in [`operations/ADMIN_BOOTSTRAP.md`](../operations/ADMIN_BOOTSTRAP.md).

---

## 5. CI definition location

Reference pipeline YAML lives under [`ops/ci/`](../../ops/ci/) (e.g. `pr-pipeline.yml`). A lightweight GitHub Actions workflow now exists at [`.github/workflows/lightweight-validation.yml`](../../.github/workflows/lightweight-validation.yml), but it is not a full validation matrix. It covers selector/tooling checks, quick backend `pytest`, and frontend builds. PostgreSQL-backed pytest, RAR-dependent attachment coverage, and Playwright E2E remain local/manual or future cloud-profile work unless a later workflow adds those environments.

---

## 6. Dual enrollment logic

Required courses auto-sync enrollments via `sync_course_enrollments`; electives rely on explicit enrollment rows + optional blocks. Partial demo enrollments for electives are intentional — see demo seed docstrings in `domains/seed/demo.py`.

---

## 7. Effective homework score vs latest attempt body

UI and APIs may show **latest attempt content** while numeric grade reflects **eligible attempt maximum** — easy to mis-diagnose as “wrong score”. See `effective_score_display_zh` and product docs.

---

## 8. Suggested human follow-ups

Additional permission follow-up: recent hardening found multiple routes where
`class_teacher` class-linked visibility was accidentally treated as
assigned-teacher management authority. The current code is hardened across
subjects, materials, homework, scores, attendance, notifications, and course
LLM config, but every new course-owned mutation should still get an explicit
security test.

| Item | Why |
|------|-----|
| Alembic or formal migrations | Current `ensure_schema_updates` pattern works but requires discipline |
| API reference generator | OpenAPI `/docs` exists but no checked-in static export |
| Permission matrix spreadsheet |_roles × routes_ changes frequently |

---

For schema-governance work, start with
[`skills/data-migration-audit/SKILL.md`](../../skills/data-migration-audit/SKILL.md)
and `python ops/scripts/dev/check_schema_governance.py`. This is a static
guardrail only; it does not replace PostgreSQL-backed validation for
production upgrade claims.

For API-surface work, start with
[`skills/api-surface-audit/SKILL.md`](../../skills/api-surface-audit/SKILL.md)
and `python ops/scripts/dev/check_api_surface_governance.py`. This is a static
router/client/doc drift check only; it does not replace a generated OpenAPI
reference or API regression tests.

## 9. Repository normalization notes

These are not product defects, but they are recurring traps for future
cleanup passes.

| Issue | Detail |
|-------|--------|
| Dated reports live in `docs/reports/` only when still useful | Historical audit and restructure reports are not mandatory operating guides. Keep active rules in topic-specific docs; only preserve dated reports when they still add traceable evidence. |
| Web favicon uses public SVG assets | Both SPAs now read `/courseeval-mark.svg` from `public/`. If the favicon changes again, update both `apps/web/*/public/` copies and rerun both frontend builds. |
| Root-local runtime artifacts are not source layout | `__pycache__/`, `.pytest_cache/`, `.pytest_tmp/`, `.pytest-db/`, `.coverage*`, `htmlcov/`, `test-results/`, `playwright-report/`, frontend `dist` / `.vite`, package debug logs, `node_modules/`, and `.agent-run/` are working artifacts or ignored paths. Do not normalize them into committed source structure. Keep machine-specific logs, screenshots, and continuation notes under `.agent-run/`, and use committed docs only for durable repository context. |
| `subjects.py` is no longer a priority split target | After metadata, class-link, and enrollment helper extraction, `api/routers/subjects.py` is below the backend router large-file threshold. Future work should treat it as an HTTP/auth orchestration boundary unless new reusable course business rules accumulate there. |
| Remaining schema DTOs are coupled | `api/schemas.py` still owns auth/users, classes/courses/subjects, discussions, homework, learning notes, LLM, materials, scores, and shared student DTOs plus model-rebuild glue. Continue schema splitting only as dedicated schema-boundary work with inventory and compatibility-export validation. |

## 10. How to add new entries

Use this template in PR descriptions before promoting to this file:

## 11. Agent-governance automation limitations (May 2026)

| Issue | Detail |
|------|--------|
| Script-heavy governance routing is not reliable enough as the primary agent-control surface | A multi-round automation experiment showed that candidate-doc routers, prompt-driven governance scripts, and loop-style agent selection protocols are useful as design exploration but too fragile as a hard execution substrate for autonomous agents. Agents do not reliably behave like deterministic schema-bound function callers across many steps. The durable outcome is to keep the **workflow ideas** (strict/guided, pitfall-first triage, docs/ledger/update-log closeout) in text-first repository guidance rather than depend on a scripted router for primary control. See `docs/reports/AGENT_GOVERNANCE_AUTOMATION_EXPERIMENT_2026-05-14.md`. |

```text
Title:
Evidence (file/log line):
Impact:
Workaround:
Owner / 待人工确认:
```
