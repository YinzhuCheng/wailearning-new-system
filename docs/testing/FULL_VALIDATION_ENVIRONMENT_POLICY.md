# Full Validation Environment Policy

## Purpose

This document is the focused policy surface for release-grade, full-suite, and
zero-skip validation expectations in CourseEval.

Use it when:

- a run is being described as `full suite`, `full regression`, `zero-skip`,
  `release-quality`, or `ready to push after validation`
- deciding whether missing local dependencies are acceptable iteration debt or
  unacceptable final evidence
- preparing PostgreSQL-, RAR-, or Playwright-backed environment validation
- reviewing the longer historical environment recipes and full-suite caveats

`DEVELOPMENT_AND_TESTING.md` remains the broader development/testing handbook.
This document is the narrower source for heavy validation environment policy.

## Full-Suite Environment Policy

Do not accept missing-dependency skips as final evidence.

For any run described as `full suite`, `full regression`, `zero-skip`,
`release-quality`, or `ready to push after validation`, missing local tools are
not an acceptable reason to leave tests skipped. Provision the missing
environment first, then run the affected tests at least once under conditions
that make them execute.

Operational rules for agents:

- If a backend test skips because PostgreSQL is absent, install or provision a
  throwaway PostgreSQL instance and rerun with `TEST_DATABASE_URL` (or the
  documented auto-pick path where available).
- If an attachment test skips because a RAR extractor is absent, install
  `unrar` / `unrar-free` or provide a compatible `tar` / `bsdtar` fallback,
  then rerun the attachment suite so the RAR cases execute.
- If Playwright skips or aborts because Node, browser binaries, or subprocess
  permissions are missing, install the missing runtime or rerun in an approved
  execution context before claiming full browser coverage.
- If a test is conditionally skipped for seed-data, service, browser, or
  database state, create the required condition at least once during the full
  validation cycle. A skip may remain documented as a fast-loop profile, but it
  must not be the final proof for the affected code path.
- Record the environment work and any blocked/interrupted attempts in
  [`test-execution-runs.csv`](test-execution-runs.csv). Use committed docs with
  placeholders such as `<repo>`, `<local-postgres-bin>`, and
  `<local-browser-cache>`; put real machine paths only in ignored `.e2e-run/`
  notes.

This policy intentionally raises the bar for `full suite` claims. SQLite-only
pytest, Playwright discovery, or a target that skipped due to missing
dependencies can still be useful for iteration, but they are not complete
evidence that the skipped behavior works.

## Current WAI-VALID Shard Contract

For the maintained local WAI-VALID orchestration workflow:

- non-E2E pytest blocks are expected to execute at **case level** using pytest
  nodeids collected from file inputs
- school Playwright E2E remains at **file level** using one `.spec.js` file per
  shard

This distinction is deliberate:

- pytest case-level tasks improve automatic slot refill, reconnectability, and
  precise failure accounting
- Playwright file-level tasks avoid over-fragmenting browser startup, seed, and
  local port/DB isolation costs

## PostgreSQL Zero-Skip Guidance

If you only run `pytest` on the default SQLite configuration, note that
`tests/behavior/test_regression_llm_quota_behavior.py::test_r3_course_llm_config_columns_no_legacy_token_limits`
is skipped unless the dialect is PostgreSQL (unless you set
**`COURSEEVAL_AUTO_PG_TESTS=1`** after provisioning the standard throwaway DB).
That guard asserts `information_schema` shows **no** legacy token-limit or
course-level quota-policy columns on `course_llm_configs` (including removed
`quota_timezone`, `estimated_chars_per_token`, and
`estimated_image_tokens`). Full PostgreSQL-only assertions require
`TEST_DATABASE_URL` (or auto-pick) pointing at a live Postgres instance with
migrated schema. This does not replace the default workflow for most changes; it
matters when validating schema-level regressions.

**PostgreSQL local smoke (Linux example):** Install Postgres, then either:

1. **Idempotent helper (recommended):** run
   `bash ops/scripts/dev/provision_postgres_pytest.sh` as a user who may
   `sudo -u postgres psql` (creates role `courseeval_test`, database
   `courseeval_pytest_all`, password `courseeval_test` by default; override
   with `WAILEARNING_PYTEST_DB_*` env vars documented in the script). Then
   either export the printed `TEST_DATABASE_URL`, or run pytest with
   `COURSEEVAL_AUTO_PG_TESTS=1` so `tests/conftest.py` auto-selects that URL
   when TCP + credentials succeed.
2. **Manual:** create a dedicated empty database and user, export
   `TEST_DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@127.0.0.1:5432/DBNAME`,
   then run `python3 -m pytest`.

Tests recreate schema via `tests/db_reset.py` (`DROP SCHEMA public CASCADE` on
non-SQLite, plus dropping leftover `pg` ENUM types in `public` before
`create_all` so SQLAlchemy can recreate enums cleanly). Use a database reserved
for automation only; do not point at production. Avoid running two pytest
processes against the same `TEST_DATABASE_URL` concurrently because resets
collide.

## RAR Attachment Environment Policy

`tests/backend/llm/test_llm_attachment_formats.py` exercises the same RAR code
path as production (`domains/llm/attachments.py` via `llm_grading` imports).
Committed sample archives live under `tests/fixtures/llm_rar/` so tests do not
shell out to the `rar` compressor at runtime. Unpacking prefers `unrar` or
`unrar-free` on `PATH`, and can also use a libarchive-backed `tar` or `bsdtar`
executable when the local platform supports RAR extraction through that tool.
If none of those extractors is available, the RAR cases skip with a short
message. Regenerating the binary fixtures still uses `rar a ...` on a
maintainer machine; do not commit regenerated bytes without re-running the full
attachment suite.

## Full Regression Prerequisites

CI machines and anyone publishing `green full-suite` results should install
`unrar` (or `unrar-free`), provision the throwaway database, then run one of:

```bash
# Option A — explicit URL (works on all platforms once Postgres listens on TCP)
export TEST_DATABASE_URL='postgresql+psycopg2://courseeval_test:courseeval_test@127.0.0.1:5432/courseeval_pytest_all'
python3 -m pytest tests/

# Option B — Linux/macOS: auto-pick the same URL when the probe DB answers
COURSEEVAL_AUTO_PG_TESTS=1 python3 -m pytest tests/
```

That executes `tests/postgres/`, the PostgreSQL-only `test_r3`
`information_schema` assertion, and the RAR-based attachment tests when a
supported RAR extractor is available.

## Skip Counts And Interpretation

On SQLite with `unrar` (or `unrar-free`) on `PATH` but without
`TEST_DATABASE_URL` / auto-Postgres, expect the PostgreSQL-only modules and
`test_r3` to skip (the latest full-suite report recorded **43 skipped**). If
`unrar` is missing, attachment-format tests may add extra skips depending on
fixture/tool availability. With `COURSEEVAL_AUTO_PG_TESTS=1` (or
`TEST_DATABASE_URL` set) against a live Postgres, the target is **0 skipped**;
the latest documented Postgres-forced full tree recorded **466 passed, 0
skipped** in [TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md](TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md).
Do not memorize the `passed` integer as a permanent constant.

The SQLite-only `passed` integer is not a permanent constant as new tests land
in the default collection; rely on skip classes and the Postgres 0-skip matrix
instead of memorizing a single `passed` tally. Historical rows may still show
older counts from earlier May 2026 passes.

Default `pytest` without Postgres or `unrar` remains valid for fast loops but
will report skips for those items. Treat that as environment debt, not product
absence.

## Agent Recipe: Minimal Debian/Ubuntu Cloud Image

Minimal Python-only sandboxes can still reach a 0-skip Postgres pytest run and
run one Playwright hazard file without hand-installing Node from upstream
tarballs:

1. **PostgreSQL + throwaway DB:** `sudo apt-get install -y postgresql
   postgresql-contrib` -> `sudo pg_ctlcluster 16 main start` (version may
   differ) -> `bash <REPO_ROOT>/ops/scripts/dev/provision_postgres_pytest.sh`
   (requires `sudo -u postgres`).
2. **RAR extractors:** `sudo apt-get install -y unrar rar` (or `unrar-free`
   where `unrar` is unavailable).
3. **pytest:** `python3 -m pip install -r <REPO_ROOT>/requirements.txt` then
   `cd <REPO_ROOT> && COURSEEVAL_AUTO_PG_TESTS=1 python3 -m pytest tests/ -q`
   -> expect **0 skipped** when steps 1-2 succeeded.
4. **Node + Playwright (apt, not `nvm`):** `sudo apt-get install -y nodejs
   npm` -> on Ubuntu 24.04 this typically yields **Node 18.x** and **npm 9.x**.
5. **Admin deps + browser:** `cd <REPO_ROOT>/apps/web/school && npm ci && npx
   playwright install chromium`.
6. **E2E run:** Use `E2E_PYTHON` pointing at an interpreter that has `uvicorn`
   on `PYTHONPATH` (repository `.venv` if present, else `/usr/bin/python3`
   after `pip install -r requirements.txt`). Example smoke:

```bash
cd <REPO_ROOT>/apps/web/school
CI=1 E2E_PYTHON=/usr/bin/python3 E2E_DEV_SEED_TOKEN=test-playwright-seed \
  npx playwright test e2e-agent-hazard-tier-15.spec.js --project=chromium
```

Observed in one cloud session: `npm ci` + `npx playwright install chromium`
plus the command above produced **15 passed** for
`e2e-agent-hazard-tier-15.spec.js` in about 15 seconds wall time. Do not run
multiple Playwright CLI processes on default ports **8012/3012**.

## Database-Backed Test Authoring Convention

When adding or reviewing tests that touch persistence, schema, transactions,
concurrency, or dialect-specific behavior, assume PostgreSQL as the
production-aligned reference: write assertions and fixtures compatible with
Postgres first; use SQLite for speed locally where the suite allows, but do not
rely on SQLite-only semantics as proof for shipping schema-sensitive changes.
Re-validate meaningful DB changes against `TEST_DATABASE_URL` (Postgres).

## Historical Full-Suite Notes

This section preserves longer historical environment notes that remain useful
to future agents without forcing them to stay in the everyday testing handbook.

### Historical full-suite regression runs and line-count inventory

The table below is a historical representative run from an earlier May 2026
cleanup pass. It remains useful for understanding the SQLite-vs-Postgres skip
split, but it is not the newest count. Treat integer counts as moving; treat
the skip classes and required dependencies as stable operational guidance.

| Configuration | Command pattern | Outcome (representative) | Wall-clock order of magnitude |
|---------------|-----------------|---------------------------|--------------------------------|
| **Default SQLite** (no `TEST_DATABASE_URL`, no `COURSEEVAL_AUTO_PG_TESTS`) | `cd <REPO_ROOT> && python3 -m pytest tests/ -q` | Historical: **389 passed**, **43 skipped** when `unrar` was present; newer report: **423 passed**, **43 skipped** | ~8 minutes on a typical cloud CPU |
| **PostgreSQL** (`TEST_DATABASE_URL` **or** `COURSEEVAL_AUTO_PG_TESTS=1` after `ops/scripts/dev/provision_postgres_pytest.sh`) | `export TEST_DATABASE_URL='postgresql+psycopg2://…'` or `COURSEEVAL_AUTO_PG_TESTS=1 python3 -m pytest tests/ -q` | Historical: **432 passed**, **0 skipped**; newer report: **466 passed**, **0 skipped** when `unrar` + Postgres were provisioned | ~9.5 minutes on a typical cloud CPU |

The same historical pass also recorded approximate repository line counts:

- document lines: about **7,467**
- test code lines: about **25,743**
- product code lines: about **51,386**
- total tracked text lines in that pass: about **85,222**

Treat these as trend signals, not quality scores.

## Related Files

- [`DEVELOPMENT_AND_TESTING.md`](DEVELOPMENT_AND_TESTING.md)
- [`CI_AND_VALIDATION.md`](CI_AND_VALIDATION.md)
- [`TEST_EXECUTION_PITFALLS.md`](TEST_EXECUTION_PITFALLS.md)
- [`TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md`](TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md)
- [`../../ops/scripts/dev/provision_postgres_pytest.sh`](../../ops/scripts/dev/provision_postgres_pytest.sh)
