---
name: round-plan-discipline
description: Use this when a CourseEval task should be executed in explicit rounds where each round must begin by re-reading the current plan, end by updating the plan, follow AGENTS.md closeout rules, append the agent update log when tracked files changed, and commit locally without pushing.
---

# Round Plan Discipline

## Purpose

Enforce a repeatable CourseEval round structure for long-running work:

- re-read the current plan at the start of each round
- execute one bounded round objective
- update the plan before closing the round
- follow `AGENTS.md` and repository closeout rules every round
- commit locally at the end of every repository-changing round
- do not push unless the user explicitly asks

Use this skill when the user asks for stepwise execution, phased work, durable
plan memory, or repeated "finish a round, commit, review plan, continue"
behavior.

## Execution Modes

This skill supports two operating modes:

### 1. Continuous Mode

Default mode for long tasks.

- execute consecutive rounds without stopping between every round
- only pause when a round finishes, a blocker appears, or the user changes the
  goal
- still re-read the plan at the start of each new round

### 2. Interruption Mode

Use when the user wants a tighter control loop.

- stop after every round, or even after a sub-step inside a round when the user
  asks for finer granularity
- re-check the plan and user direction before resuming
- useful when the operator wants to inspect progress between blocks, fixes, or
  validation transitions

If the user says to "hang up after each round" or to "stop after a smaller
sub-step", treat that as interruption mode. If the user says to continue until
further notice, use continuous mode.

## Round Contract

Every round must satisfy this order:

1. Read:
   - `AGENTS.md`
   - `docs/README.md`
   - `docs/governance/repository-governance.md`
   - the active plan file under `.agent-run/plan/` or another task-scoped plan
2. Re-state the current round objective from the plan before editing.
3. Execute one bounded round objective.
4. Update the plan with:
   - what changed
   - what completed
   - what remains next
5. Run repository closeout for the current round:
   - selector or other task-honest validation entrypoint
   - text / governance / skill / registry checks as appropriate
   - `git diff --check`
6. If tracked files changed:
   - append `docs/testing/agent-update-log.csv`
   - commit locally
7. Re-read the updated plan before starting the next round.

## Required Behaviors

### Plan Reawakening

At the start of every round:

- open the current plan file again even if it was open in a previous turn
- treat the plan as the memory anchor, not the chat transcript
- verify that the next step in the plan still matches repository reality

### Plan Update

At the end of every round:

- add a concise result section to the active plan
- record validation actually observed in that round
- record the next intended round objective
- mark abandoned or superseded sub-steps explicitly instead of silently
  forgetting them

### Commit Discipline

If the round changed tracked files:

- append `docs/testing/agent-update-log.csv` before commit
- commit locally in the same round
- do not push unless the user explicitly asked for push

If the round was read-only:

- do not fabricate a commit just to satisfy the pattern

## Closeout Routing

Use:

- `docs/agents/agent-closeout.md`
- `docs/governance/agent-update-log.md`
- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`

The exact validation depends on the change surface, but the round must still
end with an honest closeout sweep.

## Guardrails

- Do not let multiple unrelated goals accumulate inside one round just to save
  commits.
- Do not start the next round before the previous round's plan update is
  written.
- Do not skip `agent-update-log.csv` for repository-changing rounds.
- Do not push at round end unless the user explicitly requested push.
- Do not let `.agent-run/plan/` become stale lore; keep the active plan current
  enough that a future round can resume from it directly.

## Related Files

- `AGENTS.md`
- `docs/README.md`
- `docs/governance/repository-governance.md`
- `docs/agents/agent-closeout.md`
- `docs/governance/agent-update-log.md`
- `docs/agents/local-agent-workspace.md`
- `skills/validation-selection/SKILL.md`
