# Backend Package Structure

## Purpose

This document explains how to navigate the backend package after the namespace migration to:

- `apps.backend.courseeval_backend`

It is intended for maintainers and LLM coding agents that need to answer two recurring questions:

1. Where should a backend change go?
2. Which layer should own a new piece of code?

## Canonical Package Root

The backend package root is:

- `apps/backend/courseeval_backend/`

The canonical Python import root is:

- `apps.backend.courseeval_backend`

Examples:

- `from apps.backend.courseeval_backend.core.config import settings`
- `from apps.backend.courseeval_backend.db.models import User`
- `from apps.backend.courseeval_backend.api.schemas import Token`
- `from apps.backend.courseeval_backend.api.routers import auth`

Do not use:

- `app.*`
- `courseeval_backend.*` without the `apps.backend` prefix
- ad hoc `sys.path` edits in normal application code

## Current Layer Model

The backend is organized into four practical layers plus explicit domain packages.

### Layer 1: process entrypoints

Files:

- `main.py`
- `bootstrap.py`

Responsibilities:

- compose the FastAPI application,
- register routers,
- coordinate startup lifecycle,
- run bootstrap and repair flows.

Rules:

- keep these files thin,
- avoid putting business rules directly here,
- avoid adding import-time side effects unless they are unavoidable and documented.

### Layer 2: HTTP API surface

Directory:

- `api/`

Subdirectories and files:

- `api/routers/`
- `api/schemas.py`
- `api/schema_defs/`
- `ops/scripts/dev/inventory_api_schemas.py` (read-only inventory for planned
  `api/schemas.py` boundary work)

Responsibilities:

- request and response contracts,
- route wiring,
- parameter validation,
- translation between HTTP concerns and backend services.

Rules:

- routers may enforce authorization and orchestration,
- routers should avoid absorbing large business workflows,
- request and response DTOs belong here unless there is a strong reason otherwise,
- `api/schemas.py` is currently a deliberate schema barrel with many direct
  imports. Some low-coupling DTO groups now live under `api/schema_defs/` and
  are re-exported from `api.schemas` for compatibility. Treat additional
  schema moves as high blast radius: run
  `python ops/scripts/dev/inventory_api_schemas.py --fail-on-missing-imports`
  before any split, preserve imported names or provide a compatibility export,
  and validate FastAPI import/OpenAPI behavior after moving schema classes.
- As of the May 2026 repository-normalization pass, `api/schemas.py` still owns
  several coupled DTO groups: auth/users, classes/courses/subjects,
  discussions/recent posts, homework, learning notes, LLM settings, materials,
  scores, shared student DTOs, and the forward-reference rebuild glue for
  course roster, subject create, material chapter, learning-note chapter, and
  dashboard schemas. Do not continue splitting these opportunistically. Move a
  remaining group only when the target router/domain test scope is clear and
  the compatibility barrel remains intact.

### Layer 3: shared backend core

Directory:

- `core/`

Files:

- `core/config.py`
- `core/auth.py`
- `core/permissions.py`

Responsibilities:

- settings loading,
- token creation and current-user resolution,
- cross-domain permission helpers.

Rules:

- only put code here if it is genuinely cross-domain,
- do not turn `core/` into a new miscellaneous dumping ground,
- if logic is specific to homework, LLM, roster, or scores, it probably does not belong here.

### Layer 4: persistence primitives

Directory:

- `db/`

Files:

- `db/database.py`
- `db/models.py`

Responsibilities:

- SQLAlchemy engine and session setup,
- ORM base and shared DB dependency wiring,
- database entities and enums.

Rules:

- model definitions belong here,
- route-specific serialization does not,
- configuration parsing does not,
- app startup orchestration does not.

### Layer 5: extracted domain helpers

Directory:

- `domains/`

Current subpackages:

- `domains/courses/`
- `domains/roster/`
- `domains/scores/`
- `domains/seed/`
- `domains/llm/`
- `domains/homework/`

Responsibilities:

- hold business-domain helpers that were previously trapped inside giant modules,
- reduce router-to-router imports,
- reduce growth pressure on package-root monolith files.

Rules:

- use `domains/` for real business slices, not generic utilities,
- prefer one clear responsibility per domain module,
- if logic is still mostly HTTP orchestration, leave it in `api/`,
- if logic is still mostly persistence primitives, leave it in `db/`.

## Current Domain-Heavy Modules

The following package-root modules are still substantial and should be treated as candidates for future extraction or slimming when a task already justifies focused boundary work:

- `llm_grading.py`
- `llm_discussion.py`
- `bootstrap.py`
- `attachments.py`
- `markdown_llm.py`

Interpretation:

- these modules are acceptable only where they still act as true orchestration or shared runtime boundaries
- they should not be treated as proof that flat package-root business modules are the long-term strategy
- new business logic should prefer extending `domains/` or `services/` rather than increasing root-module count

These files are acceptable for now, but contributors should avoid making them even broader unless the change is truly local and small.

The following extractions are already in place:

- attachment and archive parsing moved into `domains/llm/attachments.py`
- discussion UI prefix stripping moved into `domains/llm/discussion_ui.py`
- quota reservation and usage-accounting helpers moved into `domains/llm/quota.py`
- admin quota-policy helpers moved into `domains/llm/token_quota.py`
- endpoint-group routing moved into `domains/llm/routing.py`
- endpoint URL / response parsing helpers moved into `domains/llm/protocol.py`
- homework grading prompt section markers and markdown field expansion helpers
  moved into `domains/llm/grading_prompt.py`
- homework score normalization, candidate precedence, and effective-score
  selection helpers moved into `domains/llm/grading_result.py`
- course access and enrollment logic moved into `domains/courses/access.py`
- required-course class-link replacement, duplicate detection, and course-create
  helper rules moved into `domains/courses/class_links.py`
- course enrollment serialization, roster-student creation, and roster-enroll
  helper loops moved into `domains/courses/enrollment.py`
- class-scope query helpers shared by routers moved into `domains/courses/class_scope.py`
- course metadata normalization and Subject response serialization helpers moved
  into `domains/courses/metadata.py`
- homework row cleanup moved into `domains/homework/cleanup.py`
- homework appeal and notification helpers moved into `domains/homework/appeals.py` and `domains/homework/notifications.py`
- homework response preview and grading-task log serialization helpers moved
  into `domains/homework/serialization.py`
- homework submission attempt late/counts-toward-final-score rules moved into
  `domains/homework/submission_rules.py`
- roster synchronization and reconciliation moved into `domains/roster/`
- score composition and score-appeal helpers moved into `domains/scores/`
- demo seed orchestration lives in `domains/seed/demo.py`, with demo teacher,
  class, student-user, and roster-row construction extracted to
  `domains/seed/demo_users.py`, and reusable demo course setup extracted to
  `domains/seed/demo_courses.py`
- operation-log helpers moved into `services/logging.py`
- low-coupling API DTO groups for appearance, attendance, dashboard, files,
  notifications, operations/settings, points, and roster moved into `api/schema_defs/` while `api/schemas.py` remains the
  compatibility barrel for existing router and test imports

That is the intended pattern for subsequent rounds: extract coherent vertical slices without inventing alternate import roots.

## Router Organization

The current route modules live in:

- `apps/backend/courseeval_backend/api/routers/`

Examples:

- `auth.py`
- `subjects.py`
- `students.py`
- `scores.py`
- `homework.py`
- `llm_settings.py`

Router modules should own:

- endpoint registration,
- endpoint-local validation,
- response shaping,
- orchestration of domain helpers.

Router modules should not become the only home of business rules. When a router grows because it owns nontrivial workflow logic, that is usually a signal to extract a domain-oriented helper module.

## How To Place New Backend Code

Use the following decision rules:

### Put code in `api/` when:

- it defines a request or response shape,
- it exists only because an HTTP endpoint needs it,
- it is route registration or endpoint orchestration.

### Put code in `core/` when:

- it is cross-domain,
- it is about authentication or permission primitives,
- it is configuration or settings parsing.

### Put code in `db/` when:

- it defines ORM models or database bootstrap primitives,
- it defines session or engine configuration,
- it is a persistence primitive used by many backend areas.

### Keep code at package root only when:

- it is a process entrypoint,
- it coordinates several domains and does not yet fit one current layer,
- it is a shared runtime adapter whose natural home is still under review,
- or it is a package entrypoint.

### Do not add code to a new random bucket when:

- the real issue is that a domain subpackage should exist.

If a change is large enough to justify a new subpackage, create or extend a domain-oriented package with a clear name such as:

- `domains/homework/`
- `domains/llm/`
- `domains/roster/`
- `domains/courses/`
- `domains/scores/`
- `domains/seed/`
- `services/`

Do not create vague buckets such as:

- `misc/`
- `helpers/`
- `common2/`
- `temp/`

## Recommended Next Domain Extractions

The next worthwhile structural reductions, when a scoped task needs them, are:

1. `llm_grading.py` worker/execution/notification slices that can preserve the
   current queue, retry, quota, endpoint failover, and summary-refresh
   behavior.
2. `api/routers/homework.py` workflow slices such as submissions, grading
   actions, and permission-heavy helper groups, each with homework/LLM/security
   validation selected first.
3. `domains/seed/demo.py` demo homework/material/notification builders, while
   keeping `seed_demo_course_bundle(db)` as the public seed orchestration
   entrypoint.
4. `bootstrap.py` startup/schema/default-data orchestration slices, only with
   schema-governance and bootstrap/default-data tests in scope.

The following candidates are explicitly deferred for now:

- `api/routers/subjects.py` is now below the backend router large-file
  threshold after metadata, class-link, and enrollment helper extraction. Treat
  it as an HTTP/auth orchestration boundary unless new reusable course business
  logic accumulates there.
- `api/routers/scores.py` is not currently a large-file governance finding.
  Split it only when a concrete score-composition or appeal boundary emerges.
- `api/schemas.py` remains a compatibility barrel plus coupled DTO ownership.
  Continue schema splits only as dedicated schema-boundary work, not as a
  side-effect of unrelated router or domain refactors.

The likely extraction shape is:

```text
apps/backend/courseeval_backend/
  domains/
    llm/
      worker.py
      routing.py
      quota.py
      grading.py
    homework/
      service.py
      appeals.py
      notifications.py
    roster/
      sync.py
      reconciliation.py
    scores/
      composition.py
      appeals.py
    seed/
      demo.py
      demo_users.py
  services/
    logging.py
```

Most of those directories now exist. The ongoing rule is to reduce the few
heavy package-root orchestration modules only through bounded, validation-backed
changes, without re-accumulating structural debt at the root.

## Import Rules For Future Refactors

When moving backend files again:

1. Preserve the canonical import root `apps.backend.courseeval_backend`.
2. Prefer a single explicit edit set over compatibility shims.
3. Update tests, docs, ops scripts, and Playwright config in the same change set.
4. Avoid partial namespace migrations that leave two valid import styles in circulation.

## Operational Consequences

Because the backend package now uses its real namespace everywhere, the following operational commands are authoritative:

- `python -m uvicorn apps.backend.courseeval_backend.main:app --host 127.0.0.1 --port 8001 --reload`
- `python -m apps.backend.courseeval_backend.bootstrap`
- `gunicorn apps.backend.courseeval_backend.main:app`

If future refactors move `main.py` or `bootstrap.py`, update:

- `ops/systemd/courseeval-backend.service`
- `ops/scripts/windows/start-backend.bat`
- `apps/web/school/playwright.config.cjs`
- developer docs and README examples

in the same change set.
