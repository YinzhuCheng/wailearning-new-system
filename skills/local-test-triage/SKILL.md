---
name: local-test-triage
description: Use this when CourseEval local pytest, SQLite, Playwright, port, process, dependency, or Windows PowerShell test failures look environment-related or inconsistent with ordered full-suite behavior.
---

# Local Test Triage

## Purpose

Separate real product regressions from known local harness hazards before
changing code. Convert repeatable pitfalls into docs, scripts, or selector
guardrails when practical.

This skill should route through the narrowest current pitfall and validation
docs first, instead of sending every agent through the older broad testing
handbook by default.

## Workflow

1. Run the pitfall memory first:
   `python ops/scripts/dev/search_pitfalls.py "<exact error or symptom>"`
2. Read the narrowest current docs first:
   - `docs/testing/pitfalls-windows-and-encoding.md`
   - `docs/testing/pitfalls-playwright-and-e2e.md`
   - `docs/testing/pitfalls-postgres-and-pytest.md`
   - `docs/testing/pitfalls-ledger-and-selector-tooling.md`
   - `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
   - `docs/governance/known-issues-and-risks.md`
3. If the failure class is still mixed or unclear, then expand to:
   - `docs/testing/TEST_EXECUTION_PITFALLS.md`
   - `docs/testing/DEVELOPMENT_AND_TESTING.md`
4. Check whether a failure is environment-shaped: missing module, port
   collision, missing browser, stale Playwright process, corrupted SQLite file,
   or concurrent pytest processes.
5. For SQLite weirdness, confirm no residual pytest/Python process is using
   `.pytest_tmp/test*.sqlite` before deleting or reusing it. Prefer the
   read-only guardrail script before manual process inspection.
6. Reproduce with one process and the narrowest relevant target.
7. If the failure is a real product regression, fix code/tests and run the
   selector-recommended targets.
8. If it is a repeatable harness pitfall, document it or add a guardrail.

## Document Routing Rules

- Use the topic pitfall docs as the first read when the failure class is
  already recognizable.
- Use `VALIDATION_WORKFLOW_AND_TOOLS.md` for selector, runner, and evidence
  interpretation.
- Use `FULL_VALIDATION_ENVIRONMENT_POLICY.md` when the failure matters only
  because the run is being treated as full-suite, zero-skip, or release-grade.
- Use `TEST_EXECUTION_PITFALLS.md` as the mixed-surface fallback, not as the
  first read in every case.

## Commands

```powershell
python ops/scripts/dev/search_pitfalls.py "<exact error or symptom>"
python ops/scripts/dev/pytest_sqlite_guard.py
python ops/scripts/dev/pytest_sqlite_guard.py --json
python ops/scripts/dev/pytest_sqlite_guard.py --fail-on-active-pytest
Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|pytest|py\.exe' } | Select-Object ProcessId,Name,CommandLine
python ops/scripts/dev/select_validation_targets.py --worktree
python ops/scripts/dev/run_validation_target.py <target-id> --timeout-seconds 120
```

## Guardrails

- Do not run concurrent pytest processes against the same SQLite artifact.
- Do not delete `.pytest_tmp/test*.sqlite` until no process is using it.
- `pytest_sqlite_guard.py` is read-only: it reports active pytest processes and
  SQLite file state, but does not stop processes or delete files.
- Treat isolated discussion-file SQLite reset noise as a harness concern unless
  it appears in ordered full-suite progression.
- Classify missing tools, port collisions, and Playwright browser absence as
  environment blockers, not product failures.
- Keep `.agent-run/` logs and machine paths out of committed docs.
- Do not treat a selector recommendation or pitfall hit as proof by itself;
  confirm that it matches the current failure before acting.

## Related Files

- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`
- `tests/conftest.py`
- `tests/db_reset.py`
- `ops/scripts/dev/pytest_sqlite_guard.py`
- `ops/scripts/dev/search_pitfalls.py`
- `docs/testing/TEST_EXECUTION_PITFALLS.md`
- `docs/testing/pitfalls-windows-and-encoding.md`
- `docs/testing/pitfalls-playwright-and-e2e.md`
- `docs/testing/pitfalls-postgres-and-pytest.md`
- `docs/testing/pitfalls-ledger-and-selector-tooling.md`
- `docs/governance/known-issues-and-risks.md`
- `ops/scripts/dev/run_validation_target.py`
