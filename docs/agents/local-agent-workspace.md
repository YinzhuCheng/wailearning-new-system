# Local Agent Workspace

## Purpose

This document defines the current contract for the ignored local agent
workspace under `.agent-run/`.

Use it when:

- continuing work on this machine after an interrupted or handed-off round;
- deciding what belongs in committed docs versus local-only notes;
- storing local logs, validation artifacts, screenshots, or private paths;
- checking whether a file is safe to commit.

## Core Rule

`.agent-run/` is the ignored, local-only workspace for machine-specific agent
artifacts. Treat it as a private continuation area, not as source layout.

## What Belongs In `.agent-run/`

Use `.agent-run/` for:

- private absolute paths and machine-local notes;
- local validation logs and runner artifacts;
- screenshots and browser evidence;
- temporary orchestrators, local plan files under `.agent-run/plan/`, and
  other local-only helper data;
- database, browser, or process evidence that would be noisy or unsafe in the
  tracked repository.

Typical stable entrypoints include:

- `.agent-run/local-private-paths.md`
- `.agent-run/plan/` for task-scoped local plan files that should be deleted
  after the plan is executed or explicitly superseded
- `.agent-run/validation-history.jsonl`
- task-scoped local scripts or notes needed only on this machine

Do not treat any local planning note in `.agent-run/` as a durable repository
entrypoint. If a plan becomes part of the repository contract, promote the
durable part into committed docs and let the local note disappear.

Plan maintenance rules:

- create one local plan file per distinct active lane when the task needs
  durable step memory;
- re-read the active plan files at the start of each new round in that lane so
  previous priorities and deferred work are not forgotten;
- keep plans detailed enough to survive interruption without guesswork;
- update each active plan at the end of every execution round so the remaining
  work stays explicit;
- delete a plan file once the plan is fully executed or clearly superseded;
- do not leave stale completed plans in `.agent-run/plan/`.

## What Stays Out Of Commits

Do not commit:

- `.agent-run/` contents;
- machine-specific usernames or home directories;
- local database directories;
- local browser cache paths;
- downloaded binary locations;
- local credentials, tokens, or private logs.

If a finding needs to survive handoff or future work across machines, promote
the durable part to committed docs under `docs/` and keep only the local-only
evidence in `.agent-run/`.

## Continuation Workflow

When continuing work on the same machine:

1. Read `AGENTS.md` and `docs/README.md`.
2. Open any task-relevant committed handoff or governance doc first.
3. Then read task-relevant local notes under `.agent-run/`, especially
   `.agent-run/plan/` for active local plans and
   `.agent-run/local-private-paths.md` when path setup matters.
4. Delete a completed or superseded local plan file instead of keeping stale
   execution plans in `.agent-run/plan/`.
5. Keep new private notes local unless the information should become a durable
   repository rule or handoff.

## Relationship To Other Ignored Paths

- `.agent-run/` is the current local agent workspace contract.
- `.e2e-run/` may still appear in older notes or ignored-path compatibility
  rules, but `.agent-run/` is the active location for local agent artifacts in
  this worktree.
- Other runtime artifacts such as `.venv/`, `node_modules/`, `uploads/`, and
  package-local `test-results/` remain runtime data, not committed source.

## Related Files

- `AGENTS.md`
- `docs/agents/agent-playbook.md`
- `docs/architecture/REPOSITORY_STRUCTURE.md`
- `docs/governance/repository-governance.md`
