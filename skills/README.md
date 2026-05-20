# Repo-Local Skills

## Purpose

This file is the durable index and layering guide for repo-local skills.

Use it when:

- deciding which skill should own a workflow;
- routing a task from broad governance into a specialized execution skill;
- updating `AGENTS.md` or `docs/README.md` without restating the full skill
  catalog there.

## Layering

Use skills from broad to narrow.

### 1. Top-level orchestrator

- [`repository-normalization/SKILL.md`](repository-normalization/SKILL.md)
  for repo-wide governance, layered agent-document routing, skill taxonomy,
  package/path drift, and broad governance routing.

### 2. Horizontal governance skills

- [`docs-governance/SKILL.md`](docs-governance/SKILL.md)
- [`boundary-governance/SKILL.md`](boundary-governance/SKILL.md)
- [`structure-governance/SKILL.md`](structure-governance/SKILL.md)

Use these to scope the problem before dropping into a specialized domain.
`docs-governance` also owns the layered agent-document-system discipline:
entrypoint layering, de-duplication without information loss, and deciding
whether a repeated workflow belongs in docs, a skill, or a script.

### 3. Specialized audit and execution skills

- [`api-surface-audit/SKILL.md`](api-surface-audit/SKILL.md)
- [`data-migration-audit/SKILL.md`](data-migration-audit/SKILL.md)
- [`deployment-governance/SKILL.md`](deployment-governance/SKILL.md)
- [`frontend-backend-contract-audit/SKILL.md`](frontend-backend-contract-audit/SKILL.md)
- [`interruptible-full-validation-rounds/SKILL.md`](interruptible-full-validation-rounds/SKILL.md)
- [`local-test-triage/SKILL.md`](local-test-triage/SKILL.md)
- [`permission-audit/SKILL.md`](permission-audit/SKILL.md)
- [`parallel-validation-orchestration/SKILL.md`](parallel-validation-orchestration/SKILL.md)
- [`postgres-release-validation/SKILL.md`](postgres-release-validation/SKILL.md)
- [`roster-identity-repair-playbook/SKILL.md`](roster-identity-repair-playbook/SKILL.md)
- [`round-plan-discipline/SKILL.md`](round-plan-discipline/SKILL.md)
- [`school-playwright-e2e/SKILL.md`](school-playwright-e2e/SKILL.md)
- [`security-redteam-parallel-attacks/SKILL.md`](security-redteam-parallel-attacks/SKILL.md)
- [`security-redteam-iteration/SKILL.md`](security-redteam-iteration/SKILL.md)
- [`seed-surface-hardening/SKILL.md`](seed-surface-hardening/SKILL.md)
- [`utf8-safe-editing/SKILL.md`](utf8-safe-editing/SKILL.md)

### 4. Validation and evidence skills

- [`validation-selection/SKILL.md`](validation-selection/SKILL.md)
- [`validation-ledger-maintenance/SKILL.md`](validation-ledger-maintenance/SKILL.md)

## Selection Rules

1. Start with the broadest skill that clarifies task scope.
2. Route into the narrowest specialized skill that owns the risky behavior.
3. Use validation skills for target choice, registry changes, and durable test
   evidence.
4. Prefer the richer, more executable skill when two skills overlap.
5. Shrink or remove duplicate guidance instead of keeping multiple competing
   versions of the same workflow.
6. Use `parallel-validation-orchestration` when the main problem is no longer
   “which test should I run?” but “how do I supervise many shards with
   automatic refill, progress files, and optional PostgreSQL isolation?”
7. Use `round-plan-discipline` when the user requires explicit multi-round
   execution with plan re-reading, round-end plan updates, AGENTS closeout,
   and local commit-without-push behavior every round. The skill supports both
   continuous execution and user-requested interruption mode with finer-grained
   pause points.
8. Use `interruptible-full-validation-rounds` when the user wants a full
   validation campaign executed block-by-block, with one block launched per
   round, communication stopped after launch, and reconnect decisions driven by
   durable WAI-VALID artifacts rather than memory. This skill must in turn
   route through `round-plan-discipline` and require plans that explicitly name
   `parallel-validation-orchestration`.

## Related Files

- `AGENTS.md`
- `docs/README.md`
- `docs/governance/repository-governance.md`
