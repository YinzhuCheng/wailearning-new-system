# CI And Validation

## Purpose

This document centralizes the current CI entrypoints and validation routing for
CourseEval.

Use it when:

- deciding which cloud checks currently exist;
- routing local validation work before or after CI;
- explaining the gap between lightweight cloud gates and fuller local/manual
  validation.

## CI Entrypoints

### GitHub Actions

Current lightweight workflow:

- [`.github/workflows/lightweight-validation.yml`](../../.github/workflows/lightweight-validation.yml)

Current scope:

- CI baseline governance for runtime-version and command drift;
- selector/tooling checks;
- diff-based validation recommendation artifacts for pull requests;
- selector policy gating against the lightweight CI lane capabilities;
- quick backend `pytest`;
- school frontend build;
- parent frontend build.

Current non-goals:

- no PostgreSQL service container;
- no zero-skip backend guarantee;
- no RAR-dependent attachment environment provisioning;
- no full Playwright E2E run;
- no automatic broad/full selector target execution.

### External CI Definitions

Cloud pipeline examples remain under:

- [`ops/ci/`](../../ops/ci/)

Current aligned baseline:

- Python `3.11` across GitHub Actions backend jobs and `ops/ci/*.yml`;
- Node `20` across GitHub Actions frontend jobs;
- canonical backend install/test commands:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
```

The baseline drift guard lives in:

- [`ops/scripts/dev/check_ci_baselines.py`](../../ops/scripts/dev/check_ci_baselines.py)

## Local Validation Entry

For detailed local validation workflow, use:

- [`VALIDATION_WORKFLOW_AND_TOOLS.md`](VALIDATION_WORKFLOW_AND_TOOLS.md)
- [`FULL_VALIDATION_ENVIRONMENT_POLICY.md`](FULL_VALIDATION_ENVIRONMENT_POLICY.md)
- [`FULL_PLAYWRIGHT_E2E_RUNBOOK.md`](FULL_PLAYWRIGHT_E2E_RUNBOOK.md)
- [`../architecture/TROUBLESHOOTING.md`](../architecture/TROUBLESHOOTING.md)
- [`../../skills/validation-selection/SKILL.md`](../../skills/validation-selection/SKILL.md)

Start with the diff selector:

```bash
python ops/scripts/dev/select_validation_targets.py --worktree
```

## How To Interpret The Current Gate

Treat GitHub Actions as the first cloud gate, not as full production-aligned
validation. A green lightweight workflow does **not** by itself prove:

- PostgreSQL-backed schema parity;
- zero-skip backend validation;
- browser-harness correctness for Playwright;
- attachment extraction paths that depend on extra runtime tools.

Use local/manual validation to close those gaps when the task scope requires
it.

On pull requests, the selector output is now also checked against the
lightweight lane's available validation classes. If the diff requires a class
that the lane does not provide, such as `full-suite` / PostgreSQL-heavy
validation, the policy gate fails even though the lightweight jobs themselves
remain intentionally narrow.

For local or future CI environment diagnosis, prefer the shared capability
probe first:

```bash
python ops/scripts/dev/check_validation_capabilities.py --json
```

This report centralizes Playwright managed-server readiness, PostgreSQL test
environment readiness, RAR extractor availability, and text-safety warnings.

For the small testing-ledger explainer docs, the generated source is:

- [`ops/scripts/dev/sync_testing_governance_docs.py`](../../ops/scripts/dev/sync_testing_governance_docs.py)

Skip/deferred coverage visibility now has two committed anchors:

- [`validation-debt-registry.csv`](validation-debt-registry.csv) for target/file
  classification
- [`validation-lane-budgets.json`](validation-lane-budgets.json) for lane-level
  thresholds

## Agent Reporting Rule

When reporting validation:

- separate selector planning from observed execution;
- separate local execution from remote CI status;
- state when broad/full targets were deferred;
- state when CI scope is intentionally narrower than the requested confidence
  level.

## Related Files

- `docs/testing/DEVELOPMENT_AND_TESTING.md`
- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`
- `docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`
- `docs/testing/TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md`
- `ops/ci/pr-pipeline.yml`
- `.github/workflows/lightweight-validation.yml`
- `skills/validation-selection/SKILL.md`
