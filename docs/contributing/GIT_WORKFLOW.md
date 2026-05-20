# Git Workflow

## Recommended Remote Layout

- `origin`: your working repository
- `upstream`: the upstream open-source source, if you track one
- optional mirror remotes if your team uses them

## Day-to-Day Flow

```bash
git checkout main
git pull --ff-only origin main
git checkout -b feature/<short-name>
```

After making changes:

```bash
git add <paths>
git commit -m "Describe the change"
git push -u origin feature/<short-name>
```

## Suggested Branch Strategy

- keep `main` or your release branch clean,
- develop features on short-lived branches,
- merge after tests and review,
- deploy from an explicit branch name instead of assuming the server is already on the right ref.

## Server-Side Deploy From Git

```bash
cd /opt/courseeval/source
sudo GIT_BRANCH=<branch> GIT_REMOTE=origin bash ops/scripts/redeploy.sh
```

This is safer than manually mixing `fetch`, `checkout`, and deploy commands on a live server.

Practical deploy notes:

- `redeploy.sh` prefers `REPO_DIR=/opt/courseeval/source` and fetches an explicit remote refspec before checkout/reset.
- Set `SAFE_BACKUP_BEFORE_DEPLOY=1` when you want the script to capture a PostgreSQL dump plus shared files before it deploys.
- Set `GIT_RESET_WORKTREE_BEFORE_FETCH=1` only when you intentionally want the server script to discard local tracked edits after saving a patch backup.
- Set `GIT_AUTO_STASH_ON_CHECKOUT_CONFLICT=0` when you want checkout conflicts to fail immediately instead of auto-stashing.
- Set `FRONTEND_ONLY=1` when you intentionally want only the school SPA rebuilt and deployed; this path reloads nginx but does not restart `courseeval-backend.service`.
- Use `pull_and_deploy.sh` only when you want the simpler “sync current server clone to branch, then full deploy” wrapper and do not need `redeploy.sh`'s `SKIP_GIT` / `FRONTEND_ONLY` controls.

Before committing deployment-script or Git-sync-script changes, run the
diff-selector recommendation. For `ops/scripts/*.sh`, `ops/scripts/*.sql`, and
`ops/scripts/lib/*.sh`, it should include:

```bash
python ops/scripts/dev/run_validation_target.py static.operator_scripts_governance --timeout-seconds 120
python ops/scripts/dev/run_validation_target.py static.validation_selector --timeout-seconds 120
python ops/scripts/dev/run_validation_target.py static.encoding_text_tools --timeout-seconds 120
```

`static.operator_scripts_governance` is a cross-platform guardrail. It verifies
the documented deploy-script contracts without executing Bash, contacting
systemd/nginx/PostgreSQL, or requiring a Linux shell. It does not replace
Linux-side syntax checks or an actual deployment rehearsal when script runtime
behavior changes.

## Updating From Upstream

If you track an upstream repository:

```bash
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
```

Resolve conflicts locally before deployment.

## Practical Rules

- Do not deploy from a dirty server worktree if you can avoid it.
- Do not assume a plain `git fetch` gave you the exact remote-tracking ref you want.
- Always verify the commit you deployed, not just the branch name.
- Pair git alignment with deployment checks.

## Related Docs

- [Deployment and Operations](../operations/DEPLOYMENT_AND_OPERATIONS.md)
