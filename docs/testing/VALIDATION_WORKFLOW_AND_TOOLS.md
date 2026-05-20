# Validation Workflow And Tools

## Purpose

This document is the focused entrypoint for CourseEval's diff-based validation
workflow, selector/runner/profile tooling, and the evidence rules that govern
how those tools should be interpreted.

Use it when:

- choosing validation scope from a diff;
- running the validation selector, target runner, or profile runner;
- deciding how to record observed validation honestly;
- checking local validation sufficiency before broader suites.

`DEVELOPMENT_AND_TESTING.md` remains the broader development/testing handbook.
This document is the narrower source for validation mechanics.

## Diff-Based Validation Workflow

The diff-based validation tools provide the repository's first standard
incremental validation workflow. Use them after edits to decide what to run
before reaching for full `pytest`, full Playwright, or PostgreSQL-heavy
profiles.

The workflow has three layers:

- selector: recommend targets from changed paths
- target runner: execute one selected target and write local artifacts
- profile runner: execute a small named group of targets

Default agent loop:

1. Review the changed-path recommendation from the repository root:

   ```bash
   python ops/scripts/dev/select_validation_targets.py --worktree
   ```

2. If the output is for automation or you need to inspect exact target IDs, use:

   ```bash
   python ops/scripts/dev/select_validation_targets.py --worktree --json
   ```

3. Use the repository default `strict` workflow unless the user explicitly asks
   for a lighter guided route.

   In the text-first workflow:

   - `strict` means starting from the repository governance entrypoints,
     reading the task-scoped docs and skills, using pitfall search before
     classifying ambiguous failures, and updating docs plus durable ledgers in
     the same repository-changing round
   - `guided` remains a lighter advisory route chosen explicitly by the user,
     but guided evidence must never be reported as strict completion

4. For documentation-only or validation-tooling changes, run the static profile
   first:

   ```bash
   python ops/scripts/dev/run_validation_profile.py static --dry-run --timeout-seconds 120
   ```

   Use the real static target when you need observed evidence rather than a
   profile smoke:

   ```bash
   python ops/scripts/dev/run_validation_target.py static.validation_selector --timeout-seconds 120
   ```

5. For ordinary product or test changes, either run the target IDs shown by the
   selector one by one, or use the selector-recommended profile:

   ```bash
   python ops/scripts/dev/run_validation_profile.py selector-recommended --worktree --max-risk targeted
   ```

6. If the selector recommends a review-required target, decide explicitly
   whether the environment is ready. Browser targets generally need Node,
   `node_modules`, Playwright browsers, clean ports, and a known
   backend/frontend startup mode:

   ```bash
   python ops/scripts/dev/run_validation_profile.py selector-recommended --worktree --max-risk broad --include-review-targets
   ```

7. Read the final selector/profile status before claiming validation coverage:

   - `acceptable`: static/targeted evidence is a reasonable first-pass result
     for the current diff
   - `needs_review`: a broad or review-required target was recommended; either
     run it or state why it was deferred
   - `not_sufficient`: targeted validation is not enough; address the blocker
     or explicitly defer it as unresolved validation

This is a planning and evidence workflow, not a magic minimizer. The selector
is conservative and path-based. It does not understand every semantic
dependency in the product. If the diff touches high-risk behavior and the
recommendation looks too narrow, run the broader target and update
[`tests/TEST_SELECTION_TARGETS.json`](../../tests/TEST_SELECTION_TARGETS.json)
when the gap is repeatable.

For larger local validation runs, especially when the operator wants:

- explicit blocks,
- different concurrency per block,
- automatic slot refill,
- or `light` / `medium` / `heavy` regression intensity,

use the committed orchestration layer described in
[`../../skills/parallel-validation-orchestration/SKILL.md`](../../skills/parallel-validation-orchestration/SKILL.md)
instead of treating the selector output as a flat manual checklist.

Current local orchestration support includes a first-pass distinction between:

- `light` regression: direct targets only
- `medium` regression: direct targets plus a small adjacent regression surface
- `heavy` regression: direct targets plus a wider related logic surface

This expansion is currently implemented as a committed explicit mapping table
in the local orchestration runtime, not as an all-knowing semantic planner.

When the local orchestration layer is used, shard granularity is intentionally
mixed:

- non-E2E pytest surfaces (`tests/backend/**`, `tests/behavior/**`,
  `tests/security/**`, `tests/postgres/**`) should expand file inputs into
  pytest nodeids and run one collected case per task
- school Playwright E2E remains at one `.spec.js` file per task unless a future
  committed browser harness explicitly proves a safer finer-grained model

Treat this as the current repository contract for WAI-VALID planning,
monitoring, and reconnect reasoning.

### Custom Self-Organized Sample Blocks

When an agent/operator wants to run any series of concrete samples that is not
already one explicitly requested single command, build a self-organized
WAI-VALID block and run it concurrently. Do not hand-run a list of samples as a
serial terminal checklist.

Supported sample inputs:

- positional samples passed directly to `wai_valid_supervisor.py`
- repeated `--sample <path-or-nodeid>`
- repeated `--samples-file <utf8-text-or-json-file>`
- the Windows convenience launcher
  `ops\scripts\windows\start-custom-validation-block.bat`

Sample files may be UTF-8 text with one sample per line and `#` comments, or a
JSON list / object with `samples`, `paths`, or `targets`.

Default custom-block behavior:

- default concurrency is `10` when no lower value is explicitly justified
- `regression_mode=light` means only the supplied direct samples are scheduled
- fixed repository block launchers remain the default full-validation lanes,
  but arbitrary sample lists are first-class validation inputs
- Playwright samples are safe to include in WAI-VALID custom blocks because the
  supervisor assigns isolated API/UI ports and SQLite state per shard
- if a Playwright shard exceeds its per-shard timeout, the supervisor records a
  `worker-timeout` failure and continues draining the rest of the block

Example:

```powershell
@"
tests/backend/manual/test_validation_selector.py::ValidationSelectorTests::test_wai_valid_sample_file_loads_text_samples
tests/backend/manual/test_validation_selector.py::ValidationSelectorTests::test_wai_valid_custom_block_args_keep_default_concurrency_10
tests/backend/integration/test_sqlite_connection_pragmas.py::test_sqlite_connection_pragmas_enable_busy_timeout_and_foreign_keys
"@ | Set-Content -Encoding UTF8 .agent-run\plan\custom-tooling-samples.txt

ops\scripts\windows\start-custom-validation-block.bat custom-tooling-<date> self-organized-tooling .agent-run\plan\custom-tooling-samples.txt 900 10 light
```

This rule also applies to lightweight regression after a fix: compose the
directly affected samples plus the smallest adjacent safety surface into a new
custom block, run it with concurrent slot refill, then report the remaining
failure count from `block-summary.txt` / `block-report.json`.

For the repository-default full validation block set on Windows, prefer the
maintained launcher:

```powershell
ops\scripts\windows\start-full-validation-supervisor.bat full-validation-<date>
```

This launcher writes the long block list into a JSON args file, launches the
detached supervisor through the normal repository entrypoint, and opens the
visible monitor for the same run id.

The optional second positional argument is the maximum supervisor lifetime in
seconds:

```powershell
ops\scripts\windows\start-full-validation-supervisor.bat full-validation-<date> 10800
```

Current bootstrap visibility rule:

- a new WAI-VALID run should register `WAI-VALID-current-run.json` and write an
  initial `progress.json` before expensive pytest item collection finishes
- the monitor should therefore show a bootstrap phase such as `collecting`
  rather than only `waiting for a progress file...`
- on Windows, repository launchers should prefer
  `ops\scripts\windows\start-validation-monitor-detached.ps1` so the monitor is
  opened as a clearly visible independent PowerShell window instead of a
  fragile nested shell

Current lifetime/cleanup rule:

- WAI-VALID-owned python processes should carry a command-line marker such as
  `--process-tag WAI-VALID-<run-id>`
- the monitor should self-exit after startup timeout or final-state grace
- while a run is active, one foreground `python.exe` can be the visible monitor
  process; treat it as expected when `WAI-VALID-monitor.pid` points to it and
  heartbeat artifacts keep updating
- after monitor Python exits, the visible PowerShell shell may remain open to
  preserve the final report; it should use a `WAI-VALID-monitor:<run>` title and
  is not a WAI-VALID Python zombie
- the supervisor should self-stop when `--max-runtime-seconds` is exceeded
- explicit cleanup of stale tagged python processes should use:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\stop-tagged-python-processes.ps1 "WAI-VALID-<run-id>"
```

Interpretation rule for early block launches:

- if the visible monitor shows `phase=collecting` and a temporary `0/0`
  summary, do not immediately conclude that the block never started
- first check:
  - `events.log` contains `BOOTSTRAP collect-start`
  - `progress.json` keeps getting fresh timestamps
- the block should be considered fully collected only after
  `BOOTSTRAP collect-finished` is written and the progress payload reports a
  non-zero task total
- on Windows, monitor launchers should also verify lightweight
  `WAI-VALID-monitor-ready.json` and `WAI-VALID-monitor-heartbeat.json`
  artifacts under `.agent-run/validation-daemon/` so the workflow can tell the
  difference between:
  - no visible monitor process,
  - a live monitor waiting on progress,
  - and a live monitor actively rendering fresh progress
- the heartbeat payload should also carry the latest `progress.json` timestamp
  observed by the monitor so operators can distinguish:
  - stale monitor display
  - stale run progress
  - healthy monitor attached to a healthy run
- if `WAI-VALID-monitor-heartbeat.json` keeps updating but its
  `progress_updated_at` value does not move, the monitor is alive and the run
  progress is stale; inspect or clean-restart the run instead of relaunching
  only the monitor

For a block-level clean restart, use the maintained wrapper:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\restart-validation-block-round-clean.ps1 behavior behavior-round-<date> 10800 10 light
```

The wrapper stops recorded WAI-VALID process trees for that run, removes the
stale run directory and monitor heartbeat artifacts, relaunches the block
through the normal WAI-VALID block launcher, opens the visible monitor, and
waits until both fresh `progress.json` and monitor heartbeat artifacts point at
the requested run. Its startup proof must also show that:

- `WAI-VALID-current-run.json` points at the same run id;
- `WAI-VALID-monitor-ready.json` belongs to the same run id;
- `WAI-VALID-monitor-heartbeat.json` belongs to the same run id; and
- `heartbeat.progress_updated_at` matches `progress.json.updated_at`.

Use this wrapper as the default next-block launch path for interruptible full
validation rounds. Hand-built supervisor/monitor command pairs are a fallback
only when debugging the launcher itself.

When the bug being fixed is in the WAI-VALID workflow itself, prefer a
lightweight concurrent WAI-VALID verification run before any full rerun.

Repository-default post-fix rule:

- keep the same supervisor / monitor / progress-file path;
- derive the target seed set through the repository selector workflow first:
  `python ops/scripts/dev/select_validation_targets.py --worktree --json` or
  `python ops/scripts/dev/run_validation_profile.py selector-recommended --worktree --max-risk targeted --dry-run`;
- use one explicit block and a small selector-derived direct target set;
- keep concurrency above `1` when the block is safely parallelizable, so the
  fix is still exercised under concurrent slot refill;
- use `regression_mode=light`;
- only escalate to a larger block or full run after this lightweight
  concurrency-backed verification is green.

Example shape:

```powershell
python ops/scripts/dev/run_validation_profile.py selector-recommended --worktree --max-risk targeted --dry-run
ops\scripts\windows\start-validation-supervisor.bat --run-id light-bugfix-<topic>-<date> --replace-run-dir --regression-mode light --block-spec backend-sqlite-compatible:2:<selector-derived-targets> --process-tag WAI-VALID-light-bugfix-<topic>-<date> --max-runtime-seconds 900
ops\scripts\windows\start-validation-monitor.bat WAI-VALID-light-bugfix-<topic>-<date>
```

Treat this as the default proof step after fixing selector, monitor,
supervisor, launch, or workflow-contract regressions.

## Artifact And Evidence Rules

- `.agent-run/validation-history.jsonl` and `.agent-run/logs/` are ignored
  local evidence. They can help the selector identify fresh local runs for the
  same changed-path signature.
- Do not commit `.agent-run/` artifacts.
- For WAI-VALID reconnect/status checks, use the compact status wrapper first:

  ```powershell
  ops\scripts\windows\show-validation-status.bat --run-id <run-id>
  ```

  The wrapper calls `ops/scripts/dev/wai_valid_status.py` and prints bounded
  failed/running/event lists plus WAI-VALID pid-file liveness. Do not paste raw
  `summary.json` or `progress.json` into chat by default because those files can
  contain long `completed_shards` lists and truncate the useful status output.
  On Windows the status script falls back from `tasklist` to PowerShell
  `Get-Process` when `tasklist` reports access denied for a visible monitor
  shell.
- Do not update [`test-execution-runs.csv`](test-execution-runs.csv) for
  selector output, dry-run planning, or commands that were only recommended.
- Do update the CSV ledger manually when an actual target run should become
  durable project history. Review the generated `ledger-snippet.md` first and
  redact any private machine details.
- If a runner result is `blocked`, `timed out`, `interrupted`, or `skipped`, do
  not summarize it as a pass. Record or hand off the unresolved validation
  state.

Windows note: prefer `.venv\Scripts\python.exe` when the repository virtual
environment exists. If it does not, the runner falls back to the current Python
and records that fallback in local artifacts; this is acceptable for selector
smoke work but not proof that the full application dependency environment is
ready.

## Local Pytest SQLite Guardrail

Default pytest runs use a repository-local per-process SQLite file under
`.pytest_tmp/` when no PostgreSQL test URL is configured. Before deleting or
reusing a local `test*.sqlite` artifact after an interrupted run, use the
read-only guardrail:

```bash
python ops/scripts/dev/pytest_sqlite_guard.py
python ops/scripts/dev/pytest_sqlite_guard.py --json
```

For preflight scripts that should stop when another pytest process is already
running, use:

```bash
python ops/scripts/dev/pytest_sqlite_guard.py --fail-on-active-pytest
```

Interpretation:

- `status=pass` means the guardrail did not detect another pytest process
- `status=warn` means it found an active pytest-like process; stop that process
  before deleting or reusing the reported SQLite artifact(s)
- The script is diagnostic only. It does not kill processes and does not delete
  files under `.pytest_tmp/`

## Diff-Based Validation Target Selection

Use the validation selector when you need a conservative first pass for
answering: "Given this diff, which validation targets should I run first?"

The selector is intentionally advisory. It does **not** run tests, does **not**
edit the execution ledger, and does **not** prove that the recommended set is a
mathematically minimal or complete safety proof. It turns the current diff plus
a machine-readable target registry into a reviewable command list with reasons.

Run from repository root:

```bash
python ops/scripts/dev/select_validation_targets.py
python ops/scripts/dev/select_validation_targets.py --base origin/main
python ops/scripts/dev/select_validation_targets.py --base origin/main --head HEAD --json
python ops/scripts/dev/select_validation_targets.py --staged
python ops/scripts/dev/select_validation_targets.py --worktree
python ops/scripts/dev/select_validation_targets.py --paths apps/backend/courseeval_backend/api/routers/learning_notes.py
```

Windows agents should use the venv interpreter when available:

```powershell
.venv\Scripts\python.exe ops\scripts\dev\select_validation_targets.py --base origin/cursor/discussion-avatar-chat-ui-921d --head HEAD
```

Inputs:

- changed paths come from `git diff --name-status --no-renames <base>...<head>`,
  from `git diff --cached --name-status --no-renames` when `--staged` is used,
  from `git diff --name-status --no-renames` when `--worktree` is used, or
  from explicit `--paths`
- `--worktree` includes untracked, non-ignored files by default using
  `git ls-files --others --exclude-standard`; use `--no-include-untracked` if
  you need only tracked worktree modifications
- the machine-readable registry is
  [`tests/TEST_SELECTION_TARGETS.json`](../../tests/TEST_SELECTION_TARGETS.json)
- the script also parses target-level history from
  [`test-execution-targets.csv`](test-execution-targets.csv) so recommendations
  can show the last observed result, last commit, and pass/run count when a
  ledger entry exists
- unless `--no-history` is supplied, the script also reads ignored structured
  local history from `<repo>/.agent-run/validation-history.jsonl`. Structured
  history is treated as fresh evidence only when its changed-path signature
  matches the current selector input; otherwise it is reported as stale

Outputs:

- Markdown by default for agent review
- JSON with `--json` for future automation
- `non_full_validation.status`, one of `acceptable`, `needs_review`, or
  `not_sufficient`
- per-target `history_status`, one of `fresh`, `stale`, `unknown`, or
  `blocked`, or `not-recorded`
- changed paths and statuses
- recommended target IDs, categories, risk levels, working directories, command
  argv arrays, matched paths, selection reasons, coverage tags, review reasons,
  ledger history, and the latest matching structured history record when one is
  available
- unmatched paths, which mean "the first-version registry has no precise rule",
  not "no validation is needed"
- a ledger snippet template for observed results

Operational rules:

- Treat `risk=static` targets as hygiene checks, not product behavior coverage
- Treat `risk=targeted` targets as the normal first pass for bounded code
  surfaces
- Treat `risk=broad` and `risk=full` targets as escalation recommendations.
  They may be expensive or environment-dependent; review the reason before
  starting PostgreSQL or full Playwright
- If a changed path is unmatched, do not silently skip validation. Either add a
  registry rule, run a broader profile, or document why no runtime target is
  appropriate
- If the selector recommends no Playwright target for docs-only diffs, that is
  expected. If it recommends no Playwright target for school UI, E2E fixture,
  Playwright config, route, auth, or seed changes, treat that as a registry gap
- If `non_full_validation.status` is `not_sufficient`, do not present targeted
  validation as complete evidence until the blocking reason is addressed or
  explicitly deferred. Typical blockers are recommended full targets or
  unmatched product source paths
- If `non_full_validation.status` is `needs_review`, targeted validation may
  still be the right first pass, but the output names the expensive or
  environment-sensitive target that needs operator judgment
- For long-running block-based validation, prefer the WAI-VALID supervisor
  artifacts plus the generated `block-summary.txt` / `block-report.json` pair
  when reconnecting after a dropped chat session.
- `history_status=stale` does not mean a target failed. It means the previous
  ledger or structured run result should not be counted as current evidence for
  this diff
- `history_status=blocked` means the latest structured runner evidence for the
  current changed-path snapshot was blocked by environment or orchestration
  preflight. Treat it as unresolved validation, not a product pass or fail
- Record only tests that actually ran in
  [`test-execution-runs.csv`](test-execution-runs.csv). Selector output and
  `--paths` smoke runs are planning/discovery, not observed test execution

## Validation Target Runner

The runner executes a single target from
[`tests/TEST_SELECTION_TARGETS.json`](../../tests/TEST_SELECTION_TARGETS.json)
and writes local artifacts under the ignored agent workspace:

```bash
python ops/scripts/dev/run_validation_target.py static.validation_selector
python ops/scripts/dev/run_validation_target.py frontend.school.build --timeout-seconds 900
python ops/scripts/dev/run_validation_target.py backend.learning_notes.api
python ops/scripts/dev/run_validation_target.py static.validation_selector --dry-run
```

Windows agents may use the same command with the repository virtual environment
when present:

```powershell
.venv\Scripts\python.exe ops\scripts\dev\run_validation_target.py static.validation_selector
```

The runner is deliberately narrower than the selector:

- it runs one target ID at a time
- it reads the same target registry as the selector
- it resolves the repository virtualenv Python when present, otherwise it uses
  the current interpreter and records that fallback in local artifacts
- it normalizes portable registry command names before execution: `python`
  resolves to the repository virtualenv when available, `npm`/`npm.cmd` and
  `npx`/`npx.cmd` resolve to the platform-appropriate executable
- it writes `<repo>/.agent-run/logs/<timestamp>-<target-id>/run.json`
- it writes `<repo>/.agent-run/logs/<timestamp>-<target-id>/ledger-snippet.md`
- it appends a compact structured record to
  `<repo>/.agent-run/validation-history.jsonl` unless `--no-history` is passed
- it captures per-command stdout/stderr logs under the same artifact directory
- for `python -m pytest` targets that do not already specify `--junitxml`, it
  adds an ignored JUnit XML artifact and records testcase-level totals and case
  statuses in `run.json` and structured history
- for real execution, it classifies missing interpreters, missing pytest,
  missing npm/npx/browser command, or unresolved command placeholders as
  `blocked` rather than product failures
- `--dry-run` is planning-only and does not check whether runtime tools are
  installed; add `--preflight` to a dry-run when the goal is to prove command
  and environment readiness without running the product test command
- it does not provision PostgreSQL, install dependencies, install browsers, or
  mutate the committed execution ledger

Exit codes:

- `0`: target commands passed, or `--dry-run` recorded the target without
  execution
- `1`: target command ran and failed
- `2`: environment or command preflight blocked execution
- `4`: command timed out
- `5`: command was interrupted
- `6`: invalid target, invalid registry, or invalid arguments

Treat runner artifacts as local evidence. If a run should become durable
project history, review the generated `ledger-snippet.md`, redact any private
details if needed, and then update
[`test-execution-runs.csv`](test-execution-runs.csv) and
[`test-execution-targets.csv`](test-execution-targets.csv) manually with the
observed result.

Structured history is a machine-readable local companion to the committed CSV
ledger, not a replacement for it. It records target id, result, failure class,
artifact pointers, changed paths, a changed-path signature, and parsed test
artifact summaries when available so the selector can tell whether a local run
actually covered the current diff. Keep it under ignored `.agent-run/`; do not
commit local history files.

## Validation Profile Runner

The profile runner orchestrates one or more target runner invocations and
writes a profile-level summary under ignored `.agent-run/logs/`:

```bash
python ops/scripts/dev/run_validation_profile.py static
python ops/scripts/dev/run_validation_profile.py selector-recommended --paths apps/web/school/src/views/HomeworkSubmissions.vue --dry-run
python ops/scripts/dev/run_validation_profile.py selector-recommended --worktree --max-risk targeted
python ops/scripts/dev/run_validation_profile.py selector-recommended --include-review-targets --max-risk broad
```

Initial profiles:

- `static`: runs the static selector validation target
- `selector-recommended`: runs selector recommendations for explicit `--paths`
  or the current worktree

Profile safety defaults:

- `--max-risk targeted` is the default; `broad` and `full` recommendations are
  skipped unless explicitly allowed
- targets with `requires_review_reason` are skipped unless
  `--include-review-targets` is passed
- `--dry-run` is useful for proving orchestration and artifact writing without
  executing the underlying commands
- `--dry-run --preflight` keeps the product commands unexecuted but still checks
  command placeholders, Python module availability, and platform executables
- if selector output says `non_full_validation.status=not_sufficient`, the
  profile exits with code `4` even if the runnable subset passed or was skipped

Profile exit codes:

- `0`: no product or environment failure was observed, including dry-run or
  policy-skipped targets
- `1`: at least one executed target failed or timed out
- `2`: at least one executed target was blocked by environment or command
  preflight
- `4`: selector policy says non-full validation is not sufficient
- `6`: profile setup, selector execution, or JSON parsing failed

Known first-version limitations:

- the registry is conservative and incomplete. It covers the high-value targets
  currently represented in the ledger plus maintained Playwright suites,
  important behavior/security pytest targets, and several broad escalation
  rules
- the selector works at target level, not individual `pytest` test item or
  Playwright `test(...)` case level. The runner can now record pytest JUnit XML
  case summaries, but the selector still uses target-level history for
  sufficiency decisions
- CSV ledger parsing is intentionally shallow: it extracts `last_result`,
  `last_commit`, `pass_count`, and `run_count` from
  [`test-execution-targets.csv`](test-execution-targets.csv). The
  machine-readable registry remains the source for selection rules
- Python `fnmatch` treats `**` as a glob pattern, not as a full
  gitignore-style recursive operator with every edge case. When writing
  registry rules, include both one-level and recursive patterns if both are
  required, for example `apps/backend/courseeval_backend/*.py` and
  `apps/backend/courseeval_backend/**/*.py`
- this tool is not a replacement for reading task-scoped docs. It makes the
  first recommendation easier to audit; it does not understand every semantic
  dependency in the application
- the runner is a first operational layer, not a full validation orchestrator.
  PostgreSQL lifecycle management, Playwright port isolation, browser install
  detection beyond executable preflight, and machine-readable
  pytest/Playwright item-level result parsing remain follow-up work

## Related Files

- [`DEVELOPMENT_AND_TESTING.md`](DEVELOPMENT_AND_TESTING.md)
- [`CI_AND_VALIDATION.md`](CI_AND_VALIDATION.md)
- [`TEST_EXECUTION_PITFALLS.md`](TEST_EXECUTION_PITFALLS.md)
- [`../../skills/validation-selection/SKILL.md`](../../skills/validation-selection/SKILL.md)
- [`../../skills/validation-ledger-maintenance/SKILL.md`](../../skills/validation-ledger-maintenance/SKILL.md)
- [`../../ops/scripts/dev/select_validation_targets.py`](../../ops/scripts/dev/select_validation_targets.py)
- [`../../ops/scripts/dev/run_validation_target.py`](../../ops/scripts/dev/run_validation_target.py)
- [`../../ops/scripts/dev/run_validation_profile.py`](../../ops/scripts/dev/run_validation_profile.py)
