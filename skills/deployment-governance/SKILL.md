---
name: deployment-governance
description: Use this when changing CourseEval deployment scripts, setup scripts, nginx/systemd templates, .env.production, production bootstrap docs, Git deploy wrappers, post-deploy checks, or operator-facing upgrade guidance.
---

# Deployment Governance

## Purpose

Keep operator scripts, environment templates, service definitions, and
operations documentation aligned with the deployable implementation.

This skill should optimize for deploy-truth routing: operators and agents
should land on the current contract quickly, without confusing script examples,
template defaults, and historical operational notes.

## Workflow

1. Read:
   - `docs/operations/DEPLOYMENT_AND_OPERATIONS.md`
   - `docs/operations/ADMIN_BOOTSTRAP.md`
   - `docs/architecture/CONFIGURATION_REFERENCE.md`
   - `docs/operations/README.md`
2. Compare script behavior with documented commands before trusting prose.
3. Treat `DEPLOYMENT_AND_OPERATIONS.md` as the canonical source for the current
   deploy shape, script roles, required production settings, and safe upgrade
   sequencing.
4. Keep `.env.production`, config docs, bootstrap behavior, and deployment
   scripts in the same change set when their contracts move.
5. Prefer scriptable guardrails over prose-only warnings when a deploy rule can
   be checked statically.
6. Use text-first routing before adding new helper scripts when the problem is
   primarily operational explanation rather than executable enforcement.
7. Run operator-script and repository-normalization checks before handoff.
8. Document environment blockers honestly; Windows cannot prove Linux Bash
   runtime behavior by itself.

## Document Routing Rules

- Use `docs/operations/DEPLOYMENT_AND_OPERATIONS.md` as the canonical source
  for production shape, bootstrap, deployment scripts, Git-based deploy flow,
  validation checklist, and troubleshooting.
- Use `docs/operations/ADMIN_BOOTSTRAP.md` for startup/admin/demo-seed
  bootstrap sequencing rather than repeating that contract here.
- Use `docs/architecture/CONFIGURATION_REFERENCE.md` for env-var truth, not
  deployment prose summaries.
- Use `docs/contributing/GIT_WORKFLOW.md` when the deployment task is really a
  Git-sync workflow question.
- Keep this skill as the deployment/ops governance router and checklist, not as
  a shadow copy of the full operations handbook.

## Commands

```powershell
python ops/scripts/dev/check_operator_scripts.py
python ops/scripts/dev/run_validation_target.py static.operator_scripts_governance --timeout-seconds 120
python ops/scripts/dev/check_repository_normalization.py
python ops/scripts/dev/select_validation_targets.py --worktree
git diff --check
```

## Guardrails

- Do not restore old service names, old domains, or retired package paths as
  current deployment truth.
- Frontend deploy scripts must not restart `courseeval-backend.service`.
- Public health checks in `post_deploy_check.sh` must remain opt-in unless docs
  and scripts are changed together.
- `init_db.sql` must fail fast when required `psql -v` variables are missing.
- Treat `bash -n` as blocked on Windows when Bash resolves to the WSL installer;
  validate shell runtime on Linux/CI/deployment hosts.
- Do not present static operator-script checks as proof that Linux runtime
  behavior was exercised.

## Related Files

- `.env.production`
- `ops/scripts/`
- `ops/nginx/`
- `ops/systemd/courseeval-backend.service`
- `docs/operations/README.md`
- `docs/operations/DEPLOYMENT_AND_OPERATIONS.md`
- `docs/operations/ADMIN_BOOTSTRAP.md`
- `docs/architecture/CONFIGURATION_REFERENCE.md`
- `docs/contributing/GIT_WORKFLOW.md`
