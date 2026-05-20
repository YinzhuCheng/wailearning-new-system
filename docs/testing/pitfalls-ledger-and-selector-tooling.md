# Ledger And Selector Tooling Pitfalls

## Purpose

Use this route when the failure shape suggests:

- validation selector or runner confusion;
- CSV ledger append or encoding issues;
- borrowed or mismatched `ledger_id` values;
- update-log sequence or BOM problems;
- private-path scanner false positives;
- evidence recording that reports only green runs and loses blocked context.

This file is a **route, summary, and canonical home** for the ledger and
selector-tooling pitfall clusters that have already been migrated here.
Historical entries that have not been moved yet still remain in
[TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md).

## Start Here

1. Run:

   ```powershell
   python ops\scripts\dev\search_pitfalls.py "<selector or ledger symptom>"
   ```

2. Open:
   - [VALIDATION_WORKFLOW_AND_TOOLS.md](VALIDATION_WORKFLOW_AND_TOOLS.md)
   - [README.md](README.md)
   - [../governance/agent-update-log.md](../governance/agent-update-log.md)
3. If the issue is about target choice or durable evidence, route through:
   - [../../skills/validation-selection/SKILL.md](../../skills/validation-selection/SKILL.md)
   - [../../skills/validation-ledger-maintenance/SKILL.md](../../skills/validation-ledger-maintenance/SKILL.md)

## Primary Pitfall Clusters

| Cluster | Start with |
|---------|------------|
| selector/runner registry drift | Pitfalls 3144, 3180, validation-selector sections |
| update-log / CSV BOM / append tooling | Pitfalls 87 and 89 |
| grep / Playwright target over-selection | Pitfall 88 |
| private-path scan and self-match issues | private-path scanner pitfall |
| green-only history or line-count misclassification | execution-ledger and repo-line-health pitfalls |

## Key Pitfalls

- **Pitfall 87**: update-log append tooling must read BOM-prefixed CSV headers
  safely.
- **Pitfall 88**: Playwright `--grep` can accidentally match describe text and
  run the whole spec.
- **Pitfall 89**: CSV ledger rewrites must not add a UTF-8 BOM to the header.
- **Pitfall 3144** in the encyclopedia: validation targets must not borrow
  unrelated ledger IDs.
- **Pitfall 3180** in the encyclopedia: school Playwright validation targets
  must use the external runner.

## Recommended Commands

```powershell
python ops\scripts\dev\lint_validation_registry.py
python ops\scripts\dev\select_validation_targets.py --worktree --json
python -m unittest tests.backend.manual.test_validation_selector -v
```

Use these before changing selector registry, update-log append rules, or ledger
metadata contracts.

## Related Files

- [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)
- [README.md](README.md)
- [../governance/agent-update-log.md](../governance/agent-update-log.md)
- [../../skills/validation-selection/SKILL.md](../../skills/validation-selection/SKILL.md)
- [../../skills/validation-ledger-maintenance/SKILL.md](../../skills/validation-ledger-maintenance/SKILL.md)

## Detailed migrated entries

### Pitfall: validation targets must not borrow unrelated ledger IDs

The validation selector reads `ledger_id` from
`tests/TEST_SELECTION_TARGETS.json` and joins it to
`docs/testing/test-execution-targets.csv`. During the
repository-normalization hardening pass, several behavior pytest targets were
found pointing at unrelated existing ledger rows, for example a notification
API target using a Playwright discussion target's ledger id.

Why this is dangerous:

- selector output can show stale or unrelated pass history as if it covered the
  current target;
- a target without its own committed row can appear more trustworthy than it
  is;
- future agents may skip the correct validation because another target's
  ledger row happened to be green.

Current rule:

- `ledger_id` must be `null` or exactly equal to the target's own `id`;
- if a target has durable run history, add a matching row to
  `test-execution-targets.csv` and set `ledger_id` to the same id;
- do not use another target's ledger row as an informal alias.

Verification pattern:

```powershell
.venv\Scripts\python.exe -m json.tool tests\TEST_SELECTION_TARGETS.json
.venv\Scripts\python.exe ops\scripts\dev\lint_validation_registry.py
.venv\Scripts\python.exe -m unittest tests.backend.manual.test_validation_selector -v
```

If an alias mechanism is ever needed, design it explicitly in the registry,
selector, lint script, and tests before using it in target metadata.

### Pitfall: school Playwright validation targets must use the external runner

The school Playwright registry used to mix direct `npx playwright test ...`
commands with the repository-owned external runner. Direct commands can bypass
the environment contract that the current Windows and agent workflows rely on:
the runner starts FastAPI and Vite on the expected loopback ports, sets E2E
seed environment variables, waits for readiness, invokes Playwright with
external server mode, and cleans up only the processes it started.

Current metadata rule:

- every `category: "school-playwright"` target in
  `tests/TEST_SELECTION_TARGETS.json` must start with:

```json
["node", "scripts/playwright-external-runner.cjs"]
```

- direct `npx playwright test ...` is still useful for manual local debugging,
  but it should not be the committed selector command for school Playwright
  targets unless the external-runner contract is intentionally changed.

Verification pattern:

```powershell
.venv\Scripts\python.exe ops\scripts\dev\lint_validation_registry.py
.venv\Scripts\python.exe -m unittest tests.backend.manual.test_validation_selector -v
```

The selector tests include a repository-wide check that all current
`school-playwright` targets use `node scripts/playwright-external-runner.cjs`.

### Pitfall: Playwright external-runner API readiness can time out before slow FastAPI startup finishes

The repository school Playwright external runner waits for `/api/health` with a
fixed readiness window. In one May 2026 hardening run,
`node scripts/playwright-external-runner.cjs e2e-security-hardening-followup.spec.js --project=chromium`
failed with:

```text
api did not become ready at http://127.0.0.1:<local-port>/api/health within 120000ms
```

The FastAPI log printed `Application startup complete` immediately after the
runner had already given up. A repeat run on the same changed code reached the
tests and later passed after a test-side matcher correction, so the first
failure was an environment/startup timing hazard, not evidence of a product
regression.

Mitigation:

- Treat this specific failure shape as an observed run and record it, but check
  for residual `uvicorn`/`node` processes before rerunning.
- Prefer a second external-runner attempt on the same isolated ports when the
  only failure is readiness timeout and the API completes startup right after
  the timeout.
- If this recurs frequently, extend the runner's API readiness timeout or add a
  startup-progress diagnostic before the timeout fires; do not silently
  classify the target as product-failed without a request reaching the app.

### Pitfall: Playwright array containment does not apply asymmetric string matchers to array elements

In Playwright/Jest-style `expect`, `toContain(expect.stringContaining("..."))`
checks whether the array contains that matcher object; it does not apply the
matcher to each string element. During the parent-portal hardening E2E, the
array contained a seeded title with `E2E_UI`, but the assertion failed:

```javascript
expect(titles).toContain(expect.stringContaining('E2E_UI'))
```

Use one of these patterns instead:

```javascript
expect(titles.some(title => title.includes('E2E_UI'))).toBe(true)
expect(titles).toContainEqual(expect.stringContaining('E2E_UI'))
```

This is a test-authoring pitfall. If the response payload visibly contains the
expected substring, fix the matcher before changing product code.

### Pitfall: private-path scanners can flag their own detection regexes

Repository-local privacy scanners often contain literal examples or regular
expressions for forbidden path shapes such as `C:/Users/...` or
`C:\Users\...`. If the scanner simply scans all changed text files, including
its own source, those rule definitions can appear as false positives.

Mitigation:

- Keep scanner self-tests or allowlist snippets for the rule definitions
  themselves.
- Allow explicitly redacted placeholders such as `<repo>/.agent-run/logs/...`
  in tests and docs, but continue to flag real `.agent-run/logs/<run-id>`
  artifact paths.
- Still scan untracked files by default; otherwise new scripts and new skill
  files are invisible until after they are staged.
- Treat scanner self-hits as tooling false positives only when the matched line
  is clearly a detection pattern or placeholder, not a real local path.

### Pitfall 87: agent update append script must read BOM-prefixed CSV headers

`docs/testing/agent-update-log.csv` may start with a UTF-8 BOM.
If a helper opens it with plain `encoding="utf-8"`, `csv.DictReader` sees the
first header as `\ufeffupdate_sequence` instead of `update_sequence`. A
sequence calculation that looks up `row["update_sequence"]` then sees no values
and can append a duplicate `update_sequence=1` even when the ledger already
contains higher rows.

Mitigation:

- Use `encoding="utf-8-sig"` for CSV helpers that read repository ledger
  headers.
- Inspect the tail of `agent-update-log.csv` after using append helpers; the
  sequence must increase monotonically by one.
- Treat a duplicate low sequence as a transcription/tooling error and correct
  the newly appended row before commit.

### Pitfall 88: Playwright grep can accidentally match describe text and run the whole spec

The admin external runner passes `--grep` through to Playwright, where the
regular expression is evaluated against the full test title, including
`describe(...)` text. During the notification update-clearing hardening round,
this command intended to run only cases 23 and 24:

```powershell
node apps\web\school\scripts\playwright-external-runner.cjs e2e-notification-sync-deep-tier.spec.js --project=chromium --grep "23|24"
```

The suite title contained `24 cases`, so every test title matched through the
describe text and the runner executed all 24 cases. The long unintended run
then hit unrelated browser/SQLite pressure: several course-card lookups failed
after backend `QueuePool` exhaustion, obscuring the actual two new cases.

Mitigation:

- Grep on a distinctive case-title phrase, not just a bare number or a common
  word from the `describe(...)` title. For example:

```powershell
node apps\web\school\scripts\playwright-external-runner.cjs e2e-notification-sync-deep-tier.spec.js --project=chromium --grep "23 explicit null|24 switching"
```

- After a targeted Playwright run starts, check the `Running N tests` line
  before interpreting failures. If `N` is much larger than intended, stop and
  rerun with a narrower grep before changing product code.
- Do not over-anchor with `^23` unless you have verified Playwright's full
  title starts with the case number; a too-strict anchor can produce
  `No tests found`.

### Pitfall 89: CSV ledger rewrites must not add a UTF-8 BOM to the header

PowerShell `Set-Content -Encoding utf8` can rewrite repository CSV ledgers with
a UTF-8 BOM. For ledgers such as
`docs/testing/test-execution-targets.csv`, registry tooling reads
the first header literally, so `test_id` becomes `\ufefftest_id`. The registry
lint then reports every configured `ledger_id` as missing, and selector history
can degrade from `stale` to `not-recorded`.

Mitigation:

- Prefer repository append/update helpers or CSV libraries that preserve the
  existing encoding.
- If a full-file rewrite is unavoidable, write UTF-8 without BOM, for example
  with `.NET` `System.Text.UTF8Encoding($false)` from PowerShell.
- After touching CSV ledgers, run `lint_validation_registry.py` and the
  validation selector unit tests before assuming widespread missing-ledger
  failures are real product or registry issues.
- Inspect the first bytes when all ledger ids appear missing. `239 187 191`
  (`EF BB BF`) at the start of a CSV ledger indicates a BOM.

### Pitfall 90: detached validation runners can leave a stale progress file that looks alive

During the May 2026 parallel-validation experiments, several ad hoc detached
orchestrators launched test workers successfully but then stopped updating the
shared `progress.json`. The visible monitor continued to show the last known
state, making it look as if eight shards were still running even though the
real child processes had already exited or been replaced.

Observed pattern:

1. a detached launcher writes `progress.json` once when the first workers start;
2. the launcher or its worker-tracking loop hangs, exits, or loses access to
   its child state;
3. shard logs continue to exist and some even complete successfully;
4. the monitor is truthful to the file it was given, but the file itself is
   stale and no longer represents reality.

Mitigation:

- Treat the progress file as a protocol, not an assumption.
- The active run must be registered through a durable current-run pointer such
  as `.agent-run/validation-daemon/WAI-VALID-current-run.json`.
- The supervisor must rewrite `progress.json` on every state change, not only
  at batch start.
- If `updated_at` stops moving while CPU and child-process counts also fall,
  suspect a frozen supervisor rather than a slow test.
- Cross-check with shard log `LastWriteTime`, `results.jsonl`, and live process
  tables before concluding the tests themselves are hung.

### Pitfall 91: PowerShell-generated worker scripts can corrupt PostgreSQL DSNs through variable interpolation

The local PostgreSQL worker templates initially embedded:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg2://$dbUser:$dbPass@127.0.0.1:$port/$dbName"
```

Inside a generated PowerShell script this can fail because `:` directly after a
variable name is parsed as part of the variable reference. The resulting worker
dies before pytest starts, and the outer scheduler may incorrectly attribute
the failure to the shard rather than to worker bootstrap.

Observed symptom:

- the PostgreSQL shard directory contains only the generated worker script plus
  empty wrapper logs;
- `pytest.log` never appears;
- stderr shows:
  `Variable reference is not valid. ':' was not followed by a valid variable name character.`

Mitigation:

- In generated PowerShell scripts, use `${dbUser}`, `${dbPass}`, `${port}`, and
  `${dbName}` inside DSN strings.
- Prefer validating the generated script once before launching many PostgreSQL
  workers.
- When a PostgreSQL shard fails too quickly to produce `pytest.log`, inspect
  the worker wrapper stderr before debugging product code.

### Pitfall 92: reusing the same validation run directory can append old events and hide the real run boundary

During the May 2026 parallel-validation experiments, some ad hoc reruns reused
an existing run directory and appended new `START ...` lines to the existing
`events.log`. That produced misleading duplicates for the first wave of shards
and made it harder to tell whether the scheduler had actually refilled slots or
had simply replayed old evidence in place.

Observed symptom:

- the same shard appears to "start" twice in one event log even though only one
  final result record exists for the later attempt;
- the visible monitor looks frozen or contradictory because the old run history
  and the new partial rerun live in the same directory.

Mitigation:

- treat the run directory as part of the execution identity, not just a cache;
- use a fresh `WAI-VALID-*` run id for fresh work;
- only reuse a run directory when resume semantics are explicit and the
  supervisor knows how to reconstruct queue/running/completed state from it;
- otherwise fail fast when the target run directory already exists.

### Pitfall 93: local WAI-VALID result ledgers can mark fully passing shards as failed when worker exit codes are missing

During the May 2026 behavior-block rerun experiments, a local fallback runner
recorded:

```text
passed=0/17 failed=17
```

even though every per-shard pytest log ended with `N passed` and every
corresponding `*.err` file was empty.

Observed artifact shape:

- `results.jsonl` stored `exit_code: null` for completed `Start-Process`
  workers;
- the runner treated `null` as failure by default;
- `summary.json` and `progress.json` therefore reported all shards failed;
- direct inspection of `tests_behavior_*.log` showed normal pytest success
  summaries such as `16 passed`, `42 passed`, or `2 passed, 1 skipped`.

Interpretation:

- this is an orchestration/accounting bug, not evidence that the behavior block
  genuinely failed;
- a green block can look fully red if the runner trusts only the PowerShell
  process object and does not have a fallback interpretation path.

Mitigation:

- when `ExitCode` is unavailable from a completed worker process, inspect the
  captured stdout/stderr and classify success from the pytest trailer only if:
  - a `passed` summary is present;
  - no `failed` summary is present;
  - no `ERROR`, `Traceback`, `AssertionError`, or `FAILURES` section is present.
- prefer structured supervisor results over ad hoc per-window local runners for
  durable validation claims.
- when a block summary looks suspiciously all-red or all-green, sample several
  shard logs before deciding whether the product or the runner is at fault.

### Pitfall 94: Windows WAI-VALID launchers can silently drop very long block arguments before the detached supervisor starts

During the May 2026 Playwright block restart work, the visible launch command
returned without error and the monitor window could still open, but no new
`WAI-VALID-*` run directory, `progress.json`, or `events.log` appeared for the
requested Playwright block.

Observed artifact shape:

- `wai_valid_windows_launcher.py` recorded the intended long `--block-spec`
  argument in `WAI-VALID-launcher.log`;
- `WAI-VALID-supervisor-launch.log` showed no matching `START/ARGS/PID` entry
  for that run id;
- `WAI-VALID-current-run.json` still pointed at the older successful run;
- re-running a short proof launch through the same path succeeded immediately.

Interpretation:

- the failure is in the Windows launch chain before the detached supervisor
  begins, not in `wai_valid_supervisor.py`, the monitor, or the Playwright
  worker itself;
- long block argument payloads, especially full Playwright spec lists, should
  not be trusted to survive direct pass-through as one giant command line.

Mitigation:

- for detached Windows launches, write a short wrapper script that contains the
  real argument array and launch PowerShell against that wrapper instead of
  passing the full shard list inline;
- after any long-argument launch, confirm all three signals before trusting the
  monitor:
  - a new `WAI-VALID-supervisor-launch.log` `START/ARGS/PID` entry,
  - a new run directory under `.agent-run/logs/`,
  - `WAI-VALID-current-run.json` updated to the new run id.

### Pitfall 95: a monitor started with `--run-id` can falsely show an older run if the target progress file has not been created yet

During the May 2026 block-by-block validation restart, a visible monitor window
was launched for the next block with an explicit run id, but the window still
rendered the last successful backend run instead of waiting for the new block.

Observed artifact shape:

- the operator launched `start-validation-monitor.bat <new-run-id>`;
- the requested run did not yet have `.agent-run/logs/<run-id>/progress.json`;
- `wai_valid_monitor.py --run-id <new-run-id>` fell back into the normal
  auto-discovery path instead of waiting for the requested run;
- the visible window therefore rendered the old run pinned in
  `WAI-VALID-current-run.json`, which looked like a stale monitor bug even
  though the new run had simply not written its first progress file yet.

Interpretation:

- explicit monitor pinning is only trustworthy if the monitor treats the run id
  as a hard requirement;
- when the forced run is not ready yet, the correct operator signal is
  "waiting for that run", not a silent fallback to unrelated historical
  progress.

Mitigation:

- when `wai_valid_monitor.py` is started with `--run-id`, return `None` and the
  requested run id until that exact `progress.json` exists;
- only resume auto-discovery when the monitor was started without a forced run
  id;
- after launching a new block, treat a monitor that immediately shows an older
  completed run as a launch/pinning bug and inspect both:
  - whether the new run wrote `progress.json`,
  - whether the monitor was allowed to fall back from the requested run id.

### Pitfall 96: full WAI-VALID launches can spend a long time in pytest collection before any progress file exists

During the May 2026 full validation launch attempts, the detached supervisor
process could be alive and still not write a run-local `progress.json` for a
long time because it first expanded large backend/behavior/security file lists
into pytest nodeids via repeated `pytest --collect-only` calls.

Observed symptom:

- the operator starts a fresh full validation run;
- the monitor window shows only:

```text
[WAI-VALID] waiting for a progress file...
```

- the new supervisor PID exists, but `WAI-VALID-current-run.json` still points
  at the previous run or the requested run directory has not yet appeared;
- this looks like a broken launch even though the process is still busy doing
  expensive collection work.

Mitigation:

- write `WAI-VALID-current-run.json`, an initial `progress.json`, and
  `WAI-VALID-state.json` immediately after argument parsing and run-directory
  creation, before pytest item collection begins;
- expose a bootstrap phase such as `collecting` or `prepared` in the progress
  payload so the monitor can render real status during pre-queue work;
- for repository-default full runs on Windows, prefer
  `ops/scripts/windows/start-full-validation-supervisor.bat`, which also
  avoids fragile inline mega-command block lists by using a JSON args file.

### Pitfall 97: long-lived WAI-VALID python processes can survive indefinitely without explicit lifetime rules

During repeated local validation iterations, detached supervisors, monitors, or
worker wrappers could stay alive after the operator had already abandoned the
run, especially when startup or progress visibility was inconsistent. That left
stale tagged python processes competing for ports, SQLite files, or attention.

Mitigation:

- give every WAI-VALID-owned long-lived python process a shared marker such as
  `--process-tag WAI-VALID-<run-id>`;
- make the supervisor self-stop when `--max-runtime-seconds` is exceeded;
- make the monitor self-stop when the requested run never produces progress
  within the startup timeout, and after a short final-state grace period;
- use the explicit cleanup command when stale tagged python processes still
  need operator-forced removal:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\stop-tagged-python-processes.ps1 "WAI-VALID-<run-id>"
```
