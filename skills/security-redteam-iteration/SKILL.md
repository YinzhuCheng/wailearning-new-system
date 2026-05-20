---
name: security-redteam-iteration
description: Use this when continuing CourseEval iterative red-team hardening rounds: selecting dense security tests, planning four parallel attacks with at least one E2E/browser-backed attack, fixing discovered bugs, updating docs and CSV ledgers, recording pitfalls, running scoped validation, and committing without push.
---

# Security Red-Team Iteration

## Purpose

Run one complete CourseEval hardening iteration: choose high-value risk points,
add dense tests, let tests expose bugs, fix narrowly, update docs and ledgers, run
change-scoped validation, and commit locally.

## When to Use

Use when the user asks to continue a hardening round, add about 10 high-difficulty
security/robustness tests, include E2E, red-team a surface, or follow the
previous "test, fix, docs, ledger, commit without push" workflow.

## Round Contract

This skill must follow the repository startup contract in `AGENTS.md` and the
task-scoped reading gates it routes to before editing code, tests, docs, or
validation ledgers.

Default red-team operating contract for this repository:

1. One red-team attack attempt has a default wall-clock budget of `5` minutes.
2. If an attack reveals a real product bug, fix that bug in the same attack
   turn before moving on.
3. After an immediate bug fix, do not run broad regression by default. Record
   the observed attack result honestly and continue the attack campaign unless
   the user explicitly asks for regression or the next step is otherwise
   blocked.
4. Run attacks in batches of `4`, planned as one parallel batch.
5. After every `4` attacks, stop and do one concentrated hardening pass that
   addresses the shared root causes or nearby latent weaknesses exposed by
   those attacks. The goal is not only to cover the exact exploited surface,
   but to prevent closely related attacks from succeeding again through the
   same underlying flaw class.
6. Define `4` red-team attacks plus `1` concentrated hardening pass as one
   repository round.
7. After each repository round, summarize:
   - which attacks succeeded or were blocked;
   - which bugs were fixed immediately;
   - which deeper structural weaknesses were found;
   - what the concentrated hardening pass changed;
   - what should be attacked next round.

## Workflow

1. Preflight: read `AGENTS.md`, `docs/README.md`,
   `docs/testing/README.md`, `docs/testing/TEST_SUITE_MAP.md`,
   `docs/testing/TEST_EXECUTION_PITFALLS.md`, and feature-specific docs.
   Capture the starting commit hash for `agent-update-log.csv` and new pitfalls.
2. Before starting a repository round, declare the current attack count within
   the round (`1/4` through `4/4`) and keep each attack narrowly scoped enough
   to fit the default `5` minute budget unless the user explicitly overrides
   it.
3. Plan the four attacks as one batch before implementing them. That batch must
   contain at least one browser-backed E2E attack from `tests/e2e/web-school/`.
   Route through `skills/security-redteam-parallel-attacks/SKILL.md` and the
   helper script when the batch needs a durable slot plan instead of ad hoc
   attack selection.
4. Select risks from recent failures, current pitfalls/known issues, and
   current code. Prefer boundaries around role vs ownership, parent-code,
   course enrollment, class links, bulk APIs, status re-entry, dashboard
   aggregation, notification state, seed/dev APIs, and UI cache bypass.
5. Design a compact batch, usually 8-12 tests. Use pytest for dense API/data
   invariants and require at least 1 Playwright/browser-backed case when
   seed/login/localStorage or UI state adds value. One test may assert multiple
   related invariants.
6. Implement tests first. Accept red runs. Classify failures as product bug,
   test-contract bug, or harness/environment issue before editing product code.
7. Fix every confirmed product bug found by the current attack before moving to
   the next attack. Keep the immediate patch bounded to the surfaced behavior,
   then use the concentrated hardening pass after attack `4/4` to widen the fix
   where shared root causes justify it.
8. After an immediate attack fix, do not run broad regression by default. Run
   only the minimum validation needed to confirm the attack surface changed as
   intended, and record broader validation debt honestly.
9. Update docs whenever behavior, permissions, API contracts, validation flow,
   or agent workflow changes. Update pitfalls when a repeatable failure mode,
   timeout, tool trap, or harness issue occurs.
10. Append observed runs to `test-execution-runs.csv`, including failed,
   timed-out, blocked, and final passed runs. Add concise summary rows when
   useful. Append `agent-update-log.csv` once per repository-changing round.
11. Run selector-recommended static checks, targeted tests, targeted Playwright,
   and a broad suite when the selector or risk warrants it. Record high-cost
   full targets such as `full.pytest.postgres` honestly when deferred.
12. Use the post-attack concentrated hardening pass to attack the flaw class,
   not only the exact failing example. Expand guards, shared helpers,
   permission checks, or state-convergence rules when the first four attacks
   show a repeated pattern.
13. Before commit, scan changed files for private paths/artifacts, run CSV
   parse smoke, `git diff --check`, and enough validation to support the final
   claim.
14. Commit locally. Do not push unless the user explicitly asks.

## Script Helpers

Scripts live in `skills/security-redteam-iteration/scripts/`. They are helpers,
not replacements for judgment.

Use these from the repository root:

```powershell
python skills/security-redteam-iteration/scripts/suggest_next_ids.py
python skills/security-redteam-iteration/scripts/changed_text_files.py
python skills/security-redteam-iteration/scripts/csv_smoke.py
python skills/security-redteam-iteration/scripts/private_path_scan.py --staged
python skills/security-redteam-iteration/scripts/plan_parallel_attack_batch.py
```

Append CSV rows with:

```powershell
python skills/security-redteam-iteration/scripts/append_run_ledger.py --test-id security.api_regression --result passed --command "<observed command>" --summary "<observed summary>" --notes "<short notes>"
python skills/security-redteam-iteration/scripts/append_agent_update.py --source-commit <hash> --scope "<round scope>" --changed-files "<files>" --code true --tests true --docs true --pitfalls false --validation "<summary>" --notes "<notes>"
python skills/security-redteam-iteration/scripts/append_pitfall.py --heading "<Pitfall: ...>" --category playwright-startup --notes "<short notes>"
```

Run a bundled static validation profile with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File skills/security-redteam-iteration/scripts/validation_smoke.ps1
```

## Guardrails

- Record only observed command outcomes in run ledgers.
- Do not put real local paths, tokens, browser cache paths, or `.agent-run/`
  artifact paths into committed rows; use placeholders like `<repo>` and
  `<local-port>`.
- New pitfalls use the most recent committed hash at the time they are recorded.
- If a script appends rows, inspect the diff before commit.
- Scripts may classify and format mechanical data, but the agent decides risk
  selection, bug classification, repair scope, validation breadth, and next
  concerns.

## Related Skills

- `skills/permission-audit/SKILL.md`
- `skills/school-playwright-e2e/SKILL.md`
- `skills/security-redteam-parallel-attacks/SKILL.md`
- `skills/validation-selection/SKILL.md`
- `skills/validation-ledger-maintenance/SKILL.md`
- `skills/repository-normalization/SKILL.md`
