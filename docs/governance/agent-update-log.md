# Agent Update Log Policy

## Purpose

This document defines when and how to append
`docs/testing/agent-update-log.csv`.

Use it when:

- finishing a repository-changing conversation round;
- updating append helpers or CSV governance;
- deciding what level of detail belongs in the update log versus other docs or
  ledgers.

## Role Of The Update Log

`agent-update-log.csv` is a concise per-round index. It is not the full
handoff, not a replacement for commit messages, and not the place for long
validation narratives.

Use it to answer:

- what the user-visible round changed;
- which files or surfaces were touched;
- whether code, tests, docs, pitfalls, and validation were involved;
- what validation evidence was actually observed.

## Append Rule

Append one row at the end of every user-visible repository-changing
conversation round before committing.

Do not append rows for:

- read-only exploration;
- selector planning that produced no repository changes;
- local-only artifact cleanup that does not touch tracked files;
- abandoned experiments that never become part of the tracked diff.

## Required Fields

The CSV uses:

- `update_sequence`
- `source_commit_sha`
- `request_summary`
- `changed_files`
- `touched_code`
- `touched_tests`
- `touched_docs`
- `touched_pitfalls`
- `validation_summary`
- `notes`

Operational rules:

1. `update_sequence` increases by one from the previous committed row.
2. `source_commit_sha` is the most recent committed hash at the **start** of
   the round.
3. `request_summary` stays short and outcome-focused.
4. `changed_files` is an index, not a full changelog; keep detail in commits,
   docs, and ledgers.
5. `validation_summary` records only observed validation, not mere plans.

## Relationship To Other Evidence

Keep detailed evidence in the appropriate surface:

- long validation history: `docs/testing/test-execution-runs.csv`
- target metadata: `docs/testing/test-execution-targets.csv`
- repeatable failures: `docs/testing/TEST_EXECUTION_PITFALLS.md`
- durable handoff context: `docs/handoffs/`
- machine-local logs and private paths: `.agent-run/`

## Editing Notes

- Preserve UTF-8 without BOM when editing CSV ledgers.
- Use the repository safe-text workflow on Windows PowerShell.
- Re-run validation registry / CSV smoke checks when changing append helpers or
  ledger tooling.

## Related Files

- `docs/testing/agent-update-log.csv`
- `docs/testing/README.md`
- `docs/testing/TEST_EXECUTION_PITFALLS.md`
- `skills/validation-ledger-maintenance/SKILL.md`
- `skills/security-redteam-iteration/SKILL.md`
