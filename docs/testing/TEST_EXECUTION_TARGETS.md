<!-- Generated from ops/scripts/dev/sync_testing_governance_docs.py. Edit that script instead of editing this file directly. -->

# Test Execution Targets

This document is the stable explainer for
[`test-execution-targets.csv`](test-execution-targets.csv).

## What The CSV Stores

`test-execution-targets.csv` stores one row per durable validation target,
including:

- target id
- category
- scope
- canonical command
- working directory
- relevant paths
- retest triggers
- last observed result metadata
- pass count
- run count

## When To Update It

Update this CSV when:

- a validation target becomes part of the durable repository target set;
- the canonical command, path surface, or working directory changes;
- a selector registry target needs a matching durable ledger row;
- reviewed observed results should update `last_*`, `pass_count`, or
  `run_count`.

## Related Files

- [test-execution-targets.csv](test-execution-targets.csv)
- [test-execution-runs.csv](test-execution-runs.csv)
- [TEST_EXECUTION_LEDGER.md](TEST_EXECUTION_LEDGER.md)
