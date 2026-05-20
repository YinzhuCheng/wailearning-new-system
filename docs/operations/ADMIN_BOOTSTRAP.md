# Admin Bootstrap and Demo Seed

## Bootstrap Admin Account

The backend creates an initial admin account during startup from `INIT_ADMIN_*`
settings when that username does not already exist. This is independent of the
demo seed: production deployments can keep `INIT_DEFAULT_DATA=false` and still
receive the first admin account.

Environment variables:

- `INIT_ADMIN_USERNAME`
- `INIT_ADMIN_PASSWORD`
- `INIT_ADMIN_REAL_NAME`

Defaults in code currently are:

- username: `admin`
- password: `ChangeMe123!`
- real name: `System Administrator`

These defaults are suitable only for local development. Production deployments must override them.

## Important Behavior

- The bootstrap logic creates the admin account only if that username does not already exist.
- Startup does not overwrite an existing admin password just because environment variables changed later.
- The bootstrap flow is part of application startup and uses the main backend settings.
- The admin bootstrap and the demo seed are both controlled during application startup, but they are not the same concern:
  the admin account uses `INIT_ADMIN_*` values, while the larger demo bundle is controlled by `INIT_DEFAULT_DATA`.
- In the current implementation, startup also runs schema repair, normalization, roster reconciliation, and optional demo seeding inside the FastAPI lifespan path. Treat bootstrap-related failures as startup-path issues, not only as authentication issues.

## Demo Seed Bundle

When `INIT_DEFAULT_DATA=true`, startup can also seed a demo teaching bundle.

That bundle includes:

- demo teacher account `teacher` (shared demo password via module constant),
- additional demo teacher `teacher_pro` (password equals username `teacher_pro`) teaching the elective **初等概率论** showcase course,
- several demo student accounts,
- a demo class,
- required and elective courses (including Markdown/LaTeX-heavy probability materials),
- demo materials and homework,
- related roster synchronization behavior.

This is useful for local development and E2E testing, but should usually be disabled in production.

### Demo content depth for post-deploy smoke checks

The required demo course is intentionally more substantial than a bare smoke fixture. It is meant to let an operator deploy the product, log in as teacher/student users, and inspect realistic course surfaces without manually authoring sample content first.

Current required-course seed behavior:

- The required course **数据挖掘** receives a built-in cover image when `subjects.cover_image_url` is empty, so course-selection cards and material banners exercise the cover rendering path.
- Its material area is seeded as a multi-unit, multi-level outline rather than a single placeholder. The outline keeps the original three demo chapter nodes used by regression tests, then adds later units for data quality checks, standardization, EDA report writing, and classroom discussion notes.
- Several Markdown course materials are placed under the chapter tree. They include a course-running checklist, Wine dataset field notes, environment FAQ, DataFrame quality-check lab notes, standardization board notes, an EDA report template, and a classroom discussion record.
- The first homework remains the same assignment conceptually, but demo submissions are no longer one-line placeholders. The seed writes realistic Markdown submissions for `stu1` through `stu5`: some complete, some partial, and some with ordinary environment/configuration problems. This makes the teacher submission list, detail view, content preview, and LLM/manual grading surfaces look like a course that has already run for several weeks.

Additional reading-page showcase behavior:

- the probability elective now intentionally keeps chapter-linked homework,
  multiple chapter materials, and uncategorized material/homework so the
  student reading page can render **本章作业 / 本章资料 / 未归档资料 / 未归档作业**
  from one seeded course;
- the E2E reset scenario also seeds a minimal reader-showcase structure for its
  required course, so local screenshot automation can prove the same layout
  contract without depending on the larger demo bundle.

### E2E reader-showcase seed

`POST /api/e2e/dev/reset-scenario` now creates:

- two structured root chapters plus the uncategorized chapter;
- one structured chapter with a linked homework and multiple materials;
- one uncategorized material and one uncategorized homework link;
- a screenshot-friendly path for
  `npm run capture:student-material-reader` in `apps/web/school`.

Idempotency detail:

- The demo seed inserts missing chapters/materials/submissions and refreshes seeded material bodies by title.
- Existing homework submissions are not overwritten by the prefill helper, because a local deployment may already contain real student work. To see newly enriched submission samples in an existing database that already had the older short demo submissions, reset/recreate the demo database or delete only the old demo submission rows in a controlled local environment.
- Course materials are matched by `subject_id + title`, so changing a seeded material title creates a new row instead of mutating the old one. Prefer appending or editing content under stable titles unless a new sample resource is intentionally desired.

Current implementation context:

- `main.py` creates tables, runs schema-update helpers, normalizes teacher/class and semester links, backfills homework grading data, ensures the bootstrap admin exists, reconciles student users and roster rows, and only then applies optional demo seeding
- if `INIT_DEFAULT_DATA=true`, the demo seed is followed by another roster reconciliation before startup completes
- if `ENABLE_LLM_GRADING_WORKER=true` and `LLM_GRADING_WORKER_LEADER=true`, the in-process grading worker is started after startup initialization

## Recommended Production Values

```dotenv
INIT_DEFAULT_DATA=false
INIT_ADMIN_USERNAME=admin
INIT_ADMIN_PASSWORD=<strong-password>
INIT_ADMIN_REAL_NAME=System Administrator
```

## Password Reset Scripts

Useful repository scripts:

- `ops/scripts/reset_user_password.sh <username> <new_password>` resets an existing user's password and increments `token_version`.
- `ops/scripts/set-password.sh <username> <new_password>` creates the named admin user if missing, or resets/promotes it to an active admin if it already exists.

Use these instead of keeping plaintext credentials in repository-side note files.

The tracked [`.env.production`](../../.env.production) template now exposes the
related first-run defaults explicitly: `PUBLIC_REGISTRATION_VALIDATE_CLASS_EXISTS=true`,
forgot-password throttles, and a blank `DEFAULT_LLM_API_KEY=` placeholder for
operators who want the built-in preset validated during bootstrap.

## Why The Old Plaintext Admin Note Was Removed

The repository should not rely on a stray text file containing credentials. The source of truth is the environment-backed bootstrap configuration plus the database state.

## LLM default preset bootstrap (`DEFAULT_LLM_API_KEY`)

Schema repair (`ensure_schema_updates()` in `apps/backend/courseeval_backend/bootstrap.py`) ensures the built-in `"gpt-5.4"` LLM endpoint preset row exists once per database.

- **Without `DEFAULT_LLM_API_KEY`**: the row is created with `validation_status=pending`, validation steps marked skipped, and `is_active=false`. This avoids claiming remote connectivity was proven offline.
- **With `DEFAULT_LLM_API_KEY` set during first insert**: the bootstrap issues live HTTP checks for **text and vision** paths. Vision validation uploads the same conceptual payload as an administrator validating with a logo image: a **bundled minimal PNG** bytes payload encoded as a `data:image/png;base64,...` URL. Only an all-green check run marks the preset validated and active.

For the relationship between this bootstrap, demo data seeding, and local pytest (where outbound LLM calls are typically absent), see the「Demo seed and `DEFAULT_LLM_API_KEY`」section in [Test execution pitfalls](../testing/TEST_EXECUTION_PITFALLS.md).

## Related Docs

- [Deployment and Operations](DEPLOYMENT_AND_OPERATIONS.md)
- [Development and Testing](../testing/DEVELOPMENT_AND_TESTING.md)
