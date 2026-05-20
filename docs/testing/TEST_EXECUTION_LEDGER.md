<!-- Generated from ops/scripts/dev/sync_testing_governance_docs.py. Edit that script instead of editing this file directly. -->

# Test Execution Ledger

The durable validation ledger facts live in CSV tables under this directory:

- [`test-execution-targets.csv`](test-execution-targets.csv)
- [`test-execution-runs.csv`](test-execution-runs.csv)
- [`test-execution-summary.csv`](test-execution-summary.csv)

Use [`README.md`](README.md) for the full source-of-truth map and maintenance
rules. Keep this file as a stable entrypoint for older links and quick human
routing.

## Counting Semantics

- Increment `run_count` for any started validation command that produced an
  observed result: `passed`, `failed`, `blocked`, `timed out`, `interrupted`,
  or `skipped`.
- Increment `pass_count` only for observed `passed` runs.
- Do not record selector recommendations, dry-run planning, grep/static
  inspection, or commands that never executed.

## Current Source Of Truth

- target metadata and last-run durability signals:
  [`test-execution-targets.csv`](test-execution-targets.csv)
- append-only observed execution history:
  [`test-execution-runs.csv`](test-execution-runs.csv)
- rolling recent/important summary:
  [`test-execution-summary.csv`](test-execution-summary.csv)
