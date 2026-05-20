# Encoding And Mojibake Safety

## Purpose

This document defines the repository policy for editing multilingual files from Windows + PowerShell without introducing mojibake into tracked source.

The audience is primarily LLM coding agents and automation-oriented maintainers. The goal is operational correctness, not brevity.

Read this before:

- editing any file that contains Chinese UI text or comments,
- rewriting long Markdown files from terminal output,
- "cleaning up" text that only looks broken in the console,
- or auditing whether a previous refactor accidentally introduced encoding corruption.

## Core Rule

PowerShell console output is not the source of truth for Unicode text in this repository.

If terminal rendering and repository history disagree, trust the file bytes on disk and the version-controlled diff, not the glyphs shown in the shell window.

## What Can Go Wrong

The repository is frequently edited from Windows environments where:

- UTF-8 file contents may render incorrectly in the terminal,
- copied terminal text may contain mojibake that was never in the source file,
- mixed-language Markdown can be damaged by full-file rewrites,
- and test fixtures may intentionally contain historical strings that should not be "fixed" during unrelated work.

This creates two different classes of problem:

1. display-only mojibake
2. real file-content corruption

Those classes must not be conflated.

## Safe Editing Strategy

Use this workflow for any multilingual or encoding-sensitive file.

1. Prefer structural edits over text rewrites.
2. Anchor edits on ASCII context such as file paths, route names, identifiers, Markdown headings, JSON keys, or `data-testid` values.
3. Use patch-based edits instead of copying text out of terminal output.
4. If a non-ASCII literal truly must change, verify it through a UTF-8-safe editor or another byte-safe path before editing.
5. After the edit, review the git diff for the specific file and confirm that only the intended lines changed.

## Repository Helpers Added For Windows + PowerShell

The repository now includes small utilities whose purpose is to reduce encoding
mistakes during agent work. These helpers are not a license to trust terminal
glyphs blindly. They provide safer defaults and repeatable inspection paths.

### Default Windows text-workflow entrypoint

Use this as the default workflow before inspecting or editing multilingual
repository files from Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1
```

Important:

- this wrapper always starts a child PowerShell process with
  `-NoProfile -ExecutionPolicy Bypass`;
- inside that child process it dot-sources
  `enter-safe-text-session.ps1`, then runs `assert-safe-text-session.ps1`;
- use `-Command "<repo command>"` to keep repository work in that same
  UTF-8-safe child process;
- prefer committed wrappers for complex shell invocations instead of long
  PowerShell one-liners; for example use
  `ops\scripts\windows\invoke-safe-rg.ps1` for ripgrep patterns with pipes or
  quotes and `ops\scripts\windows\invoke-safe-pytest.ps1` for long pytest
  target lists;
- if you intentionally need to mutate an already-trusted interactive shell,
  dot-source `set-utf8-session.ps1` yourself, but that is not the default agent
  workflow.

If you already know the target file, pass it immediately:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1 `
  -Path apps\web\school\src\views\Layout.vue -StartLine 1 -EndLine 120
```

This entrypoint:

1. starts a child PowerShell process with `-ExecutionPolicy Bypass`;
2. applies the UTF-8-oriented console/session settings inside that child;
3. asserts the safe-text state before repository work continues;
4. optionally routes into the safe multilingual file inspection workflow for a
   specific path;
5. can run a repository command in the same safe-text child process.

Use `assert-safe-text-session.ps1` when you want a yes/no check that the
current shell already entered the safe-text workflow:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\assert-safe-text-session.ps1
```

### Low-level UTF-8 session setup

Run this at the start of a Windows PowerShell session that may inspect or edit
multilingual repository files:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\set-utf8-session.ps1
```

If you want the environment changes to stay in the current interactive shell,
dot-source it instead:

```powershell
. .\ops\scripts\windows\set-utf8-session.ps1
```

The script changes only the current process and child-process environment. It
sets:

- console code page `65001`;
- `[Console]::OutputEncoding` to UTF-8 without BOM;
- `[Console]::InputEncoding` to UTF-8 without BOM;
- `$OutputEncoding` to UTF-8 without BOM;
- `PYTHONUTF8=1`;
- `PYTHONIOENCODING=utf-8`;
- `LESSCHARSET=utf-8`.

It also sets `COURSEEVAL_SAFE_TEXT_SESSION=1`, which repository helper scripts
use as a lightweight marker that the current shell already entered the safe
UTF-8 baseline.

### File inspection workflow

When a Windows PowerShell session is about to inspect or edit a multilingual
repository file, use this command first:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1 -Path <repo-relative-path>
```

Example:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1 `
  -Path apps\web\school\src\views\Layout.vue -StartLine 1 -EndLine 120
```

What this rule enforces:

1. Start the safe-text child process with `invoke-safe-text-command.ps1`.
2. Enter a UTF-8-oriented session with `enter-safe-text-session.ps1`.
3. Display the target file through `safe_show_text.py`.
4. Run `check_text_encoding.py` on that exact path.
5. Only then make patch-based edits or an intentional full-file write.

Implementation note:

- `invoke-safe-text-command.ps1` is now the default Windows PowerShell
  wrapper for agents and automation.
- `safe-text-workflow.ps1` remains as the lower-level file-inspection helper
  invoked by `enter-safe-text-session.ps1` and can still be run directly for
  compatibility.

Use `-Escape` when terminal rendering is still suspicious and
`-FailOnSuspicious` when the selected file is expected to be clean.

Interpretation rules:

- This reduces mojibake in many PowerShell sessions, but it does not prove that
  terminal-rendered Chinese is correct.
- If output still looks garbled, treat the terminal as display-only and verify
  bytes through `safe_show_text.py --escape`, a UTF-8 editor, or `git diff`.
- Do not put machine-specific profile paths or console screenshots into
  committed documentation. Use placeholders such as `<repo>` in tracked docs and
  `.agent-run/` for private local notes. `.e2e-run/` is legacy local
  workspace naming and remains ignored only for compatibility with older
  handoffs or tools.

### UTF-8-safe file display

Use `safe_show_text.py` when a terminal might render valid UTF-8 incorrectly:

```powershell
python ops\scripts\dev\safe_show_text.py docs\contributing\ENCODING_AND_MOJIBAKE_SAFETY.md
python ops\scripts\dev\safe_show_text.py apps\web\school\src\views\Layout.vue --start-line 1 --end-line 120
python ops\scripts\dev\safe_show_text.py tests\e2e\web-school\e2e-scenario-resilience.spec.js --escape --start-line 1 --end-line 80
```

Normal mode decodes the file as UTF-8 and prints text. Escape mode prints
non-ASCII as Python `unicode_escape` sequences so the terminal cannot hide the
actual code points behind mojibake. Escape mode is less pleasant for humans, but
it is useful for agents deciding whether a suspicious string is present in the
file bytes or only in the display layer.

When a file fails to decode as UTF-8, the script exits non-zero with the byte
position. Treat that as a real file-content issue for that path, not as ordinary
PowerShell rendering noise.

### UTF-8-safe full-file writes

Use `safe_write_text.py` only when a full-file write is intentional and the
input source is trusted:

```powershell
python ops\scripts\dev\safe_write_text.py .agent-run\handoff.md --stdin --mkdirs
python ops\scripts\dev\safe_write_text.py docs\example.md --from-file .agent-run\draft.md --replace
```

Default behavior:

- reads stdin or `--from-file` as text;
- writes UTF-8 without BOM;
- normalizes output newlines to LF unless `--newline crlf` or
  `--newline preserve` is specified;
- refuses to overwrite an existing file unless `--replace` is supplied;
- writes through a temporary file and atomic replace.

Important limits:

- For small source edits, repository-aware patching is still preferred over a
  full-file rewrite.
- Do not pipe PowerShell-rendered Chinese text into this tool and assume it is
  safe; if the source stream already contains mojibake, this tool will preserve
  the mojibake as valid UTF-8.
- Use this helper for generated docs, local handoffs, machine-readable reports,
  or deliberate whole-file rewrites where the source bytes are already verified.

### Tracked text encoding audit

Use `check_text_encoding.py` before or after encoding-sensitive edits:

```powershell
python ops\scripts\dev\check_text_encoding.py
python ops\scripts\dev\check_text_encoding.py --fail-on-suspicious
python ops\scripts\dev\check_text_encoding.py docs\contributing\ENCODING_AND_MOJIBAKE_SAFETY.md
```

Default behavior:

- scans files returned by `git ls-files`;
- ignores local artifacts and private `.agent-run/` notes by construction;
- fails on UTF-8 decode errors;
- reports suspicious mojibake markers without failing.

Use `--fail-on-suspicious` only when the suspicious-marker set is expected to be
clean for the selected files. The repository has known historical hotspots, so a
whole-repo suspicious-marker failure may be useful for dedicated cleanup work
but too noisy for unrelated feature branches.

The suspicious-marker list includes common Windows/CP936 mojibake fragments
seen in this repository. When the script reports a marker in an E2E selector or
assertion, do not rewrite it casually: first confirm whether the literal is a
real product string, stale selector fallback, or intentionally broad regular
expression. Repair selector text in a dedicated change with the affected
Playwright target, not as a side effect of documentation cleanup.

### Git output settings that can help

When an agent or maintainer repeatedly reads paths or commit messages containing
non-ASCII text from Windows shells, these local git settings can reduce display
confusion:

```powershell
git config core.quotepath false
git config i18n.logOutputEncoding utf-8
git config i18n.commitEncoding utf-8
```

These settings affect the local clone. They do not repair file contents and they
do not replace the repository helpers above.

## Unsafe Practices

Do not do the following:

- copy Chinese text from PowerShell output and paste it back into tracked files,
- rewrite a whole multilingual file just to change one structural line,
- normalize a suspicious string by eye when the terminal may be lying,
- or treat any unreadable glyph sequence as proof that the repository file itself is corrupted.

## Preferred Tactics By File Type

### Python source

- Prefer structural refactors, imports, helpers, and call-site changes without touching human-language literals.
- If only a small non-ASCII literal must change, prefer a minimal patch around that literal.
- If a Unicode escape is clearer and already consistent with the file style, it is acceptable for a narrowly scoped change.

### JavaScript or Vue files

- Anchor changes on identifiers, props, API calls, selectors, and test IDs.
- Avoid terminal-driven rewrites of user-facing copy unless the task is explicitly text-focused.

### Markdown documentation

- Prefer adding new ASCII sections instead of rewriting older mixed-language sections unless the older section is clearly obsolete.
- Preserve historical notes, but translate outdated implementation references into current-branch meaning.

## Current Repository Audit Findings

Date of audit: `2026-05-03`

The current branch contains visible mojibake-like sequences in a small number of tracked files. At the time of this audit, those hotspots were treated as existing repository state that requires dedicated text-repair work, not opportunistic edits during unrelated refactors.

This audit did **not** find new suspicious mojibake sequences in the documentation files that were intentionally edited in this round.

Known hotspots identified during this audit include:

- `tests/e2e/web-school/e2e-llm-hard-scenarios.spec.js`
- `tests/e2e/web-school/e2e-scenario-resilience.spec.js`

Interpretation:

- some hotspots may be true file-content corruption from older edits,
- some may be historically checked-in text that still passes runtime use,
- some may only appear suspicious when viewed through PowerShell output.

In the two E2E files above, the suspicious strings currently appear inside selectors and text-matching helpers, which makes casual "cleanup" especially risky.

The important operational rule is the same in all three cases: do not "repair" them casually while doing structural or behavioral work.

## How To Audit For Real Corruption

When you need to decide whether a mojibake-looking string is real file corruption:

1. inspect the file through a UTF-8-safe editor,
2. run `python ops/scripts/dev/safe_show_text.py <path> --escape` around the suspicious lines,
3. run `python ops/scripts/dev/check_text_encoding.py <path>` to catch decode errors and known marker patterns,
4. compare against git history when available,
5. review whether the string is user-facing copy, test data, or a literal that affects selectors or assertions,
6. isolate the repair into a dedicated change set if possible.

Do not combine encoding cleanup with a large refactor unless the encoding issue blocks the refactor itself.

## Operational Recipes For Agents

### Beginning a Windows work session

1. Read `AGENTS.md`, `docs/README.md`, and task-scoped docs first.
2. Apply the session helper:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-rg.ps1 -Pattern "retry_scheduled|processing"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-pytest.ps1 -Targets "tests/backend/llm/test_llm_group_routing.py" -PytestArgs "-q"
```

3. Use `-Command "<repo command>"` when the repository work should run inside
   that same safe-text child process.
4. Prefer the committed Windows wrappers instead of long inline PowerShell
   commands when the task needs `rg`, `pytest`, or other quoting-sensitive
   tools.
5. If you intentionally need to mutate an already-trusted interactive shell,
   dot-source `set-utf8-session.ps1` instead of using the child-process
   wrapper.
6. Use `assert-safe-text-session.ps1` when you need a quick verification that
   the current shell is still in the safe-text workflow.
7. Continue to prefer ASCII anchors and patch-based edits for source files.

### Inspecting a suspicious multilingual file

1. Identify an ASCII anchor with `rg`, such as a function name, test id, route
   path, or Markdown heading.
2. Display a narrow range with:

```powershell
python ops\scripts\dev\safe_show_text.py <path> --start-line <n> --end-line <m>
```

3. If glyphs still look wrong, repeat with `--escape`.
4. Compare with `git diff` or `git show` before editing the literal.

### Writing local handoff notes that contain private paths

1. Keep the file under `.agent-run/`.
2. Use `safe_write_text.py` when generating the file from a known-good source.
3. Use real absolute paths only in `.agent-run/` notes.
4. Use `<repo>`, `<user-home>`, `<artifact-dir>`, `<local-port>`, and similar
   placeholders in committed docs.

### After editing encoding-sensitive files

Run the narrowest useful checks:

```powershell
python ops\scripts\dev\check_text_encoding.py <edited-file>
git diff --check
```

For Python helpers added under `ops/scripts/dev/`, also run:

```powershell
python -m py_compile ops\scripts\dev\safe_show_text.py ops\scripts\dev\safe_write_text.py ops\scripts\dev\check_text_encoding.py
```

## Rules For Documentation Upgrades

Documentation work in this repository should follow these rules:

- keep the docs detailed enough for an LLM agent to act on them,
- prefer additive clarification over deletion unless the old text is truly obsolete,
- preserve historical lessons and traps,
- but rewrite outdated implementation details so they remain meaningful under the current code layout.

When an older paragraph contains useful operational history but refers to paths or modules that no longer exist, keep the lesson and update the implementation reference.

## Recommended Verification After Editing

For documentation-only changes in encoding-sensitive files:

- review the file diff directly,
- confirm that headings, links, and code fences remain intact,
- confirm that no unrelated multilingual blocks were rewritten,
- and confirm that any new policy text points to the current repository paths.

For code changes in encoding-sensitive files:

- review the diff,
- confirm imports and syntax by inspection,
- and isolate any separate text-repair work from the structural change when possible.
