# Troubleshooting

## Purpose

Symptom-first pointers for **local development**, **tests**, and **deployments**. Each item links deeper detail elsewhere; prefer those documents for full procedures.

---

## Backend will not start

| Symptom | Likely cause | Where to read |
|---------|--------------|---------------|
| `ValidationError` for `SECRET_KEY` or `DATABASE_URL` | Production or `REQUIRE_STRONG_SECRETS=true` with placeholder secrets | [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md) |
| `E2E_DEV_SEED_ENABLED must be false when APP_ENV is production` | Mis-set env in prod template | `core/config.py` validator |
| Import errors for `apps.backend.courseeval_backend` | Running Python from wrong cwd or broken venv | [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md) |

---

## JWT / login failures after change

- Password resets invalidate tokens via `token_version` on user rows; if login succeeds but APIs return `401`, confirm client storage was cleared and the user row is not stuck mid-migration.
- If the browser shows CORS failures, verify `BACKEND_CORS_ORIGINS` includes the SPA origin and that you did not enable wildcard origins while relying on credentials.

---

## LLM grading stuck or noisy failures

| Symptom | Check |
|---------|-------|
| Tasks stay `queued` | `ENABLE_LLM_GRADING_WORKER`, `LLM_GRADING_WORKER_LEADER` vs process count; worker logs |
| Tasks stuck `processing` | Stale reclaim interval `LLM_GRADING_TASK_STALE_SECONDS`; DB connectivity |
| Quota unexpected | Global policy timezone and per-student overrides; see [../product/LLM_HOMEWORK_GUIDE.md](../product/LLM_HOMEWORK_GUIDE.md) |

---

## Playwright E2E unreliable or slow

Most failures are **environment or harness**, not application logic.

| Symptom | Likely cause | Detail |
|---------|--------------|--------|
| Port already in use (`3012`, `8012`, etc.) | Stale `node` / `uvicorn` | [../testing/pitfalls-playwright-and-e2e.md](../testing/pitfalls-playwright-and-e2e.md) for port hygiene and Playwright harness startup |
| Seed returns `404` | `E2E_DEV_SEED_ENABLED` false or wrong token | [../testing/VALIDATION_WORKFLOW_AND_TOOLS.md](../testing/VALIDATION_WORKFLOW_AND_TOOLS.md) and [../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md](../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md) |
| Powerful `/api/e2e/dev/*` returns `401` or `403` | Dual gate requires admin JWT plus seed header | same |
| Element Plus dropdowns behave flakily | Hover-trigger menus, teleported poppers | pitfalls doc for course switcher / dialog patterns |
| Full suite timeouts on layout tests | Too many `boundingBox()` calls | pitfalls doc for sampling strategy |

Full runbook: [../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md](../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md).

---

## pytest failures only on SQLite or only on PostgreSQL

- Some tests require PostgreSQL (`TEST_DATABASE_URL`); see [../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md](../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md) and [../testing/pitfalls-postgres-and-pytest.md](../testing/pitfalls-postgres-and-pytest.md).
- SQLite has different concurrency and timestamp semantics; do not assume parity.

---

## pytest `no such table` / `FOREIGN KEY` failures on default SQLite file

| Symptom | Likely cause | Mitigation |
|---------|--------------|------------|
| `sqlite3.OperationalError: no such table: ...` inside `ensure_schema_updates()` right after `reset_test_database_schema()` | Stale or corrupted `<repo-root>/.pytest_tmp/test*.sqlite`, import/metadata ordering edge, or concurrent pytest processes sharing the same SQLite artifact | Run `python ops/scripts/dev/pytest_sqlite_guard.py`, delete the affected `test*.sqlite` artifact, and rerun a **single** pytest process; read [../testing/pitfalls-postgres-and-pytest.md](../testing/pitfalls-postgres-and-pytest.md) for the SQLite/PostgreSQL harness route |
| `UNIQUE constraint failed: users.username` across many tests | Shared SQLite state plus tests expecting an empty DB | Same as above; avoid parallel pytest without isolated `TEST_DATABASE_URL`. |

Full risk notes: [../governance/known-issues-and-risks.md](../governance/known-issues-and-risks.md).

---

## Missing `tools/testing/` paths after a documentation refresh

| Symptom | Likely cause | Where to read |
|---------|--------------|---------------|
| Docs or bookmarks reference `tools/testing/audit_test_redundancy.py` but the path does not exist | Test maintenance scripts live under `tests/devtools/` | [`tests/devtools/README.md`](../../tests/devtools/README.md) |

Executable surfaces (`*.py`, CI YAML, shell) should not reference the legacy path. Use `rg 'tools/testing' -g '*.{py,yml,yaml,sh,bat,cjs,js,json}'` from the repo root when verifying migrations.

---

## Uploads / attachments `403` or wrong file

- Attachment authorization is centralized in `api/routers/files.py` with `_has_attachment_access`; duplicate filenames may require `attachment_url` query disambiguation (see pitfalls).

---

## nginx / production static assets

- Admin vs parent base paths: [../operations/DEPLOYMENT_AND_OPERATIONS.md](../operations/DEPLOYMENT_AND_OPERATIONS.md).
- After upgrade, run `ops/scripts/post_deploy_check.sh`; it always checks local backend health, and public checks are enabled only when `APP_URL` or `API_HEALTH_URL` is set.
- If `redeploy.sh` appears to finish but the site still serves old assets, confirm the script used the intended `REPO_DIR` clone and did not run with `SKIP_GIT=1` against stale source.
- If the public health endpoint differs from the default `APP_URL -> /api/health` derivation, override `PUBLIC_API_HEALTH_URL` before rerunning `post_deploy_check.sh`.

---

## Still stuck?

1. Reduce scope: one pytest module or one Playwright file.
2. Confirm env printed by `playwright.config.cjs` / backend settings (non-secret fields only).
3. Search [../testing/TEST_EXECUTION_PITFALLS.md](../testing/TEST_EXECUTION_PITFALLS.md) for the HTTP status or error string, then route into the narrower topic doc when the failure class is clear.
