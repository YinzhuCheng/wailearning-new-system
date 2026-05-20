# System Overview

## What the System Does

CourseEval is a multi-role teaching-management platform for classroom administration, academic records, homework workflows, course materials, notifications, and parent access. It is designed to work as a normal school-management system even when LLM features are disabled, while also supporting course-level AI-assisted grading when configured.

## Major Capability Areas

### Identity and access

- JWT-based authentication for admin, class teacher, subject teacher, and student accounts.
- Optional student self-registration, disabled by default (see `ALLOW_PUBLIC_REGISTRATION` and `PUBLIC_REGISTRATION_VALIDATE_CLASS_EXISTS` in [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md)).
- Parent access through parent codes instead of full user accounts.
- Trusted-host and CORS controls through backend configuration.

### Roles (`UserRole`)

Stored on `users.role` as lowercase strings — see `apps/backend/courseeval_backend/db/models.py`:

| Role value | Typical capability surface |
|------------|----------------------------|
| `admin` | Full API access; bypasses most class-scoped filters; user/class/subject administration. |
| `class_teacher` | Class-scoped visibility; union of courses in `user.class_id` plus courses where `Subject.teacher_id == user.id` — see `get_accessible_courses_query` in `domains/courses/access.py`. |
| `teacher` | Courses where the user is the assigned subject teacher (`Subject.teacher_id`). |
| `student` | Enrolled courses only; learner identity is the bound `students.id` reached through `users.student_id`. |

Parent-code flows (`/api/parent/*`) authenticate with a **different mechanism** than JWT staff/student users — see [../product/PARENT_PORTAL.md](../product/PARENT_PORTAL.md).

For **permission-style helpers** in routers (e.g. `is_teacher`, instructor checks), grep `UserRole` and `core/permissions.py` alongside domain access helpers.

### Class, student, and user administration

- Class creation and maintenance.
- Student roster management and batch import.
- User management for staff and students.
- Reconciliation between student accounts and roster rows during bootstrap and seed flows.
- Batch class reassignment with downstream enrollment synchronization.

### Courses and enrollments

- Subject management for required and elective courses.
- Teacher-to-course ownership.
- Required-course enrollment repair and elective self-enrollment flows (multi-class required bindings via `subject_class_links`; electives do not mirror an administrative class).
- Roster-driven enrollment, enrollment blocking, and class-bound access checks.

### Homework and grading

- Homework publication with due dates, max score, grade precision, late rules, and max-submission limits.
- Student submission history with multiple attempts.
- Teacher review, score candidates, manual regrade, and batch regrade flows.
- Homework-grade appeals and score-composition appeals.

### Course materials and notifications

- Hierarchical material chapters and material placement.
- Course covers are stored on `subjects.cover_image_url`; the student course catalog/cards and the materials page render that URL when present. Demo seed attaches a small built-in SVG data URL to the required demo course only when no cover already exists, so user-uploaded covers are not overwritten.
- Learning notes (`/api/learning-notes`) are separate from course materials: teachers and students can create named, editable notes; new notes default to private owner-only visibility. Public learning notes reuse the stored `visibility="course"` value for compatibility, but their audience is decided by `subject_id`: notes with a course are readable/commentable by users who already have that course access, while public notes without a course are readable/commentable by any authenticated user.
- Class-wide, course-wide, targeted-student, and targeted-user notifications.
- Per-user read-state tracking and mark-all-read behavior.
- Notification support for grading and appeal events.

### Scores, attendance, and points

- Score entry, grade schemes, exam weights, and composition views.
- Attendance tracking and bulk attendance flows. The teaching calendar is no longer a separate sidebar destination; `/teaching-calendar` redirects to `/attendance`, where `TeachingCalendar.vue` is embedded and clicking a rendered course day selects that date for the attendance form.
- Points system for rewards, ranking, and classroom incentive scenarios.

### Parent portal

- Separate frontend application under `/parent/`.
- Parent-code verification and student-bound read-only views.
- Access to scores, notifications, homework, and summary statistics.

## LLM-Centered Features

LLM support is tightly integrated with homework and course configuration.

- Endpoint presets are centrally managed by admins.
- Course-level LLM config controls whether a course uses LLM grading at all.
- Courses maintain endpoint selection order, prompt behavior, response language, and single-call token boundaries.
- LLM daily quota timezone, student daily caps, reservation estimation, and grading concurrency are system-level policy, not course-level policy.
- Auto-grading is async and queue-backed.
- Token usage is tracked per student and per course.
- Attachments are normalized into model-friendly payloads where possible.
- Teachers can recover from failures through regrade flows without losing attempt history.

The implementation details are documented in [../product/LLM_HOMEWORK_GUIDE.md](../product/LLM_HOMEWORK_GUIDE.md).

## Architecture

### Backend

- FastAPI application in `apps/backend/courseeval_backend/`
- Canonical Python import root `apps.backend.courseeval_backend`
- API-facing contracts and route modules under `apps/backend/courseeval_backend/api/`
- Shared auth, config, and permission primitives under `apps/backend/courseeval_backend/core/`
- SQLAlchemy engine/session/models under `apps/backend/courseeval_backend/db/`
- Business-domain helpers under `apps/backend/courseeval_backend/domains/`
- Cross-cutting operational helpers under `apps/backend/courseeval_backend/services/`
- SQLAlchemy models and bootstrap migrations
- PostgreSQL as the primary database
- In-process grading worker controlled by configuration
- File handling and attachment authorization through backend routes

Current backend domain packages:

- `domains/courses/` for course access, enrollment repair, and class-bound rules
- `domains/homework/` for cleanup, appeal, and notification helpers
- `domains/llm/` for attachments, protocol parsing, quota accounting, routing, and admin quota-policy helpers
- `domains/roster/` for student-user synchronization and roster reconciliation
- `domains/scores/` for score composition and score-appeal helpers
- `domains/seed/` for demo-seed and bootstrap seed flows

Important package-root modules that still act as shared runtime boundaries:

- `main.py` for app assembly and startup lifecycle
- `bootstrap.py` for schema repair and normalization entrypoints
- `llm_grading.py` for the grading worker and grading orchestration
- `llm_discussion.py` for discussion-LLM runtime orchestration
- `attachments.py` and `markdown_llm.py` for file and content adaptation concerns

### School frontend

- Vue 3 SPA in `apps/web/school/`
- Element Plus component layer
- Pinia state management
- Playwright E2E coverage in `tests/e2e/web-school/` with config in `apps/web/school/playwright.config.cjs`

### Parent portal

- Separate Vue 3 SPA in `apps/web/parent/`
- Served from `/parent/` in production

### Operational helpers

- Linux deployment assets live in `ops/scripts/`, `ops/systemd/`, and `ops/nginx/`
- Windows convenience launchers live in `ops/scripts/windows/`
- Repository-level pytest bootstrap lives in the root `conftest.py`

The detailed repository boundary rules are documented in [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md).

## Backend Route Groups

Router registration order is visible in `apps/backend/courseeval_backend/main.py` (`app.include_router(...)`). Prefixes below match the `APIRouter(prefix=...)` declarations in `api/routers/*.py`.

**Core product**

- `/api/auth` — login, password flows, optional student registration
- `/api/classes`, `/api/students`, `/api/users` — administration and roster
- `/api/subjects` — courses (the `Subject` model is the persistence “course” row)
- `/api/homeworks` — homework lifecycle, submissions, grading visibility
- `/api/materials`, `/api/material-chapters` — course materials tree
- `/api/discussions` — course homework/material discussion threads (`discussions.py`)
- `/api/notifications` — notifications + read state + `sync-status` lightweight polling
- `/api/scores`, `/api/attendance`, `/api/points`, `/api/semesters` — academic records
- `/api/dashboard` — aggregated dashboard endpoints
- `/api/logs` — operational logging views for staff

- `/api/learning-notes` — owned learning-note CRUD, editable note outline/resources, public note discovery for same-course and all-authenticated scopes, and note-scoped discussion threads. In `main.py`, this router is mounted between homework and course-discussion routers; it is a first-class product route, not a frontend-only feature.

**LLM and appearance**

- `/api/llm-settings` — presets, course LLM config, quota policy
- `/api/appearance` — user theme presets / appearance styles (`appearance.py`)

**Files and parent**

- `/api/files` — uploads, downloads, attachment authorization
- `/api/parent` — parent-code verified read APIs

**E2E / automation (never exposed in production)**

- `/api/e2e` — gated by `settings.expose_e2e_dev_api()` (returns **404** when disabled — router still registered so tests can toggle `E2E_DEV_SEED_ENABLED` without reloading `main`). See `api/routers/e2e_dev.py`, [../testing/VALIDATION_WORKFLOW_AND_TOOLS.md](../testing/VALIDATION_WORKFLOW_AND_TOOLS.md), and [../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md](../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md).

Cross-cutting flow diagrams (submission → DB queue → worker → UI) live in [CORE_BUSINESS_FLOWS.md](CORE_BUSINESS_FLOWS.md).

## Bootstrap Behavior

On application startup, the backend:

- creates tables if needed,
- applies schema updates,
- normalizes teacher/class and semester links,
- synchronizes subject-semester links,
- backfills homework grading data,
- reconciles student users and roster rows,
- optionally seeds demo data,
- re-runs roster reconciliation after demo seeding when seed mode is enabled,
- optionally starts the LLM grading worker leader.

The current `lifespan` sequence in `main.py` is intentionally ordered so that:

- schema and normalization run before domain repair logic,
- roster reconciliation sees the post-normalization model state,
- demo data seeding happens only after the base repair pass is committed,
- and worker startup does not race the bootstrap transaction.

See [../operations/ADMIN_BOOTSTRAP.md](../operations/ADMIN_BOOTSTRAP.md) and [../operations/DEPLOYMENT_AND_OPERATIONS.md](../operations/DEPLOYMENT_AND_OPERATIONS.md).

## Related architecture docs

- [CORE_BUSINESS_FLOWS.md](CORE_BUSINESS_FLOWS.md) — vertical slices (homework grading chain, notifications, E2E gates)
- [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md) — environment variables backed by `Settings`
- [MAINTAINER_AGENT_GUIDE.md](MAINTAINER_AGENT_GUIDE.md) — grep keywords and high-risk modules
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — symptom-first index to pitfalls and ops docs
