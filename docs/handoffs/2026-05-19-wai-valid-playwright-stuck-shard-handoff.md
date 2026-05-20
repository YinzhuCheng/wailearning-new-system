# 2026-05-19 WAI-VALID Playwright Stuck Shard Handoff

## Purpose

This handoff is for the next agent/session that will continue the WAI-VALID
full validation campaign after the current chat context became too long.

The immediate issue is not the 19 failed Playwright shards. The user explicitly
asked to inspect only the one shard still reported as `running`:

- `tests/e2e/web-school/e2e-scenario-resilience.spec.js`

Do not start by investigating the failed shards unless the user asks. First
decide how to handle the still-running shard and preserve its artifacts.

## Branch And Baseline

- Branch: `cursor/repository-normalization-schema-notifications`
- HEAD at handoff creation: `f5eb5922c08ae9b78534ff81bc18f74580e5b44f`
- Current date/time context: 2026-05-19, Asia/Shanghai
- No push has been performed.

## Completed WAI-VALID Blocks

Observed durable green blocks in this campaign:

- `WAI-VALID-selector-light-validation-20260518`: `7/7` passed,
  `static-and-build`.
- `WAI-VALID-behavior-round-20260518`: `179/179` passed.
- `WAI-VALID-security-round-20260519`: `172/172` passed.
- `WAI-VALID-backend-postgres-round-20260519`: `43/43` passed.

Important caveat:

- `WAI-VALID-clean-restart-block1-20260518` covered the full
  `backend-sqlite-compatible` block and reached `480` tasks with `2` failures.
  Those failures were repaired and later covered by selector-light validation,
  but the full backend SQLite block itself has not been re-run green.

## Current Active Run

Run id:

- `WAI-VALID-playwright-school-round-20260519`

Block:

- `playwright-school-e2e`

Monitor snapshot reported by the user at 2026-05-19 around 12:46:

```text
passed=17/37 failed=19 running=1 queue=0
running slot:
 - tests/e2e/web-school/e2e-scenario-resilience.spec.js [primary]
```

Local progress snapshot observed at 2026-05-19T12:55:07:

```text
run_id: WAI-VALID-playwright-school-round-20260519
status: running
block: playwright-school-e2e
total: 37
completed: 17
failed: 19
running: 1
queue: 0
stuck_pid: 11496
stuck_elapsed_min: 35.6
```

Primary local artifact paths:

- `.agent-run/logs/WAI-VALID-playwright-school-round-20260519/progress.json`
- `.agent-run/logs/WAI-VALID-playwright-school-round-20260519/events.log`
- `.agent-run/logs/WAI-VALID-playwright-school-round-20260519/results.jsonl`
- `.agent-run/logs/WAI-VALID-playwright-school-round-20260519/run-config.json`
- `.agent-run/logs/WAI-VALID-playwright-school-round-20260519/block-report.json`
- `.agent-run/logs/WAI-VALID-playwright-school-round-20260519/block-summary.txt`

`summary.json`, `block-report.json`, and `block-summary.txt` may be absent or
stale until the supervisor exits. Use `progress.json` and `events.log` first
while the run is still active.

## Stuck Shard Evidence

Shard:

- `tests/e2e/web-school/e2e-scenario-resilience.spec.js`

Progress slot:

```text
shard: tests/e2e/web-school/e2e-scenario-resilience.spec.js
block: playwright-school-e2e
kind: playwright
origin: primary
origin_detail: direct-target
pid: 11496
started_at: 2026-05-19 12:19:34 local
```

`events.log` contains a `START` but no matching `END` for this shard:

```text
START playwright tests/e2e/web-school/e2e-scenario-resilience.spec.js block=playwright-school-e2e origin=primary detail=direct-target 2026-05-19T12:19:34
```

`results.jsonl` had no row for `e2e-scenario-resilience` when checked.

WAI-VALID worker logs for this shard were still empty:

```text
.agent-run/logs/WAI-VALID-playwright-school-round-20260519/WAI-VALID-worker-tests_e2e_web-school_e2e-scenario-resilience_spec_js__879edd87c7bc.log      length=0
.agent-run/logs/WAI-VALID-playwright-school-round-20260519/WAI-VALID-worker-tests_e2e_web-school_e2e-scenario-resilience_spec_js__879edd87c7bc.err.log  length=0
```

## Process Tree

Read-only elevated process tree query showed:

```text
ProcessId       : 11496
ParentProcessId : 7440
Name            : node.exe
CreationDate    : 2026/5/19 12:19:33
CommandLine     : node <repo>\apps\web\school\scripts\playwright-external-runner.cjs e2e-scenario-resilience.spec.js --project=chromium

ProcessId       : 9416
ParentProcessId : 11496
Name            : python.exe
CreationDate    : 2026/5/19 12:19:36
CommandLine     : <repo>\.venv\Scripts\python.exe -m uvicorn apps.backend.courseeval_backend.main:app --host 127.0.0.1 --port 18136

ProcessId       : 16148
ParentProcessId : 11496
Name            : node.exe
CreationDate    : 2026/5/19 12:20:07
CommandLine     : node <repo>\apps\web\school\node_modules\vite\bin\vite.js --host 127.0.0.1 --port 19136

ProcessId       : 12976
ParentProcessId : 11496
Name            : node.exe
CreationDate    : 2026/5/19 12:20:32
CommandLine     : "C:\Program Files\nodejs\node.exe" <repo>\apps\web\school\node_modules\@playwright\test\cli.js test e2e-scenario-resilience.spec.js --project=chromium
```

Resource snapshot around 2026-05-19T12:55:

```text
pid    process  run_minutes  cpu_s  working_set_mb
9416   python   35.5         0.00   2.9
11496  node     35.6         0.31   48.7
12976  node     34.6         7.69   140.1
16148  node     35.0         19.86  148.3
```

A 5-second CPU delta check across `11496`, `9416`, `16148`, and `12976` showed
`0` CPU delta for all four processes. This supports "not actively doing work"
rather than "slow but progressing".

## Local Playwright Artifacts

The shard did create Playwright `test-results` artifacts before appearing to
stall. Preserve these until the next agent mines them.

Directory root:

- `apps/web/school/test-results/`

Most recent `e2e-scenario-resilience` artifacts observed:

```text
apps/web/school/test-results/e2e-scenario-resilience-E2-ed91c-nvalidates-the-old-password-chromium/error-context.md
apps/web/school/test-results/e2e-scenario-resilience-E2-ed91c-nvalidates-the-old-password-chromium/test-failed-1.png
apps/web/school/test-results/e2e-scenario-resilience-E2-80249-the-migrated-class-snapshot-chromium/error-context.md
apps/web/school/test-results/e2e-scenario-resilience-E2-80249-the-migrated-class-snapshot-chromium/test-failed-1.png
apps/web/school/test-results/e2e-scenario-resilience-E2-9d913--one-final-unenrolled-state-chromium/error-context.md
apps/web/school/test-results/e2e-scenario-resilience-E2-9d913--one-final-unenrolled-state-chromium/test-failed-1.png
apps/web/school/test-results/e2e-scenario-resilience-E2-9d913--one-final-unenrolled-state-chromium/test-failed-2.png
```

Latest observed test-result write:

- `2026/5/19 12:53:51`

This means the spec did run multiple cases and generated failure artifacts, but
the outer WAI-VALID worker did not finish and did not write stdout/stderr.

## Interpretation

The still-running shard is very likely stuck in the Playwright external runner,
Playwright CLI, or teardown/server lifecycle. It is not obviously an active
test that is still making progress.

Key signals:

- The shard has no WAI-VALID worker stdout/stderr.
- The process tree still contains the external runner, backend server, Vite
  server, and Playwright CLI.
- CPU did not move across a 5-second sample.
- Local Playwright artifacts exist and continue beyond the WAI-VALID worker
  log silence.
- The supervisor is waiting for pid `11496` to exit before it can finalize the
  block.

## Do Not Do First

- Do not investigate the 19 failed shards first unless the user asks.
- Do not delete `apps/web/school/test-results/` before mining the stuck shard
  artifacts.
- Do not paste raw `summary.json` or raw `progress.json` into chat; use compact
  status or summarize selected fields.
- Do not claim the Playwright block is complete while `progress.json` still
  shows one running slot.

## Suggested Next Steps

1. Ask the user whether to stop only the stuck process tree for pid `11496` and
   its children (`9416`, `16148`, `12976`) or wait for the supervisor
   `--max-runtime-seconds` cutoff.
2. After the run finalizes, inspect only this shard first:
   - WAI-VALID worker logs
   - `events.log`
   - `results.jsonl`
   - `apps/web/school/test-results/e2e-scenario-resilience-*`
3. Add or harden a per-shard Playwright worker timeout in the WAI-VALID
   supervisor/external-runner path so a single Playwright CLI cannot hold the
   block forever.
4. Investigate `apps/web/school/scripts/playwright-external-runner.cjs` and the
   Playwright config/server teardown behavior for the scenario-resilience spec.
5. Once the stuck-shard orchestration issue is fixed, rerun this spec in a
   focused way before classifying the remaining 19 failures.

## WAI-VALID Workflow Changes In This Worktree

This worktree also contains WAI-VALID orchestration hardening that should remain
available to the next agent:

- clean block restart wrapper:
  `ops/scripts/windows/restart-validation-block-round-clean.ps1`
- compact status wrapper:
  `ops/scripts/windows/show-validation-status.bat`
- compact status script:
  `ops/scripts/dev/wai_valid_status.py`
- block/full/selector-light args builders under `ops/scripts/dev/`
- monitor detached helper:
  `ops/scripts/windows/start-validation-monitor-detached.ps1`
- marker-based cleanup scripts under `ops/scripts/windows/`
- updated workflow docs:
  `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- updated skills:
  `skills/parallel-validation-orchestration/SKILL.md`
  `skills/interruptible-full-validation-rounds/SKILL.md`

Known status-script caveat:

- During active Playwright pressure, `show-validation-status.bat` can take long
  enough to hit the caller timeout because Windows PID probing may fall back
  from `tasklist` to PowerShell `Get-Process`.
- For quick active-run checks, directly read selected fields from
  `.agent-run/logs/<run-id>/progress.json` and `events.log`.
