# Agent Execution Entrypoints

## Purpose

This document holds the execution-focused entrypoints that an agent needs once
task routing is already known.

Use it when:

- launching repository work from Windows PowerShell;
- triaging ambiguous local failures;
- selecting validation scope and evidence workflow;
- checking current CI entrypoints and reporting boundaries.

Keep [`agent-startup-routing.md`](agent-startup-routing.md) focused on startup
order, task routing, high-risk areas, and grep discovery. Use this document for
the execution mechanics that follow.

## Windows PowerShell Safe Entry

Windows PowerShell default safe-text command wrapper:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops/scripts/windows/invoke-safe-text-command.ps1
```

Use `-Command "<repo command>"` to keep repository work in the same safe-text
child process. Use `-Path <repo-relative-path>` when the safe multilingual-file
inspection workflow should run before editing.

Prefer:

- `ops/scripts/windows/invoke-safe-rg.ps1` for complex ripgrep patterns
- `ops/scripts/windows/invoke-safe-pytest.ps1` for long pytest target lists

Detailed safe-edit guidance lives in:

- [`agent-playbook.md`](agent-playbook.md)
- [`../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md`](../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md)

## Failure Triage Entrypoint

Start every ambiguous local failure with:

```powershell
python ops/scripts/dev/search_pitfalls.py "<error text or symptom>"
```

Then route through:

- [`../testing/TEST_EXECUTION_PITFALLS.md`](../testing/TEST_EXECUTION_PITFALLS.md)
- [`../testing/pitfalls-windows-and-encoding.md`](../testing/pitfalls-windows-and-encoding.md)
- [`../testing/pitfalls-playwright-and-e2e.md`](../testing/pitfalls-playwright-and-e2e.md)
- [`../testing/pitfalls-postgres-and-pytest.md`](../testing/pitfalls-postgres-and-pytest.md)
- [`../testing/pitfalls-ledger-and-selector-tooling.md`](../testing/pitfalls-ledger-and-selector-tooling.md)
- [`../architecture/TROUBLESHOOTING.md`](../architecture/TROUBLESHOOTING.md)
- [`../../skills/local-test-triage/SKILL.md`](../../skills/local-test-triage/SKILL.md)

Use repository pitfall docs and tooling for repeatable execution traps; do not
guess whether a failure is product, harness, or environment shaped.

## Validation Entrypoint

Use change-scoped validation by default unless the user explicitly asks for
full-suite, release-quality, or zero-skip validation.

Start with:

```powershell
python ops/scripts/dev/select_validation_targets.py --worktree
```

Use the repository default `strict` workflow unless the user explicitly asks
for a lighter guided route.

Strict mode means:

- start from `AGENTS.md`, `docs/README.md`,
  `docs/governance/repository-governance.md`,
  `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`,
  `docs/testing/CI_AND_VALIDATION.md`, and
  `docs/testing/TEST_EXECUTION_PITFALLS.md`;
- then read the task-scoped docs and skills already routed elsewhere in the
  agent docs bundle;
- if code behavior, permissions, config, validation flow, or workflow
  contracts change, update committed docs in the same round;
- use the pitfall search before classifying ambiguous failures;
- use selector output and observed validation honestly;
- update durable logs and ledgers when the round changed the repository.

Guided mode means:

- the user explicitly chose a lighter route;
- startup docs still matter, but task-specific reading is advisory rather than
  hard-locked;
- the agent may choose a narrower reading path first and expand if needed;
- guided evidence must never be reported as strict completion.

Then use the detailed workflow in:

- [`../testing/VALIDATION_WORKFLOW_AND_TOOLS.md`](../testing/VALIDATION_WORKFLOW_AND_TOOLS.md)
- [`../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`](../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md)
- [`../../skills/validation-selection/SKILL.md`](../../skills/validation-selection/SKILL.md)
- [`../../skills/parallel-validation-orchestration/SKILL.md`](../../skills/parallel-validation-orchestration/SKILL.md) when the main problem is shard supervision, automatic slot refill, or visible live monitoring rather than simple target choice
- [`agent-closeout.md`](agent-closeout.md)

Use repository-normalization guardrails for docs/governance/path work:

```powershell
python ops/scripts/dev/check_repository_normalization.py
```

## CI Entrypoints

Use these as the current cloud validation entrypoints:

- [`.github/workflows/lightweight-validation.yml`](../../.github/workflows/lightweight-validation.yml)
- [`../../ops/ci/`](../../ops/ci/)

Use [`../testing/CI_AND_VALIDATION.md`](../testing/CI_AND_VALIDATION.md) for
current scope, non-goals, and how to report local versus remote validation
honestly.

## Related Files

- [`agent-startup-routing.md`](agent-startup-routing.md)
- [`agent-playbook.md`](agent-playbook.md)
- [`agent-closeout.md`](agent-closeout.md)
- [`../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md`](../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md)
- [`../testing/VALIDATION_WORKFLOW_AND_TOOLS.md`](../testing/VALIDATION_WORKFLOW_AND_TOOLS.md)
- [`../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`](../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md)
- [`../testing/CI_AND_VALIDATION.md`](../testing/CI_AND_VALIDATION.md)
