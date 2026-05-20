---
name: security-redteam-parallel-attacks
description: Use this when a CourseEval red-team repository round must be planned or executed as four parallel attacks with at least one browser-backed E2E attack, and the agent needs a durable attack-batch plan instead of ad hoc attack selection.
---

# Security Red-Team Parallel Attacks

## Purpose

Plan one CourseEval red-team attack batch under the repository's current round
contract when the batch must contain exactly four attacks executed in parallel
planning terms, with at least one browser-backed E2E attack.

This skill does not replace `security-redteam-iteration`; it narrows the attack
selection algorithm used inside that larger round workflow.

## When To Use

Use this skill when:

- a red-team round must be decomposed into four attack slots;
- the user, handoff, or skill contract explicitly requires parallel attacks;
- the batch must guarantee at least one Playwright/browser-backed attack;
- the next agent needs a durable attack plan for thin/fragile surfaces before
  starting implementation.

## Attack-Batch Contract

1. One repository round contains exactly `4` attacks plus `1` concentrated
   repair pass.
2. Treat the `4` attacks as a parallel batch-planning problem even when the
   implementation/fix work still proceeds serially.
3. The batch must include at least `1` browser-backed E2E attack from
   `tests/e2e/web-school/`.
4. The remaining attacks should prefer the cheapest lane that can prove the
   risk: backend pytest, behavior pytest, backend E2E-dev TestClient, then
   Playwright when browser state is intrinsic to the hypothesis.
5. Every attack slot needs:
   - target surface;
   - risk hypothesis;
   - primary test lane;
   - expected proof artifact (pytest file/case, Playwright spec/grep, or API route).
6. Do not run four unrelated broad regressions. The four attacks should cluster
   around one or two nearby flaw classes so the later concentrated repair can
   widen the fix coherently.

## Workflow

1. Read `AGENTS.md`, `docs/README.md`, and the active red-team handoff.
2. Read `skills/security-redteam-iteration/SKILL.md`.
3. Read `skills/school-playwright-e2e/SKILL.md` when choosing the required E2E
   slot.
4. Generate a four-slot plan with:
   - `attack_id` (`1/4`..`4/4`)
   - `surface`
   - `risk`
   - `lane`
   - `test_anchor`
   - `why_this_slot_now`
5. Ensure at least one slot uses `lane = school-playwright-e2e`.
6. Prefer existing maintained suites before inventing a new spec file.
7. If no maintained E2E suite is close enough, document that a new targeted
   Playwright case must be added and list the nearest existing helper/spec.
8. Hand the resulting plan back to `security-redteam-iteration` for actual
   test-first execution, immediate bug fixes, ledgers, and closeout.

## Script Helper

Use the repo-local helper to emit a durable batch template:

```powershell
python skills/security-redteam-iteration/scripts/plan_parallel_attack_batch.py
python skills/security-redteam-iteration/scripts/plan_parallel_attack_batch.py --surface notifications --surface score_appeals
```

The script only builds a candidate batch; the agent still decides the final
attack ordering and whether an existing suite already proves the same risk.

## Related Files

- `skills/security-redteam-iteration/SKILL.md`
- `skills/school-playwright-e2e/SKILL.md`
- `docs/handoffs/README.md`
- `docs/testing/TEST_SUITE_MAP.md`
- `tests/TEST_SELECTION_TARGETS.json`
