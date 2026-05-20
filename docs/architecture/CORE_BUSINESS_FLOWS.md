# Core Business Flows (Implementation-Aligned)

## Purpose

This document traces **how features actually run** in this repository: HTTP entrypoints, domain helpers, persistence, background processing, and how state appears back in clients. It is written primarily for maintainers and LLM coding agents who need to avoid guessing from folder names alone.

When this document conflicts with marketing language or older notes elsewhere, **trust the cited code paths**.

If you change router signatures, queue semantics, or worker startup, update this file in the same change set.

---

## Conventions

- **School SPA**: `apps/web/school/` — Vue 3 + Element Plus; API calls go through `apps/web/school/src/api/` helpers (axios) and typically hit `/api/*` via Vite dev proxy (`apps/web/school/vite.config.js`: `VITE_PROXY_TARGET` defaults to `http://127.0.0.1:8001`).
- **Parent SPA**: `apps/web/parent/` — separate build; dev server defaults to port **5174** (`apps/web/parent/vite.config.js`); same `/api` proxy pattern.
- **Backend**: FastAPI app assembled in `apps/backend/courseeval_backend/main.py`; route modules under `apps/backend/courseeval_backend/api/routers/`; Pydantic contracts in `apps/backend/courseeval_backend/api/schemas.py`.
- **Course access**: Most course-scoped routes call `ensure_course_access` / `ensure_course_access_http` in `apps/backend/courseeval_backend/domains/courses/access.py`. The `_http` variant maps `PermissionError` → **403** and `ValueError` → **404** for consistent API behavior.

---

## 1. Authentication and sessions

### Cross-cutting course access rule

Course visibility and course management are intentionally separate:

- `ensure_course_access_http(subject_id, user, db)` answers "may this user see
  or enter this course?"
- `is_course_instructor(user, course)` answers "may this user manage this
  course-owned state?"

Administrators and the assigned `Subject.teacher_id` may manage course-owned
state. A `class_teacher` who sees a course through `subject_class_links` may
read/list/enter the course where the feature allows it, but that visibility
does not authorize them to mutate another teacher's course.

This rule applies to course update/delete/cover/roster operations, course
materials/homework creation, scores, attendance, course notifications, and
course LLM config. Future course-owned mutation routes should add both the
router guard and a hardening test in
`tests/security/test_security_hardening_followup.py`.

### Entry

- `POST /api/auth/login` — `apps/backend/courseeval_backend/api/routers/auth.py`
- JWT dependency — `apps/backend/courseeval_backend/core/auth.py` (`get_current_user`, `get_current_active_user`, optional JWT for E2E gates)

### Behavior (high level)

1. Client sends credentials; router validates user and returns a JWT (`ACCESS_TOKEN_EXPIRE_MINUTES` from settings).
2. Subsequent requests send `Authorization: Bearer <token>`.
3. Role checks use string values stored on `users.role` aligned with `UserRole` enum — `apps/backend/courseeval_backend/db/models.py` (`admin`, `class_teacher`, `teacher`, `student`).

For **student** accounts, login also finalizes canonical learner context:

4. After successful login, the router caches the role/class decision **before** writing the login `operation_logs` row, then re-queries the user when needed and runs `prepare_student_course_context(...)`.
5. `prepare_student_course_context(...)` resolves the bound `Student` through `users.student_id`, repairs missing default/demo bindings through `sync_student_roster_from_user_accounts` when needed, and then syncs required-course enrollments.

This is important because student quota APIs, homework submission, and discussion LLM billing all depend on the resolved `Student.id`, not merely on `users.id`.

### Related configuration

- `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` — `apps/backend/courseeval_backend/core/config.py`

### Pitfalls

- Forgot-password throttling and registration validation interact with `operation_logs` and optional public registration flags — see [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md).

---

## 2. Course visibility and enrollment

### Entry (examples)

- Subject listing and mutations — `apps/backend/courseeval_backend/api/routers/subjects.py`
- Student elective catalog / enroll / drop — same router (endpoints gated by `UserRole.STUDENT`)
- Class-scoped administration — `apps/backend/courseeval_backend/api/routers/classes.py`, `students.py`, `users.py`

### Domain logic

- **Which courses a user sees** — `get_accessible_courses_query` and related helpers in `domains/courses/access.py`:
  - **Admin**: all subjects.
  - **Student**: subjects linked through `CourseEnrollment` for the canonical `Student` bound by `users.student_id`.
  - **Teacher**: subjects where `Subject.teacher_id == user.id`.
  - **Class teacher**: subjects that have a `subject_class_links` row for the teacher's class, union subjects where the user is the assigned teacher (`Subject.teacher_id`). `Subject.class_id` is a compatibility/display anchor and is not the class-teacher access fallback.

- **Multi-class required offerings** — `subject_class_links` (`SubjectClassLink` ORM) stores `(subject_id, class_id, enrollment_mode)`. Whole-class auto sync only applies to links with `enrollment_mode == all_in_class`. Electives intentionally have **no** links and `Subject.class_id IS NULL`; student self-enroll writes `CourseEnrollment.class_id` from the student's roster class, not from the course.

### Student roster coupling

- `reconcile_student_users_and_roster` runs during app lifespan — `main.py` — and ensures student login identities bind to canonical `Student` rows through `users.student_id`. It may recover default/demo data without a binding, but feature code should not treat `username` and `student_no` as the relationship.

---

## 3. Homework: submission → queue → worker → UI

This is the highest-traffic “vertical slice” for the product.

### 3.1 Student submission (HTTP)

1. **Frontend**: student homework UI calls `POST /api/homeworks/{homework_id}/submission` with body validated by `HomeworkSubmissionCreate` — see `api/schemas.py`.
2. **Router**: `submit_homework` in `api/routers/homework.py`.
3. **Access**: `_ensure_homework_access` / `_resolve_student_for_user` ensure the caller is the roster-linked student for that homework’s class/course.
4. **Roster + enrollment side effects (student logins)**: `prepare_student_course_context` in `domains/courses/access.py` runs on many student requests and can **synchronize** `CourseEnrollment` rows for **required** courses by inspecting `subject_class_links` where `enrollment_mode == all_in_class`. It no longer treats `Subject.class_id == student.class_id` as a course-access fallback, so historical courses must be backfilled into `subject_class_links` before this path can auto-enroll their class roster. Students may therefore gain enrollment implicitly without an explicit teacher click only when the link table is complete. **`_resolve_student_for_user`** still checks enrollment when `homework.subject_id` is set; cross-class cases may hit **`ensure_course_access_http`** first (**403**) before roster mismatch (**404**).

5. **Persistence**:
   - Upserts `HomeworkSubmission` summary row.
   - Inserts immutable `HomeworkAttempt` for each submission.
6. **Auto grade enqueue**: if `homework.auto_grading_enabled`, calls `queue_grading_task(db, attempt, "new_submission")` — defined in `apps/backend/courseeval_backend/llm_grading.py`.
7. **Summary refresh**: `refresh_submission_summary` recomputes denormalized fields on `HomeworkSubmission`. The displayed **「有效成绩」** (`review_score` / `review_comment`) is **not** necessarily tied only to `latest_attempt_id`: among attempts linked to the submission summary, only rows that are **on/before the homework due time** or have **`counts_toward_final_score == true`** participate; the winner is the maximum score after resolving teacher-vs-auto precedence **per attempt**, then taking the global max across those attempts. Tie-break favors higher score, then teacher source, then newer candidate timestamps. Effective-score selection lives in `apps/backend/courseeval_backend/domains/llm/grading_result.py`; `apps/backend/courseeval_backend/llm_grading.py` keeps `refresh_submission_summary`, worker orchestration, and compatibility exports. The summary row still mirrors **latest** attempt body/attachments/`latest_task_*` fields for UX continuity while the score reflects the aggregate rule.
8. **Commit** and response serialized via `_serialize_submission`.

Code anchor for enqueue:

```1059:1061:apps/backend/courseeval_backend/api/routers/homework.py
    if homework.auto_grading_enabled:
        queue_grading_task(db, attempt, "new_submission")
```

### 3.2 Queue model (database-backed, not Redis)

- New rows in `HomeworkGradingTask` with `status="queued"` — created by `queue_grading_task` — `llm_grading.py`.
- Duplicate protection: if a queued/processing task already exists for the attempt, the existing task is reused and submission summary task fields are aligned.

### 3.3 Worker execution

- **Startup**: `main.py` lifespan calls `start_grading_worker()` when `ENABLE_LLM_GRADING_WORKER` and `LLM_GRADING_WORKER_LEADER` are true — only the leader process should drain in multi-worker `gunicorn`.
- **Implementation**: `llm_grading.py` — polling loop + thread pool for LLM HTTP calls; stale task reclamation controlled by `LLM_GRADING_TASK_STALE_SECONDS`.
- **Outcome**: writes `HomeworkScoreCandidate` rows, updates task status/error fields, records token usage through `domains/llm/quota.py`, and may emit notifications via `domains/homework/notifications.py`.

There is **no separate message broker** (no Redis/Celery) in this codebase; the queue is the `homework_grading_tasks` table.

### 3.4 Teacher / admin views

- Lists and batch actions — still `api/routers/homework.py` (e.g. submissions list, batch regrade).
- Regrade paths enqueue new tasks or reuse queue logic depending on operation — follow call sites of `queue_grading_task` and teacher-triggered helpers in the same module.
- **Serialization rule**: `_serialize_homework(..., viewer=current_user)` strips `reference_answer` and `rubric_staff_only` when `viewer.role == student`, while retaining both fields for teachers/admins/creators. Agents altering homework visibility must update serializers and LLM/discussion prompt builders together — see [LLM homework guide](../product/LLM_HOMEWORK_GUIDE.md) «Rubric visibility» section.

### 3.5 Parent portal read path

- Parent-facing aggregated homework/score routes live under `api/routers/parent.py` — they enforce parent-code verification and read student data indirectly; they do not bypass homework access rules for staff routes.
- Parent homework and notification reads combine class/global visibility with
  the linked student's course enrollments. Rows with `subject_id IS NULL` stay
  class/global scoped; rows with `subject_id` require a matching
  `CourseEnrollment(student_id, subject_id)`. This prevents same-class elective
  homework or course notifications from leaking to guardians of students who
  never enrolled in that elective.
- Staff-side parent-code generation/revocation in the same router is not a
  generic course-visible operation. `admin` may manage any student's code, while
  `class_teacher` is limited to students in the class teacher's own
  `users.class_id`. A course linked through `subject_class_links` can make a
  foreign class visible for reading, but it must not let that class teacher
  revoke or regenerate parent codes for students outside their direct class.
  Regular `teacher` users currently follow `get_accessible_class_ids_from_courses(...)`;
  treat any policy change there as a permissions change requiring docs and
  hardening tests.

---

## 4. LLM configuration and quotas

### Admin / teacher configuration HTTP

- `api/routers/llm_settings.py` — presets, course LLM config, global quota policy, student overrides.
- Student-facing quota **read** endpoints avoid side effects that mutate course configuration (quota snapshots read from policy + usage tables).

Course LLM config management (`GET` and `PUT`
`/api/llm-settings/courses/{subject_id}`) is intentionally restricted to the
assigned course teacher or admin. Class-linked `class_teacher` visibility alone
is not sufficient because reading the config initializes/returns management
state through `ensure_course_llm_config(...)`.

### Domain

- Quota math and recording — `domains/llm/quota.py`, `domains/llm/token_quota.py`.
- Routing between endpoint presets — `domains/llm/routing.py`.

### Persistence (conceptual)

- Described in [../product/LLM_HOMEWORK_GUIDE.md](../product/LLM_HOMEWORK_GUIDE.md) — source of truth for table names and field responsibilities.

---

## 5. Materials and chapters

### HTTP

- Materials and placement — `api/routers/materials.py`
- Hierarchical chapters — `api/routers/material_chapters.py`
- Course-directory homework links — `api/routers/material_chapters.py`

### Access

- Instructor checks often use `is_course_instructor` / `ensure_course_access_http` — `domains/courses/access.py`.
- A chapter can link course-level homework through `course_material_homework_links`. This does not move or duplicate homework ownership: `Homework.subject_id` remains the authoritative course scope, while the chapter link is only a course-directory placement.
- Creating/removing homework links is restricted to the course instructor/admin via the same chapter-management gate. Reading the chapter tree still starts with `ensure_course_access_http`, so students only receive links inside courses they can already access.

---

## 6. Notifications

### HTTP

- CRUD and read-state — `api/routers/notifications.py`
- Lightweight poll snapshot — `GET /api/notifications/sync-status` (same visibility as list query helpers in-router).

Course-scoped notification publishing is a management operation. A
`class_teacher` may read notifications for a class-linked course they can
access, but creating or rebinding a notification with `subject_id` requires the
assigned course teacher or admin.

Score-composition appeal rows follow a terminal-state model. Teachers may
reply to a pending `score_grade_appeals` row, but once that row is marked
`resolved` or `rejected` it stays immutable; reopening the workflow happens by
creating a fresh appeal row instead of mutating the finalized one back into an
actionable state.

Global notification publishing is an admin operation. A row with both
`subject_id IS NULL` and `class_id IS NULL` is visible in unscoped notification
streams across roles, so teachers and class teachers must not be able to create
one or update a scoped notice into that shape.

Targeted manual notification writes are validated before persistence. A row may
target one student or one user, but not both. `target_student_id` must match the
selected class and, for course notices, an enrollment in the selected course.
Non-admin staff may only set `target_user_id` to their own user id; admin can
target other users. Notification updates are field-presence aware: omitted
scope/target fields preserve existing values, while explicit JSON `null`
clears a stored scope or target and then applies the same write-scope and
target-scope validation to the effective row. A target switch therefore needs
both sides in the payload, for example clearing `target_student_id` while
setting `target_user_id`; setting the new target alone is rejected if the old
target would remain.

Course-scoped notification reading has two class-scope layers. Admins and the
assigned course teacher see the whole course notification scope, including
class broadcasts for all `subject_class_links`. Students and class teachers
who are not the assigned course teacher see only their own administrative
class plus global rows, so a multi-class required course does not leak another
class's broadcast into a student's header badge, list, detail, or read-state
rows.

### School SPA behavior

- Header badge + polling + `BroadcastChannel` — documented in [../frontend/NOTIFICATION_HEADER_AND_REALTIME_SYNC.md](../frontend/NOTIFICATION_HEADER_AND_REALTIME_SYNC.md).

---

## 7. Learning notes

### HTTP

- `api/routers/learning_notes.py` - prefix `/api/learning-notes`.
- `GET /api/learning-notes?scope=mine|public&subject_id=...` lists owned notes or public notes. The persisted enum value for public notes is still `visibility="course"` for compatibility, but the effective audience is determined by `subject_id`: a public note with a course remains same-course-visible, while a public note with `subject_id IS NULL` is visible to every authenticated user. Public listing with a `subject_id` filter returns only notes bound to that accessible course; public listing without a filter returns unbound public notes plus public notes for courses from `get_accessible_course_ids(current_user, db)`.
- `POST /api/learning-notes` creates a named note. `visibility` defaults to `private`; `visibility="course"` may be saved with a valid accessible `subject_id` for same-course sharing or with `subject_id = NULL` for all-authenticated sharing.
- `GET/PUT/DELETE /api/learning-notes/{note_id}` enforce owner-only mutation and owner-or-public-scope read. Private notes remain owner-only. Public notes bound to a course require normal course access for non-owner readers/commenters. Public notes without a course can be read and discussed by any authenticated user.
- `/{note_id}/chapters` and `/{note_id}/resources` implement an editable note-local outline and resource tree.
- `/{note_id}/discussion` stores note-scoped discussion entries. Private note discussion is readable/commentable only by the owner. Course-visible note discussion is readable/commentable by same-course users.
- Note-discussion create/list payloads also support a `linked_targets` array for structured internal references. Each link is validated against the current caller's visibility when the comment is created, then re-expanded per viewer so inaccessible or deleted targets degrade to an unavailable card instead of exposing stale titles.

### Copy semantics

Learning notes deliberately do **not** reuse `CourseMaterial` rows. When a note is created with `copy_from_subject_id`, the backend copies the course's `CourseMaterialChapter` tree into `LearningNoteChapter` rows owned by the new note. If `copy_materials` is true, each copied resource stores a note-owned snapshot of title/body/content format and keeps attachment URLs by reference through `LearningNoteResource.source_material_id` / `attachment_url`. This avoids physical file duplication while allowing students to freely edit their note structure and resource text.

### LLM discussion behavior

The note discussion assistant reuses the course LLM routing stack (`ensure_course_llm_config` + `_call_discussion_with_routing`) only after the note is associated with a course. Student callers still must resolve to a roster row through the discussion binding helper before an assistant reply is attempted. Current implementation caveat: learning-note assistant replies do **not** reserve or write rows in `LLMQuotaReservation` / `LLMTokenUsageLog` because those quota rows are currently tied to `discussion_llm_jobs` or homework grading jobs. A robust future implementation should add a note-specific LLM job/usage attribution table or generalize quota attribution before claiming parity with course discussion billing.

### School SPA

`apps/web/school/src/views/LearningNotes.vue` exposes the teacher/student sidebar destination `/learning-notes`. It lets users create private notes, optionally copy course outline/materials from accessible courses, publish a note either to same-course users (when a course is selected) or to all authenticated users (when no course is selected), edit the note-local outline/resources, and participate in the note discussion. The composer now includes a structured internal-link picker backed by `/api/discussions/link-targets`, and persisted rows render those links as compact cards. Admin users are intentionally routed away by `adminHiddenPaths`; the feature was requested for teachers and students.

---

## 8. Course discussions (homework / materials threads)

### HTTP

- `api/routers/discussions.py` — prefix `/api/discussions`.
- Access uses `ensure_course_access_http` and `is_course_instructor` patterns consistent with other course features.

Discussion LLM jobs (if enabled for a course) are orchestrated through `api/routers/discussions.py`, `llm_discussion.py`, and the shared runtime helpers under `domains/llm/`.
Current implementation lifecycle:

- `POST /api/discussions` with `invoke_llm=true` writes a durable `DiscussionLLMJob(status="pending")`;
- the router still triggers an immediate best-effort background attempt for low-latency success paths;
- transient failures move the same row to `retry_scheduled` with persisted `retry_count`, `failure_class`, `last_error_at`, and `next_retry_at`;
- the shared runtime classifier decides transient vs permanent using normalized error codes plus HTTP/error-message semantics, so hard provider failures such as `401`, `403`, `404`, and `413` do not keep re-entering the retry lane;
- retry intervals grow exponentially but cap at 20 minutes, and the default total retry lifetime is 7 days before the row becomes permanently failed;
- the grading worker loop in `llm_grading.py` also drains due discussion jobs, so later recovery uses the same process-level worker instead of a second daemon;
- successful completion writes the assistant reply row and discussion usage log, then marks the job `success`;
- permanent failures end in `failed` and may surface a visible assistant-side failure message.

Implementation-aligned student binding rule for discussion LLM:

- the assistant reply path no longer requires `Subject.class_id` to be populated;
- instead it runs the same `prepare_student_course_context(...)` + `get_student_profile_for_user(...)` chain used elsewhere and validates the discussion's explicit `class_id` scope against the resolved roster row;
- this matters for elective / multi-class-compatible course shapes where `subjects.class_id` may be `NULL` while the homework/material discussion itself is still class-scoped and the student is legitimately enrolled.

Implementation-aligned role / quota rule for discussion LLM:

- students may invoke discussion LLM and are billed against the same per-student daily pool used by homework grading;
- teachers, class teachers, and administrators may also invoke discussion LLM on accessible course discussions;
- those staff/admin discussion-LMM calls are **not** gated by student token caps and do not require a `requester_student_id`;
- student-only hidden rubric / reference-answer leakage rules still apply: staff/admin invocation changes quota treatment, not content redaction boundaries.

School SPA discussion list rendering:

- each discussion row now serializes `author_avatar_url` alongside author identity fields;
- the frontend discussion panel fetches authenticated avatar blobs when available and otherwise falls back to role-colored initials (or `助` for the assistant user).

---

## 9. Appearance presets (user themes)

### HTTP

- `api/routers/appearance.py` — prefix `/api/appearance`.

---

## 10. E2E and mock LLM (non-production only)

### Router registration

- `api/routers/e2e_dev.py` mounted under `/api/e2e` with a **dependency** that returns **404** unless `settings.expose_e2e_dev_api()` is true — see `main.py` comments.
- `expose_e2e_dev_api()` is **false** when `APP_ENV` is production or `E2E_DEV_SEED_ENABLED` is false — `core/config.py`.

### Typical automation flow

1. `POST /api/e2e/dev/reset-scenario` with `X-E2E-Seed-Token` seeds users/courses/homework for Playwright.
2. “Powerful” endpoints (mock LLM, forced grading pump) may require **dual gate**: seed token **plus** admin JWT when `E2E_DEV_REQUIRE_ADMIN_JWT=true` — default in `apps/web/school/playwright.config.cjs` for managed subprocesses.

Details: [../testing/VALIDATION_WORKFLOW_AND_TOOLS.md](../testing/VALIDATION_WORKFLOW_AND_TOOLS.md), [../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md](../testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md), and [../testing/TEST_EXECUTION_PITFALLS.md](../testing/TEST_EXECUTION_PITFALLS.md).

---

## 11. Operational logging

### HTTP

- `api/routers/logs.py` — audit / operation logs for administrator views.

---

## Cross-links

- Deployment shape — [../operations/DEPLOYMENT_AND_OPERATIONS.md](../operations/DEPLOYMENT_AND_OPERATIONS.md)
- Full env reference — [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md)
- Test layers and commands — [../testing/VALIDATION_WORKFLOW_AND_TOOLS.md](../testing/VALIDATION_WORKFLOW_AND_TOOLS.md) and [../testing/DEVELOPMENT_AND_TESTING.md](../testing/DEVELOPMENT_AND_TESTING.md)
