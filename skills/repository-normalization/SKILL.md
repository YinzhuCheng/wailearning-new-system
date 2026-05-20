---
name: repository-normalization
description: Top-level CourseEval governance orchestrator for repository normalization, layered agent-document routing, skill taxonomy, docs-as-governance, package/path/name drift, and deciding when to route into docs-governance, boundary-governance, structure-governance, validation-selection, validation-ledger-maintenance, or specialized audit skills.
---

# Repository Normalization

## Purpose

Coordinate CourseEval repository governance without becoming a duplicate of
specialized skills. Use this as the top-level entrypoint for code-as-docs,
docs-as-governance, package/name drift, skill taxonomy, layered
agent-document design, and handoff preparation.

This skill should optimize for one outcome first: let future agents reach the
correct source of truth quickly, with the fewest wrong turns, while preserving
durable repository memory.

## Skill Layers

1. Top-level orchestrator: this skill.
2. Horizontal governance: `skills/docs-governance/SKILL.md`,
   `skills/boundary-governance/SKILL.md`, and
   `skills/structure-governance/SKILL.md`.
3. Specialized audit skills:
   - permissions: `skills/permission-audit/SKILL.md`;
   - API contracts: `skills/api-surface-audit/SKILL.md`;
   - frontend/backend request contracts:
     `skills/frontend-backend-contract-audit/SKILL.md`;
   - schema/bootstrap/data repair: `skills/data-migration-audit/SKILL.md`;
   - deployment/ops: `skills/deployment-governance/SKILL.md`;
   - seed/E2E dev surface: `skills/seed-surface-hardening/SKILL.md`;
   - Playwright: `skills/school-playwright-e2e/SKILL.md`;
   - PostgreSQL release gates: `skills/postgres-release-validation/SKILL.md`;
   - UTF-8 editing: `skills/utf8-safe-editing/SKILL.md`;
   - local failures: `skills/local-test-triage/SKILL.md`.
4. Validation and evidence:
   `skills/validation-selection/SKILL.md` and
   `skills/validation-ledger-maintenance/SKILL.md`.

## Workflow

1. Read `AGENTS.md`, `docs/README.md`, and task-scoped docs.
2. Check whether the task is really a layered agent-document or governance
   routing task, rather than a direct domain fix.
3. Decide whether this is a broad governance-routing task:
   - docs or process: use `docs-governance`;
   - module/import/ownership boundary: use `boundary-governance`;
   - root layout, moves, or directory hierarchy: use `structure-governance`.
4. Route any high-risk domain to the specialized skill instead of copying its
   rules here.
5. Search code and tests before trusting documentation claims.
6. Classify old names as historical records or active drift.
7. Update docs in the same change set as behavior, config, path, or service
   changes.
8. Prefer CSV/JSON/YAML for append-only structured ledgers; keep Markdown as
   the interpretation layer.
9. Prefer layered documentation before automation when the problem is primarily
   agent routing, structure, or durable explanation:
   - root contract in `AGENTS.md`
   - hub in `docs/README.md`
   - topic routing in `docs/agents/`
   - topic truth in the narrowest authoritative doc or skill
10. Remove redundancy before reducing detail. Shorter is only better when the
    same meaning remains easier to reach.
11. Add or update executable checks when a repeated rule can be automated, but
    do not force a script-first solution when a text-first routing layer is the
    clearer control surface.
12. Use `validation-selection` for target choice and
   `validation-ledger-maintenance` for durable evidence.

## Agent-Document Layering Rules

When the task touches `AGENTS.md`, `docs/README.md`, or `docs/agents/`, keep
the layers sharp:

1. `AGENTS.md`:
   - startup contract
   - non-negotiable rules
   - shortest high-signal routing surface
2. `docs/README.md`:
   - hub and reading index
   - cross-topic reading paths
3. `docs/agents/agent-startup-routing.md`:
   - startup workflow details
   - task-routing matrix
   - high-risk and grep discovery
4. `docs/agents/agent-execution-entrypoints.md`:
   - Windows safe entry
   - failure triage
   - validation
   - CI entrypoints
5. `docs/agents/agent-playbook.md`:
   - procedural defaults
   - tracing and feature-touch workflow
6. `docs/agents/agent-closeout.md`:
   - validation closeout
   - update-log
   - cleanup and workflow-promotion rules
7. `docs/agents/local-agent-workspace.md`:
   - `.agent-run/`
   - local plan and artifact rules

If a layer is getting long, split by function, not by arbitrary size.
Prefer moving whole responsibility clusters into a narrower doc over scattering
micro-sections across many files.

## Closeout Conditions

Before ending a repository-normalization sequence, make the state durable:

- classify each touched boundary as accepted, active follow-up, or explicitly
  deferred;
- sync `AGENTS.md`, `docs/README.md`, architecture/reference docs, the active
  handoff, and `docs/testing/agent-update-log.csv` when they are
  part of the task surface;
- record selector output and the static/runtime validation actually run;
- keep private planning notes, `.agent-run/`, `.pytest_cache/`, `.pytest_tmp/`,
  and other generated artifacts out of commits.

Treat `check_boundary_governance.py --details` warnings as candidates, not as
automatic refactor orders. A warning is closed only when the code is split with
focused validation or when durable docs explain why the current boundary is
accepted or deferred.

## De-Duplication Rule

Keep the most precise, executable skill or script as the source of truth. Do
not preserve a simple, broad checklist when a richer specialized skill or guard
script covers the same behavior. If a broad skill is still useful, reduce it to
routing, scope control, and validation coordination.

Apply the same rule to documentation:

- keep the most precise layer as the source of truth;
- remove repeated prose from broader entrypoints once a narrower authoritative
  layer exists;
- keep broad docs as routers, not shadow handbooks.

## Commands

```powershell
git status --short --branch
python ops/scripts/dev/check_repo_skills.py
python ops/scripts/dev/select_validation_targets.py --worktree
python ops/scripts/dev/check_repository_normalization.py
python ops/scripts/dev/check_docs_governance.py
python ops/scripts/dev/check_boundary_governance.py --details
python ops/scripts/dev/check_structure_governance.py --details
python ops/scripts/dev/check_text_encoding.py --fail-on-suspicious <changed-file>
git diff --check
```

For multilingual files:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1 -Path <repo-relative-path>
```

## Checks

- Current names remain `CourseEval`, `apps.backend.courseeval_backend`,
  `courseeval-backend.service`, and `ops/nginx/courseeval.example*.conf`.
- Retired names appear only in historical notes, append-only ledgers, or
  explicit "do not restore" warnings.
- Documentation claims cite current code paths, config, tests, or scripts.
- Skill references use existing `skills/<name>/SKILL.md` paths.
- Validation failures are recorded with command, symptom, likely cause, and next step.
- Agent-facing docs should minimize lookup hops without deleting durable
  repository memory.

## Failure Handling

If a script reports stale names, classify each hit:

- historical record: preserve and document why it is allowed;
- active drift: update the doc/code/template;
- uncertain behavior: mark as `待验证` or "needs audit" and add a follow-up.

If tests cannot run, record the environment blocker rather than claiming the
change is verified.

## Related Files

- `AGENTS.md`
- `docs/README.md`
- `docs/contributing/ENCODING_AND_MOJIBAKE_SAFETY.md`
- `docs/testing/README.md`
- `docs/agents/agent-startup-routing.md`
- `docs/agents/agent-execution-entrypoints.md`
- `docs/agents/agent-playbook.md`
- `docs/agents/agent-closeout.md`
- `docs/agents/local-agent-workspace.md`
- `docs/operations/DEPLOYMENT_AND_OPERATIONS.md`
- `skills/docs-governance/SKILL.md`
- `skills/boundary-governance/SKILL.md`
- `skills/structure-governance/SKILL.md`
- `ops/scripts/dev/check_repo_skills.py`
- `ops/scripts/dev/check_repository_normalization.py`
- `ops/scripts/dev/check_text_encoding.py`
