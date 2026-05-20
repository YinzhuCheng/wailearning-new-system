# AGENTS — CourseEval Agent Startup Contract

## Purpose

This file is the **startup contract and task router** for coding agents working
in this repository. Read it before editing code, docs, tests, scripts, or
repository structure.

Use this file to answer:

- what must be true before you start;
- which docs or skills to open next;
- which boundaries remain high-risk;
- where validation and CI entrypoints live.

For the full documentation hub, start at [`docs/README.md`](docs/README.md).
For repo-wide governance routing, use
[`skills/repository-normalization/SKILL.md`](skills/repository-normalization/SKILL.md)
plus the horizontal governance skills
[`skills/docs-governance/SKILL.md`](skills/docs-governance/SKILL.md),
[`skills/boundary-governance/SKILL.md`](skills/boundary-governance/SKILL.md),
and
[`skills/structure-governance/SKILL.md`](skills/structure-governance/SKILL.md).

## Governance model

CourseEval treats **code as documentation** and **documentation as
governance**.

- Use code as the source of truth for current implementation behavior.
- Use committed docs, skills, and scripts for durable rules and repeated
  workflows.
- Use [`docs/governance/repository-governance.md`](docs/governance/repository-governance.md)
  for the full repository governance model.

## Non-negotiable operating rules

1. Use [`docs/README.md`](docs/README.md) as the task-scoped reading gate
   before editing.
2. Use the canonical backend import root
   `apps.backend.courseeval_backend`; keep package-boundary work aligned with
   [`docs/architecture/REPOSITORY_STRUCTURE.md`](docs/architecture/REPOSITORY_STRUCTURE.md).
3. Use backend authorization as the real permission boundary. Frontend hiding
   does not replace router or domain enforcement.
4. Use UTF-8-safe editing practices on Windows PowerShell; start with
   [`docs/contributing/ENCODING_AND_MOJIBAKE_SAFETY.md`](docs/contributing/ENCODING_AND_MOJIBAKE_SAFETY.md).
   If the current shell is Windows PowerShell, use
   `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops/scripts/windows/invoke-safe-text-command.ps1`
   as the default repository entrypoint before inspection/editing. Treat
   Windows PowerShell as a launcher, not as the primary surface for complex
   repository edits. Use the detailed wrappers and safe-text workflow in
   [`docs/agents/agent-startup-routing.md`](docs/agents/agent-startup-routing.md)
   and
   [`docs/contributing/ENCODING_AND_MOJIBAKE_SAFETY.md`](docs/contributing/ENCODING_AND_MOJIBAKE_SAFETY.md).
5. Use `.agent-run/` for local-only logs, private paths, and machine-specific
   continuation notes; keep durable repository context in committed docs. See
   [`docs/agents/local-agent-workspace.md`](docs/agents/local-agent-workspace.md).
   Use `.agent-run/plan/` for local private plan files and remove a plan file
   after the plan is fully executed or superseded. Keep screenshot and
   handoff details in their scoped docs instead of expanding this root file.
   See [`docs/agents/agent-playbook.md`](docs/agents/agent-playbook.md),
   [`docs/agents/agent-closeout.md`](docs/agents/agent-closeout.md), and
   [`docs/handoffs/README.md`](docs/handoffs/README.md).
6. Use the pitfall search before classifying local failures:
   `python ops/scripts/dev/search_pitfalls.py "<symptom>"`.
7. Use the diff-based validation selector before broad manual test selection:
   `python ops/scripts/dev/select_validation_targets.py --worktree`.
8. At the end of every round, clean local reproducible artifacts under
   `C:\Users\bloom\wailearning\.agent-run` and other safe cache locations with
   `python ops/scripts/dev/clean_local_artifacts.py`.
9. Before every repository-changing commit, append the round to
   `docs/testing/agent-update-log.csv` under the rules in
   [`docs/governance/agent-update-log.md`](docs/governance/agent-update-log.md).
   Treat this as a required closeout step, not an optional documentation extra.
10. After completing a repeated or failure-prone workflow, explicitly decide
   whether it should become a committed script or repo-local skill.
   Prefer scripts for stable executable workflows and skills for routing or
   multi-step agent procedure; do not leave frequently reused workflows as
   ad hoc terminal lore.
11. Interpret `round`, `iteration`, `batch`, `attack`, and similar execution
    units by the most specific active contract first:
    - if the user explicitly defines the unit, follow the user;
    - else if a task-scoped doc or repo-local skill defines the unit, follow
      that doc or skill;
    - else treat one action unit as one round by default.
    Do not silently collapse a multi-attack contract into a single fix/commit
    turn when the active skill or handoff defines a larger repository round.

High-risk hard boundaries that stay explicit:

- Do not weaken `/api/e2e/dev/*` exposure gates without tracing the current E2E
  contract in
  [`docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`](docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md)
  and
  [`docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md`](docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md).

## Startup workflow

Use this order:

1. Read this file.
2. Read [`docs/README.md`](docs/README.md).
3. Read [`docs/governance/repository-governance.md`](docs/governance/repository-governance.md).
4. Then follow the detailed startup routing in
   [`docs/agents/agent-startup-routing.md`](docs/agents/agent-startup-routing.md).

Detailed operational defaults, safe-text wrappers, tracing workflow, and
documentation-maintenance triggers live in:

- [`docs/agents/agent-startup-routing.md`](docs/agents/agent-startup-routing.md)
- [`docs/agents/agent-playbook.md`](docs/agents/agent-playbook.md)
- [`docs/agents/agent-closeout.md`](docs/agents/agent-closeout.md)

## Task routing

Use the detailed task-routing table in
[`docs/agents/agent-startup-routing.md`](docs/agents/agent-startup-routing.md).
Keep this root file as the routing contract, not the full task matrix.

## High-risk areas

Use the short high-risk list in
[`docs/agents/agent-startup-routing.md`](docs/agents/agent-startup-routing.md)
and the expanded explanations in
[`docs/architecture/HIGH_RISK_MODULES.md`](docs/architecture/HIGH_RISK_MODULES.md).

## Fast grep map

Use the quick grep jump table in
[`docs/agents/agent-startup-routing.md`](docs/agents/agent-startup-routing.md),
then expand with
[`docs/reference/CODE_MAP_AND_ENTRYPOINTS.md`](docs/reference/CODE_MAP_AND_ENTRYPOINTS.md).

## Failure triage entrypoint

Start every ambiguous local failure with
`python ops/scripts/dev/search_pitfalls.py "<error text or symptom>"`, then
follow the detailed triage routing in
[`docs/agents/agent-startup-routing.md`](docs/agents/agent-startup-routing.md).

## Validation entrypoint

Use change-scoped validation by default unless the user explicitly asks for
full-suite, release-quality, or zero-skip validation. Start with
`python ops/scripts/dev/select_validation_targets.py --worktree`, then follow
the strict/guided workflow in
[`docs/agents/agent-startup-routing.md`](docs/agents/agent-startup-routing.md)
plus
[`docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`](docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md).
Use
[`docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`](docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md)
when the task needs release-grade, full-suite, or zero-skip evidence.

## CI entrypoints

Use the detailed CI entrypoint references in
[`docs/agents/agent-startup-routing.md`](docs/agents/agent-startup-routing.md)
and the current scope rules in
[`docs/testing/CI_AND_VALIDATION.md`](docs/testing/CI_AND_VALIDATION.md).
