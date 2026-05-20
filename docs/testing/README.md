# Structured Test Execution Tables

This directory stores test execution history as CSV tables. The Markdown files
one level up remain human entry points and policy documents; the durable facts
that agents append and tooling parses live here.

## Files

| File | Purpose |
|------|---------|
| `test-execution-targets.csv` | One row per validation target: category, scope, canonical command, last observed result, pass count, run count, relevant paths, and retest triggers. |
| `test-execution-runs.csv` | Append-only observed run history. Add failed, blocked, timed-out, interrupted, and skipped attempts as well as passes. |
| `test-execution-summary.csv` | Short scan aid for recent or important observed validation runs. |
| `pitfall-index.csv` | Structured index for pitfalls recorded in Markdown docs. New pitfalls use increasing positive `pitfall_sequence`; legacy Markdown-only entries may use `0` and `Null`. |
| `agent-update-log.csv` | One row per user-visible repository-changing conversation round, starting at sequence 1. Summaries stay short; details remain in docs, ledgers, and commits. |
| `validation-debt-registry.csv` | Classification registry for high-cost or backlog-shaped validation targets and files so "not in this lane" is explicit policy instead of implied coverage. |
| `validation-lane-budgets.json` | Per-lane skip/deselect/xfail budget thresholds for CI reporting and future enforcement. |

## Source Of Truth

- Target definitions:
  `tests/TEST_SELECTION_TARGETS.json` is the machine routing source for selector
  policy and target commands. `test-execution-targets.csv` is the durable
  per-target ledger for observed metadata and counters.
- Execution history:
  `test-execution-runs.csv` is the append-only source of observed validation
  attempts.
- Pitfall index:
  `pitfall-index.csv` is the structured source for searchable pitfall metadata,
  while the canonical explanatory bodies stay in
  `TEST_EXECUTION_PITFALLS.md` and the narrower topic-route pitfall docs.
- Coverage summary:
  `test-execution-summary.csv` is the rolling concise summary source.
  Dated narrative reports such as `TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md`
  are historical evidence, not rolling source tables.

## Generated Views

These small explainer entrypoints are generated from
`ops/scripts/dev/sync_testing_governance_docs.py` and should not be edited by
hand:

- `TEST_EXECUTION_LEDGER.md`
- `TEST_EXECUTION_TARGETS.md`
- `TEST_EXECUTION_RUNS.md`
- `TEST_EXECUTION_SUMMARY.md`
- `PITFALL_INDEX.md`

Run:

```bash
python ops/scripts/dev/sync_testing_governance_docs.py
python ops/scripts/dev/sync_testing_governance_docs.py --check
```

## Debt Visibility

Use these when deciding whether skipped or deferred coverage is acceptable
policy or visible debt:

- [VALIDATION_DEBT_REGISTRY.md](VALIDATION_DEBT_REGISTRY.md)
- [validation-debt-registry.csv](validation-debt-registry.csv)
- [validation-lane-budgets.json](validation-lane-budgets.json)

## Topic Routes

Use these when you already know the failure class and want a narrower entry
than the full pitfall encyclopedia:

- [pitfalls-windows-and-encoding.md](pitfalls-windows-and-encoding.md)
- [pitfalls-playwright-and-e2e.md](pitfalls-playwright-and-e2e.md)
- [pitfalls-postgres-and-pytest.md](pitfalls-postgres-and-pytest.md)
- [pitfalls-ledger-and-selector-tooling.md](pitfalls-ledger-and-selector-tooling.md)

The canonical detailed pitfall body still lives in
[TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md) plus any canonical
clusters already migrated into the topic docs above. Use the encyclopedia for
unmigrated or mixed-surface entries; use the topic docs directly when the
structured index already routes that cluster there.

## Validation workflow entrypoint

Use [VALIDATION_WORKFLOW_AND_TOOLS.md](VALIDATION_WORKFLOW_AND_TOOLS.md) when
the task is specifically about:

- diff-based validation scope
- selector output
- validation target runner
- validation profile runner
- artifact/evidence interpretation

## Full validation policy entrypoint

Use [FULL_VALIDATION_ENVIRONMENT_POLICY.md](FULL_VALIDATION_ENVIRONMENT_POLICY.md)
when the task is specifically about:

- zero-skip / release-quality expectations
- PostgreSQL-backed full validation
- RAR extractor environment policy
- Playwright/runtime dependency requirements for full validation

## Rules

1. Record only observed executions. Selector output, dry-run planning, and typed
   but unexecuted commands do not belong in these CSV files.
2. Append run rows; do not rewrite history unless correcting a transcription
   error.
3. Keep committed paths repository-relative. Put private absolute paths and
   machine-local logs under ignored `.agent-run/` or `.e2e-run/` directories.
4. Keep long explanations in Markdown docs such as
   `../TEST_EXECUTION_PITFALLS.md`; keep CSV notes short and factual.
5. Use UTF-8 and the repository safe-text workflow before editing these files
   from Windows PowerShell. The default entrypoint is
   `ops/scripts/windows/invoke-safe-text-command.ps1`; use
   `set-utf8-session.ps1` directly only when an already-open interactive shell
   must be mutated.
6. Follow the pitfall recording policy in `TEST_EXECUTION_PITFALLS.md` when
   adding or reclassifying a pitfall.
7. Follow the per-round update-log policy in
   `../governance/agent-update-log.md` when appending `agent-update-log.csv`.

## Ledger entrypoints

Use these stable explainers before editing the corresponding CSV:

- [TEST_EXECUTION_TARGETS.md](TEST_EXECUTION_TARGETS.md)
- [TEST_EXECUTION_RUNS.md](TEST_EXECUTION_RUNS.md)
- [TEST_EXECUTION_SUMMARY.md](TEST_EXECUTION_SUMMARY.md)
- [PITFALL_INDEX.md](PITFALL_INDEX.md)
- [../governance/agent-update-log.md](../governance/agent-update-log.md)
