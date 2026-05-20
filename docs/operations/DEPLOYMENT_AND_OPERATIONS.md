# Deployment and Operations

## Scope

This document consolidates the current production, upgrade, and operational guidance for the repository. It replaces the older scattered deployment notes, upgrade runbooks, and server-specific markdown files.

Environment variables referenced below are documented field-by-field in [../architecture/CONFIGURATION_REFERENCE.md](../architecture/CONFIGURATION_REFERENCE.md) (derived from `apps/backend/courseeval_backend/core/config.py`). Keep deploy templates aligned with that file when defaults change.

## Target Production Shape

- Nginx serves the school SPA at `/`
- Nginx serves the parent portal at `/parent/`
- Nginx proxies `/api/*` to FastAPI on `127.0.0.1:8001`
- FastAPI runs under `gunicorn` with `uvicorn` workers and `systemd`
- PostgreSQL runs locally on the same host

Typical filesystem layout:

- `/opt/courseeval/source`
- `/opt/courseeval/venv`
- `/opt/courseeval/shared/.env.production`
- `/opt/courseeval/shared/uploads`
- `/opt/courseeval/backups`
- `/var/www/courseeval.example/admin`
- `/var/www/courseeval.example/parent`

**Repository source tree note (not production-critical):** the Git checkout is a multi-app monorepo (`apps/`, `docs/`, `ops/`, `tests/`). Test hygiene utilities such as the redundancy auditor live under `tests/devtools/` in source control. Production servers do not need those files unless you intentionally run repository QA on the host — deployment automation remains under `ops/scripts/`. Structural truth vs local artifacts: [../architecture/REPOSITORY_STRUCTURE.md](../architecture/REPOSITORY_STRUCTURE.md).

## Server Bootstrap

Use the repository scripts rather than hand-building the environment:

```bash
sudo bash ops/scripts/setup_server.sh
```

Useful bootstrap overrides:

- `APP_ROOT=/opt/courseeval` changes the application root created by `setup_server.sh`.
- `WEB_ROOT=/var/www/courseeval.example` changes where the admin and parent SPA directories are created.
- `APP_USER=courseeval` changes the system user/group created for the service.

Then prepare the production env file:

```bash
sudo install -m 640 .env.production /opt/courseeval/shared/.env.production
sudo nano /opt/courseeval/shared/.env.production
```

The tracked [`.env.production`](../../.env.production) template now uses current
CourseEval names, domains, and production-oriented defaults. It is still a
template: replace every `CHANGE_ME` value before the first deploy.

## Required Production Settings

At minimum, set:

```dotenv
APP_ENV=production
DEBUG=false
DATABASE_URL=postgresql://courseeval:<password>@127.0.0.1:5432/courseeval
SECRET_KEY=<strong-random-value>
ALLOW_PUBLIC_REGISTRATION=false
PUBLIC_REGISTRATION_VALIDATE_CLASS_EXISTS=true
INIT_ADMIN_USERNAME=admin
INIT_ADMIN_PASSWORD=<strong-admin-password>
INIT_ADMIN_REAL_NAME=System Administrator
INIT_DEFAULT_DATA=false
BACKEND_CORS_ORIGINS=https://courseeval.example,https://www.courseeval.example
TRUSTED_HOSTS=courseeval.example,www.courseeval.example,127.0.0.1,localhost
ENABLE_LLM_GRADING_WORKER=true
LLM_GRADING_WORKER_LEADER=true
LLM_GRADING_WORKER_POLL_SECONDS=2
LLM_GRADING_TASK_STALE_SECONDS=600
FORGOT_PASSWORD_USERNAME_COOLDOWN_SECONDS=600
FORGOT_PASSWORD_MAX_REQUESTS_PER_IP_PER_HOUR=40
REQUIRE_STRONG_SECRETS=true
```

Production rules:

- never keep placeholder database credentials,
- never keep the default weak secret,
- normally keep `ALLOW_PUBLIC_REGISTRATION=false`,
- keep `PUBLIC_REGISTRATION_VALIDATE_CLASS_EXISTS=true` unless you intentionally need looser self-registration semantics,
- use `INIT_DEFAULT_DATA=false` unless you intentionally want demo accounts and demo courses,
- set `TRUSTED_HOSTS` and `BACKEND_CORS_ORIGINS` deliberately instead of relying on development defaults,
- consider `REQUIRE_STRONG_SECRETS=true` even outside strict production startup paths so weak secrets fail early,
- keep forgot-password throttles enabled unless you have a measured reason to relax them,
- only one production backend leader should usually run the grading worker.
- Optional: set `DEFAULT_LLM_API_KEY` when you want the built-in `gpt-5.4` preset to perform first-start text/vision connectivity validation automatically; if left empty, the preset remains pending/inactive until an administrator validates it manually.
- Optional: set `FRONTEND_ADMIN_BASE_URL` to the public admin origin (for example `https://courseeval.example`) so **忘记密码** notifications include an absolute link to the password-reset screen; if unset, the notification still contains a relative `/users?...` path that works when opened inside the same admin site.

## Administrator password after deployment (SSH)

If you can SSH into the application server, you can reset any existing user password (including the bootstrap `INIT_ADMIN_USERNAME`) **without using the web UI** by running the bundled script against the production virtualenv and `.env.production`:

```bash
cd /opt/courseeval/source
sudo bash ops/scripts/reset_user_password.sh admin 'YourNewStrongPasswordHere!'
```

The script updates the password hash in the database and increments `token_version` so existing JWT sessions for that user are invalidated. For a missing admin account, use `sudo bash ops/scripts/set-password.sh admin 'YourNewStrongPasswordHere!'`; it creates the named active admin if absent, or resets/promotes it if present. On first startup, `INIT_ADMIN_*` creates the initial admin independently of `INIT_DEFAULT_DATA`, so production can keep `INIT_DEFAULT_DATA=false` and still bootstrap access. For an already-deployed database with a working admin login, an in-app admin reset from **用户管理** is also acceptable.

## Database Initialization

Use the bundled SQL script:

```bash
cp ops/scripts/init_db.sql /tmp/init_db.sql
chmod 644 /tmp/init_db.sql
sudo -u postgres psql \
  -v db_name='courseeval' \
  -v db_user='courseeval' \
  -v db_password='REPLACE_WITH_A_STRONG_DB_PASSWORD' \
  -f /tmp/init_db.sql
```

`ops/scripts/init_db.sql` is intentionally idempotent for the common first-host
bootstrap path:

- creates the PostgreSQL login role when missing,
- rotates that role password to the supplied `db_password`,
- creates the target database when missing,
- grants database and schema privileges for future tables/sequences.

The script now refuses to run when `db_name`, `db_user`, or `db_password` were
not passed via `psql -v ...`, so avoid calling it as a bare `psql -f`.

## Deployment Scripts

Primary scripts:

- `ops/scripts/deploy_all.sh`
- `ops/scripts/deploy_backend.sh`
- `ops/scripts/deploy_frontend.sh`
- `ops/scripts/deploy_parent_portal.sh`
- `ops/scripts/fresh_install_and_deploy.sh`
- `ops/scripts/post_deploy_check.sh`
- `ops/scripts/redeploy.sh`
- `ops/scripts/pull_and_deploy.sh`

Operator-script governance:

- `ops/scripts/dev/check_operator_scripts.py` performs cross-platform static
  checks for deployment script contracts that are easy to break during
  maintenance: Bash entry headers, frontend deploys using `npm ci`, frontend
  deploys not restarting the backend service, backend deploys preserving shared
  uploads, `post_deploy_check.sh` keeping public health checks opt-in, explicit
  Git refspec fetches, and `init_db.sql` fail-fast variable handling.
- The diff selector recommends `static.operator_scripts_governance` for
  `ops/scripts/*.sh`, `ops/scripts/*.sql`, and helper-script changes. It is not
  a substitute for running the scripts on Linux, but it is the default cheap
  guardrail before handoff.

Implementation notes that matter operationally:

- `deploy_backend.sh` creates `${APP_ROOT}/shared/uploads` and non-destructively syncs any legacy `${SOURCE_DIR}/uploads/` content there when present, leaving the old directory in place for manual cleanup
- backend deployment installs `ops/systemd/courseeval-backend.service` and restarts `courseeval-backend.service`
- frontend deployment builds from `apps/web/school` and syncs `dist/` into `${ADMIN_WEB_ROOT}`
- parent deployment builds from `apps/web/parent` and syncs `dist/` into `${PARENT_WEB_ROOT}`
- both frontend deploy scripts also refresh the nginx site file from `ops/nginx/courseeval.example*.conf`
- frontend-only deploy scripts reload nginx after publishing static assets, but they do not restart `courseeval-backend.service`
- `post_deploy_check.sh` always verifies local backend health; public `/health` is skipped by default and only runs when `APP_URL` or `API_HEALTH_URL` is set. When the public health URL is exactly `${APP_URL}/health`, the script also checks the derived `/api/health` path unless `PUBLIC_API_HEALTH_URL` overrides it explicitly
- `redeploy.sh` and `pull_and_deploy.sh` resolve `REPO_DIR` through `ops/scripts/lib/deploy_repo_dir.sh`: they prefer `/opt/courseeval/source` when it is a git clone and only fall back to the script-adjacent checkout when that preferred path is absent

Recommended full deploy:

```bash
sudo bash ops/scripts/deploy_all.sh
sudo bash ops/scripts/post_deploy_check.sh
```

### Fresh host bootstrap and first deploy

When the target machine is effectively starting from zero, use:

```bash
sudo \
  GIT_BRANCH=main \
  DB_PASSWORD='<strong-db-password>' \
  SECRET_KEY='<long-random-secret>' \
  INIT_ADMIN_PASSWORD='<strong-admin-password>' \
  PUBLIC_HOST='courseeval.example' \
  PUBLIC_WWW_HOST='www.courseeval.example' \
  bash ops/scripts/fresh_install_and_deploy.sh
```

What this script does:

- runs `ops/scripts/setup_server.sh`,
- clones or force-syncs the repository into `/opt/courseeval/source`,
- writes `/opt/courseeval/shared/.env.production` from current repository conventions,
- initializes PostgreSQL with `ops/scripts/init_db.sql`,
- runs `ops/scripts/deploy_all.sh`,
- runs `ops/scripts/post_deploy_check.sh`,
- optionally issues a Let's Encrypt certificate when `ENABLE_CERTBOT=1` and `CERTBOT_EMAIL=...` are provided.

Important safety notes:

- it intentionally refuses to run while `DB_PASSWORD`, `SECRET_KEY`, or `INIT_ADMIN_PASSWORD` still use `CHANGE_ME...` placeholders,
- it uses the current CourseEval paths and service names (`/opt/courseeval`, `courseeval-backend.service`, `ops/nginx/courseeval.example*.conf`),
- when reusing an existing server clone, it performs a hard reset and `git clean -ffd` inside `${SOURCE_DIR}`, so do not keep server-only edits there,
- if you are deploying by bare public IP before DNS exists, set `PUBLIC_IP=...`; HTTPS issuance should wait until the real hostnames resolve.

To include public checks in the final step:

```bash
sudo APP_URL=https://courseeval.example bash ops/scripts/post_deploy_check.sh
```

If the public `/health` endpoint is not simply `${APP_URL}/health`, call the
script with `API_HEALTH_URL=https://.../health` directly and optionally set
`PUBLIC_API_HEALTH_URL=https://.../api/health` for the proxied API probe.

## Git-Based Server Updates

Preferred update path:

```bash
cd /opt/courseeval/source
sudo GIT_BRANCH=main GIT_REMOTE=origin bash ops/scripts/redeploy.sh
```

What `redeploy.sh` does:

1. Resolves `REPO_DIR` with a production-first preference for `/opt/courseeval/source`.
2. Fetches the exact remote branch refspec instead of trusting an older local remote-tracking ref.
3. Optionally backs up database/shared data before deployment.
4. Deploys either the full stack or only the school SPA, depending on flags.
5. Runs `post_deploy_check.sh` against local health and, when configured, the public URL.

Use `pull_and_deploy.sh` when you are already in the intended server clone and want a shorter Git-sync-plus-full-deploy wrapper without the extra `SKIP_GIT` / `FRONTEND_ONLY` branching used by `redeploy.sh`.

Useful variants:

- `REPO_DIR=/opt/courseeval/source` when the active server clone is not at the default path.
- `DD_DEFAULT_REPO_DIR=/opt/courseeval/source` when you want to change the preferred auto-detected production clone path without editing the helper.
- `GIT_RESET_WORKTREE_BEFORE_FETCH=1` when local server edits are blocking checkout.
- `SAFE_BACKUP_BEFORE_DEPLOY=1` when you want a pre-upgrade database and shared-data backup.
- `GIT_AUTO_STASH_ON_CHECKOUT_CONFLICT=0` when you want fail-fast behavior instead of auto-stash.
- `SKIP_GIT=1` when the desired source tree is already staged into `REPO_DIR` and you explicitly do not want `redeploy.sh` to fetch or checkout anything.
- `FRONTEND_ONLY=1` when you intentionally want only the school SPA rebuilt and deployed; this path reloads nginx but does not restart the backend service.
- `APP_URL=https://...` when you want the post-deploy public check to hit a specific public hostname.
- `API_HEALTH_URL=https://.../health` when the public `/health` check should target an explicit URL instead of deriving it from `APP_URL`.
- `PUBLIC_API_HEALTH_URL=https://.../api/health` when public API health should not be derived from `APP_URL`.

## Safe Upgrade Principles

When upgrading a live system:

1. Back up the database first.
2. Back up shared uploads and env files.
3. Align the intended git revision explicitly.
4. Deploy backend and frontends together unless you have a deliberate split rollout.
5. Validate with health checks, logs, and the intended git `HEAD`.

Do not treat a clean `git status` or a single public URL response as proof that deployment finished.

### CourseEval normalization prechecks

Before deploying the CourseEval normalization line to a database that predates the package/branding cleanup, confirm these invariants or run a dry deployment against a restored backup:

- `users.student_id` is populated for active student login accounts that should participate in quota, homework, discussion, and course enrollment flows. The runtime reconciliation path may repair default/demo drift, but feature code should not rely on `username == student_no` as a relationship.
- Required courses have `subject_class_links` rows for each administrative class that should auto-enroll. Student and class-teacher course access no longer falls back to `subjects.class_id`; that column remains a primary/display anchor for compatibility-heavy rows.
- Upload files are present under the effective `UPLOADS_DIR` / `${APP_ROOT}/shared/uploads` path. The deployment script now copies any legacy `${SOURCE_DIR}/uploads/` content into the shared path when found, but leaves the old directory untouched; operators should still verify attachment URLs before cutting over and remove the legacy tree deliberately later.
- System settings in the database already contain the intended CourseEval branding. Frontend normalization no longer rewrites stored legacy brand text at render time.
- Service and Nginx names match the current templates: `courseeval-backend.service` and `ops/nginx/courseeval.example*.conf`.

## Validation Checklist

After deployment:

- check `systemctl status courseeval-backend`,
- run `curl http://127.0.0.1:8001/health`,
- run `bash ops/scripts/post_deploy_check.sh` for local health, or set `APP_URL=https://...` so it also checks the public `/health` and `/api/health` paths,
- run `sudo nginx -t`,
- verify the school frontend loads,
- verify the parent portal loads,
- verify backend logs are clean,
- confirm the repo `HEAD` matches the intended revision,
- if using LLM grading, confirm endpoint presets and course-level config still load.

## LLM-Specific Production Concerns

- Presets must be valid before teachers can rely on them.
- Worker leadership must be explicit in multi-instance deployments.
- Token quotas and endpoint retries are production behavior, not just test behavior.
- If attachments matter operationally, include the uploads directory in your backup plan.

## Backups

Database:

```bash
sudo -u postgres pg_dump -Fc courseeval > /opt/courseeval/backups/courseeval-$(date +%F-%H%M%S).dump
```

Shared files:

```bash
sudo tar -czf /opt/courseeval/backups/courseeval-files-$(date +%F-%H%M%S).tar.gz \
  /opt/courseeval/shared \
  /var/www/courseeval.example
```

If homework attachments are important in your deployment, also back up the effective upload root defined by `UPLOADS_DIR`.

## Troubleshooting

Backend logs:

```bash
sudo journalctl -u courseeval-backend -f
```

Nginx logs:

```bash
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

PostgreSQL:

```bash
sudo journalctl -u postgresql -n 100 --no-pager
```

## Related Docs

- [LLM and Homework Guide](../product/LLM_HOMEWORK_GUIDE.md)
- [Admin Bootstrap and Demo Seed](ADMIN_BOOTSTRAP.md)
- [Git Workflow](../contributing/GIT_WORKFLOW.md)
