# Configuration Reference

## Purpose

Single place to document **environment variables and runtime settings** backed by `apps/backend/courseeval_backend/core/config.py` (Pydantic `Settings`). Values load from the process environment and optional `.env` file (`env_file=".env"`, UTF-8).

If code adds a field to `Settings`, update this document in the same change set.

---

## Reading settings in code

- Import `settings` from `apps.backend.courseeval_backend.core.config`.
- Do not duplicate defaults in unrelated modules; extend `Settings` instead.

---

## Core server and database

| Variable | Default / notes | Role |
|----------|-----------------|------|
| `APP_NAME` | `CourseEval API` | Display/name metadata for the backend application. |
| `APP_ENV` | `development` | Drives production checks; `production`/`prod` triggers strong secret validation. |
| `DEBUG` | `false` | FastAPI/debug tooling flag. |
| `HOST` | `127.0.0.1` | Bind address for documented uvicorn examples. |
| `PORT` | `8001` | Default backend port in docs and examples. |
| `DATABASE_URL` | PostgreSQL URL with **placeholder** credentials in repo default | **Must** be replaced for real deployments; rejected when strong secrets mode + production rules apply. |
| `SECRET_KEY` | Placeholder string in repo default | JWT signing; **must** be a long random value when `APP_ENV` is production or `REQUIRE_STRONG_SECRETS=true`. |
| `ALGORITHM` | `HS256` | JWT algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24h) | JWT lifetime. |
| `UPLOADS_DIR` | `""` | Optional override for upload root; empty falls back to repo-local `uploads/`, while the production systemd template pins `/opt/courseeval/shared/uploads`. |

---

## CORS and host safety

| Variable | Alias | Purpose |
|----------|-------|---------|
| `BACKEND_CORS_ORIGINS` | `BACKEND_CORS_ORIGINS_RAW` | Comma-separated list **or** list/tuple in env. If it contains `*`, CORS allows all origins and credentials are disabled (Starlette behavior). |
| `TRUSTED_HOSTS` | `TRUSTED_HOSTS_RAW` | Passed to `TrustedHostMiddleware` unless empty or `*` included. |

---

## Bootstrap and identity

| Variable | Default | Notes |
|----------|---------|-------|
| `INIT_ADMIN_USERNAME` | `admin` | Initial admin user name created during startup when missing. Independent of demo seed. |
| `INIT_ADMIN_PASSWORD` | `ChangeMe123!` | Password used only when the initial admin row is first created; **change** for any shared or networked environment. Later env changes do not overwrite an existing password. |
| `INIT_ADMIN_REAL_NAME` | `System Administrator` | Display name used when the initial admin row is first created. |
| `INIT_DEFAULT_DATA` | `true` | When true, `main.py` lifespan runs demo seed (`seed_demo_course_bundle`) after repairs and initial admin bootstrap. Production should normally set this to `false`. |
| `ALLOW_PUBLIC_REGISTRATION` | `false` | Enables student self-registration API when true. |
| `PUBLIC_REGISTRATION_VALIDATE_CLASS_EXISTS` | `true` | When true with public registration, `class_id` must reference an existing class row. |

---

## Email / link bases

| Variable | Notes |
|----------|-------|
| `FRONTEND_ADMIN_BASE_URL` | Optional absolute admin origin for links in notifications (for example `https://www.courseeval.example`). Empty means relative `/users?...` paths in messages. |

---

## Forgot-password throttling

| Variable | Default | Notes |
|----------|---------|-------|
| `FORGOT_PASSWORD_USERNAME_COOLDOWN_SECONDS` | `600` | Minimum spacing for repeated forgot-password attempts for the same username (reduces admin-notification spam). Set `0` to disable per-user cooldown. |
| `FORGOT_PASSWORD_MAX_REQUESTS_PER_IP_PER_HOUR` | `40` | Rolling hourly cap per client IP recorded via `operation_logs`. Set `0` to disable IP gate. |

---

## Process and logging knobs

| Variable | Default | Notes |
|----------|---------|-------|
| `GUNICORN_WORKERS` | `3` | Intended process count for Gunicorn-based deployment templates and operator configuration. Keep this aligned with the worker-leader rule below; more web workers does not mean more intended grading leaders. |
| `LOG_LEVEL` | `info` | Backend process logging level used by deployment/runtime entrypoints that read settings. |

---

## LLM grading worker

| Variable | Default | Notes |
|----------|---------|-------|
| `ENABLE_LLM_GRADING_WORKER` | `true` | Master switch for in-process worker thread. |
| `LLM_GRADING_WORKER_LEADER` | `true` | If true, only leader process runs worker (safe for gunicorn multi-worker). If false, **every** process with worker enabled drains the DB queue; acceptable for single-uvicorn dev, risky if duplicated accidentally in production. |
| `LLM_GRADING_WORKER_POLL_SECONDS` | `2` | Poll interval for queued tasks. |
| `LLM_GRADING_TASK_STALE_SECONDS` | `600` | Reclaim stuck `processing` tasks. |
| `DEFAULT_LLM_API_KEY` | `""` | When non-empty, bootstrap inserts (once) the built-in `"gpt-5.4"` preset row and immediately runs **live** text + vision connectivity checks against the vendor URL using a **bundled PNG probe** (equivalent to validating with a small logo image). On success the preset is marked validated and active. When empty, the preset row is still inserted but stays `pending` / inactive until an administrator validates through the UI or sets this variable and restarts. Never commit real keys. |
| `DEFAULT_ESTIMATED_IMAGE_TOKENS` | `850` | Estimation knob (see LLM domain). |

---

## Safety rails

| Variable | Default | Notes |
|----------|---------|-------|
| `REQUIRE_STRONG_SECRETS` | `false` | When true (or when `APP_ENV` is production), weak `SECRET_KEY` and placeholder DB URLs fail settings validation at startup. |

---

## E2E / Playwright dev API

Never enable in production. `model_validator` rejects `E2E_DEV_SEED_ENABLED` when `APP_ENV` is production.

| Variable | Default | Notes |
|----------|---------|-------|
| `E2E_DEV_SEED_ENABLED` | `false` | When true **and** non-production, `/api/e2e/*` routes are exposed (still check `expose_e2e_dev_api()`). |
| `E2E_DEV_SEED_TOKEN` | `""` | Shared secret header `X-E2E-Seed-Token` for seed endpoints. |
| `E2E_DEV_REQUIRE_ADMIN_JWT` | `false` | When true, powerful `/api/e2e/dev/*` routes also require `Authorization: Bearer` for an admin user. Playwright config defaults this to true for managed subprocesses; see `apps/web/school/playwright.config.cjs`. |
| `E2E_DEV_ADMIN_USERNAME` | `""` | Credentials helper for automation (paired with password). |
| `E2E_DEV_ADMIN_PASSWORD` | `""` | |

---

## Frontend dev (Vite) - not in `Settings`

These are **client** environment variables read by Vite:

| Variable | Admin default | Parent default | Purpose |
|----------|---------------|----------------|---------|
| `VITE_DEV_PORT` | `3000` (`apps/web/school/vite.config.js`) | `5174` (`apps/web/parent/vite.config.js`) | Dev server port. |
| `VITE_PROXY_TARGET` | `http://127.0.0.1:8001` | same | Backend for `/api` proxy. |
| `VITE_APP_BASE_PATH` | `/` | `/` | SPA base path for deployments under subpaths. |

Playwright additionally defines `E2E_API_PORT` / `E2E_UI_PORT` (defaults **8012** / **3012**) inside `apps/web/school/playwright.config.cjs` for managed test servers; see [../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md](../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md).

---

## Related documents

- Operational env templates and nginx layout - [../operations/DEPLOYMENT_AND_OPERATIONS.md](../operations/DEPLOYMENT_AND_OPERATIONS.md)
- Bootstrap ordering - [../operations/ADMIN_BOOTSTRAP.md](../operations/ADMIN_BOOTSTRAP.md)
- Business impact of LLM settings - [../product/LLM_HOMEWORK_GUIDE.md](../product/LLM_HOMEWORK_GUIDE.md)
