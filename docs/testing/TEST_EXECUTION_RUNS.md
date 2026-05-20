<!-- Generated from ops/scripts/dev/sync_testing_governance_docs.py. Edit that script instead of editing this file directly. -->

# Test Execution Runs

This document is the stable explainer for
[`test-execution-runs.csv`](test-execution-runs.csv).

## What The CSV Stores

`test-execution-runs.csv` is the append-only observed run history.

Each row records a real validation attempt with fields such as:

- target id
- date
- branch
- source commit
- observed command
- result
- summary
- notes

## When To Update It

Append a row when a validation command actually executed and produced an
observable outcome.

Record:

- `passed`
- `failed`
- `blocked`
- `timed out`
- `interrupted`
- `skipped`

Do not record selector recommendations, dry-run planning, or commands that
never ran.

## Related Files

- [test-execution-runs.csv](test-execution-runs.csv)
- [test-execution-targets.csv](test-execution-targets.csv)
- [test-execution-summary.csv](test-execution-summary.csv)
