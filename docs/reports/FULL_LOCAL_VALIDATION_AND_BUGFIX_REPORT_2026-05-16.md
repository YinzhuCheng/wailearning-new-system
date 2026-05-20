# Full Local Validation And Bugfix Report (2026-05-16)

## Purpose

This report tracks the local full-validation attempt requested on 2026-05-16.
It is intended to be updated incrementally during the run so the final report
does not need to reconstruct long execution history from memory.

## Scope Requested

- run a local full validation cycle
- use repository-supported local E2E and environment setup paths
- investigate and fix failures iteratively
- rerun affected scopes after each bug-fix round
- keep the report concise by updating roughly every 30 completed examples /
  meaningful validation chunks

## Environment Preflight

### Read entrypoints

- `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`
- `docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`
- `docs/testing/CI_AND_VALIDATION.md`

### Capability probe

Command:

```powershell
C:\Users\bloom\wailearning\.venv\Scripts\python.exe ops/scripts/dev/check_validation_capabilities.py --json
```

Observed result:

- `playwright-managed`: `pass`
- `postgres-test-env`: `fail`
- `rar-extraction`: `pass`
- `text-safety`: `warn`

Interpretation:

- local Playwright-managed E2E appears runnable with the repository `.venv`
- PostgreSQL-backed zero-skip pytest is **not yet configured**
- RAR-dependent attachment coverage should be runnable once the suite gets that far

## Progress Log

### Checkpoint 0: startup / environment discovery

Status:

- report created
- capability probe captured
- Playwright prerequisites look present
- PostgreSQL environment still needs provisioning or an alternative local path

Open blockers at this checkpoint:

- `TEST_DATABASE_URL` is not configured
- no confirmed local `psql` / PostgreSQL install path has been found yet

### Checkpoint 1: local PostgreSQL runtime discovery

Findings:

- local PostgreSQL binaries exist under `<local-user>/tools/postgres/pgsql/bin`
- local `psql.exe` exists under that runtime
- candidate data directories exist, including:
  - `<local-user>/tools/postgres/data-wailearning-test`
  - `<local-user>/tools/postgres/data-wailearning-test-full`
- historical archived validation logs show a previous successful local
  PostgreSQL run on port `15452`

Complication:

- `pg_ctl.exe start ...` failed in the current shell with a Windows token /
  startup error, so the next attempt should use `postgres.exe` directly or a
  previously known-good invocation pattern

## Current Working Hypothesis

- PostgreSQL-backed full pytest is likely achievable on this machine with the
  private runtime already present
- the missing piece is reliable instance startup in the current shell context,
  not package installation from scratch

## Failure Sample Summary

### Failure cluster 1: PostgreSQL test environment bootstrapping

Observed while running the local PostgreSQL orchestrator:

- `tests/postgres/test_postgres_dialect_guards.py` failed during collection
- root error:
  `psycopg2.OperationalError: role "courseeval_test" does not exist`

Why this happened:

- the local orchestrator started `postgres.exe` successfully
- but the role/database initialization commands began while the server still
  reported `the database system is starting up`
- as a result, the dedicated throwaway role/database were not reliably created
  before pytest imported the backend app with `TEST_DATABASE_URL`

Initial fix direction:

- harden readiness detection to require a successful `select 1`
- write the role/database bootstrap SQL into a file and run it with
  `psql -v ON_ERROR_STOP=1 -f ...`
- fail early if role/database initialization does not complete cleanly

## Bug Fix Rounds

### Bug-fix round 1: PostgreSQL orchestrator readiness and init hardening

Changed local-only artifact:

- `.agent-run/plan/run-full-postgres-pytest.ps1`

Adjustments:

- increased startup readiness loop budget
- require a successful `psql ... -tAc "select 1"` before proceeding
- replaced inline `DO $$ ... $$` command composition with a generated SQL file
- added explicit exit-code checks around role/database init and schema grant

### Failure cluster 2: local SQL bootstrap file syntax

Observed on rerun:

- `psql ... -f postgres-init.sql` failed with
  `syntax error at or near "BEGIN"`

Why this happened:

- the generated SQL file emitted `DO $$ ... $$` in a way that PostgreSQL did
  not parse correctly from the PowerShell-generated file content

Fix direction:

- emit escaped `DO \$\$ ... \$\$;` delimiters in the generated SQL file

### Bug-fix round 2: SQL bootstrap delimiter correction

Changed local-only artifact:

- `.agent-run/plan/run-full-postgres-pytest.ps1`

Adjustment:

- corrected the generated SQL file to emit `DO \$\$ ... \$\$;`

### Failure cluster 3: `psql` treated escaped dollar quoting as a client command

Observed on rerun:

- `psql ... -f postgres-init.sql` failed with
  `invalid command \$`

Why this happened:

- escaping that was appropriate for PowerShell string construction was not
  appropriate for the final SQL file consumed by `psql`

Fix direction:

- stop generating a `DO $$` SQL file entirely
- switch to explicit `SELECT role existence`, then `CREATE ROLE` / `ALTER ROLE`
  / `DROP DATABASE` / `CREATE DATABASE` command sequence

### Bug-fix round 3: replace generated SQL file with explicit `psql -c` sequence

Changed local-only artifact:

- `.agent-run/plan/run-full-postgres-pytest.ps1`

Adjustment:

- removed fragile generated SQL-file bootstrap
- replaced it with direct `psql -tAc` probe and explicit create/alter/drop/create
  commands with exit-code checks

### Checkpoint 2: PostgreSQL package green, full pytest entered first failure cluster

Observed results:

- `tests/postgres`: `43 passed, 1 warning in 93.23s`
- full `pytest tests -q` progressed to about `25%`
- current progress sample from the live log:
  - `........................................................................ [  8%]`
  - `........................................................................ [ 16%]`
  - `...............................FF....................................... [ 25%]`

Interpretation:

- PostgreSQL-backed zero-skip package validation is now working locally
- the next actionable work is not environment bootstrap anymore; it is product-
  or test-level failure investigation for the first two failing examples in the
  full tree

Pending at this checkpoint:

- wait for the current full pytest run to finish or expose the first traceback
- extract the exact failing test ids and group them into the next bug-fix round

### Failure cluster 4: hard-coded quota calendar in regrade billing tests

First real product/test failure from the PostgreSQL full run:

- `tests/backend/llm/test_homework_regrade_billing_behavior.py::test_teacher_regrade_is_not_counted_against_student_quota`

Observed assertion:

- expected `student_used == 120`
- actual `student_used == 0`

Root cause from inspection:

- the test manually inserted `LLMQuotaReservation` rows using hard-coded
  `usage_date="2026-05-15"` and `timezone="Asia/Shanghai"`
- `record_usage_if_needed(...)` and `get_used_tokens_for_scope(...)` use the
  runtime result of `resolve_global_quota_calendar(db)`
- when the actual local quota calendar does not match the hard-coded test date,
  the query legitimately returns `0`

Classification:

- test bug / brittle test fixture, not backend product bug

### Bug-fix round 4: use runtime quota calendar in regrade billing tests

Changed tracked file:

- `tests/backend/llm/test_homework_regrade_billing_behavior.py`

Adjustment:

- replaced hard-coded `usage_date` / `timezone` values with
  `resolve_global_quota_calendar(db)` in the affected tests

### Checkpoint 3: first real failure fixed and first-fail rerun resumed

Observed targeted regression:

- `tests/backend/llm/test_homework_regrade_billing_behavior.py -q`
  -> `4 passed in 11.15s`

Current next-step status:

- a fresh-cluster PostgreSQL `pytest -x -vv` rerun is in progress to surface the
  next failing example after the regrade-billing test fix
- live progress has already advanced past the previously failing billing test
  and through the `test_llm_concurrency_scenarios.py` block without a new
  failure in the visible tail

### Checkpoint 4: monitoring / orchestration hardening

Observed operator pain:

- a visible monitor window was needed because chat rounds are not a reliable
  long-lived observability surface
- stale `progress.json` snapshots made it look like workers were still running
  after the launcher had frozen

Changes made:

- added `ops/scripts/dev/wai_valid_monitor.py`
- added `ops/scripts/dev/wai_valid_register_current_run.py`
- added `ops/scripts/windows/start-validation-monitor.bat`
- added the repo-local skill
  `skills/parallel-validation-orchestration/SKILL.md`
- added pitfall notes for stale detached progress files and PowerShell DSN
  interpolation in generated PostgreSQL workers

Current status:

- the monitor/current-run protocol is now present in tracked code
- the existing ad hoc mixed-run launchers are still not trustworthy enough to
  count as final orchestration
- a later round should promote the orchestration itself to the documented
  `WAI-VALID-supervisor` / `WAI-VALID-worker` / `WAI-VALID-pg-worker` model

### Checkpoint 5: stale progress diagnosis after the visible monitor freeze report

Observed symptom from the visible monitor:

- the console kept showing roughly `done=10/20`, `running=8`, `failed=1`,
  `queue=1`
- `updated_at` stopped advancing even though the operator expected active
  progress

Diagnosis:

- the monitor itself was not the primary fault; it was faithfully rendering the
  last `progress.json` snapshot it was given
- the real failure mode was the detached launcher/scheduler layer: it stopped
  updating the shared progress file, so the monitor could only keep repainting
  stale state
- this means the previous mixed/manual launchers cannot be trusted as the
  durable source of truth for long-running parallel validation

Immediate consequence:

- old `manual-10way-*` and similarly ad hoc runs should be treated as stale
  evidence unless their progress timestamps, shard logs, and live processes all
  still agree
- the next trustworthy validation round should start from a fresh controlled
  run with the current-run pointer and visible monitor, rather than attempting
  to infer completion from the frozen snapshot

Follow-up direction:

- keep the new monitor/current-run protocol
- replace the fragile scheduler layer with an explicit tracked supervisor that
  rewrites progress on every state change and performs automatic slot refill
  instead of batch-style manual topping up

### Checkpoint 6: run-directory reuse drift identified and supervisor replacement started

Additional diagnosis from the stale `manual-10way` artifacts:

- the same event log contained duplicate `START` lines for the first wave of
  behavior shards at different timestamps;
- this is consistent with an ad hoc rerun reusing the same run directory and
  appending new evidence to old evidence instead of starting a fresh
  run-identity boundary.

Immediate hardening direction:

- the tracked supervisor should use a `WAI-VALID-*` run id as the execution
  identity;
- a fresh run must refuse to reuse an existing run directory unless resume or
  explicit replacement semantics were requested;
- the supervisor must own the current-run pointer, queue snapshot, progress
  file, state file, and results file together so the monitor has one coherent
  source of truth.

### Checkpoint 7: validation routing and selector alignment completed

After the first tracked supervisor landed, the validation routing layer still
had one gap:

- `ops/scripts/windows/start-validation-supervisor.bat` was not yet covered by
  the selector registry, so the diff selector reported an unmatched path

Follow-up completed in this round:

- updated `tests/TEST_SELECTION_TARGETS.json` so `ops/scripts/windows/*.bat`
  routes into the static encoding / text-tooling validation surface
- updated `docs/agents/agent-startup-routing.md` to route parallel shard
  supervision into `parallel-validation-orchestration`
- updated `docs/agents/agent-execution-entrypoints.md` so validation execution
  explicitly references the new orchestration skill when the problem is live
  shard supervision instead of plain target selection

Observed result:

- `check_docs_governance.py` passed
- `check_repo_skills.py` passed
- `lint_validation_registry.py` passed
- the diff selector no longer reported unmatched paths for the new supervisor
  launcher and the non-full validation status returned to `acceptable`

## Final Outcome

In progress.
