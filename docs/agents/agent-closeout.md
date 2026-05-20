# Agent Closeout

## Purpose

This document collects the closeout steps that every repository-changing round
must satisfy before commit or handoff.

Use it when:

- preparing to commit repository changes;
- deciding which durable logs or docs must be updated in the same round;
- checking whether local-only artifacts must be cleaned or kept;
- reviewing whether a repeated workflow should graduate into a script or skill.

`AGENTS.md` keeps the non-negotiable rule summaries. This file holds the
detailed closeout procedure.

## Required Closeout Sequence

For every user-visible repository-changing round:

1. Review the tracked diff and confirm the change still matches the task.
2. Run the narrowest honest validation starting from the diff selector:

   ```powershell
   python ops/scripts/dev/select_validation_targets.py --worktree
   ```

3. Update committed docs in the same round when behavior, permissions,
   configuration, validation flow, or operational workflow changed.
4. Append one row to `docs/testing/agent-update-log.csv` under
   [`../governance/agent-update-log.md`](../governance/agent-update-log.md).
5. Scan for private-path leaks and machine-local artifacts in tracked changes.
6. Clean reproducible local artifacts under `.agent-run/` and other safe cache
   locations with:

   ```powershell
   python ops/scripts/dev/clean_local_artifacts.py
   python ops/scripts/dev/clean_local_artifacts.py --apply
   ```

7. Decide whether any repeated or failure-prone workflow from this round should
   become a committed script or repo-local skill.

## Validation Expectations

Use change-scoped validation by default unless the user explicitly asks for:

- full-suite validation;
- release-quality validation;
- zero-skip validation.

Start with the selector and then route through:

- [`../testing/VALIDATION_WORKFLOW_AND_TOOLS.md`](../testing/VALIDATION_WORKFLOW_AND_TOOLS.md)
- [`../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`](../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md)
- [`../testing/CI_AND_VALIDATION.md`](../testing/CI_AND_VALIDATION.md)
- [`../../skills/validation-selection/SKILL.md`](../../skills/validation-selection/SKILL.md)

Report only observed validation, not planned validation.

## Update-Log Rule

Append one row to `docs/testing/agent-update-log.csv` before every
repository-changing commit.

The log is:

- required for tracked repository-changing rounds;
- concise and outcome-focused;
- not a replacement for commit messages, reports, or handoffs.

Use the detailed policy in
[`../governance/agent-update-log.md`](../governance/agent-update-log.md).

When the ledger already has historical anomalies, do not silently hide them.
Record the new row honestly and note the anomaly in the round if it affects
sequence confidence or tooling.

## Private-Path And Artifact Review

Before commit:

- keep machine-specific paths, ports, browser caches, local DB paths, and
  local logs in `.agent-run/` instead of tracked docs;
- keep screenshots in `pics/` local-only by default unless the user explicitly
  asks to push them;
- preserve `<repo>`, `<local-port>`, and similar placeholders in committed
  docs and ledgers.

Use:

- [`local-agent-workspace.md`](local-agent-workspace.md)
- [`../testing/pitfalls-ledger-and-selector-tooling.md`](../testing/pitfalls-ledger-and-selector-tooling.md)
- [`../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md`](../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md)

## Local Artifact Cleanup

At the end of the round, clean reproducible local artifacts under `.agent-run/`
and other safe cache locations.

Run a dry-run first:

```powershell
python ops/scripts/dev/clean_local_artifacts.py
```

Apply cleanup only when the action list is limited to reproducible caches or
local housekeeping/archival targets:

```powershell
python ops/scripts/dev/clean_local_artifacts.py --apply
```

Do not treat cleanup as license to remove non-reproducible user work or
unrelated local state.

## Promote Repeated Workflows

Before closing a repeated or failure-prone round, explicitly decide whether the
workflow should become:

- a committed script, when the workflow is stable and executable;
- a repo-local skill, when the workflow is multi-step agent procedure;
- a durable doc rule, when the workflow is policy or routing rather than
  execution.

Do not leave frequently reused workflows as ad hoc terminal lore.

## Related Files

- `AGENTS.md`
- [`agent-startup-routing.md`](agent-startup-routing.md)
- [`agent-playbook.md`](agent-playbook.md)
- [`local-agent-workspace.md`](local-agent-workspace.md)
- [`../governance/agent-update-log.md`](../governance/agent-update-log.md)
- [`../testing/VALIDATION_WORKFLOW_AND_TOOLS.md`](../testing/VALIDATION_WORKFLOW_AND_TOOLS.md)
- [`../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`](../testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md)
- [`../testing/pitfalls-ledger-and-selector-tooling.md`](../testing/pitfalls-ledger-and-selector-tooling.md)
