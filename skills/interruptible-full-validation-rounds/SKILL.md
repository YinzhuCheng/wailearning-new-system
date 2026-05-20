---
name: interruptible-full-validation-rounds
description: Use this when CourseEval full validation should run as explicit block-by-block rounds where one block is launched, the agent stops communication, the user reconnects after that block finishes, and the next move is decided from durable WAI-VALID artifacts.
---

# Interruptible Full Validation Rounds

## Purpose

Run CourseEval full validation as a **block-scoped interruption workflow**
instead of one long uninterrupted conversation.

Use this skill when the user wants all of the following at once:

- a full validation campaign
- explicit block order
- user-specified concurrency per block
- one block launched per round
- the agent stops communication after launching that block
- the user reconnects later
- the next action is chosen from durable block artifacts rather than memory

This skill is the **workflow coordinator**. It does not replace the two lower
level skills it depends on:

- [`../round-plan-discipline/SKILL.md`](../round-plan-discipline/SKILL.md)
- [`../parallel-validation-orchestration/SKILL.md`](../parallel-validation-orchestration/SKILL.md)

## Required Reading

Before using this skill, read these exact files in this order:

1. [`../../AGENTS.md`](../../AGENTS.md)
2. [`../../docs/README.md`](../../docs/README.md)
3. [`../../docs/governance/repository-governance.md`](../../docs/governance/repository-governance.md)
4. [`../../docs/agents/agent-closeout.md`](../../docs/agents/agent-closeout.md)
5. [`../../docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`](../../docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md)
6. [`../../docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`](../../docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md)
7. [`../../docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`](../../docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md)
8. [`../round-plan-discipline/SKILL.md`](../round-plan-discipline/SKILL.md)
9. [`../parallel-validation-orchestration/SKILL.md`](../parallel-validation-orchestration/SKILL.md)

Do not substitute ad hoc docs when these files already define the workflow.

## Skill Dependencies

### 1. Plan Skill

This skill **must** use:

- [`../round-plan-discipline/SKILL.md`](../round-plan-discipline/SKILL.md)

Reason:

- this full-validation mode is round-driven and cannot rely on chat memory
- the plan file is the recovery anchor after every intentional communication
  stop

### 2. Parallel Validation Skill

The plan written under this skill **must explicitly name**:

- [`../parallel-validation-orchestration/SKILL.md`](../parallel-validation-orchestration/SKILL.md)

Reason:

- each block is executed through WAI-VALID supervisor/monitor artifacts
- concurrency and automatic slot refill belong to that lower-level skill, not
  to this one

## What Counts As A Round

This definition is mandatory.

A **round** is exactly one of these two things:

### A. Validation Block Round

One block is prepared and launched, then the agent stops communication.

A validation block round contains:

1. re-read the active plan
2. identify the single target block
3. reconstruct that block's shard list
4. choose the user-specified concurrency for that block
5. open the visible monitor window for the current run when the repository has
   one
6. launch one WAI-VALID run for that block only
7. confirm that durable run artifacts are being written
8. stop communication

The monitor requirement is strict:

- the round should replace any previous WAI-VALID monitor ownership with the
  newly launched block run;
- the visible monitor should point at the new run id for that block, not an
  older current-run pointer;
- the launch is not confirmed until the run's `progress.json`,
  `WAI-VALID-current-run.json`, `WAI-VALID-monitor-ready.json`, and
  `WAI-VALID-monitor-heartbeat.json` all point at the same new run id;
- after confirming the new block wrote durable artifacts, the agent should stop
  communication without continuing to narrate execution in chat.

### B. Bug-Fix Round

The user reconnects after a block finished and the agent either:

- advances directly to the next block, or
- enters a repair round for failures found in the completed block

A bug-fix round contains:

1. re-read the active plan
2. inspect WAI-VALID artifacts first
3. classify failures from durable logs/reports
4. either:
   - mark the block complete and prepare the next block, or
   - fix one bounded failure set
5. update the plan
6. perform AGENTS closeout if tracked files changed
7. commit locally if tracked files changed

Do **not** blur multiple validation blocks into one round.

## AGENTS Workflow Requirement

Every round under this skill must obey the repository workflow from
[`../../AGENTS.md`](../../AGENTS.md).

At minimum, every round must:

1. re-read:
   - [`../../AGENTS.md`](../../AGENTS.md)
   - [`../../docs/README.md`](../../docs/README.md)
   - [`../../docs/governance/repository-governance.md`](../../docs/governance/repository-governance.md)
   - the active plan file under `.agent-run/plan/`
2. state the single round objective before work starts
3. execute only that bounded round objective
4. update the plan before the round ends
5. follow [`../../docs/agents/agent-closeout.md`](../../docs/agents/agent-closeout.md) when tracked files changed
6. append `docs/testing/agent-update-log.csv` before every repository-changing
   commit
7. commit locally and do not push unless the user explicitly asks

## Plan Contract

When this skill is active, create or update a plan file under:

- `.agent-run/plan/`

The plan must include all of the following:

1. exact path to the active plan file
2. explicit statement that the plan is governed by:
   - [`../round-plan-discipline/SKILL.md`](../round-plan-discipline/SKILL.md)
   - [`../parallel-validation-orchestration/SKILL.md`](../parallel-validation-orchestration/SKILL.md)
3. exact block order
4. exact concurrency per block, as supplied by the user
5. explicit statement that communication stops after launching each block
6. explicit reconnect behavior:
   - inspect WAI-VALID artifacts first
   - then decide whether to fix failures or move to the next block
7. definition of what counts as a round
8. progress sections that can be resumed from directly

If the plan does not name the parallel-validation skill explicitly, the plan is
incomplete.

## Concurrency Contract

The user may specify concurrency in any of these forms:

- if the user does not specify a value, the repository default is `10` for
  every block
- one global value applied to every block
- one value per block
- a mixed map such as:
  - `static-and-build = 10`
  - `backend-sqlite-compatible = 10`
  - `behavior = 10`
  - `security = 10`
  - `backend-postgres-sensitive = 10`
  - `playwright-school-e2e = 10`

This skill must preserve the user's chosen values in the plan file.

Do not silently replace the requested value. If later instability forces a
change, record the exact reason in the plan before using a different value.

## Current Shard Contract

Unless the repository contract changes again, assume:

- non-E2E pytest blocks run at case level using pytest nodeids
- school Playwright E2E runs at file level using one `.spec.js` file per task

Route execution through the committed WAI-VALID runtime:

- [`../../ops/scripts/dev/wai_valid_supervisor.py`](../../ops/scripts/dev/wai_valid_supervisor.py)
- [`../../ops/scripts/dev/wai_valid_monitor.py`](../../ops/scripts/dev/wai_valid_monitor.py)
- [`../../ops/scripts/dev/wai_valid_render.py`](../../ops/scripts/dev/wai_valid_render.py)
- [`../../ops/scripts/windows/start-validation-supervisor.bat`](../../ops/scripts/windows/start-validation-supervisor.bat)
- [`../../ops/scripts/windows/start-validation-monitor.bat`](../../ops/scripts/windows/start-validation-monitor.bat)

## Canonical Block Order

Default full-validation order:

1. `static-and-build`
2. `backend-sqlite-compatible`
3. `behavior`
4. `security`
5. `backend-postgres-sensitive`
6. `playwright-school-e2e`

Only change the order when the user explicitly asks or the current plan records
an honest reason.

## Required Artifacts Per Block

Every launched block must leave durable artifacts under the run directory, at
minimum:

- `summary.json`
- `progress.json`
- `block-report.json`
- `block-summary.txt`
- `events.log`

For reconnect/status answers, use the compact status entrypoint first:

```powershell
ops\scripts\windows\show-validation-status.bat --run-id <run-id>
```

Equivalent direct Python entrypoint:

```powershell
python ops\scripts\dev\wai_valid_status.py --run-id <run-id>
```

Do not paste raw `summary.json` or `progress.json` into chat by default. Those
files can contain long shard lists such as `completed_shards` and can truncate
the useful answer. The compact status entrypoint also reports WAI-VALID pid-file
liveness for supervisor, monitor Python, and monitor shell ownership. Open raw
JSON only when debugging serialization or artifact corruption, and then
summarize the relevant fields. On Windows, let the status script's PowerShell
`Get-Process` fallback resolve `tasklist` access-denied probes before calling a
pid file stale.

Use these artifacts, not chat memory, to answer on reconnect:

- what ran
- what passed
- what failed
- whether the failures look like product, test, or environment issues

## Monitor Requirement

When this skill launches a validation block, it should also start the visible
monitor window whenever the repository provides one.

Current repository path:

- [`../../ops/scripts/windows/start-validation-monitor.bat`](../../ops/scripts/windows/start-validation-monitor.bat)
- [`../../ops/scripts/windows/start-validation-monitor-detached.ps1`](../../ops/scripts/windows/start-validation-monitor-detached.ps1)

Current monitor runtime:

- [`../../ops/scripts/dev/wai_valid_monitor.py`](../../ops/scripts/dev/wai_valid_monitor.py)

Default policy for future rounds:

- for normal repository block rounds, prefer
  `ops/scripts/windows/restart-validation-block-round-clean.ps1` rather than
  manually composing supervisor and monitor commands
- when the block itself is launched from another script, prefer the detached
  visible monitor helper so the user reliably gets a separate monitor window
- for a clean block restart after stale progress, use
  `ops/scripts/windows/restart-validation-block-round-clean.ps1` so cleanup,
  cache removal, block launch, monitor launch, and heartbeat verification stay
  one reproducible workflow
- keep it as the user-facing live status surface
- rely on durable artifacts as the source of truth on reconnect
- do not treat an early `collecting` screen with `0/0` as proof that the block
  failed to launch; verify `events.log` and fresh `progress.json` timestamps
  first
- prefer launch flows that also verify monitor ready/heartbeat artifacts before
  declaring the monitor successfully attached
- when deciding whether a launched block is genuinely progressing, compare the
  monitor heartbeat's observed progress timestamp with the run's own
  `progress.json` timestamp before concluding the run is stuck
- when using the clean restart wrapper, require its freshness check to compare
  `heartbeat.progress_updated_at` to `progress.json.updated_at`; if they differ,
  the monitor is not proven attached to the latest rendered state
- if the monitor heartbeat is fresh but the observed progress timestamp is old,
  diagnose the run/supervisor rather than the monitor; a clean block restart is
  the default recovery when the supervisor is no longer alive

## Launch / Hang-Up Procedure

When the user says to start the next block:

1. re-read the active plan
2. reconstruct the shard list for the next block
3. launch one WAI-VALID run for that block only through
   `ops/scripts/windows/restart-validation-block-round-clean.ps1` unless the
   user explicitly asks for a lower-level command
4. verify that the run directory, current-run pointer, monitor ready artifact,
   and heartbeat artifact all point at the requested run
5. tell the user which block was launched and which run id to watch
6. stop communication

For repository-default block launches, treat this as a hang-up boundary:

- once the requested block is launched and the monitor is attached to that run,
  do not continue the round in chat;
- the next turn should begin from WAI-VALID artifacts after the user reconnects.

Do not remain in chat narrating the run after the block has been launched if
the user requested hang-up mode.

## Reconnect Procedure

When the user reconnects after a block finished:

1. re-read:
   - the active plan
   - compact status from `ops\scripts\windows\show-validation-status.bat`
   - `block-report.json`
   - `block-summary.txt`
   - `events.log`
2. classify the block result as one of:
   - green, advance
   - red, needs bug-fix round
   - blocked, needs environment or orchestration round
3. update the plan with observed evidence
4. only then decide whether to:
   - move to the next block
   - or repair failures

## Guardrails

- Do not launch more than one validation block in one round.
- Do not skip plan updates after a block finishes.
- Do not skip `AGENTS.md` workflow because the round was “only a launch”.
- Do not rely on memory for reconnect status.
- Do not push after a repository-changing repair round unless the user
  explicitly asks.
- Do not let old `.agent-run/plan/` files accumulate when they are clearly
  completed or superseded.

## Related Files

- [`../../AGENTS.md`](../../AGENTS.md)
- [`../../docs/README.md`](../../docs/README.md)
- [`../../docs/governance/repository-governance.md`](../../docs/governance/repository-governance.md)
- [`../../docs/agents/agent-closeout.md`](../../docs/agents/agent-closeout.md)
- [`../../docs/agents/local-agent-workspace.md`](../../docs/agents/local-agent-workspace.md)
- [`../../docs/governance/agent-update-log.md`](../../docs/governance/agent-update-log.md)
- [`../../docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`](../../docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md)
- [`../../docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`](../../docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md)
- [`../../docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`](../../docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md)
- [`../round-plan-discipline/SKILL.md`](../round-plan-discipline/SKILL.md)
- [`../parallel-validation-orchestration/SKILL.md`](../parallel-validation-orchestration/SKILL.md)
