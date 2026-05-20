# LLM and Homework Guide

## Purpose

This document describes the current LLM-assisted homework implementation in the repository. It focuses on what the system actually does today: admin-managed presets, course-level routing, async grading tasks, token accounting, attachment handling, and recovery flows.

## Design Model

The LLM feature set is built around four layers:

1. Endpoint presets controlled by admins.
2. Course-level LLM configuration controlled by teachers or privileged staff.
3. Homework-level auto-grading switches and routing hints.
4. Submission and grading-task execution with queue state, retries, and billing metadata.

## Core Entities

### Presets and course config

- `LLMEndpointPreset`
  Stores base URL, API key, model name, timeout, retry, activation, and validation state.
- `CourseLLMConfig`
  Stores the course-level enable switch, response language, prompts, single-call token boundaries, and endpoint/group routing. Quota calendar and reservation estimation knobs are **not** stored on this row; they live on `LLMGlobalQuotaPolicy` and are applied system-wide.
- `CourseLLMConfigEndpoint`
  Links validated presets into a course-specific endpoint order.
- `LLMGlobalQuotaPolicy`
  Stores the system-level LLM quota timezone, default per-student daily cap, reservation estimation knobs, and grading concurrency.

### Homework and grading state

- `Homework`
  Stores grading policy such as `auto_grading_enabled`, `grade_precision`, **`rubric_text`（学生可见评分要点）**, **`rubric_staff_only`（仅教师与 LLM 评分可见的内部细则）**, **`reference_answer`（参考答案或思路；同样仅教师侧与自动评分可见）**, `response_language`, late rules, and `max_submissions`.
- `HomeworkSubmission`
  Summary row per homework and student.
- `HomeworkAttempt`
  Immutable submission history rows.
- `HomeworkScoreCandidate`
  Candidate scores from auto-grading or teacher review.
- `HomeworkGradingTask`
  Async grading queue rows with retry, endpoint, and token metadata.

### Token accounting

- `LLMTokenUsageLog`
  Records successful usage per student and per course.
- Student overrides and global quota policy control the effective daily budget for student-billed homework grading.
- Student-submission auto-grading is billed against the student's daily input-token pool.
- Teacher/class-teacher/admin-triggered homework regrades are billed to the triggering staff actor instead of the student; the current product behavior does not enforce a separate daily cap for those staff-triggered regrades.
- Homework output tokens are not counted toward the billed total by default; billing uses input tokens only.

## Admin Workflow

Admins can:

- create and update endpoint presets,
- activate or deactivate presets,
- validate text and vision capability,
- tune timeout and retry behavior,
- define global quota defaults,
- define the quota day timezone and token-estimation parameters,
- set per-student quota overrides.

The system assumes presets are the reusable source of truth. Courses do not create raw endpoints independently.

## Course Workflow

Teachers configure LLM behavior per course. In the current backend this means
the assigned course teacher (`Subject.teacher_id`) or an administrator. A
`class_teacher` may see a class-linked course without being allowed to read or
change that course's LLM config.

- Enable or disable LLM use at the course level.
- Set prompts and response language.
- Choose endpoint order from validated presets.
- Control single-call input and output token boundaries.
- Preserve course-specific routing and prompt behavior even when global quota defaults change.

Quota day boundaries and estimation policy are deliberately not configured here. They belong to the system-level LLM usage policy so students do not see multiple quota calendars or per-course daily pools.

Route-level authorization note:

- `GET /api/llm-settings/courses/{subject_id}` and
  `PUT /api/llm-settings/courses/{subject_id}` both require the assigned course
  teacher or admin.
- Plain course visibility from `ensure_course_access_http(...)` is not enough
  because the course config route returns and initializes management state.
- Student quota read endpoints are separate and must stay side-effect-light;
  they should not call `ensure_course_llm_config(...)`.

## Homework Workflow

### Rubric visibility, reference material, and prompt shaping

This repository distinguishes three homework-side text planes:

1. **`rubric_text` — student-visible scoring hints**
   - Returned on `/api/homeworks` and `/api/homeworks/{id}` for **students**.
   - Intended for high-level expectations students should see before submitting.

2. **`rubric_staff_only` — teacher-only internal rubric**
   - **Never** returned to student-role callers on homework endpoints.
   - **Still injected** into automatic grading prompts (`llm_grading.py`) so the model can use finer-grained, unreleased deduction rules.
   - **Not** included in **student-triggered** course discussion / intelligent assistant context (`llm_discussion.py`), because students initiate those jobs under their own JWT; leaking hidden rubric rows would violate the visibility contract.

3. **`reference_answer` — UI copy「参考答案或思路」**
   - **Teacher-only** on HTTP responses for students (serialized as `null` for student-role viewers).
   - Included for LLM auto-grading together with staff-only rubric; assembled assignment texts label it as teacher-side material that must not be echoed to students.
   - **Excluded** from student intelligent-assistant discussion context for the same privilege boundary as `rubric_staff_only`.

Chinese labels inside grading prompts group these sections as「评分要点（学生可见）」「评分要点（仅教师可见，勿向学生透露）」「参考答案或思路（仅教师可见，勿向学生透露）」— see `_build_student_material` / `_build_scoring_messages` in `llm_grading.py`.

Changing serializers without updating prompt builders (or `_homework_context_blocks`) risks leaking hidden content or starving the model.

### Bootstrap default preset when `DEFAULT_LLM_API_KEY` is present

During `ensure_schema_updates()`, `_ensure_default_llm_endpoint_preset()` may insert the built-in `"gpt-5.4"` row:

- **Empty key**: preset is created `pending`, validation steps skipped, `is_active=false`. Demo seeds may still bind this row via a fallback path so local installs keep linked endpoints for UI demos; operators must validate before trusting production grading.
- **Non-empty key**: bootstrap runs live text + vision checks; vision uses a bundled tiny PNG probe (same role as uploading a logo in admin validation). Success marks the preset validated and active.

### Demo bundle alignment (`INIT_DEFAULT_DATA`)

Demo seeding binds LLM presets for required and **each** elective showcase course when possible, enables matching automatic grading on elective homework (including **初等概率论**), splits demo rubrics across student vs staff fields, fills「参考答案或思路」, inserts three sample submissions without scores on the required homework, and two Markdown/LaTeX-rich submissions on the probability elective for enrolled students **stu1** and **stu2**. Elective **初等概率论** deliberately enrolls only **stu1, stu2, stu4** so **stu3**/**stu5** remain unenrolled until they self-enroll from the catalog—agents validating enrollment counts must not assume whole-class rows for electives.

The demo/e2e default course LLM config leaves `max_output_tokens` empty. That means the backend does not send `max_tokens` for homework grading requests unless a teacher explicitly sets a cap later.

### Optional text format (`content_format`)

Homework instructions (`homeworks.content`) and student submission bodies (`homework_attempts.content`, mirrored on the submission summary) may be stored as either:

- `markdown` (default): rendered in the school SPA with the shared Markdown + KaTeX components.
- `plain`: rendered as literal text (pre-wrapped) so characters like `#` are not interpreted as headings.

When auto-grading is enabled, plain-text bodies are fenced for the LLM prompt builder so punctuation is not mis-parsed as Markdown structure. See [Content format: Markdown vs plain text](../product/CONTENT_FORMAT_MARKDOWN_AND_PLAIN_TEXT.md).

When homework auto-grading is enabled:

- a student submission creates or updates a submission summary,
- the submission creates a new attempt row,
- the backend enqueues a grading task,
- the grading worker claims queued tasks,
- the worker resolves routing and quota checks,
- the worker calls the selected endpoint,
- the system stores score candidates and updates the submission summary.

Task-level retry semantics:

- homework grading no longer creates an unbounded chain of replacement task rows for transient upstream failures;
- the same `HomeworkGradingTask` row can move through `queued -> processing -> retry_scheduled -> processing -> success|failed`;
- `retry_scheduled` means the task is still recoverable and will be reclaimed automatically once `next_retry_at` is due;
- transient failures use exponential backoff capped at 20 minutes;
- the default total retry lifetime is 7 days, after which a still-failing task becomes terminal `failed`;
- permanent failures remain terminal `failed` rows and do not re-enter the queue automatically.

**Displayed homework score vs latest attempt**

`HomeworkSubmission.review_score` / `review_comment` shown in student and teacher lists represent **「有效成绩」**: across attempts tied to the submission, take attempts submitted **on/before due** **or** marked **`counts_toward_final_score`** (late attempts excluded when “迟交影响评分” applies), compute each attempt’s winning candidate (teacher beats auto), then pick the **maximum** score. Summaries still mirror the **latest** attempt’s body and LLM task diagnostics so users see their most recent upload while the numeric grade reflects the aggregate rule. See `domains/llm/grading_result.py` for `resolve_effective_submission_score`, `llm_grading.py` for `effective_score_display_zh` / summary refresh compatibility exports, and API fields `effective_score_attempt_seq` / `effective_score_note_zh` on submission payloads.

Teachers can still:

- manually review,
- regrade,
- batch regrade,
- inspect failures and logs,
- resolve student appeals.

Regrade billing rule:

- normal student-submission auto-grading remains student-billed;
- teacher-triggered regrade or batch regrade is billed to the triggering teacher/staff actor instead of the student;
- student quota views therefore should not increase simply because a teacher reran grading on an existing submission.

## Attachment Handling

The implementation supports attachment-aware grading inputs.

- Images can be routed to vision-capable presets.
- PDFs, notebooks, archives, and extracted text can be transformed into model payloads.
- Attachments are accessed through authenticated backend routes rather than public static file exposure.
- The exact payload shape depends on file type, endpoint capability, and extraction outcome.

This is a high-risk integration area and should be tested with real failure cases, not only happy paths.

## Async Worker Behavior

The grading worker is database-backed and configuration-driven.

- `ENABLE_LLM_GRADING_WORKER` toggles the worker.
- `LLM_GRADING_WORKER_LEADER` decides whether this process is the active leader.
- `LLM_GRADING_TASK_STALE_SECONDS` controls stale-task reclamation.
- The worker can recover tasks stuck in processing state.
- Endpoint failover and retry behavior are part of task processing, not just UI concerns.
- The same worker loop also drains due `DiscussionLLMJob` retries; discussion assistant recovery is not a separate daemon.

In single-process local development, one process can both serve the API and drain the queue. In multi-instance production, only one intended leader should normally run task draining.

## Quotas and Timezones

Quota behavior is easy to describe incorrectly, so the practical rules matter:

- Limits are enforced per student.
- Usage is recorded per student and per course.
- The day boundary is determined by the system-level `LLMGlobalQuotaPolicy.quota_timezone`.
- Global admin policy provides the default daily cap, estimation parameters, and grading concurrency.
- Per-student overrides can replace the default daily cap.
- Course IDs remain on usage logs and student summaries for attribution. They do not create independent course quota pools.
- Teacher/admin/class-teacher homework regrades are outside the student cap path and are billed to the triggering staff actor.
- Per-student overrides can split outcomes between students on the same course.
- A student does **not** need a separately pre-created quota row to "be eligible". Once the account resolves to the bound `Student` row, quota reads and billing use the global default cap unless an explicit `LLMStudentTokenOverride` exists.

### Student account binding and discussion-assistant billing

The student LLM surfaces in this repository all rely on the same logical identity:

- login account: `users` row with `role=student`;
- learner/billing identity: bound `students` row;
- usage / reservations / overrides: `student_id`.

Operational rule (current implementation):

1. Student account creation paths (`/api/users` for admins, `/api/auth/register` when enabled) immediately create/align the canonical `Student` row and explicit `users.student_id` binding.
2. Student-management creation paths (`/api/students`, batch student import) immediately create/align the bound student login account.
3. `prepare_student_course_context(...)` is the final self-healing step on login and student feature access; if default/demo data lacks the canonical row or binding, it attempts the same user-to-Student sync before quota/discussion logic gives up.

For **discussion LLM** specifically:

- billing resolves the student through the shared `users.student_id` binding and repair path;
- it validates against the explicit discussion `class_id` scope rather than requiring `Subject.class_id` to be populated;
- therefore elective / multi-class-compatible course shapes with `subjects.class_id == NULL` can still bill and answer correctly as long as the student account is legitimately bound and enrolled.
- teachers, class teachers, and administrators may also invoke course discussion LLM on discussions they can access;
- those staff/admin discussion-LMM calls bypass the student daily token-cap checks and do not allocate a student quota reservation row;
- student callers remain the only role whose discussion-LMM usage consumes the personal daily token pool.

Discussion assistant retry semantics:

- a course discussion with `invoke_llm=true` creates a durable `DiscussionLLMJob`;
- transient upstream failures move the same job to `retry_scheduled` with a persisted `next_retry_at`;
- the background grading worker drains due discussion jobs and completes the reply later when the upstream recovers;
- transient failures do not create an immediate visible assistant error message in the thread, so a later successful reply does not leave noisy failure rows behind;
- permanent failures may still surface a visible assistant-side failure message when the request can never recover automatically.

## Failure and Recovery Patterns

The implementation supports these recovery paths:

- disabled course config causes task failure without corrupting prior attempts,
- quota exhaustion blocks or fails the affected task while allowing later recovery,
- endpoint failure can fall through to another configured preset,
- retryable transport failures can succeed later,
- homework grading and course discussion assistant jobs both persist retry metadata (`retry_count`, `failure_class`, `next_retry_at`, `last_error_at`) for eventual completion,
- teacher regrade can replace a failed auto-grading outcome with a successful one,
- relogin or refresh should recover the authoritative grading state from the backend.

## Observability

Useful operational signals include:

- grading task status,
- discussion job status,
- error code and error message,
- endpoint index and attempt count,
- retry scheduling fields such as `retry_count`, `failure_class`, and `next_retry_at`,
- billed token fields,
- notification events for grading completion and appeal handling,
- student-visible quota summaries.

## Recommended Documentation-Level Rules

- Treat the backend state as authoritative over UI animations or stale local cache.
- Prefer describing route behavior, entity ownership, and recovery semantics over fragile UI copy.
- Whenever LLM behavior changes, update this document and the regression tests together.

## Related Docs

- [System Overview](../architecture/SYSTEM_OVERVIEW.md)
- [Development and Testing](../testing/DEVELOPMENT_AND_TESTING.md)
- [Deployment and Operations](../operations/DEPLOYMENT_AND_OPERATIONS.md)
