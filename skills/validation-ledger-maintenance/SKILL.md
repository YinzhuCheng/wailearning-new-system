---
name: validation-ledger-maintenance
description: Use this when adding or revising CourseEval validation targets, wiring ledger_id, updating test-execution CSV ledgers, correcting selector history drift, or recording observed validation evidence.
---

# Validation Ledger Maintenance

## Purpose

Keep the machine-readable validation registry, durable target ledger, and
observed run history aligned. Selector output is planning data; committed CSV
rows are reviewed project history.

This skill should treat the focused validation docs and ledger explainers as the
first reading layer, not the larger testing handbook alone.

## Workflow

1. Read:
   - `skills/validation-selection/SKILL.md`
   - `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
   - `docs/testing/README.md`
   - `docs/governance/agent-update-log.md` when `agent-update-log.csv` is in scope
2. For a registry target, decide whether it already has durable run history:
   if yes, `ledger_id` must match the target id; if no, leave `ledger_id` null.
3. Add target rows to `docs/testing/test-execution-targets.csv`
   only when the target should become durable metadata. Add run rows only for
   commands that actually executed.
4. Never point one target's `ledger_id` at an unrelated target as an informal
   alias. Add an explicit alias mechanism first if aliases ever become needed.
5. Update selector/manual tests for new registry invariants.
6. Run lint and selector checks before committing.

## Document Routing Rules

- Use `VALIDATION_WORKFLOW_AND_TOOLS.md` for selector/runner/profile behavior
  and evidence interpretation.
- Use `docs/testing/README.md` for the CSV ledger/source-of-truth map.
- Use `docs/governance/agent-update-log.md` for per-round update-log policy.
- Use `pitfalls-ledger-and-selector-tooling.md` when the issue is BOM, ledger
  drift, selector-history mismatch, or append-tooling behavior.

## Commands

```powershell
.venv\Scripts\python.exe -m json.tool tests\TEST_SELECTION_TARGETS.json
.venv\Scripts\python.exe ops\scripts\dev\lint_validation_registry.py
.venv\Scripts\python.exe -m unittest tests.backend.manual.test_validation_selector -v
.venv\Scripts\python.exe ops\scripts\dev\select_validation_targets.py --worktree --json
git diff --check
```

## Guardrails

- Record only observed command outcomes in CSV run history.
- Keep private paths out of CSV rows; use `<repo>`, `<local-port>`, and similar
  placeholders.
- Treat `needs_review` and `not_sufficient` selector states as decision points,
  not failures to hide.
- Do not commit `.agent-run/` artifacts. Use them only as local evidence while
  preparing reviewed ledger rows.
- Prefer updating the narrowest ledger explainer or policy doc instead of
  copying ledger rules into unrelated docs.

## Related Files

- `tests/TEST_SELECTION_TARGETS.json`
- `docs/testing/test-execution-targets.csv`
- `docs/testing/test-execution-runs.csv`
- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `docs/testing/README.md`
- `docs/governance/agent-update-log.md`
- `docs/testing/pitfalls-ledger-and-selector-tooling.md`
- `ops/scripts/dev/lint_validation_registry.py`
- `ops/scripts/dev/select_validation_targets.py`
- `tests/backend/manual/test_validation_selector.py`
