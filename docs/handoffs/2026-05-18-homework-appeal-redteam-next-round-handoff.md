# Homework-Appeal Red-Team Next-Round Handoff (2026-05-18)

## Purpose

Hand off the next red-team round on branch:

- `cursor/repository-normalization-schema-notifications`

This round narrowed one backend flaw class:

- `homework appeal` terminal states are now protected against stale teacher
  rewrites, matching the existing `score appeal` immutability policy.

The next agent should continue from that point instead of reopening the already
fixed terminal-rewrite bug.

## Required Reading Order

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/governance/repository-governance.md`
4. `skills/security-redteam-iteration/SKILL.md`
5. `skills/security-redteam-parallel-attacks/SKILL.md`
6. `docs/testing/REDTEAM_PARALLEL_ATTACKS.md`
7. `skills/school-playwright-e2e/SKILL.md` when using browser attacks
8. Re-read this handoff

## What This Round Proved

### Notification convergence already hardened

The prior round closed a real notification race:

- deleting a notification while `mark-read` was in flight could leave orphan
  `NotificationRead` rows in SQLite

Repair outcome:

- SQLite connections now enable `PRAGMA foreign_keys=ON`
- `notification_reads.notification_id` now cascades on delete
- the school notifications page now refreshes cleanly if the row disappears
  before detail fetch finishes

Observed proof already recorded in the validation ledger:

- targeted pytest for notification delete/read and delete/mark-all-read races
- targeted Playwright for notification detail/delete and mark-all-read/delete
  convergence

### Homework-appeal terminal rewrite bug was real

This round exposed and fixed a product inconsistency:

- `score appeals` already blocked stale teacher rewrites after terminal state
- `homework appeals` did not

Confirmed bug shape before repair:

- teacher resolves a homework appeal
- stale teacher request can later rewrite the same appeal to `rejected`

Repair outcome:

- `apps/backend/courseeval_backend/domains/appeal_notifications.py`
  - added `can_transition_homework_appeal_status`
- `apps/backend/courseeval_backend/api/routers/homework.py`
  - `respond_grade_appeal` now rejects stale terminal rewrites with `409`
  - exact replay of the same terminal status + teacher response remains
    idempotent

### New backend red-team coverage added

Changed test surface:

- `tests/backend/homework/test_homework_appeal_redteam.py`

Added / extended proof for:

1. terminal homework appeal cannot be rewritten by stale teacher request
2. concurrent acknowledge + resolve converges without duplicate notification
   rows
3. exact terminal replay stays stable
4. notification detail still reports the final terminal status consistently

Observed and passed:

- `.venv\Scripts\python.exe -m pytest tests/backend/homework/test_homework_appeal_redteam.py -k "terminal_homework_appeal_cannot_be_rewritten_by_stale_teacher_request" -q`
- `.venv\Scripts\python.exe -m pytest tests/backend/homework/test_homework_appeal_redteam.py -k "concurrent_homework_appeal_acknowledge_and_resolve_do_not_both_win or final_homework_appeal_replay_keeps_notification_projection_stable or notification_detail_for_homework_appeal_stays_consistent_after_terminal_transition or terminal_homework_appeal_cannot_be_rewritten_by_stale_teacher_request" -q`

## What Is Still Not Settled

The remaining uncomfortable surface is no longer backend terminal rewrite
immutability. It is browser-side stale-state handling around homework appeals.

### Highest-value next attack cluster

Focus the next repository round on **teacher stale-tab / reload / modal
convergence for homework appeals**.

Best candidate slots:

1. stale teacher tab tries to reject after another tab already resolved
   - expected result:
     - backend returns `409`
     - modal closes or refreshes cleanly
     - page re-renders the authoritative terminal state

2. stale teacher tab tries to resolve after another tab already rejected
   - same expectations as above

3. teacher `review` path vs teacher `appeal` path interleave
   - one tab uses review flow
   - another uses explicit appeal modal
   - final history, notification status, and teacher detail page must converge

4. reload / back-forward after terminal transition
   - detail page should not re-open a stale actionable appeal affordance
   - teacher response should remain authoritative after refresh

At least one of those should be browser-backed E2E in the next batch.

## Important Execution Note

`tests/e2e/web-school/e2e-scenario-resilience.spec.js` currently carries enough
historical text/encoding drift that it is a poor long-term host for more and
more homework-appeal cases.

The next agent should strongly consider:

- either cleaning the helper/text drift first,
- or extracting homework-appeal stale-tab coverage into a smaller dedicated
  Playwright spec instead of expanding this one further.

Do not treat the current resilience spec as a stable foundation without that
decision.

## Recommended Next Move

Do not reopen notification delete/read races first.

Do not reopen the fixed homework-appeal stale terminal rewrite on the backend
except as a regression check.

Start the next red-team round with:

- one narrow browser stale-tab homework-appeal attack,
- then cluster the other three slots around homework-appeal teacher-state
  convergence.
