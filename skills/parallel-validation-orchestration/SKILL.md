---
name: parallel-validation-orchestration
description: Use this when CourseEval validation should run in parallel with automatic slot refill, explicit process supervision, persistent progress files, per-block concurrency, and shard-specific PostgreSQL isolation instead of manual batch launching.
---

# Parallel Validation Orchestration

## Purpose

Run large CourseEval validation workloads with:

- automatic slot refill instead of manual batch replacement
- arbitrary self-organized sample blocks instead of fixed block-only runs
- explicit long-lived supervisor processes
- stable progress files that future rounds can read
- per-block and per-shard concurrency settings
- isolated PostgreSQL workers for dialect-sensitive shards

This skill exists to replace manual “launch a batch, wait, manually top up”
testing loops with durable process orchestration.

## Canonical Process Names / Prefixes

Use the prefix **`WAI-VALID-`** for every durable process, state file, and log
surface so the operator can rediscover them without relying on memory.

These names must remain explicit in every future revision of the workflow:

- `WAI-VALID-supervisor`
- `WAI-VALID-worker`
- `WAI-VALID-pg-worker`
- `WAI-VALID-watchdog`

Every long-lived WAI-VALID-owned python process should also carry a
command-line marker:

- `--process-tag WAI-VALID-<run-id-or-operator-tag>`

On Windows the actual executable name may still be `python.exe` or
`powershell.exe`, but the **script filenames, pid files, state files, command
lines, log directories, and progress files** must include the `WAI-VALID-`
prefix.

## Durable Local State

Recommended local-only state root:

- `.agent-run/validation-daemon/`

Recommended files:

- `.agent-run/validation-daemon/WAI-VALID-state.json`
- `.agent-run/validation-daemon/WAI-VALID-queue.json`
- `.agent-run/validation-daemon/WAI-VALID-progress.json`
- `.agent-run/validation-daemon/WAI-VALID-current-run.json`
- `.agent-run/validation-daemon/WAI-VALID-supervisor.pid`
- `.agent-run/validation-daemon/WAI-VALID-watchdog.pid`

Recommended log roots:

- `.agent-run/logs/WAI-VALID-backend-*/`
- `.agent-run/logs/WAI-VALID-behavior-*/`
- `.agent-run/logs/WAI-VALID-e2e-*/`

## Workflow

1. Read:
   - `AGENTS.md`
   - `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
   - `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`
   - `docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md` when browser shards are in scope
2. Classify incoming test examples / paths into blocks:
   - backend SQLite-compatible
   - backend PostgreSQL-sensitive
   - behavior
   - Playwright E2E
3. Choose concurrency **per block**, not globally. Default to `10` unless the
   operator or a committed run plan records a specific lower value and why.
4. Before starting a run, ask the operator to confirm:
   - blocks
   - per-block concurrency
   - whether visible monitoring should use the default repository monitor flow
5. Start one **`WAI-VALID-supervisor`** process for the current run.
6. The supervisor:
   - loads the task queue
   - fills up to the configured slot count
   - watches for completed workers
   - immediately refills freed slots from the queue
   - writes progress after every state change
7. Open a **foreground progress monitor window** that tails the progress file
   and prints updates, unless the user explicitly asked for no visible monitor.
8. Normal backend/behavior shards use `WAI-VALID-worker`.
9. PostgreSQL-sensitive shards use `WAI-VALID-pg-worker`, one isolated fresh
   cluster / port / data dir per shard.
10. If needed, a lightweight **`WAI-VALID-watchdog`** watches the supervisor and
   restarts it only when the current state files show resumable work.
11. When the queue drains, the supervisor writes a final summary and exits
   cleanly.

## Input / Output Contract

### Input

Accept either:

- explicit test paths/files
- explicit pytest nodeids or Playwright spec files
- repeated `--sample` values
- one or more `--samples-file` UTF-8 text / JSON files
- a directory list
- a mixed list of test samples
- a natural-language regression intent such as `light`, `medium`, or `heavy`

The skill must then perform **automatic block splitting** by:

1. identifying the shard family
2. grouping into backend / behavior / Playwright
3. further separating PostgreSQL-sensitive shards from SQLite-compatible shards
4. assigning the requested concurrency per block

For any operator-selected series of samples, the default execution shape is a
self-organized custom WAI-VALID block with concurrent slot refill. Do not run
that series as serial ad hoc terminal commands unless the user explicitly names
one single command or requests serial execution.

### Output

Produce these durable artifacts:

- a block plan file
- a queue file
- a progress file
- a results file
- per-shard logs
- a final summary
- a block report file
- a plain-text block summary file

## Automatic Block Splitting

When the input is a set of test samples or file paths, split them
automatically using these rules:

1. **backend** first
2. within backend:
   - `tests/backend/postgres`-like or explicit PostgreSQL-only paths go to the
     PostgreSQL-sensitive lane
   - everything else goes to the SQLite-compatible lane
3. **behavior** second
4. **Playwright E2E** third

If a sample belongs to multiple lanes, prefer the narrowest lane that can be
executed safely and deterministically.

## Per-Block Concurrency Controls

Each block may have a different concurrency value.

Examples:

- backend SQLite-compatible: `4`
- backend PostgreSQL-sensitive: `1` per isolated cluster unless you explicitly
  provision one cluster per worker
- behavior: `5` or `10` depending on machine headroom
- Playwright: `1` unless you have isolated ports and DBs

The supervisor must keep the block-specific concurrency in the progress file so
the operator can see which block is using which budget.

The first tracked runtime now supports block-aware launch specs such as:

```text
--block-spec behavior:5:tests/behavior/test_admin_llm_policy_behavior.py,tests/behavior/test_discussion_api_behavior.py
--block-spec backend-postgres-sensitive:2:tests/postgres/test_postgres_dialect_guards.py,tests/postgres/test_postgres_llm_schema_and_policy.py
```

It also supports custom arbitrary sample blocks:

```powershell
ops\scripts\windows\start-custom-validation-block.bat custom-light-<date> self-organized-light .agent-run\plan\custom-samples.txt 900 10 light
```

Lower-level equivalent:

```powershell
ops\scripts\windows\start-validation-supervisor.bat --run-id custom-light-<date> --replace-run-dir --regression-mode light --block self-organized-light --concurrency 10 --samples-file .agent-run\plan\custom-samples.txt --process-tag WAI-VALID-custom-light-<date> --max-runtime-seconds 900
```

## Regression Intensity

The orchestration layer should accept a regression intensity label in addition
to the raw shard list.

Recommended vocabulary:

- `light`
  - direct targets only
  - minimum static/governance validation
- `medium`
  - direct targets
  - nearby related blocks
  - historically fragile regressions when relevant
- `heavy`
  - any logic change expands to the related logic surface
  - still not equivalent to full-suite by default

The run config, progress file, and monitor should all expose the chosen
regression intensity explicitly.

The first tracked implementation now expands some domains this way:

- `light`
  - direct targets only
- `medium`
  - direct targets plus a small adjacent regression surface
- `heavy`
  - direct targets plus a wider related logic surface

Current first-pass domain coverage includes:

- `homework`
- `llm`
- `notifications`
- `discussions`
- `roster`

These expansion rules are intentionally conservative and committed in the
runtime so they can be revised through repository history instead of terminal
lore.

Observed first-pass proof:

- `light` on `tests/backend/homework/test_homework_llm_grading.py` stayed at
  1 direct task
- `heavy` on the same input expanded to a 6-task run that also scheduled
  related behavior suites

## Progress Listener

The process pair should include a progress listener that:

1. reads the progress file on an interval
2. prints a concise progress line
3. reports:
   - active block
   - concurrency
   - completed / total
   - running shard count
   - failed shard count
4. never replaces the source of truth in the progress file

This listener is for observability only.

Recommended console format:

```text
[WAI-VALID] behavior 10-way | 10/20 done | running=8 | failed=1 | queue=1
```

### Visible Monitor Window

The workflow should expose a foreground monitor window by default rather than a
hidden-only background process. Skip it only when the user explicitly asks for
no visible monitor.

The visible monitor window must:

- remain open for the duration of the run
- refresh on an interval
- show block name, concurrency, running, completed, failed, and queue counts
- list the currently running shards
- show regression intensity and regression-origin breakdown
- show per-block pass / fail / total and current slot occupancy
- be easy to inspect without switching away from chat

The first tracked monitor layout now aims to read like a live report with:

- a run header
- an overall summary
- a per-block section
- a running-slot section
- a recent-events section

The monitor window is for visibility; the progress file remains the source of
truth.

Recommended implementation files:

- `ops/scripts/dev/wai_valid_supervisor.py`
- `ops/scripts/dev/wai_valid_monitor.py`
- `ops/scripts/dev/wai_valid_status.py`
- `ops/scripts/dev/wai_valid_build_full_args.py`
- `ops/scripts/windows/restart-validation-block-round-clean.ps1`
- `ops/scripts/windows/show-validation-status.bat`
- `ops/scripts/windows/start-validation-monitor.bat`
- `ops/scripts/windows/start-validation-monitor-detached.ps1`
- `ops/scripts/windows/start-validation-supervisor.bat`
- `ops/scripts/windows/start-full-validation-supervisor.bat`

Default operator behavior:

- launching `start-validation-supervisor.bat` should start a visible Win10
  console titled `WAI-VALID-supervisor`
- launching `start-validation-monitor.bat` should open a visible Win10 console
  window titled `WAI-VALID-monitor`
- repository launchers should prefer `start-validation-monitor-detached.ps1`
  when they need to open that visible monitor from another background or batch
  entrypoint
- on Windows, prefer the detached PowerShell monitor helper over `cmd /c` or a
  nested batch launch so the user gets a clearly visible independent monitor
  window rather than a short-lived shell host
- the monitor should discover the current run automatically from
  `WAI-VALID-current-run.json`
- the monitor should also publish lightweight ready/heartbeat artifacts under
  `.agent-run/validation-daemon/` so automation can distinguish:
  - monitor window failed to launch
  - monitor process is alive but waiting for progress
  - monitor is actively rendering fresh progress
- the monitor heartbeat should include the latest progress timestamp it has
  observed from the run's `progress.json`
- when started with a concrete run id, the monitor should exit by itself if the
  requested progress file never appears within the startup timeout
- after a run reaches a final state, the monitor should keep the final summary
  visible briefly and then exit by itself
- during an active run, Windows may show a foreground `python.exe` process
  owned by the visible monitor window; this is expected while the monitor is
  rendering progress and is not a zombie process by itself
- after the monitor Python process exits, the detached PowerShell shell may
  remain open by design to preserve the final visible report; the shell should
  have a `WAI-VALID-monitor:<run>` title and is low-memory compared with the
  supervisor/workers

Operator interpretation rule:

- during long pytest collection, the monitor may temporarily show `phase=collecting`
  with `passed=0/0` or `discovered_tasks=0`
- this does **not** mean the block failed to launch by itself
- treat the run as alive when:
  - `events.log` contains `BOOTSTRAP collect-start`, and
  - `progress.json` keeps receiving fresh timestamps
- treat collection as complete only after `events.log` records
  `BOOTSTRAP collect-finished` and `progress.json` shows a non-zero total
- when the window appears visually stale, compare:
  - the monitor heartbeat `updated_at`
  - the heartbeat `progress_updated_at`
  - the run `progress.json` `updated_at`
  This distinguishes a stale display from a stalled run
- if the monitor heartbeat `updated_at` advances but both
  `progress_updated_at` and the run `progress.json` timestamp do not advance,
  treat the run as stalled/stale; restart the block with the clean block
  restart workflow instead of repeatedly restarting only the monitor

## Block Switching Rules

Do not mix blocks without explicit policy.

Recommended sequence:

1. backend SQLite-compatible
2. backend PostgreSQL-sensitive
3. behavior
4. Playwright E2E

Only switch blocks when:

- the current block is clean
- or it is honestly blocked
- or the operator explicitly requests a transition

## Post-Fix Lightweight Validation

After fixing a bug in the WAI-VALID workflow itself, do not jump straight to a
full repository rerun unless the user explicitly asks for that.

Preferred repository-default sequence:

1. keep the same WAI-VALID supervisor / monitor / progress-file workflow;
2. derive the seed set through the repository selector workflow first, using
   `skills/validation-selection/SKILL.md` and
   `run_validation_profile.py selector-recommended` or
   `select_validation_targets.py --json`;
3. launch a **small concurrent bugfix verification run** from that
   selector-derived seed set instead of hand-picking ad hoc nodeids;
4. allow the orchestration layer to keep `regression_mode=light`, which means
   direct targets only from the selected seed set;
5. keep concurrency greater than `1` when the lane is safely parallelizable, so
   the post-fix run still exercises slot refill and concurrent orchestration;
6. only escalate to a larger block or full run after the lightweight
   concurrent verification is green.

Recommended shape for this post-fix run:

- `regression_mode=light`
- one explicit block only
- selector-derived direct targets only
- a short operator-visible run id such as
  `WAI-VALID-light-bugfix-<topic>-<date>`
- the same `--process-tag`, monitor, timeout, and durable artifacts as a normal
  WAI-VALID run

This rule exists so orchestration fixes are validated through the real
repository workflow without paying the cost or risk of an immediate full-suite
rerun.

## Resume Rules

The supervisor should resume from state if:

- the queue file exists
- the progress file exists
- the task list can be reconstructed deterministically

If a run is resumed, the supervisor should preserve:

- already completed shards
- failed shards
- current block
- current concurrency

## Exact Process Naming Convention

Keep these names in the docs and scripts:

- supervisor: `WAI-VALID-supervisor`
- watcher: `WAI-VALID-watchdog`
- generic worker: `WAI-VALID-worker`
- PostgreSQL worker: `WAI-VALID-pg-worker`

Do not rename these casually. They are intentionally the stable discovery
surface for the operator.

The first tracked implementation now lives in:

- `ops/scripts/dev/wai_valid_supervisor.py`
- `ops/scripts/windows/start-validation-supervisor.bat`
- `ops/scripts/dev/wai_valid_monitor.py`
- `ops/scripts/windows/start-validation-monitor.bat`

For the repository-default full validation block plan, prefer the maintained
launcher:

```powershell
ops\scripts\windows\start-full-validation-supervisor.bat full-validation-<date>
```

This launcher:

- discovers the maintained backend / behavior / security / postgres /
  Playwright file lists;
- writes the long `--block-spec` array into a JSON args file instead of
  trusting one huge inline Windows command line;
- launches the detached supervisor through the normal repository entrypoint;
- opens the visible monitor for the same run id by default.

Treat this as the default full-run entrypoint unless the task needs a custom
block subset or custom block order.

## Early Bootstrap Visibility

The supervisor must expose bootstrap progress before the expensive pytest
collection/classification stage finishes.

Current contract:

- after parsing arguments and creating the run directory, immediately write:
  - `WAI-VALID-current-run.json`
  - an initial `progress.json`
  - an initial `WAI-VALID-state.json`
- the initial progress payload should show a bootstrap phase such as
  `collecting` with a short message like:
  `Collecting pytest nodeids and classifying run blocks.`
- the visible monitor should render this bootstrap phase instead of waiting on
  a missing progress file for long-running full validation launches

This avoids the operator-facing false signal where the supervisor is alive but
the monitor only shows `waiting for a progress file...` during long
`pytest --collect-only` expansion work.

## Lifetime And Self-Exit Contract

WAI-VALID-owned python processes should not live forever by accident.

Current repository contract:

- supervisor:
  - exits normally when the queue drains
  - force-stops the run when `--max-runtime-seconds` is exceeded
- monitor:
  - exits if a forced `--run-id` still has no progress file after the startup
    timeout
  - exits shortly after the run reaches a final state
- pytest worker wrapper processes:
  - carry the same `--process-tag`
  - exit naturally when their single target finishes

For repository-default full validation on Windows, the maintained launcher now
accepts:

```powershell
ops\scripts\windows\start-full-validation-supervisor.bat full-validation-<date> 10800
```

where the second positional argument is the maximum supervisor lifetime in
seconds. Keep this value operator-adjustable.

## Tagged Cleanup

Use the tagged cleanup script when a stale WAI-VALID python fleet needs to be
cleared explicitly:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\stop-tagged-python-processes.ps1 "WAI-VALID-full-validation-<date>"
```

This script is intentionally marker-based rather than path-guess-based.

For stale block runs, prefer the clean block restart wrapper:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\restart-validation-block-round-clean.ps1 behavior behavior-round-<date> 10800 10 light
```

This wrapper is the default recovery path when a block shows stale progress. It:

- stops the recorded supervisor, worker, and monitor process trees for the run;
- removes the stale run directory and monitor heartbeat artifacts;
- rebuilds the block args through the repository block selector;
- launches the block with the configured concurrency and max lifetime;
- opens the visible monitor; and
- verifies that `progress.json`, `WAI-VALID-current-run.json`,
  `WAI-VALID-monitor-ready.json`, and `WAI-VALID-monitor-heartbeat.json` all
  point at the fresh run before reporting success;
- verifies that `heartbeat.progress_updated_at` matches the run's
  `progress.json.updated_at`, proving the monitor rendered the latest known
  progress rather than only starting a stale window.

Use the same clean wrapper for ordinary next-block launches, not only for stale
run recovery, unless the operator explicitly asks for manual lower-level
commands. This keeps cleanup, launch, monitor startup, and freshness checks on
one reproducible path.

## Input Contract

The orchestrator should accept:

- a list of test examples, directories, or files
- a block type or auto-classification mode
- a concurrency value per block
- CPU and memory ceilings
- a PostgreSQL isolation toggle
- a resume-from-state toggle

Example conceptual input:

```json
{
  "block": "behavior",
  "targets": [
    "tests/behavior/test_discussion_api_behavior.py",
    "tests/behavior/test_multi_actor_timeline_behavior.py"
  ],
  "concurrency": 10,
  "cpu_target": 75,
  "memory_target": 85,
  "postgres_isolation": true,
  "resume": true
}
```

## Default Concurrency Contract

Unless the user or an explicit plan file says otherwise, assume a default
concurrency of **10 for every block**.

This repository default applies to:

- `static-and-build`
- `backend-sqlite-compatible`
- `behavior`
- `security`
- `backend-postgres-sensitive`
- `playwright-school-e2e`

If a run needs a lower value for stability or isolation, do not silently drift
from the default. Record the exact override and the concrete reason in the plan
or handoff before launching that block.

## Automatic Slot Refill Rule

This is the core rule of the skill:

- **never wait for a whole batch to finish before starting the next shard**
- the supervisor must refill any freed slot as soon as a worker ends and the
  queue still has work
- when running a chosen series of samples, create a custom concurrent block and
  let WAI-VALID refill slots; do not iterate through the list by hand

The only exceptions are:

- browser/E2E shards where explicit port / DB isolation is not available
- operator-chosen serial or low-concurrency safety mode

## Block-Specific Rules

### Backend SQLite-compatible

- parallel workers are allowed because `tests/conftest.py` uses per-process
  SQLite files by default
- use high concurrency if machine resource ceilings permit it

### Backend PostgreSQL-sensitive

- never share one `TEST_DATABASE_URL` across concurrent workers
- every `WAI-VALID-pg-worker` gets:
  - a fresh data dir
  - a unique port
  - a fresh test database

### Behavior

- pytest case-level shards are preferred via collected nodeids
- automatic refill is allowed
- keep a close eye on CPU because behavior collections can expand one file into
  many runnable tasks

### General pytest blocks

- for non-E2E blocks (`tests/backend/**`, `tests/behavior/**`,
  `tests/security/**`, `tests/postgres/**`), the preferred shard unit is one
  pytest nodeid per task
- the orchestrator may accept file paths as input, but it should collect and
  expand them into case-level runnable targets before queue execution
- progress and monitor output should show both the source file and the current
  pytest case when possible

### Playwright E2E

- keep Playwright at file-level `.spec.js` shards by default
- parallelism is allowed only with explicit isolation:
  - distinct API ports
  - distinct UI ports
  - distinct DB / SQLite state
  - separate webServer lifecycles
- otherwise run serial or low-concurrency
- WAI-VALID custom blocks provide the required isolated API/UI ports and should
  use the default custom-block concurrency of `10` unless local resource
  pressure requires a documented lower value
- a Playwright shard timeout defaults to `900` seconds; timeout failures should
  be reported as `worker-timeout` rather than leaving the block permanently
  running

## Monitoring Rules

The supervisor must write progress often enough that an interrupted human can
ask “what is still running?” and get a real answer from files, not memory.

Minimum fields in the progress file:

- updated timestamp
- total shard count
- queue remaining
- running shards
- completed shard count
- failed shard count
- completed shard list
- failed shard list
- active block name
- configured concurrency
- regression intensity
- running slot metadata
- per-block summary metadata
- regression-origin totals
- block concurrency mapping

## Failure Handling

When a worker fails:

1. record the shard as failed
2. keep the supervisor alive
3. continue refilling remaining slots unless operator policy says “stop on
   first failure”
4. write the failed shard log path into state
5. leave enough information for a later focused rerun

## Resume / Reconnect Aid

Every finished run should leave behind a quick human-readable summary file in
the run directory. Use it on reconnect to answer:

- which blocks completed
- which shards failed
- whether the failures look like product/test regressions or environment /
  bootstrap problems

Status inspection should use the compact status entrypoint first:

```powershell
ops\scripts\windows\show-validation-status.bat --run-id <run-id>
```

This wrapper calls `ops/scripts/dev/wai_valid_status.py`, prints WAI-VALID
pid-file liveness, and intentionally omits long completed-shard lists. Do not
dump raw `summary.json` or `progress.json` into chat by default; those files may
include hundreds of completed shards and can truncate the useful answer. Open
raw JSON only for artifact corruption or serialization debugging, and summarize
the relevant fields. On Windows, treat `tasklist` access-denied PID probes as
ambiguous until the compact status script's PowerShell `Get-Process` fallback
also says the pid is gone.

Preferred artifact pair:

- `block-report.json`
- `block-summary.txt`

## Task Metadata

Every supervised task should be able to carry:

- `block`
- `kind`
- `origin`
  - `primary`
  - `regression`
  - `retry`
- `origin_detail`
  - short label such as `direct-target`, `adjacent-surface`, or
    `failure-rerun`

The monitor should expose these labels so the operator can distinguish direct
tests from expanded regression coverage.

## Guardrails

- Do not use one PostgreSQL database for multiple concurrent pytest workers.
- Do not let Playwright default-port jobs run in parallel without explicit
  isolation.
- Do not rely on transient in-memory state as the only source of truth.
- Do not present batch-level status from stale cache files; rewrite progress on
  every state change.
- Keep process names / prefixes stable so the operator can rediscover them.
- Do not let the listener become the only source of truth; the progress file is
  the source of truth.
- Do not write a single monolithic “all tests” queue when a block-specific queue
  can be reconstructed from inputs.

## When To Request Escalation

Escalation may be required when:

- starting durable detached supervisor or watchdog processes outside the default
  sandbox lifecycle
- creating or running isolated PostgreSQL clusters that need a less restricted
  execution context
- binding ports or running browser/webServer processes in a context where the
  default sandbox kills background children
- opening multiple isolated PostgreSQL worker instances for parallel shards

If escalation is required, request it explicitly and explain that it is for the
`WAI-VALID-*` supervisor / worker system.

## Current Runtime Boundary

The first tracked runtime now supports:

- multi-block runs through repeated `--block-spec`
- custom arbitrary samples through `--sample` and `--samples-file`
- default single-block concurrency of `10`
- Windows custom launch through
  `ops/scripts/windows/start-custom-validation-block.bat`
- per-block concurrency enforcement
- block-aware progress reporting
- Playwright shard timeout enforcement

It does **not** yet fully implement:

- automatic natural-language expansion from `light` / `medium` / `heavy`
  regression modes into additional tasks
- a finished watchdog/resume stack

## Related Files

- `AGENTS.md`
- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`
- `docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`
- `skills/validation-selection/SKILL.md`
- `skills/postgres-release-validation/SKILL.md`
- `skills/school-playwright-e2e/SKILL.md`
