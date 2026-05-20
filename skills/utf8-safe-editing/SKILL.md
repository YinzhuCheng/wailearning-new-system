---
name: utf8-safe-editing
description: Use this before editing CourseEval multilingual, Chinese, Markdown, Vue, JSON, env, shell, or documentation files from Windows PowerShell, especially when output shows mojibake, suspicious glyphs, or encoding-sensitive text.
---

# UTF-8 Safe Editing

## Purpose

Prevent PowerShell display artifacts from becoming committed text corruption.
Treat terminal mojibake as untrusted until verified by UTF-8-aware tooling.

This skill should route through the current Windows safe-text entrypoint and
the current agent document layers, not through older helper names or
single-surface command lore.

## Workflow

1. Read:
   - `docs/contributing/ENCODING_AND_MOJIBAKE_SAFETY.md`
   - `docs/agents/agent-execution-entrypoints.md`
   - `docs/agents/local-agent-workspace.md` when local notes or path hygiene
     matter
2. Use the default Windows safe-text entrypoint first:
   `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops/scripts/windows/invoke-safe-text-command.ps1`
3. Inspect suspicious files with UTF-8-safe helpers instead of trusting the
   PowerShell console rendering.
4. Prefer `apply_patch` around stable ASCII anchors for manual edits.
5. After editing, run the changed-file encoding check.
6. If text still looks suspicious, verify by bytes, escaped output, or the
   repository helper scripts before making further edits.

## Document Routing Rules

- Use `docs/contributing/ENCODING_AND_MOJIBAKE_SAFETY.md` as the canonical
  source for detailed UTF-8-safe workflow, helper semantics, and corruption
  diagnosis.
- Use `docs/agents/agent-execution-entrypoints.md` for the current Windows
  safe-text entrypoint and related execution routing.
- Use `docs/testing/pitfalls-windows-and-encoding.md` when the problem is a
  known Windows/Python/PowerShell execution trap rather than a source-editing
  question.
- Use `docs/agents/local-agent-workspace.md` for local path / `.agent-run/`
  handling, not this skill.

## Commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1 -Path <repo-relative-path>
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1 -Command "<repo command>"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-rg.ps1 -Pattern "<rg-pattern>" -Paths "apps/backend/courseeval_backend/llm_grading.py","tests"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-pytest.ps1 -Targets "tests/backend/llm/test_llm_group_routing.py" -PytestArgs "-q"
python ops/scripts/dev/check_text_encoding.py --fail-on-suspicious <changed-file>
python ops/scripts/dev/run_validation_target.py static.encoding_text_tools --timeout-seconds 120
git diff --check
```

## Guardrails

- Do not run destructive grep-replace over Chinese or mixed-language text.
- Do not "fix" mojibake seen only in PowerShell until UTF-8 checks confirm the
  file bytes are wrong.
- Do not prefer long ad hoc PowerShell one-liners over committed wrappers when
  quoting-sensitive commands can be scripted once and reused.
- Keep private local paths out of committed diagnostics.
- For docs/governance work, also run
  `python ops/scripts/dev/check_repository_normalization.py`.
- Treat display-layer weirdness and file-content corruption as different
  problems until the bytes prove otherwise.

## Related Files

- `docs/contributing/ENCODING_AND_MOJIBAKE_SAFETY.md`
- `docs/agents/agent-execution-entrypoints.md`
- `docs/agents/local-agent-workspace.md`
- `docs/testing/pitfalls-windows-and-encoding.md`
- `ops/scripts/windows/invoke-safe-text-command.ps1`
- `ops/scripts/dev/check_text_encoding.py`
- `ops/scripts/dev/safe_show_text.py`
- `ops/scripts/dev/safe_write_text.py`
