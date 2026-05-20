# Windows And Encoding Pitfalls

## Purpose

Use this route when the failure shape suggests:

- Windows PowerShell execution-policy issues;
- mojibake or UTF-8 display corruption;
- wrong local Python / npm entrypoint;
- process-spawn or shell-environment behavior that fails before product code.

This file is a **route, summary, and canonical home** for the Windows and
encoding pitfall clusters that have already been migrated here. Historical
entries that have not been moved yet still remain in
[TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md).

## Start Here

1. Run:

   ```powershell
   python ops\scripts\dev\search_pitfalls.py "<exact error or symptom>"
   ```

2. If the issue is text or shell rendering, also open:
   [../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md](../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md)
3. If the issue is local test execution rather than product behavior, route
   through:
   [../../skills/local-test-triage/SKILL.md](../../skills/local-test-triage/SKILL.md)

## Primary Pitfall Clusters

| Cluster | Start with |
|---------|------------|
| PowerShell mojibake / UTF-8 display | Pitfall 1, plus the UTF-8 helper extension |
| `npm.ps1` execution policy | Pitfall 2 |
| sandbox or shell spawn `EPERM` | Pitfall 3, Pitfall F, targeted Playwright spawn notes |
| stale local process and port confusion | Pitfalls 4-8 |
| Windows `python` resolves outside `.venv` | Pitfall 81 |
| local machine path / private-path handling | pitfall sections that mention `.agent-run/` or `.e2e-run/` placeholders |

## Key Pitfalls

- **Pitfall 1**: PowerShell output can display mojibake even when tracked file
  bytes are correct.
- **Pitfall 2**: `npm` PowerShell shim may be blocked by execution policy;
  prefer `npm.cmd` or `npx.cmd`.
- **Pitfall 3**: sandboxed Node child-process spawning can fail with `EPERM`
  before application code runs.
- **Pitfalls 4-8**: webServer auto-start, wrong readiness signals, stale
  listeners, pytest temp-path behavior, and detached-process lifetime.
- **Pitfall 10**: some `git` index update paths may need elevated execution in
  this environment.
- **Pitfall 81**: `python` may be the system interpreter even when the repo
  `.venv` exists.
- **Pitfall 87 / 89**: BOM-prefixed CSV headers and PowerShell UTF-8 rewrites
  can break ledger tooling.

## Recommended Commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1
python ops\scripts\dev\safe_show_text.py <path> --escape
python ops\scripts\dev\check_text_encoding.py <path>
python ops\scripts\dev\pytest_sqlite_guard.py --json
```

Use `set-utf8-session.ps1` directly only when you intentionally need to mutate
an already-trusted interactive shell instead of using the default child-process
wrapper.

## Related Files

- [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)
- [../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md](../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md)
- [../../skills/local-test-triage/SKILL.md](../../skills/local-test-triage/SKILL.md)

## Detailed migrated entries

### Scope of the recorded Windows session

- Host shell: Windows PowerShell
- Repository root: `<repo>`
- Python runtime: repository `.venv`
- Frontend package runner: `npm.cmd` / `npx.cmd`
- Browser cache path: `<local-browser-cache>`
- Tested after repository structure migration into:
  - `apps/backend/courseeval_backend/`
  - `apps/web/school/`
  - `apps/web/parent/`
  - `ops/`
  - `tests/e2e/web-school/`

### Pitfall 1: PowerShell output can display mojibake

#### Symptom

Chinese output shown in the terminal may render as mojibake even when the
underlying file content is correct.

#### Why it matters

- Terminal copy-paste is not trustworthy for Chinese strings.
- Batch files, YAML comments, and legacy script files are especially easy to
  corrupt if edited by copying text from PowerShell output.

#### Safe handling strategy

- Do not copy Chinese text from terminal output back into repository files.
- Prefer patch-based file edits over terminal-mediated rewrite flows.
- When touching files that may already contain Chinese text, treat the file
  content on disk as authoritative, not the shell rendering.
- If a file appears garbled in the shell, inspect it through a safer path
  before editing.

#### Extension: repository UTF-8 helpers for PowerShell sessions and text I/O

The branch now includes explicit helper scripts so agents do not have to
rediscover the same PowerShell encoding setup every time.

For the default repository-safe workflow, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1
```

For an already-open interactive shell that must keep the encoding changes in
place, dot-source instead:

```powershell
. .\ops\scripts\windows\set-utf8-session.ps1
```

What the script changes:

- console code page `65001`
- `[Console]::OutputEncoding`
- `[Console]::InputEncoding`
- `$OutputEncoding`
- `PYTHONUTF8`
- `PYTHONIOENCODING`
- `LESSCHARSET`

This reduces display and child-process decoding friction, but it does not turn
PowerShell output into the source of truth. If a multilingual string matters,
inspect it through:

```powershell
python ops\scripts\dev\safe_show_text.py <path> --start-line <n> --end-line <m>
python ops\scripts\dev\safe_show_text.py <path> --escape --start-line <n> --end-line <m>
```

For generated or trusted full-file writes, use:

```powershell
python ops\scripts\dev\safe_write_text.py <path> --stdin --replace
```

For tracked-file audits, use:

```powershell
python ops\scripts\dev\check_text_encoding.py
python ops\scripts\dev\check_text_encoding.py <path>
```

Interpretation:

- `set-utf8-session.ps1` is an environment mitigation, not a content repair.
- `safe_show_text.py --escape` is the preferred CLI view when terminal glyphs
  are suspect.
- `safe_write_text.py` is for deliberate full-file writes from trusted input;
  it must not be used to pipe already-garbled terminal text into source files.
- `check_text_encoding.py` scans `git ls-files` by default and intentionally
  ignores `.e2e-run/` private notes. Use placeholders such as `<repo>` in
  committed docs and keep real machine paths in `.e2e-run/`.

### Pitfall 2: `npm` PowerShell shim may be blocked by execution policy

#### Symptom

Running `npm run ...` directly from PowerShell can fail with
script-execution-policy errors because `npm.ps1` is blocked.

#### What worked

Use `npm.cmd` or `npx.cmd` explicitly.

Example:

```powershell
& 'C:\Program Files\nodejs\npm.cmd' run test:e2e
& 'C:\Program Files\nodejs\npx.cmd' playwright test --list
```

#### Recommendation

Any automation intended for Windows PowerShell should prefer `.cmd` entrypoints
when invoking Node package tools.

### Pitfall 3: sandboxed Node child-process spawning can fail with `EPERM`

#### Symptom

Playwright and Vite failed inside the default sandbox with errors such as:

- `spawn EPERM`
- Vite/esbuild startup failure
- Playwright worker fork failure

#### Where it happened

- Playwright internal worker processes
- Playwright `webServer` startup mode
- Vite config loading via esbuild

#### Operational conclusion

This was an execution-environment limitation, not a repository-code regression.

#### What worked

The browser suite had to be run outside the default sandbox on isolated ports,
with the backend and frontend started explicitly first.

#### Recommendation

If Playwright fails immediately with process-spawn `EPERM`, treat it as an
environment problem first, not as an application problem.

### Pitfall 4: Playwright `webServer` auto-start was too fragile for this environment

#### Symptom

Even after the repository structure was fixed, Playwright startup remained
unreliable when it was allowed to manage backend/frontend servers itself.

#### Root causes observed

- sandbox restrictions on subprocess creation
- stale ports responding from older processes
- frontend dev server returning misleading non-application responses

#### What worked

Introduce a mode where Playwright does not start `webServer` itself and instead
reuses pre-started external servers.

Operationally this required:

- isolated API/UI ports
- explicit health checks
- explicit `E2E_API_URL`
- explicit `PLAYWRIGHT_BASE_URL`
- explicit `PLAYWRIGHT_USE_EXTERNAL_SERVERS=1`

#### Recommendation

For long or important Windows E2E runs, prefer:

1. start backend explicitly
2. start Vite explicitly
3. verify API `200`
4. verify UI root returns a real `200`, not just "a port is open"
5. run Playwright against those servers

### Pitfall 5: a `404` from the UI port is not a valid readiness signal

#### Symptom

At one point the UI port returned `404`, which looked like "the server is
reachable", but the actual SPA was not serving correctly for the intended test
session.

#### Why this is dangerous

- A stale process or wrong server can occupy the target port.
- The browser tests may then time out on missing controls rather than failing
  at startup.
- This can waste significant debugging time because the failure presents as
  missing DOM state instead of incorrect environment boot.

#### Recommendation

Treat a UI dev server as healthy only if the root page returns `200` and
renders the expected app shell.

Do not accept "some HTTP response exists" as sufficient readiness.

### Pitfall 6: old listening processes can silently poison later test runs

#### Symptom

Ports previously used by older frontend or backend processes may remain
occupied, causing later runs to hit stale services instead of the newly started
test stack.

#### Consequences

- false-positive readiness checks
- wrong database backing the test run
- UI selectors timing out because the browser is looking at an old page

#### What worked

- use isolated ports for each serious rerun
- explicitly verify both API and UI against the intended process
- avoid reusing 3012/8012 blindly if earlier test attempts may have left
  residue

### Pitfall 7: pytest temporary-directory behavior on Windows can fail before business assertions run

#### Symptom

Backend tests initially failed in pytest temp-directory setup/cleanup with
`PermissionError` and directory-numbering failures unrelated to application
logic.

Observed failure shapes included:

- cleanup of basetemp failing
- temp root under `%TEMP%` inaccessible
- numbered temp dir creation failing on Windows
- pytest helper symlink behavior not behaving well in this environment

#### Important distinction

These were test-runner infrastructure failures, not backend logic failures.

#### What was needed

Repository-level pytest bootstrapping had to force a safer Windows temp-root
strategy and soften problematic Windows temp-dir behavior for this environment.

#### Recommendation

When backend tests fail before test bodies run, inspect pytest temp-path
behavior first before blaming the product code.

### Pitfall 8: background process survival differs between direct execution and detached PowerShell sessions

#### Symptom

A backend command that stayed alive when run interactively did not necessarily
stay alive when launched as a hidden detached process from a separate
automation step.

#### Consequence

Health checks could fail even though the exact same command was valid.

#### What worked

Using a single controlling script that:

- starts the backend
- starts the frontend
- waits for health
- runs the browser tests
- then tears everything down

was much more reliable than trying to launch background services in one step
and test them in later independent shell calls.

### Pitfall 9: migrated test files may lose implicit Node module resolution

#### Symptom

After moving E2E specs from `frontend/e2e/` to `tests/e2e/web-school/`, Node
module resolution for `@playwright/test` no longer worked automatically for the
moved files.

#### Why it happened

The specs were no longer physically under the frontend package tree, so
relative module lookup assumptions changed.

#### What worked

The Playwright config had to set up module resolution explicitly from the
school frontend package context.

#### Recommendation

Whenever tests are moved outside the owning package root, re-check module
resolution immediately with `playwright test --list` before attempting the full
suite.

### Pitfall 10: `git` index updates may need elevated execution in this environment

#### Symptom

Some `git` operations failed with inability to create `.git/index.lock`.

#### Practical effect

Normal local staging may fail even though file changes are correct on disk.

#### Recommendation

If `git add` or related index-writing commands fail with index-lock permission
errors in this environment, treat that as an execution-permission problem
rather than a repository-integrity problem.

### Pitfall 11: visible validation windows can flash and disappear when the launcher kills or depends on its own console host

During the May 2026 WAI-VALID monitor/supervisor hardening pass on Windows,
visible startup wrappers repeatedly showed this failure shape:

- a PowerShell or batch window flashes open;
- the window closes immediately;
- the intended background validation or monitor process never survives long
  enough to write fresh progress.

Observed causes included:

1. the monitor batch file set its own console title to `WAI-VALID-monitor`
   before calling `taskkill /FI "WINDOWTITLE eq WAI-VALID-monitor"`, so the
   launcher could kill the just-opened window instead of only stale prior
   monitors;
2. startup chains that rely on the visible PowerShell window as the lifetime
   anchor can still die if the host console exits before the real child process
   has been detached cleanly.

Mitigation:

- do not use the current console title as the selector before the replacement
  monitor process is safely launched;
- prefer a launcher that creates a new process independently of the visible
  startup shell;
- on Windows, treat "window flashed and disappeared" as a launcher/process-model
  bug first, not as proof that the validation target itself failed immediately;
- keep a local launch log or pid file for the monitor/supervisor startup path
  so the next triage step is evidence-based instead of guessing from the UI.
