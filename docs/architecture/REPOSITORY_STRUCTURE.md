# Repository Structure

## Purpose

This document defines the current repository layout after the full backend namespace migration.

It is written for both human contributors and LLM coding agents. Read it before:

- moving files,
- inventing new top-level directories,
- changing Python import paths,
- adding scripts or launchers,
- or deciding where a new test or document should live.

The repository no longer uses a root-level `app/` compatibility package. The canonical backend import namespace is now:

- `apps.backend.courseeval_backend`

That namespace is not a suggestion or an alias. It is the real package boundary and should be treated as the only authoritative backend import root.

## High-Level Layout

```text
repo/
  apps/
    __init__.py
    backend/
      __init__.py
      courseeval_backend/         canonical FastAPI backend package
    web/
      admin/                       school SPA and Playwright config
      parent/                      parent-facing SPA
  docs/                            authoritative documentation tree
    reports/                       dated audits, remediation notes, and restructure reports
  ops/                             deployment, CI, nginx, systemd, helper scripts
  tests/                           pytest suites, Playwright specs, and optional devtools (see Test Boundaries)
  README.md                        public repository entrypoint
  LICENSE                          license text
  requirements.txt                 Python dependency surface for the backend
  pytest.ini                       repository-level pytest defaults
  conftest.py                      repository-level pytest bootstrap for Windows temp handling
```

## Root-Level Boundary Contract

The repository root is intentionally restrictive.

Only these categories should normally remain at the top level:

- repository metadata and onboarding files,
- repository-wide Python test configuration,
- ecosystem-recognized config and dependency files (`.editorconfig`,
  `.gitattributes`, `.gitignore`, `requirements.txt`, `pytest.ini`),
- main structural directories such as `apps/`, `docs/`, `ops/`, and `tests/`.

The root should not be used as a generic dumping ground for:

- ad hoc utility scripts,
- app-specific launchers,
- deploy-only wrappers,
- browser artifacts,
- local databases,
- copied frontend outputs,
- scratch migration helpers,
- or compatibility packages for historical import paths.

If a file is not repository-scoped, it should not live at the root.

## Why `apps/` Exists And Why There Is No Root `app/`

The repository contains multiple applications and therefore keeps application code under `apps/`.

That is intentional:

- `apps/backend/courseeval_backend/` is the backend Python application package
- `apps/web/school/` is the main school web application for admin, teacher, and student roles
- `apps/web/parent/` is the parent-facing web application

The older root-level `app/` package was removed because it created two sources of truth:

- a conceptual package name used by imports,
- and a different on-disk location for the real code.

That ambiguity is no longer acceptable. Agents should not recreate it.

## Python Namespace Rules

The canonical backend import root is:

- `apps.backend.courseeval_backend`

Examples:

- `from apps.backend.courseeval_backend.core.config import settings`
- `from apps.backend.courseeval_backend.db.database import SessionLocal`
- `from apps.backend.courseeval_backend.api.schemas import UserResponse`
- `from apps.backend.courseeval_backend.api.routers import auth`
- `python -m apps.backend.courseeval_backend.bootstrap`
- `python -m uvicorn apps.backend.courseeval_backend.main:app`

Do not add:

- `from app...`
- `from courseeval_backend...`
- path hacks that depend on manual `PYTHONPATH` edits
- new compatibility forwarding packages

The reason for using the full namespace instead of a shorter alias is practical:

- it works from the repository root without custom environment setup,
- it matches the on-disk layout,
- it makes app ownership explicit,
- it removes the need for import shims.

## Backend Package Layout

The backend package lives in:

- `apps/backend/courseeval_backend/`

Within that package, the current structural intent is:

```text
apps/backend/courseeval_backend/
  __init__.py
  main.py                          FastAPI app assembly and process entrypoint
  bootstrap.py                     bootstrap and repair entrypoint
  api/
    __init__.py
    schemas.py                     API-facing request and response models
    routers/                       FastAPI route modules
  core/
    __init__.py
    auth.py                        authentication helpers and current-user resolution
    config.py                      settings model and environment parsing
    permissions.py                 shared authorization predicates
  db/
    __init__.py
    database.py                    engine, session, Base, and DB dependency wiring
    models.py                      SQLAlchemy models and enums
  domains/
    courses/                       course access and enrollment logic
    homework/                      homework lifecycle helpers
    llm/                           LLM attachment/quota/protocol/routing helpers
    roster/                        user-roster reconciliation logic
    scores/                        score composition and appeal helpers
    seed/                          demo and bootstrap seed helpers
  services/
    logging.py                     operation-log write helpers
  attachments.py                   attachment storage and authorization helpers
  llm_discussion.py
  llm_grading.py
  markdown_llm.py
  semester_utils.py
```

This layout now establishes three foundational layers plus explicit domain subpackages:

- `api/` for HTTP-facing shape and route registration,
- `core/` for configuration, authentication, and shared access rules,
- `db/` for persistence primitives,
- `domains/` for business-domain logic,
- `services/` for the small remaining cross-cutting service layer.

The backend package root should now stay intentionally small. In particular:

- new course logic should prefer `domains/courses/`,
- new roster-reconciliation logic should prefer `domains/roster/`,
- new score composition or score appeal logic should prefer `domains/scores/`,
- new homework lifecycle helpers should prefer `domains/homework/`,
- new LLM routing/quota/protocol helpers should prefer `domains/llm/`,
- new cross-cutting operational service code should prefer `services/` over package-root utility files.

For deeper backend-package guidance, read [BACKEND_PACKAGE_STRUCTURE.md](BACKEND_PACKAGE_STRUCTURE.md).

## Backend Entry Points

The backend process entrypoints are:

- app server: `apps.backend.courseeval_backend.main:app`
- bootstrap module: `python -m apps.backend.courseeval_backend.bootstrap`

These entrypoints are referenced by:

- local development commands,
- Playwright bootstrapping,
- Windows convenience launchers,
- Linux `systemd` service definitions,
- deploy and maintenance scripts.

If you rename or move backend entrypoint modules, update every operational surface in the same change set.

## School Frontend Boundary

The school SPA lives in:

- `apps/web/school/`

This directory owns:

- Vite application code,
- frontend dependencies and lockfile,
- frontend runtime config,
- Playwright startup config for the school app.

Playwright test specs do not live inside the frontend tree. They live in:

- `tests/e2e/web-school/`

That split is intentional:

- app-local config stays with the app,
- repository-wide test suites stay under `tests/`.

## Parent Frontend Boundary

The parent SPA lives in:

- `apps/web/parent/`

It remains a separate app because it has:

- a distinct route base,
- a distinct user journey,
- a distinct deployment surface,
- and a smaller read-only role-oriented feature set.

Do not collapse it into the school frontend unless product and deployment boundaries truly disappear.

## Test Boundaries

Tests live under `tests/` and are grouped by style and purpose:

- `tests/backend/` for focused backend regressions grouped by domain,
- `tests/behavior/` for higher-level workflow and multi-actor behavior,
- `tests/e2e/web-school/` for browser E2E coverage,
- `tests/fixtures/` for test assets,
- `tests/scenarios/` for reusable scenario builders and stress helpers,
- `tests/devtools/` for **non-pytest** Python utilities that operate on the test tree itself (for example, regenerating redundancy audit markdown). Files here must **not** match `test_*.py` so `pytest` discovery ignores them.
- `tests/conftest.py` for repository test defaults beneath the root bootstrap.

The root `conftest.py` remains repository-scoped on purpose. It stabilizes Windows temp-path behavior before test discovery becomes fragile.

Do not move the root `conftest.py` into an app-local subtree unless pytest invocation strategy changes with it.

## Documentation Boundaries

Documentation lives under `docs/` and is organized by topic, not by arbitrary chronology:

- `docs/architecture/` for structural and system-shape documents,
- `docs/agents/` for LLM-agent operating playbooks,
- `docs/contributing/` for Git, encoding, and contributor workflow,
- `docs/frontend/` for browser/UI-state behavior,
- `docs/governance/` for active risks, unresolved ownership, and durable
  repository rules,
- `docs/operations/` for deployment and operational behavior,
- `docs/product/` for feature behavior and user-facing workflow,
- `docs/reference/` for lookup maps and compact domain references,
- `docs/testing/` for validation runbooks, pitfalls, maps, and CSV ledgers,
- `docs/development/` as a sparse compatibility bucket only when a document
  truly does not fit a more specific topic folder,
- `docs/handoffs/` for explicit user-requested committed handoffs,
- `docs/reports/` for dated audits, restructure reports, remediation reports,
  and other historical runbooks that should stay searchable but should not
  clutter the active topic indices.

Keep active guidance in the topic directory. Move completed audit trails and
dated pass reports to `docs/reports/`, then update `docs/README.md`, `AGENTS.md`,
and any task-specific references in the same change.

When a structural refactor changes commands, package paths, or file placement, update at least:

- `README.md`
- `docs/architecture/REPOSITORY_STRUCTURE.md`
- any affected architecture or workflow document
- any ops doc that contains executable commands

## Operations And Deployment Boundaries

Operational assets live under `ops/`:

- `ops/scripts/` for deployment and maintenance scripts,
- `ops/scripts/windows/` for Windows convenience wrappers,
- `ops/nginx/` for reverse-proxy templates,
- `ops/systemd/` for Linux service definitions,
- `ops/ci/` for CI workflow configuration.

Operational files are not application code and should not be mixed into backend or frontend source directories unless they are truly app-local runtime config.

## Local Runtime Artifacts

Directories such as the following may appear on developer machines but are not part of the intended source layout:

- `frontend/`
- `uploads/`
- `test-results/`
- `.pytest_tmp/`
- `.pytest_tmpbasetemp/`
- `.pytest-db/`
- `.e2e-run/`

They are runtime artifacts, local caches, or test byproducts. Do not document them as source architecture, and do not build new source layout around them.

## Rules For Future Structural Changes

When adding or moving files, use these rules:

1. If a file applies to the whole repository, keep it at the root only if it is truly repository-scoped.
2. If a file belongs to one application, keep it under that app's subtree.
3. If a file is deployment-only, keep it under `ops/`.
4. If a file is test-only, keep it under `tests/` unless pytest itself requires a repository-level location. **Test-corpus maintenance scripts** (not pytest modules) belong in `tests/devtools/` — do not recreate a generic top-level `tools/` directory for them.
5. If a file defines HTTP contracts or route registration, prefer `apps/backend/courseeval_backend/api/`.
6. If a file defines shared backend configuration, auth, or permission logic, prefer `apps/backend/courseeval_backend/core/`.
7. If a file defines engine, session, Base, or SQLAlchemy models, prefer `apps/backend/courseeval_backend/db/`.
8. Do not create new compatibility packages or duplicate namespaces to save a few import edits.

## Near-Term Cleanup Direction

The repository is in a better state than before, and a first major backend flattening pass has already been completed.

Interpretation of current state:

- top-level repository shape is already mostly correct and should be preserved
- the backend package root is now reserved primarily for entrypoints and a shrinking set of still-heavy orchestration modules
- the main remaining structural debt is concentrated in large modules such as `llm_grading.py`, `llm_discussion.py`, and `bootstrap.py`

The next structural steps should focus on domain extraction inside `apps/backend/courseeval_backend/`, especially around:

- LLM grading,
- route-heavy homework flows,
- route-heavy subject/course flows,
- and further reduction of monolithic orchestration in `bootstrap.py`.

That work should preserve the current namespace rules and build richer domain subpackages without reintroducing ambiguous import roots.
