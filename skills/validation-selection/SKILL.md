---
name: validation-selection
description: Use this when choosing, running, or documenting CourseEval validation for a code, test, documentation, ops, or governance change. Triggers include test planning, selector output, validation target registry edits, final handoff validation summaries, and avoiding over-broad or under-scoped test claims.
---

# Validation Selection

## Purpose

Choose validation that is proportional to the change while staying honest about
coverage, skipped targets, blockers, and broad/full recommendations.

This skill now treats the focused testing validation docs as the primary
document layer for selector/runner behavior, rather than sending every agent
through the larger `DEVELOPMENT_AND_TESTING.md` handbook first.

## Workflow

1. Read `AGENTS.md`, `docs/README.md`, and the task-scoped docs.
2. Use the focused validation docs first:
   - `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md` for selector, runner,
     profile, artifact, and evidence rules
   - `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md` when the change or
     claim is `full suite`, `zero-skip`, `release-quality`, or otherwise
     environment-heavy
3. Inspect the diff or intended paths:
   `python ops/scripts/dev/select_validation_targets.py --worktree`
4. Use `--json` when you need exact target IDs, `non_full_validation.status`,
   unmatched paths, or `requires_review_reason` values.
5. Run recommended static and targeted targets directly, or use:
   `python ops/scripts/dev/run_validation_profile.py selector-recommended --worktree --max-risk targeted`
6. If the selector reports `needs_review`, decide and document whether to run
   the review target now.
7. If the selector reports `not_sufficient`, do not call validation complete
   until the full/broad target is run or explicitly deferred with a reason.
8. Record only real executed results in durable docs; selector planning output
   alone is not a test ledger entry.
9. When the task is no longer just "which target should I run?" but also
   "how should I expand this into light/medium/heavy regression blocks with
   different concurrency?", route into
   `skills/parallel-validation-orchestration/SKILL.md`.

## Document Routing Rules

- Use `VALIDATION_WORKFLOW_AND_TOOLS.md` as the canonical source for:
  - `strict` / `guided` selector workflow
  - selector, target runner, and profile runner mechanics
  - artifact/evidence interpretation
  - local SQLite guardrail
- Use `FULL_VALIDATION_ENVIRONMENT_POLICY.md` as the canonical source for:
  - PostgreSQL zero-skip expectations
  - RAR / browser dependency expectations
  - release-grade and full-suite environment policy
- Use `CI_AND_VALIDATION.md` for cloud/local scope interpretation, not for the
  local selector mechanics themselves.

## Commands

```powershell
python ops/scripts/dev/select_validation_targets.py --worktree
python ops/scripts/dev/select_validation_targets.py --worktree --json
python ops/scripts/dev/run_validation_target.py <target-id> --timeout-seconds 120
python ops/scripts/dev/run_validation_profile.py selector-recommended --worktree --max-risk targeted
python ops/scripts/dev/lint_validation_registry.py
```

## Guardrails

- Treat the selector as advisory, not as a substitute for engineering judgment.
- Add registry mappings when a repeated change path falls through to an
  imprecise fallback.
- Keep broad/full recommendations visible in the final answer or handoff even
  when they are deferred.
- Do not claim product coverage from static checks alone.
- Keep `.agent-run/` run artifacts local and uncommitted.
- Prefer the focused validation docs over repeating large chunks of selector or
  environment policy in handoffs and nearby docs.
- Do not treat `light` / `medium` / `heavy` regression expansion as the
  selector's responsibility alone; selector chooses targets, while the
  orchestration layer may widen them into block-aware regression runs.
- When the user explicitly asks for a regression intensity, preserve the
  selector's target choice as the seed set and let the orchestration layer
  expand from there instead of hand-widening the target list ad hoc.

## Related Files

- `tests/TEST_SELECTION_TARGETS.json`
- `tests/backend/manual/test_validation_selector.py`
- `ops/scripts/dev/select_validation_targets.py`
- `ops/scripts/dev/run_validation_target.py`
- `ops/scripts/dev/run_validation_profile.py`
- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `docs/testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md`
- `docs/testing/CI_AND_VALIDATION.md`
- `docs/testing/README.md`
