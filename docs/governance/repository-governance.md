# Repository Governance

## Purpose

This document holds the durable governance model for CourseEval. It explains
how code, docs, skills, validation, and repository structure interact so that
future agents can make consistent decisions without treating the root
`AGENTS.md` file as a full handbook.

Use this document when:

- refining repository-wide rules;
- deciding whether a repeated workflow belongs in docs, scripts, or skills;
- classifying a governance concern as active, accepted, or historical;
- updating entrypoint documentation such as `AGENTS.md`, `docs/README.md`, or
  skill indexes.

## Governance Model

CourseEval treats **code as documentation** and **documentation as
governance**.

- **Code as documentation:** implementation is normally the source of truth.
  When documentation conflicts with code, update the documentation to match the
  current implementation unless the task explicitly asks for a product fix.
  If the documentation records a more coherent intended rule that should now be
  enforced, update code and tests in the same change and keep the docs explicit
  about current versus intended behavior.
- **Documentation as governance:** durable repository rules, operational
  workflows, and repeated agent procedures belong in committed documentation.
  When a workflow is common, fragile, or repeatedly rediscovered, prefer an
  executable script or repo-local skill over prose alone.

## Repository-Normalization Principles

Use these principles when cleaning up naming, layout, path drift, or doc
contracts:

1. Keep the active entrypoint docs short and routable. Put detailed procedures
   in topic docs or repo-local skills.
2. Keep the more precise source of truth. If a detailed skill or script exists,
   link to it instead of recreating the same instructions in multiple docs.
3. Preserve durable structure. Root files, package roots, and deployment
   entrypoints are repository contracts, not opportunistic cleanup targets.
4. Classify historical drift instead of carrying it forever. Resolved cleanup
   or naming issues should move to reports or commit history rather than remain
   active rules.
5. Close the loop in committed docs. A repository-normalization change is not
   complete until the current contract, routing, and validation entrypoints are
   updated together.

## Where Governance Lives

Use the most specific durable location first:

| Topic | Primary location |
|-------|------------------|
| Agent startup contract and routing | `AGENTS.md` |
| Agent startup matrix, high-risk routing, and grep discovery | `docs/agents/agent-startup-routing.md` |
| Agent execution entrypoints | `docs/agents/agent-execution-entrypoints.md` |
| Agent workflows and defaults | `docs/agents/agent-playbook.md` |
| Agent closeout procedure | `docs/agents/agent-closeout.md` |
| Local workspace rules | `docs/agents/local-agent-workspace.md` |
| Repository structure and path rules | `docs/architecture/REPOSITORY_STRUCTURE.md` |
| High-risk module explanations | `docs/architecture/HIGH_RISK_MODULES.md` |
| Validation flow and CI | `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`, `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`, `docs/testing/CI_AND_VALIDATION.md` |
| Pitfall recording and triage | `docs/testing/TEST_EXECUTION_PITFALLS.md`, `skills/local-test-triage/SKILL.md` |
| Validation registry and ledgers | `skills/validation-selection/SKILL.md`, `skills/validation-ledger-maintenance/SKILL.md`, `docs/testing/README.md` |
| Agent update log policy | `docs/governance/agent-update-log.md` |
| Skill taxonomy and index | `skills/README.md` |

## When To Encode A Workflow

Prefer a committed script or skill when a workflow is:

- repeated across multiple tasks or agents;
- easy to misremember or easy to do inconsistently;
- dependent on command ordering, path conventions, or validation semantics;
- expensive to rediscover from raw code every time.

Use:

- **docs** for durable policy and routing;
- **skills** for executable multi-step agent workflows;
- **scripts** for repeatable machine-enforced checks or append helpers;
- **reports** only for dated evidence that still needs to remain searchable.

For the agent-facing doc system specifically, prefer layered text-first routing
when it is clearer than a script-first control surface:

- keep `AGENTS.md` short and contractual;
- keep hub/index routing in `docs/README.md`;
- keep startup routing, execution entrypoints, playbook defaults, closeout, and
  local workspace rules in separate `docs/agents/` topic docs;
- remove repeated prose from broader entrypoints once a narrower authoritative
  layer exists.

## Historical Drift Policy

Do not keep solved cleanup work as an active rule.

Examples of what should usually leave active governance once resolved:

- historical naming cleanups that no longer drive current behavior;
- one-time root-directory housekeeping campaigns;
- retired local cleanup instructions superseded by current workspace rules;
- old migration reminders after the repository contract and validation rules are
  already in place.

If older names, paths, or practices remain relevant, document them only when
they still affect:

- security or production exposure;
- data integrity or migration safety;
- validation correctness;
- compatibility with append-only historical ledgers.

## Related Files

- `AGENTS.md`
- `docs/README.md`
- `docs/agents/agent-startup-routing.md`
- `docs/agents/agent-execution-entrypoints.md`
- `docs/agents/agent-playbook.md`
- `docs/agents/agent-closeout.md`
- `docs/agents/local-agent-workspace.md`
- `docs/architecture/REPOSITORY_STRUCTURE.md`
- `docs/architecture/HIGH_RISK_MODULES.md`
- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`
- `docs/testing/CI_AND_VALIDATION.md`
- `docs/testing/TEST_EXECUTION_PITFALLS.md`
- `docs/governance/agent-update-log.md`
- `skills/README.md`
