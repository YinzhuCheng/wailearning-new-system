# Code map and entrypoints

**Purpose:** File-level orientation for agents — **what exists and where**, aligned to the **current tree** (not aspirational architecture).

**Naming:** Product branding uses **CourseEval**. Retired pre-CourseEval names should appear only in historical notes, append-only test ledgers, or explicit "do not restore" warnings; current ops paths and code use CourseEval names.

---

## 1. Repository top level

| Path | Role |
|------|------|
| [`README.md`](../../README.md) | Human + agent entry; quick start; links to `docs/README.md` |
| [`AGENTS.md`](../../AGENTS.md) | Agent handbook (dense pointers) |
| [`requirements.txt`](../../requirements.txt) | Backend Python deps |
| [`pytest.ini`](../../pytest.ini) | `testpaths = tests` |
| [`conftest.py`](../../conftest.py) | Repo-root pytest hooks (Windows temp dir hardening) |
| [`tests/conftest.py`](../../tests/conftest.py) | **Critical:** sets `DATABASE_URL`, disables demo seed during pytest, worker defaults |
| [`ops/`](../../ops/) | nginx, systemd, CI YAML (`ops/ci/*.yml`), deploy shell scripts |
| [`tests/devtools/`](../../tests/devtools/) | Test-tree maintenance scripts (not collected by pytest); start at [`tests/devtools/README.md`](../../tests/devtools/README.md) |
| [`apps/backend/courseeval_backend/`](../../apps/backend/courseeval_backend/) | Canonical FastAPI package |
| [`apps/web/school/`](../../apps/web/school/) | School SPA + Playwright |
| [`apps/web/parent/`](../../apps/web/parent/) | Parent SPA |

---

## 2. Backend entrypoints

| File | Responsibility |
|------|------------------|
| [`main.py`](../../apps/backend/courseeval_backend/main.py) | FastAPI app; middleware; **router includes**; `/health`; Bing wallpaper helper `/api/bing-background`; lifespan startup |
| [`core/config.py`](../../apps/backend/courseeval_backend/core/config.py) | `pydantic-settings` `Settings`; env parsing; production validators (`expose_e2e_dev_api`) |
| [`core/auth.py`](../../apps/backend/courseeval_backend/core/auth.py) | Password hashing, JWT creation/decoding |
| [`core/permissions.py`](../../apps/backend/courseeval_backend/core/permissions.py) | Role booleans (`is_admin`, `is_teacher`, …) — coarse helpers |
| [`bootstrap.py`](../../apps/backend/courseeval_backend/bootstrap.py) | `ensure_schema_updates()` compatibility DDL; demo LLM preset seed; homework backfills |
| [`db/database.py`](../../apps/backend/courseeval_backend/db/database.py) | `engine`, `SessionLocal`, `Base` declarative |
| [`db/models.py`](../../apps/backend/courseeval_backend/db/models.py) | SQLAlchemy ORM models (large) |
| [`api/schemas.py`](../../apps/backend/courseeval_backend/api/schemas.py) | Pydantic request/response compatibility barrel; imports and re-exports split DTO groups while preserving current router/test import paths |
| [`api/schema_defs/`](../../apps/backend/courseeval_backend/api/schema_defs/) | Domain-grouped API schema definitions currently holding appearance, attendance, dashboard, files, notifications, operations/settings, points, and roster DTOs |
| [`api/routers/*.py`](../../apps/backend/courseeval_backend/api/routers/) | HTTP routers (see §3) |
| [`llm_grading.py`](../../apps/backend/courseeval_backend/llm_grading.py) | Grading orchestration, **in-process worker manager**, summary refresh, and compatibility exports for grading helpers |
| [`domains/llm/grading_prompt.py`](../../apps/backend/courseeval_backend/domains/llm/grading_prompt.py) | Homework grading prompt section markers, LLM-assist disclosure text, and markdown field expansion helpers |
| [`domains/llm/grading_result.py`](../../apps/backend/courseeval_backend/domains/llm/grading_result.py) | Homework grading score normalization, per-attempt candidate precedence, and cross-attempt effective-score selection helpers |
| [`llm_discussion.py`](../../apps/backend/courseeval_backend/llm_discussion.py) | Course discussion assistant context assembly |
| [`attachments.py`](../../apps/backend/courseeval_backend/attachments.py) | Upload directory prep; attachment reference checks |
| [`domains/courses/access.py`](../../apps/backend/courseeval_backend/domains/courses/access.py) | Course visibility queries, enrollment sync, `ensure_course_access_http` |
| [`domains/courses/class_links.py`](../../apps/backend/courseeval_backend/domains/courses/class_links.py) | Required-course class-link replacement, duplicate detection, and course-create helper rules used by `api/routers/subjects.py` |
| [`domains/courses/enrollment.py`](../../apps/backend/courseeval_backend/domains/courses/enrollment.py) | Course enrollment serialization plus roster-student creation and roster-enroll helper loops used by `api/routers/subjects.py` while the router keeps HTTP/auth orchestration |
| [`domains/courses/class_scope.py`](../../apps/backend/courseeval_backend/domains/courses/class_scope.py) | Shared class-scope helpers (`get_accessible_class_ids`, `apply_class_id_filter`) used by class-adjacent routers without router-to-router imports |
| [`domains/courses/metadata.py`](../../apps/backend/courseeval_backend/domains/courses/metadata.py) | Course metadata normalization and response serialization helpers used by `api/routers/subjects.py` while the router keeps HTTP orchestration |
| [`domains/homework/serialization.py`](../../apps/backend/courseeval_backend/domains/homework/serialization.py) | Pure homework response helpers for preview text and grading-task call-log extraction |
| [`domains/homework/submission_rules.py`](../../apps/backend/courseeval_backend/domains/homework/submission_rules.py) | Pure homework submission attempt rules for late detection and effective-score eligibility flags |
| [`domains/seed/demo.py`](../../apps/backend/courseeval_backend/domains/seed/demo.py) | `seed_demo_course_bundle` — demo seed orchestration entrypoint |
| [`domains/seed/demo_courses.py`](../../apps/backend/courseeval_backend/domains/seed/demo_courses.py) | Demo course setup helpers: required-course construction, class links, LLM binding, course time JSON, grade weights, and enrollment sync |
| [`services/logging.py`](../../apps/backend/courseeval_backend/services/logging.py) | `LogService` — persists login and actions to `operation_logs` |

---

### Seed domain helpers

`domains/seed/demo.py` remains the public `seed_demo_course_bundle` entrypoint
for demo course, material, homework, and runtime-activity orchestration.
`domains/seed/demo_courses.py` owns reusable demo course setup that should stay
behind that entrypoint: required-course construction, class links, course time
JSON, LLM binding, grade weights, and required-course enrollment sync.
`domains/seed/demo_users.py` owns the demo teacher accounts, demo class,
student users, and roster-row construction used by that entrypoint.

## 3. HTTP routers (actual includes in `main.py`)

Routers live under `apps/backend/courseeval_backend/api/routers/`.

| Module | Typical prefix / notes |
|--------|-------------------------|
| `auth.router` | `/api/auth/*` — login, tokens |
| `classes.router` | Class CRUD |
| `students.router` | Student roster + user linkage |
| `scores.router` | Score entries |
| `attendance.router` | Attendance |
| `appearance.router` | User theme / appearance styles |
| `dashboard.router` | Dashboard aggregates |
| `subjects.router` | **Courses** (ORM `Subject`) |
| `users.router` | Staff/student user admin |
| `semesters.router` | Semester catalog |
| `logs.router` | Operation log queries |
| `points.router` | Points |
| `settings.router` | System settings (imported as `system_settings`) |
| `llm_settings.router` | Global LLM presets + quotas |
| `files.router` | Authenticated uploads/downloads |
| `homework.router` | Homework CRUD, submissions, grading tasks, appeals |
| `learning_notes.router` | `/api/learning-notes` — owned learning-note CRUD, public note discovery, note outline/resource editing, note discussion |
| `discussions.router` | Course discussions |
| `material_chapters.router` | Material hierarchy |
| `materials.router` | Materials CRUD |
| `notifications.router` | Notifications + read state |
| `parent.router` | Parent-code authenticated routes |
| `e2e_dev.router` | `/api/e2e/dev/*` — **gated** by `expose_e2e_dev_api()` |

**Exact path strings:** grep `@router.*prefix` inside each file — OpenAPI `/docs` is authoritative for live enumeration.

---

## 4. Frontend — school SPA

| Path | Role |
|------|------|
| [`apps/web/school/package.json`](../../apps/web/school/package.json) | Scripts: `dev`, `build`, `test:e2e` (Playwright) |
| [`apps/web/school/vite.config.js`](../../apps/web/school/vite.config.js) | Dev server + proxy |
| [`apps/web/school/playwright.config.cjs`](../../apps/web/school/playwright.config.cjs) | E2E ports (`E2E_API_PORT`, `E2E_UI_PORT`) |
| [`apps/web/school/src/main.js`](../../apps/web/school/src/main.js) | Vue bootstrap |
| [`apps/web/school/src/router/index.js`](../../apps/web/school/src/router/index.js) | Routes + `meta.requiresAdmin` style gates (UI only) |
| [`apps/web/school/src/api/index.js`](../../apps/web/school/src/api/index.js) | Axios client, interceptors, validation error formatting |
| [`apps/web/school/src/stores/user.js`](../../apps/web/school/src/stores/user.js) | Pinia user session |
| [`apps/web/school/src/views/HomeworkSubmissionReview.vue`](../../apps/web/school/src/views/HomeworkSubmissionReview.vue) | Teacher **全页阅卷**：`/homework/:homeworkId/submissions/:submissionId` — renders latest submission body via `PlainOrMarkdownBlock`, score/comment editor, collapsible attempt history, LLM log dialog; backed by `GET /api/homeworks/{id}/submissions/{submission_id}/status`. |
| [`apps/web/school/src/views/Attendance.vue`](../../apps/web/school/src/views/Attendance.vue) | Attendance management; embeds `TeachingCalendar.vue` so clicking a rendered course day selects the attendance date and reloads that day's records. Historical `/teaching-calendar` deep links redirect here; there is no retained standalone page component. |
| [`apps/web/school/src/views/LearningNotes.vue`](../../apps/web/school/src/views/LearningNotes.vue) | Teacher/student learning notes at `/learning-notes`: private-by-default note CRUD, optional course outline/material copy, course-visible public notes, note outline/resource editing, and note discussion. |
| [`apps/web/school/src/views/*.vue`](../../apps/web/school/src/views/) | Pages |
| [`apps/web/school/src/components/*.vue`](../../apps/web/school/src/components/) | Shared UI (e.g. `MarkdownEditorPanel.vue`, `RichMarkdownDisplay.vue`) |

---

## 5. Frontend — parent SPA

| Path | Role |
|------|------|
| [`apps/web/parent/package.json`](../../apps/web/parent/package.json) | Scripts analogous to admin |
| [`apps/web/parent/src/`](../../apps/web/parent/src/) | Routes + views for parent-code flows |

Detail: [`product/PARENT_PORTAL.md`](../product/PARENT_PORTAL.md).

---

## 6. Tests

| Path | Role |
|------|------|
| [`tests/backend/`](../../tests/backend/) | Primary FastAPI integration/unit clusters |
| [`tests/behavior/`](../../tests/behavior/) | Cross-cutting behavior specs |
| [`tests/e2e/web-school/`](../../tests/e2e/web-school/) | Playwright specs (invoked from school package) |
| [`tests/postgres/`](../../tests/postgres/) | PG-specific tests (conditional skip) |
| [`tests/db_reset.py`](../../tests/db_reset.py) | `reset_test_database_schema()` — `drop_all` + `create_all` |

---

## 7. Deployment / automation

| Path | Role |
|------|------|
| [`ops/ci/pr-pipeline.yml`](../../ops/ci/pr-pipeline.yml) | Reference CI: Python `3.11`, `python -m pip install -r requirements.txt`, `python -m pytest -q` |
| [`ops/systemd/courseeval-backend.service`](../../ops/systemd/courseeval-backend.service) | systemd unit template |
| [`ops/nginx/courseeval.example.conf`](../../ops/nginx/courseeval.example.conf) | Example nginx |
| [`ops/scripts/deploy_backend.sh`](../../ops/scripts/deploy_backend.sh) | Deploy helper |
| [`ops/scripts/dev/repo_line_health.py`](../../ops/scripts/dev/repo_line_health.py) | Repository line-count health metrics: documentation, tests, primary source, and supporting categories |
| [`ops/scripts/dev/search_pitfalls.py`](../../ops/scripts/dev/search_pitfalls.py) | Fuzzy lookup across pitfall docs, pitfall CSV index, troubleshooting notes, development testing guidance, and repo-local skills before failure triage |

---

## 8. Generated / local artifact dirs (not source)

See [`architecture/REPOSITORY_STRUCTURE.md`](../architecture/REPOSITORY_STRUCTURE.md). Common false positives: `uploads/`, `.pytest_tmp/`, `test-results/`, `dist/`.

---

## 9. Deliberately absent (do not grep forever)

- **No Redis/Celery queue** in-repo for LLM grading — queue is SQL (`homework_grading_tasks`).
- **No full GitHub Actions validation matrix** yet. A lightweight workflow exists at
  [`.github/workflows/lightweight-validation.yml`](../../.github/workflows/lightweight-validation.yml),
  while external DevOps examples still live under [`ops/ci/`](../../ops/ci/).
  PostgreSQL-backed pytest, RAR-dependent attachment coverage, and Playwright
  E2E are not yet fully cloud-orchestrated.

---

## 10. Expanded grep map

Use this section when the short grep map in `AGENTS.md` is not enough.

| Intent | Keywords / symbols |
|--------|---------------------|
| Course visibility | `get_accessible_courses_query`, `ensure_course_access_http`, `prepare_student_course_context` |
| Instructor checks | `is_course_instructor`, `subject_teacher_user_ids` |
| Homework serialization | `_serialize_homework`, `_serialize_submission`, `effective_score_note_zh`, `resolve_effective_submission_score` |
| Grading queue | `HomeworkGradingTask`, `queue_grading_task`, `claim_grading_tasks_batch`, `process_grading_task`, `process_next_grading_task` |
| Worker lifecycle | `start_grading_worker`, `worker_manager`, `_WorkerManager` |
| Quota | `precheck_quota`, `reserve_quota_tokens`, `LLMGlobalQuotaPolicy` |
| Demo seed | `seed_demo_course_bundle`, `INIT_DEFAULT_DATA`, `domains/seed/demo.py` |
| Schema repair | `ensure_schema_updates`, `bootstrap.py` |
| E2E seed | `expose_e2e_dev_api`, `E2E_DEV_SEED_ENABLED`, `/api/e2e/dev/` |
