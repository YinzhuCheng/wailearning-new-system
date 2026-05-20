# 2026-05-19 Next Red-Team Handoff: Notification Cache And Cross-Tab Drift

## Purpose

This handoff prepares the next repository round after the homework-appeal stale
write repair and the concurrent Playwright red-team workflow hardening.

The next round should not reopen the already-fixed homework-appeal terminal
rewrite bug unless a regression signal appears. The highest-value remaining
surface is **notification / selected-course / cross-tab cache drift** under
concurrent browser contexts.

## Branch And Baseline

- Branch: `cursor/repository-normalization-schema-notifications`
- HEAD after the latest red-team workflow hardening commit:
  `d3af53a0b24fe201b189e64d81d1559086f8cef3`

## Required Reading Order

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/governance/repository-governance.md`
4. `skills/security-redteam-iteration/SKILL.md`
5. `skills/security-redteam-parallel-attacks/SKILL.md`
6. `docs/testing/REDTEAM_PARALLEL_ATTACKS.md`
7. `skills/school-playwright-e2e/SKILL.md`
8. `skills/parallel-validation-orchestration/SKILL.md`
9. Re-read this handoff

## What The Last Round Changed

### Product repair already complete

The previous round fixed a real backend bug in homework appeals:

- stale teacher terminal requests could overwrite a finalized homework appeal
- `respond_grade_appeal` and `acknowledge_grade_appeal` now use compare-and-swap
  style state transitions
- targeted backend proof and the dedicated stale-tab Playwright suite passed

Relevant files:

- `apps/backend/courseeval_backend/api/routers/homework.py`
- `tests/backend/homework/test_homework_appeal_redteam.py`
- `tests/e2e/web-school/e2e-homework-appeal-stale-tabs.spec.js`

### Concurrent red-team workflow hardening already complete

The latest round also fixed real infrastructure blockers that prevented agents
from launching the repo's concurrent browser red-team flow reliably on this
machine:

1. `ops/scripts/dev/wai_valid_supervisor.py`
   - supports `WAI_VALID_STATE_DIR`
   - supports `WAI_VALID_LOG_ROOT`
2. `tests/e2e/web-school/scenario-cache.cjs`
   - centralizes Playwright scenario-cache writes with fallback paths
3. `apps/web/school/scripts/playwright-external-runner.cjs`
   - keeps per-shard API/UI/sqlite isolation
   - now isolates Playwright output directories per shard
   - writes shard output under the OS temp directory instead of one shared
     repository `test-results` path

Observed proof:

- first concurrent WAI-VALID auth/session sample block failed before product
  assertions because concurrent Playwright shards collided on shared write
  targets
- after the workflow isolation fixes, the same 4-sample concurrent block passed
  `4/4`

## What The Next Round Should Target

### Primary flaw class

Attack **browser-visible cache and state drift**, not backend transition
immutability.

The most valuable cluster is:

- selected-course cache poisoning
- same-context / same-storage login state drift
- notification badge convergence under second-tab auth churn
- cross-tab session bootstrap rollback

This cluster is uncomfortable because the repository has historical evidence
that:

- stale or empty-token failures can perturb active browser state
- selected-course state can survive longer than the authoritative course switch
  context
- notification badge convergence is vulnerable to cache and tab-local drift
  even when the API contract is correct

### Default 4-slot next round

Use this batch shape first:

1. `auth/session rollback`
   - sample anchor:
     `tests/e2e/web-school/e2e-redteam-auth-login-me-failure-rollback.spec.js`
   - risk:
     one context's failed bootstrap or `401` cleanup clears another valid
     session

2. `same-context notification tabs`
   - sample anchor:
     `tests/e2e/web-school/e2e-redteam-notification-same-context-tabs.spec.js`
   - risk:
     second-tab login churn or local token changes break first-tab badge/auth
     convergence

3. `selected_course cache poison`
   - sample anchor:
     `tests/e2e/web-school/e2e-redteam-selected-course-cache-poison-badge.spec.js`
   - risk:
     forged or stale selected-course cache drives badge or page state off the
     authoritative course context

4. `parallel login context isolation`
   - sample anchor:
     `tests/e2e/web-school/e2e-redteam-parallel-login-context-isolation.spec.js`
   - risk:
     multiple seeded roles logging in at once bleed state across contexts or
     leave partial shell/bootstrap state

If these four stay green, the next escalation should stay in the same family
instead of jumping back to unrelated surfaces:

- add a new one-file sample for notification deep-link + selected-course
  mismatch recovery
- or add a new one-file sample for auth failure cleanup not clearing foreign
  `localStorage` state

## Execution Rule For The Next Agent

Do **not** start from serial `node scripts/playwright-external-runner.cjs ...`
one spec at a time as the primary workflow.

Start from the concurrent sample block:

```powershell
$env:WAI_VALID_STATE_DIR='C:\Users\bloom\wailearning\.agent-run\validation-daemon-next'
$env:WAI_VALID_LOG_ROOT='C:\Users\bloom\wailearning\.agent-run\logs-next'
.\.venv\Scripts\python.exe ops\scripts\dev\wai_valid_supervisor.py `
  --run-id e2e-redteam-next-<date> `
  --replace-run-dir `
  --block self-organized-e2e-redteam `
  --concurrency 10 `
  --regression-mode light `
  --playwright-shard-timeout-seconds 1200 `
  --sample tests/e2e/web-school/e2e-redteam-auth-login-me-failure-rollback.spec.js `
  --sample tests/e2e/web-school/e2e-redteam-notification-same-context-tabs.spec.js `
  --sample tests/e2e/web-school/e2e-redteam-selected-course-cache-poison-badge.spec.js `
  --sample tests/e2e/web-school/e2e-redteam-parallel-login-context-isolation.spec.js
```

Why the env override is still written here:

- the supervisor now supports custom state/log roots
- this machine previously had `.agent-run/validation-daemon` permission/lock
  friction
- the override avoids rediscovering that same local blocker

## Interpretation Rules

If the block fails:

1. first classify whether the failure is:
   - product behavior
   - test contract drift
   - concurrent Playwright harness regression
2. do not assume a product hole if the first symptom is:
   - shared output-path write failure
   - cache-file `EPERM`
   - startup path collision
3. preserve the WAI-VALID run artifacts before changing code:
   - `progress.json`
   - `results.jsonl`
   - worker `*.log`
   - worker `*.err.log`

## Secondary Follow-Up Surface

If the notification/cache cluster stays green, the next-best follow-up is:

- `parent portal + enrollment drift + stale binding/session cleanup`

Do this only after the primary cluster, because the auth/session/cache cluster
is now the more direct continuation of the latest evidence.

## Relevant Files

- `apps/backend/courseeval_backend/api/routers/homework.py`
- `tests/backend/homework/test_homework_appeal_redteam.py`
- `tests/e2e/web-school/e2e-homework-appeal-stale-tabs.spec.js`
- `tests/e2e/web-school/e2e-redteam-auth-login-me-failure-rollback.spec.js`
- `tests/e2e/web-school/e2e-redteam-notification-same-context-tabs.spec.js`
- `tests/e2e/web-school/e2e-redteam-selected-course-cache-poison-badge.spec.js`
- `tests/e2e/web-school/e2e-redteam-parallel-login-context-isolation.spec.js`
- `tests/e2e/web-school/scenario-cache.cjs`
- `tests/e2e/web-school/global-setup.cjs`
- `tests/e2e/web-school/fixtures.cjs`
- `apps/web/school/scripts/playwright-external-runner.cjs`
- `ops/scripts/dev/wai_valid_supervisor.py`
