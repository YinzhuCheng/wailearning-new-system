# Data model essentials (ORM-oriented)

**Audience:** Agents needing table/field grounding without reading all 800+ lines of `models.py` first.

**Authoritative source:** `apps/backend/courseeval_backend/db/models.py`.

**Schema repair:** additive columns and compatibility DDL live in `bootstrap.py` (`ensure_schema_updates()`). There is **no separate Alembic migration tree** in this repository snapshot — agents rely on `ensure_schema_updates` + `Base.metadata.create_all`.

---

## 1. Identity & roster

| Model | Table | Notes |
|-------|-------|------|
| `User` | `users` | `role` stores `UserRole` string; `class_id` nullable for staff |
| `Class` | `classes` | |
| `Student` | `students` | Canonical learner business row; `student_no` is editable/display identity, while `users.student_id` is the account binding |
| `CourseEnrollment` | `course_enrollments` | Unique `(subject_id, student_id)` |
| `CourseEnrollmentBlock` | `course_enrollment_blocks` | Blocks auto re-sync |

### 1.1 Student roster ↔ student `User` alignment (implementation truth)

The repository maintains one learner business identity plus a bound login account for active students:

1. **`students`** — the canonical learner (`Student`), including class, gender, contact fields, parent code, and student-scoped business references.
2. **`users`** where `role=student` — login account. It binds to the learner through `users.student_id`; `username` and `students.student_no` are kept aligned by repair/sync flows.

**Authoritative source for “who is in the class”:** the **`students` table** (plus `course_enrollments` for per-course views). Login accounts are **not** created through a separate CSV import on the Users screen; instead the backend **`reconcile_student_users_and_roster`** (`domains/roster/sync.py`) runs at application startup and is invoked again on **read/list admin surfaces** so transient drift self-heals:

- `GET /api/students` (list) and `GET /api/students/{id}` call `reconcile_student_users_and_roster` then `commit` before querying/serializing.
- `GET /api/users` (admin list) does the same **before** returning rows.

Additional implementation truth (May 2026):

- **Student-role account creation paths** (`POST /api/users` for admin-created student users and `POST /api/auth/register` for public student registration when enabled) call **`sync_student_roster_from_user_accounts(...)`**. A newly created student login should immediately have a `students` row and an explicit `users.student_id` binding.
- **Student-management creation paths** (`POST /api/students`, batch student import) call **`sync_student_user_from_roster_row(...)`**. Adding a learner row should create/align the student login account and bind it through `users.student_id`.
- **`prepare_student_course_context`** is a final guard for default/demo data that is missing the canonical row or binding. It may invoke the same user-to-Student sync helper before quota, homework, or discussion code continues, but normal feature code should still treat `users.student_id` as the account-to-learner contract.

Effects for agents:

- Do **not** add a second student-import surface under user management. Student import belongs to student management and creates the canonical `Student` plus the bound login account.
- `StudentResponse` (`api/schemas.py`) still serializes `class_id` as optional for legacy compatibility, but normal create/update/repair paths now backfill missing student classes into the reserved temporary class `待分班` instead of leaving active students classless.
- Permission checks on `GET/PUT/DELETE /api/students/{id}` now assume active students are class-bound. Legacy `class_id IS NULL` rows should be repaired into `待分班` rather than treated as a durable product state.
- For LLM quota / discussion billing, the effective identity is the resolved **`Student.id`** from this same binding chain. There is **no** separate pre-created "quota row" requirement; the global default quota policy applies automatically when no `LLMStudentTokenOverride` row exists.

### 1.2 Pitfall catalog (student admin UX)

| Symptom | Likely cause | Mitigation |
|---------|----------------|------------|
| Element Plus **student form** shows two red fields immediately (性别 + 班级) | `StudentForm.vue` used `el-radio value="..."` instead of `label="..."`, so `v-model` never matched an option; combined with NULL `class_id` from API | Fixed radios; `clearValidate()` after `loadStudent()`; reconcile fills class when a matching user exists |
| Slow admin **学生管理** list on huge DB | Full `reconcile_student_users_and_roster` scans all roster + student users each request | Acceptable for demo/small schools; for very large tenants consider moving reconcile to a background job + lighter incremental sync (not implemented here) |


## 2. Courses & materials

| Model | Table | Notes |
|-------|-------|------|
| `Subject` | `subjects` | Course entity; `teacher_id`; legacy `class_id` keeps a **primary** anchor class for FK-heavy rows (first linked class for multi-class required offerings); `course_type` (`required`/`elective`) |
| `SubjectClassLink` | `subject_class_links` | **Required-course multi-class binding**: `(subject_id, class_id)` unique; `enrollment_mode` = `all_in_class` (auto roster sync) or `roster_subset` (manual roster picks only). Electives must have **zero** rows and `subjects.class_id` cleared to `NULL`. |
| `CourseMaterial` | `course_materials` | `content_format` default `markdown` |
| `CourseMaterialChapter` | `course_material_chapters` | Hierarchy + uncategorized bucket |
| `CourseMaterialSection` | `course_material_sections` | Placement linking materials to chapters |
| `CourseMaterialHomeworkLink` | `course_material_homework_links` | Placement linking course-level homework into material/course-directory chapters; homework ownership stays on `Homework.subject_id` |
| `CourseGradeScheme` | `course_grade_schemes` | Weights |
| `CourseExamWeight` | `course_exam_weights` | Exam composition |

### 2.2 Course covers

`Subject.cover_image_url` is the course-cover source of truth. Frontend course-selection cards (`MyCourses.vue`) and the materials banner (`Materials.vue`) render this URL when present. The demo seed gives the required demo course a small inline SVG data URL only when `cover_image_url` is empty; this preserves operator-uploaded covers and keeps demo installs visibly exercising the cover-card path.

### 2.1 Required vs elective class binding (implementation truth, May 2026)

- **必修课**：通过 `subject_class_links` 绑定 **多个** 行政班；每个绑定均有独立的 `enrollment_mode`。
  - `all_in_class`：`sync_course_enrollments` / `sync_student_course_enrollments` 会把对应班级的花名册学生批量写入 `course_enrollments`（仍尊重 `course_enrollment_blocks`）。
  - `roster_subset`：**不会**自动全班入课；教师需在 UI 「从花名册进课」勾选学生（后端 `/api/subjects/{id}/roster-enroll` 校验学生的行政班必须在任一绑定班级内）。
- **选修课**：**不按行政班绑定**。`subjects.class_id` 必须为 `NULL`，也不应有 `subject_class_links` 行；`SubjectResponse.class_name` 对外固定为 `"-"`（ASCII hyphen）。学生自主选课会把 **学生本人** 的 `students.class_id` 写入 `course_enrollments.class_id`（成绩/资料归档仍可有班级字段），但不再要求「课程绑定某一行政班」。
- **花名册进课与选修课**：`POST /api/subjects/{id}/roster-enroll` 对选修课 **不再** 要求课程侧存在行政班绑定；仅要求被勾选学生本身具有 `students.class_id`（与 E2E 风暴用例、管理员人工补录场景一致）。必修课仍要求绑定集合非空，且学生行政班必须属于绑定集合。
- **兼容锚点**：`Subject.class_id` 仍用于 Homework/Materials 部分筛选路径；`refresh_subject_primary_class_id`（`domains/courses/access.py`）在多班级必修课场景将其设为「排序后的首个绑定班级」。管理员 SPA `Subjects.vue`「课程详细」弹窗里考勤/成绩 API 仍按 **primary** 班级过滤——若某作业发布在另一绑定班的 `class_id` 下，汇总可能与「全班聚合视图」不完全一致；深度修复需要调用链传入班级上下文（当前未做）。
- **Bootstrap**：`bootstrap._backfill_subject_class_links()` 负责历史库兼容（选修清空班级列；必修课从旧的单列 `subjects.class_id` 回填链接）。

---

## 3. Homework lifecycle

| Model | Table | Notes |
|-------|-------|------|
| `Homework` | `homeworks` | Instructions; split rubric: `rubric_text` (student-visible), `rubric_staff_only`; `reference_answer` teacher-only; `content_format`; late rules; `auto_grading_enabled` |
| `HomeworkSubmission` | `homework_submissions` | Summary row per student per homework; mirrors latest attempt content; `review_score`/**effective** aggregate |
| `HomeworkAttempt` | `homework_attempts` | Versioned attempts; `counts_toward_final_score`, `is_late` |
| `HomeworkScoreCandidate` | `homework_score_candidates` | Parallel scores (`source`: auto/teacher, …) |
| `HomeworkGradingTask` | `homework_grading_tasks` | Async LLM grading tasks |
| `HomeworkGradeAppeal` | `homework_grade_appeals` | Appeals |

**Effective score (product semantics):** aggregation crosses attempts according to eligibility rules implemented in `domains/llm/grading_result.py` (`resolve_effective_submission_score`, `attempt_eligible_for_effective_score_aggregate`) and re-exported by `llm_grading.py` for existing callers. Summary row still reflects **latest** attempt body for UX — see [`../architecture/CORE_BUSINESS_FLOWS.md`](../architecture/CORE_BUSINESS_FLOWS.md).

---

## 4. LLM configuration & usage accounting

| Model | Table | Notes |
|-------|-------|------|
| `LLMEndpointPreset` | `llm_endpoint_presets` | Vendor config + validation fields |
| `CourseLLMConfig` | `course_llm_configs` | Per-course LLM settings |
| `CourseLLMConfigEndpoint` | `course_llm_config_endpoints` | Ordered preset attachments |
| `LLMGroup` / members | `llm_groups`, membership tables | Routing groups |
| `LLMGlobalQuotaPolicy` | `llm_global_quota_policies` | Single-row global policy |
| `LLMStudentTokenOverride` | `llm_student_token_overrides` | Per-student caps |
| `LLMTokenUsageLog` | `llm_token_usage_logs` | Billing attribution |
| `LLMQuotaReservation` | `llm_quota_reservations` | Reservation rows |

Legacy quota columns on `course_llm_configs` were dropped on Postgres via `ensure_schema_updates` — SQLite attempts best-effort `ALTER DROP COLUMN`.

---

## 5. Discussions & notifications

| Model | Table | Notes |
|-------|-------|------|
| `LearningNote` | `learning_notes` | User-owned note; `visibility` is `private` or `course`. The `course` value means "public" in the current API: with `subject_id` it is same-course-visible, and with `subject_id IS NULL` it is visible to every authenticated user. |
| `LearningNoteChapter` | `learning_note_chapters` | Note-local editable outline copied from course material chapters or created freely. |
| `LearningNoteResource` | `learning_note_resources` | Note-owned resource snapshot/reference; can copy course material text and keep attachment URLs by reference without duplicating files. |
| `LearningNoteDiscussionEntry` | `learning_note_discussion_entries` | Discussion messages scoped to one learning note; private notes remain owner-only, course-bound public notes use course access, and unbound public notes allow any authenticated participant. |
| `CourseDiscussionEntry` | `course_discussion_entries` | Thread bodies; `body_format` |
| `Notification` | `notifications` | Multiple targeting modes |
| `NotificationRead` | `notification_reads` | Read receipts |

### 5.1 Learning-note implementation notes

Learning notes intentionally do not reuse `CourseMaterial` rows. Course materials remain teacher-published course state, while learning notes are owner-editable state that students may create. Copying a course outline writes new `LearningNoteChapter` rows; copying materials writes `LearningNoteResource` rows with copied title/content/content format plus `source_material_id` and attachment URL references. Backend DDL compatibility is in `bootstrap.ensure_schema_updates()` because this repository has no separate Alembic tree.

Visibility semantics are intentionally encoded as two columns rather than a three-value enum in this branch. `visibility="private"` is owner-only regardless of `subject_id`. `visibility="course"` with a non-null `subject_id` is public only inside the normal course-access boundary. `visibility="course"` with a null `subject_id` is public to every authenticated user, so public listing queries must include `LearningNote.subject_id.is_(None)` in addition to course ids from `get_accessible_course_ids(...)`. Do not reintroduce a validator that rejects public notes without a course unless the product requirement changes and the UI/docs are updated in the same patch.

Current LLM caveat: `learning_note_discussion_entries` can receive assistant replies through the course LLM routing stack, but the note path does not yet have a dedicated quota reservation/job table. Do not assume `LLMQuotaReservation` or `LLMTokenUsageLog` contains learning-note assistant usage until a future schema generalizes quota attribution.

---

## 6. Logging & appearances

| Model | Table | Notes |
|-------|-------|------|
| `OperationLog` | `operation_logs` | Login / actions |
| `UserAppearanceStyle` | `user_appearance_styles` | Theme configs |

---

## 7. Naming traps

- **`Subject` ≠ generic English subject** — means **course offering** in most UI/API contexts (`/api/subjects`).
- **Teacher演示账号 vs roster `teacher_id`:** demo seed assigns roster students to primary demo teacher even when multiple teacher accounts exist — enrollment demos may still link to class roster teacher.

---

## 8. 待人工确认

- Whether every auxiliary table has parity coverage in `ensure_schema_updates` for greenfield SQLite installs under adversarial import orders — if pytest flakes arise, capture stack traces in [`../governance/known-issues-and-risks.md`](../governance/known-issues-and-risks.md).
