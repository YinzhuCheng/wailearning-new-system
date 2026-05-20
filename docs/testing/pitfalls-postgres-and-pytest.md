# PostgreSQL And Pytest Pitfalls

## Purpose

Use this route when the failure shape suggests:

- PostgreSQL install, startup, or throwaway-cluster issues;
- SQLite vs PostgreSQL semantic drift;
- `TEST_DATABASE_URL` / `COURSEEVAL_AUTO_PG_TESTS` environment gating;
- full-suite skips that are actually missing-environment debt;
- pytest collection or DB reset behavior that fails before business assertions.

This file is a **route, summary, and canonical home** for the PostgreSQL and
pytest pitfall clusters that have already been migrated here. Historical
entries that have not been moved yet still remain in
[TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md).

## Start Here

1. Run:

   ```powershell
   python ops\scripts\dev\search_pitfalls.py "<postgres or pytest symptom>"
   ```

2. Open:
   [FULL_VALIDATION_ENVIRONMENT_POLICY.md](FULL_VALIDATION_ENVIRONMENT_POLICY.md)
3. If the problem is local-environment shaped rather than product behavior,
   route through:
   [../../skills/local-test-triage/SKILL.md](../../skills/local-test-triage/SKILL.md)

## Primary Pitfall Clusters

| Cluster | Start with |
|---------|------------|
| SQLite temp-path / local pytest harness | Pitfall 7, local pytest SQLite sections, Pitfall 81 |
| Windows PostgreSQL bootstrap and local binaries | Pitfalls A-J, Windows Postgres dependency sections |
| PostgreSQL SQL or ORM semantics | Pitfalls 42-45, 57-62 |
| full-suite skip policy and dependency gates | Pitfalls 45-46 and full-suite dependency sections |
| schema/reset / metadata ordering | Pitfalls 79 and the PostgreSQL full-suite notes |

## Key Pitfalls

- **Pitfall 7**: pytest temp-path behavior on Windows can fail before test
  bodies execute.
- **Pitfalls A-J**: PostgreSQL on Windows often fails in provisioning, process
  lifetime, or startup-wrapper ways before any repo code is wrong.
- **Pitfall 42**: PostgreSQL rejects trailing commas in `IN (...)` lists.
- **Pitfall 43**: `Session.merge()` is not always a safe test-side upsert.
- **Pitfall 45**: many skips are environment gates, not optional quality.
- **Pitfall 46**: disposable Linux/cloud runners may simply lack `pytest`
  until `requirements.txt` is installed.
- **Pitfall 79**: some isolated pytest modules are sensitive to import order
  around `main.py` and DB reset helpers.

## Recommended Commands

```bash
python ops/scripts/dev/pytest_sqlite_guard.py --json
bash ops/scripts/dev/provision_postgres_pytest.sh
python3 -m pytest tests/ -q
```

Use:

- `TEST_DATABASE_URL` for explicit PostgreSQL runs
- `COURSEEVAL_AUTO_PG_TESTS=1` when following the repo's throwaway Postgres
  auto-pick path

## Related Files

- [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)
- [FULL_VALIDATION_ENVIRONMENT_POLICY.md](FULL_VALIDATION_ENVIRONMENT_POLICY.md)
- [VALIDATION_WORKFLOW_AND_TOOLS.md](VALIDATION_WORKFLOW_AND_TOOLS.md)
- [../../skills/postgres-release-validation/SKILL.md](../../skills/postgres-release-validation/SKILL.md)
- [../../skills/local-test-triage/SKILL.md](../../skills/local-test-triage/SKILL.md)


## Detailed migrated entries

## Incremental Field Notes: PostgreSQL-Aligned UI/UX Audit on Windows

This subsection records a later UI/UX audit setup pass where the operator needed
real browser screenshots against a PostgreSQL-backed backend, not the default
SQLite-backed Playwright webServer path. These notes are intentionally additive:
they do not replace the earlier Playwright or PostgreSQL guidance above.

### Goal

The audit goal was to inspect the school SPA through Playwright screenshots while
using a production-aligned PostgreSQL database. SQLite was acceptable only for
quick local smoke and was explicitly rejected as the main evidence source for
UI/E2E behavior that depends on real persistence semantics.

### What worked

The reliable approach in a restricted Windows automation environment was:

1. Use an ignored artifact directory such as `<repo>/.e2e-run/postgres-runtime/`.
2. Download an official EDB PostgreSQL Windows x64 binary zip into that ignored
   directory. The pass used PostgreSQL `16.13`.
3. Extract the archive locally and use the bundled `initdb.exe`,
   `postgres.exe`, `psql.exe`, and `pg_isready.exe` from
   `<artifact-dir>/pgsql/bin/`.
4. Initialize a local throwaway cluster in an ignored data directory, for
   example `<artifact-dir>/data-clean`, with local trust auth.
5. Run PostgreSQL on a non-production loopback port, for example
   `127.0.0.1:15432`.
6. Create a clearly disposable database such as `courseeval_uiux_audit`.
7. Start the backend with:
   - `DATABASE_URL=postgresql://postgres@127.0.0.1:15432/courseeval_uiux_audit`
   - `E2E_DEV_SEED_ENABLED=true`
   - `E2E_DEV_SEED_TOKEN=<test token>`
   - `INIT_DEFAULT_DATA=false`
   - `ENABLE_LLM_GRADING_WORKER=false`
   - a local-only `SECRET_KEY`
8. Seed data through `POST /api/e2e/dev/reset-scenario` with the same
   `X-E2E-Seed-Token`.
9. Start Vite from `apps/web/school` with
   `VITE_PROXY_TARGET=http://127.0.0.1:<api-port>`.
10. Use Playwright screenshots and DOM snapshots against the Vite URL.

### Pitfall A: local machine may have no PostgreSQL service, Docker, psql, or winget

The pass first checked for:

- a running PostgreSQL service,
- `psql.exe` / `postgres.exe` / `pg_ctl.exe`,
- Docker,
- `winget`,
- `DATABASE_URL` / `TEST_DATABASE_URL`.

None were available in that environment. Do not assume a Windows machine already
has a database runtime just because the repository is PostgreSQL-first.

### Pitfall B: Chocolatey can exist but still be unusable for PostgreSQL install

Chocolatey was installed, but `choco install postgresql` failed because the shell
did not have administrator access to Chocolatey system directories and could not
write `lib-bad` or clear package lock state.

Avoid treating "Chocolatey exists" as equivalent to "the agent can install a
system PostgreSQL service." If Chocolatey needs admin rights, prefer a
user-directory binary archive when the task only needs a temporary local
database.

### Pitfall C: `pg_ctl` can fail on restricted Windows tokens

`initdb.exe` completed the cluster initialization but emitted Windows restricted
token errors at the end. `pg_ctl.exe start` also failed with restricted token
errors. The cluster files were still usable.

What worked was direct `postgres.exe -D <data-dir> -h 127.0.0.1 -p <port>` rather
than `pg_ctl.exe`, provided the process was launched in a context that could keep
it alive for the audit.

### Pitfall D: PostgreSQL writes normal LOG output to stderr

When wrapping `postgres.exe` with PowerShell, normal PostgreSQL startup lines can
arrive on stderr. If a wrapper script sets `$ErrorActionPreference = 'Stop'`,
PowerShell may treat a harmless startup LOG line as a native command error and
exit before PostgreSQL finishes starting.

For wrapper scripts around `postgres.exe`, either avoid `Stop` for native stderr
or redirect/handle stderr deliberately.

### Pitfall E: background process lifetime can differ by launcher

Several background launch attempts returned a process id but did not leave a
listening PostgreSQL server for the next command. Direct foreground startup
proved PostgreSQL itself was valid, but hidden `Start-Process`, `cmd /c`, and
PowerShell job patterns were unreliable in that sandboxed automation context.

When cross-command background processes are unreliable, use one orchestrator
process that starts PostgreSQL, backend, frontend, and Playwright inside the same
lifetime. In this pass, a local ignored Node script performed that orchestration.

### Pitfall F: Node child process spawn may be blocked in the default sandbox

The orchestrator initially failed with `spawn EPERM`, matching the broader
Playwright webServer `EPERM` pitfall. The fix was to run the orchestrator outside
the restricted sandbox/with the necessary execution approval. This is an
environment restriction, not evidence that PostgreSQL, Vite, or the app is
broken.

### Pitfall G: Vite must be started from the school app directory

Starting Vite with the Vite binary path while the current working directory was
the repository root produced a root URL that returned `404`. The fix was to set
the frontend process working directory to `<repo>/apps/web/school` before running
Vite.

This matters for custom audit scripts and external-server Playwright flows:
`node <repo>/apps/web/school/node_modules/vite/bin/vite.js` is not sufficient by
itself if the working directory is wrong.

### Pitfall H: repeated role login can hang if the previous session is still active

A screenshot script that logs in as admin and then navigates to `/login` to log
in as teacher/student can hang or redirect unexpectedly if the app immediately
redirects an already-authenticated user away from `/login`.

The robust helper should clear `localStorage` and `sessionStorage` before each
fresh role login, then navigate to `/login` and submit credentials.

### Pitfall I: PostgreSQL recovery after forced audit timeouts can add startup delay

Several interrupted experiments left the throwaway cluster needing crash
recovery. `pg_isready` reported `rejecting connections` before eventually
accepting connections. For clean audit runs, either shut PostgreSQL down
gracefully or reinitialize a new throwaway data directory such as
`data-clean`.

### Pitfall J: DOM snapshots and screenshots can disagree during page startup

A UI audit can produce a JSON snapshot showing that page text, buttons, and
routes exist while the paired screenshot is still blank or partially painted.
This usually means the screenshot was taken before the stable visual container
was visible, not that the JSON snapshot is wrong.

For login and other app-shell entry pages, do not rely on `page.goto(...)`
alone. Add stable page-level test IDs in product code and wait for the visible
panel before capture. Example pattern:

```javascript
await page.goto('/login', { waitUntil: 'domcontentloaded' })
await page.getByTestId('login-panel').waitFor({ state: 'visible', timeout: 30000 })
await page.waitForTimeout(300)
await capture(page, 'login')
```

The exact script path should be documented as `<repo>/...` or
`<artifact-dir>/...` in committed docs. If the machine-specific path matters for
a handoff, put it in an ignored local note instead.

### Artifact hygiene

Keep all of the following out of tracked source:

- downloaded PostgreSQL zips,
- extracted PostgreSQL binaries,
- local data directories,
- audit launch scripts,
- screenshots,
- runtime logs,
- seeded scenario JSON files.

Use ignored directories such as `.e2e-run/`. If a temporary spec is created under
`tests/e2e/...` for experimentation, delete it before committing unless it is a
deliberate maintained test.

### Privacy hygiene

Do not paste user-specific absolute paths into committed documentation. Use
placeholders such as:

- `<repo>`
- `<user-home>`
- `<artifact-dir>`
- `<api-port>`
- `<ui-port>`

Local handoff files can contain machine-specific paths when the next operator on
the same machine needs them, but committed docs should stay portable.


## Additional migrated PostgreSQL and pytest blocks

### Pitfall 42: PostgreSQL `IN (...)` lists reject a trailing comma

Symptom:

```text
psycopg2.errors.SyntaxError: syntax error at or near ")"
```

Cause:

In PostgreSQL, `WHERE column_name IN ('a', 'b',)` is invalid because of the trailing comma after the last literal. Some editors or copy-paste patterns introduce that comma when extending a list of legacy column names.

Fix:

Remove the trailing comma after the final element in the `IN` list (or use a tuple/array constructor that your dialect documents).

### Pitfall 43: `Session.merge()` is not always a safe “upsert” in tests

Symptom:

```text
sqlalchemy.exc.IntegrityError: UniqueViolation ... llm_student_token_overrides_student_id_key
```

Context:

A test tries to model “update the per-student override twice” by calling `Session.merge(LLMStudentTokenOverride(...))` twice in the same session.

Cause:

`merge()` resolves identity using SQLAlchemy’s merge algorithm and the current session state. For rows keyed by a **natural unique column** (`student_id`) without a stable primary-key object already loaded, a second `merge()` can still emit an **INSERT** that collides with the first row, especially when the session’s identity map does not contain the persisted instance the test author assumed.

Fix:

- Prefer **`query(...).one()` then mutate attributes** and `commit()`, or
- Call the **application service** (`apply_student_daily_token_overrides` / HTTP API) that already encodes upsert semantics, or
- Use **`db.execute(update(...))`** with an explicit `WHERE student_id = :sid` in low-level constraint tests.

Interpretation:

This is usually a **test harness bug**, not evidence that the database unique constraint is wrong.

### Pitfall 44: Playwright CLI `-q` / unknown option failures in CI

Symptom:

```text
error: unknown option '-q'
```

Context:

Some automation snippets suggest `npx playwright test ... -q` for quieter logs.

Cause:

The installed `@playwright/test` major version may **not** support the `-q` flag on the `playwright test` CLI entrypoint.

Fix:

- Remove `-q` and rely on Playwright’s default reporter, or
- Use supported reporter flags for your installed version (see upstream Playwright release notes for `<REPO_ROOT>/apps/web/school/node_modules/@playwright/test`).

### Pitfall 45: Many pytest “skips” are environment gates (PostgreSQL dialect), not optional quality

Symptom:

```text
43 skipped
```

Context:

- **`tests/postgres/*`** and **`test_r3`** in `test_regression_llm_quota_behavior.py` require a **PostgreSQL** engine (`information_schema`, transactional semantics).

Cause:

Default `tests/conftest.py` uses **SQLite** unless `TEST_DATABASE_URL` is set (or **`COURSEEVAL_AUTO_PG_TESTS=1`** auto-pick is enabled — see [FULL_VALIDATION_ENVIRONMENT_POLICY.md](FULL_VALIDATION_ENVIRONMENT_POLICY.md)).

Fix:

1. Install **`unrar`** or **`unrar-free`** so `tests/backend/llm/test_llm_attachment_formats.py` can execute the RAR walks (same tooling the product uses in `domains/llm/attachments.py`). The **`rar`** compressor is **not** required at pytest runtime anymore because regression archives live under **`tests/fixtures/llm_rar/`** (generated offline by maintainers).
2. Run **`bash ops/scripts/dev/provision_postgres_pytest.sh`** (creates `courseeval_pytest_all` + role `courseeval_test`; needs `sudo -u postgres` when the cluster exists).
3. Either `export TEST_DATABASE_URL='postgresql+psycopg2://courseeval_test:courseeval_test@127.0.0.1:5432/courseeval_pytest_all'`, or set **`COURSEEVAL_AUTO_PG_TESTS=1`** so `tests/conftest.py` probes that URL and switches `DATABASE_URL` before importing the app.
4. Ensure PostgreSQL is **listening** (`pg_ctlcluster <ver> main start` or your distro equivalent). The provision script fails loudly when `sudo -u postgres` cannot connect.

Interpretation:

**SQLite-only green** is fast but **incomplete** for schema-sensitive merges; CI should aim for a **Postgres-backed 0-skip** full pytest with the recipe above (Postgres executes the modules skipped by SQLite). The latest full-suite report currently records **466 passed, 0 skipped** for that profile and **423 passed, 43 skipped** for SQLite-default. Older notes that cite **432**, **417**, or fixed **45-skip** expectations describe earlier fixture layouts and should not be used as the current branch’s pass-count oracle.

### Pitfall 46: disposable Linux / cloud-agent runners may lack `pytest` until `requirements.txt` is installed

### Symptom

Running the backend suite from `<REPO_ROOT>` fails before any test body executes:

```text
/usr/bin/python3: No module named pytest
```

Or the shell reports that `pytest` is not found when invoked as a bare executable.

### Context

Cursor cloud agents, minimal CI images, and fresh clones often do **not** ship with the repository `.venv` pre-created. The canonical developer workflow assumes `pip install -r requirements.txt` (or an equivalent venv step) before `python -m pytest`.

### Fix

At `<REPO_ROOT>`:

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest tests/ -q
```

Prefer a dedicated `.venv` when the environment allows (see [DEVELOPMENT_AND_TESTING.md](DEVELOPMENT_AND_TESTING.md) for the broader local setup handbook); the important invariant is that the **same interpreter** that runs pytest has project dependencies installed.

### Interpretation

This is **runner bootstrap debt**, not a failing test or a broken import path in `apps.backend.courseeval_backend`. Do not edit `tests/conftest.py` or `pytest.ini` to “fix” a missing `pytest` package on the system interpreter.
