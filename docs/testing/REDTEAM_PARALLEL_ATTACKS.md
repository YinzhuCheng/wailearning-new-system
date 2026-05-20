# Red-Team Parallel Attack Planning

## Purpose

This document defines the repository's current red-team attack-batch planning
algorithm when a round is governed by the `security-redteam-iteration` skill.

It exists so future agents do not silently compress a batch contract into one
narrow fix, and so the required E2E slot stays explicit in durable repository
rules instead of chat-only lore.

## Current Batch Algorithm

When the active contract is the repo-local red-team round workflow:

1. One repository round means `4 attacks + 1 concentrated repair`.
2. The four attacks must be planned as a parallel batch, even if code changes
   and bug fixes are executed serially afterward.
3. The batch must include at least one browser-backed E2E attack from
   `tests/e2e/web-school/`.
4. The other attacks should use the cheapest lane that can prove the same risk:
   backend pytest, behavior pytest, backend E2E-dev TestClient, then
   Playwright when browser state is essential.
5. The four attacks should cluster around one or two nearby flaw classes so the
   concentrated repair can widen one coherent fix instead of becoming four
   unrelated patches.

## Expected Attack-Slot Fields

Each of the four attack slots should state:

- `attack_id`
- `surface`
- `risk hypothesis`
- `primary lane`
- `test anchor`
- `why this slot belongs in the current batch`

## Entry Points

- Main round workflow: `skills/security-redteam-iteration/SKILL.md`
- Parallel batch planner: `skills/security-redteam-parallel-attacks/SKILL.md`
- School E2E execution: `skills/school-playwright-e2e/SKILL.md`
- Helper script:
  `skills/security-redteam-iteration/scripts/plan_parallel_attack_batch.py`

## Validation Note

This document changes planning rules only. It does not by itself prove any
product surface. Actual attack results still belong in targeted tests, ledgers,
handovers, and repository-changing commits.
