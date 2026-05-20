# Permissions and security boundaries

**Audience:** Agents implementing features without silently widening attack surface.

**Principle:** FastAPI dependencies + domain helpers enforce authorization. Vue `meta` flags are **UX hints only**.

---

## 1. Role enumeration (`UserRole`)

**Source:** `apps/backend/courseeval_backend/db/models.py` (`UserRole` enum).

| Stored value (`users.role`) | Typical meaning |
|----------------------------|-----------------|
| `admin` | Full administration; bypasses many class filters via queries |
| `class_teacher` | Can see class-linked courses through `subject_class_links` **plus** courses they instruct (`Subject.teacher_id`); class-linked visibility is not course management permission |
| `teacher` | Subject teacher — primarily courses where `Subject.teacher_id == user.id` |
| `student` | Student — enrolled courses only (via `CourseEnrollment`) |

**Parents:** not `UserRole`. Parent flows authenticate via parent codes (`/api/parent/*`) — see [`../product/PARENT_PORTAL.md`](../product/PARENT_PORTAL.md).

---

## 2. Coarse helpers (`core/permissions.py`)

Functions like `is_admin`, `is_teacher`, `can_manage_scores` answer **role membership**, not **object ownership**.

**Risk:** Using only these for APIs that mutate another teacher’s course is insufficient — combine with course/subject checks.

---

## 3. Course visibility & access (`domains/courses/access.py`)

Key symbols:

| Symbol | Purpose |
|--------|---------|
| `get_accessible_courses_query(user, db)` | Builds filtered `Subject` query per role |
| `prepare_student_course_context` | Student login path repairs roster/enrollment alignment |
| `ensure_course_access(course_id, user, db)` | Raises `PermissionError` if not accessible |
| `ensure_course_access_http` | Same → HTTP 403/404 |
| `is_course_instructor(user, course)` | Admin **or** assigned `Subject.teacher_id` |
| `sync_course_enrollments` | Required courses: ensures enrollments for class roster; electives skipped |
| `sync_student_course_enrollments` | Student-side repair for required courses |
| `CourseEnrollmentBlock` | Prevents auto re-enrollment after explicit removal |

**Elective rule:** `sync_course_enrollments` returns early when `course_type == elective` — elective enrollment is explicit (`CourseEnrollment` rows from self-enroll API or seeds like partial demo enrollments).

---

### Visibility is not management permission

`ensure_course_access_http(subject_id, current_user, db)` proves that the caller
may see or enter a course. It does **not** prove that the caller may mutate the
course or write business records into it.

Current management rule for course-owned writes:

- `is_course_instructor(user, course)` is the shared ownership predicate.
- It returns true for administrators and for the assigned course teacher
  (`Subject.teacher_id == user.id`).
- A `class_teacher` who sees a course only because it is linked to their class
  through `subject_class_links` is a reader/observer for that course, not the
  course manager.

The distinction was hardened after repeated May 2026 security runs found
`class_teacher` users could mutate teacher-owned visible courses through
multiple routes. Future route work must keep this layering:

1. use `ensure_course_access_http(...)` for course visibility and read/list
   scopes;
2. add `is_course_instructor(...)` or a small route-local wrapper before any
   course-owned mutation;
3. keep no-subject class-wide workflows on class filters only when the record is
   truly class-scoped.

Course-owned mutation surfaces that currently require the assigned teacher or
admin include:

- subject/course update, delete, cover upload, roster sync, roster enroll,
  enrollment-type update, and student removal;
- course material creation and course homework creation;
- score creation/update/delete, batch score import, exam weights, grade schemes,
  and score-appeal responses;
- attendance create/update/delete plus batch and class-batch course attendance;
- course notification publish/update when `subject_id` is set;
- global notification publish/update when both `subject_id` and `class_id` are
  empty is admin-only; teachers and class teachers must bind manual
  notifications to an assigned course or an accessible class and may not widen a
  class/course notice into a global broadcast;
- discussion entry deletion and course-material chapter placement/reorder/link
  operations;
- course LLM config `GET` and `PUT` under
  `/api/llm-settings/courses/{subject_id}`.

Tests that guard this boundary live in
`tests/security/test_security_hardening_followup.py` and
`tests/e2e/web-school/e2e-security-hardening-followup.spec.js`. Extend those
files when adding a new course-owned mutation route.

---

### Parent Code Management

Parent-code verification is a read-oriented guardian flow, but code generation
and revocation are staff-side management operations under `api/routers/parent.py`.
The class-teacher rule is intentionally narrower than general course visibility:

- `admin` may manage parent codes for any student.
- `class_teacher` may generate or revoke parent codes only for students whose
  `Student.class_id` is exactly the class teacher's `users.class_id`.
- A class teacher's ability to see a foreign class through a course linked by
  `subject_class_links` is not enough to manage that student's parent code.
- Non-class-teacher `teacher` users still route through
  `get_accessible_class_ids_from_courses(...)`; if product policy later wants a
  stricter direct-teacher rule, update `api/routers/parent.py`, this document,
  and the parent-code tests together.

The hardening regression is
`test_hard50_class_teacher_cannot_revoke_parent_code_for_foreign_class_student_only_visible_through_course_link`
in `tests/security/test_security_hardening_followup.py`.
Batch generation follows the same authorization policy and deduplicates
repeated student ids in one request so one caller cannot rotate the same
student's code multiple times through a duplicated payload.

Parent-code read endpoints are also student-scoped. `/api/parent/scores` and
`/api/parent/stats` use the linked `Student.id`. `/api/parent/homework` and
`/api/parent/notifications` may include class/global rows, but any row carrying
`subject_id` must also match a `CourseEnrollment` for the linked student. Same
administrative class is not enough to expose elective course homework or
notifications to that student's guardian.

Notification read-state writes use the same visibility boundary as notification
lists. `POST /api/notifications/{id}/read` first proves the current JWT user can
see the notification through `_visible_notifications_query(...)`; existing but
invisible notification ids return 403 and do not create `notification_reads`
rows. Student visibility additionally requires a matching enrollment for
subject-scoped notifications, while `subject_id IS NULL` class/global rows
remain visible when the class and target-student filters allow them. When a
notification list or read-state endpoint is explicitly scoped by `subject_id`,
course-scoped broadcasts (`Notification.subject_id IS NULL`) are limited to
global rows or rows whose `class_id` is linked to that course via
`subject_class_links`; another class's broadcast must not appear merely because
the caller can access the requested course. For multi-class courses, admin and
assigned course teachers retain a course-wide notification view across every
linked class. Students and non-instructor class teachers remain class-local:
they can read only rows for their own class plus global `class_id IS NULL`
rows, even when the selected course links multiple administrative classes.

Notification write scope is narrower than read scope. Administrators may create
or update global notices (`subject_id IS NULL` and `class_id IS NULL`) because
those rows intentionally reach every role's unscoped notification stream.
Teachers and class teachers cannot create those rows directly and cannot update
an existing class/course notice to clear both scope columns. This prevents a
course or class notification composer from becoming a site-wide broadcast tool.
The create path treats `class_id=0` the same as an empty class for this guard so
clients cannot create malformed `subject_id IS NULL`, `class_id=0` rows.

Notification target fields are also write-validated. A manual notification may
target either one student (`target_student_id`) or one staff/user account
(`target_user_id`), but not both. Targeted student notices must point at an
existing student in the selected class when `class_id` is present, and at a
student enrolled in the selected course when `subject_id` is present. Non-admin
staff may only set `target_user_id` to their own user id; administrators may
target other users. These checks happen before persisting create/update payloads
so later UI or query changes cannot accidentally expose malformed targeted
notification rows. Update payloads distinguish an omitted field from an
explicit JSON `null`: omitting `target_student_id` / `target_user_id`,
`subject_id`, or `class_id` preserves the existing value, while sending `null`
clears the stored value and re-runs the same write-scope and target-scope
checks on the resulting row. Switching from a student target to a user target,
or the reverse, must explicitly clear the old target in the same request;
otherwise the effective row would contain both targets and is rejected.
Non-admin staff still cannot clear both `subject_id` and `class_id` into a
global notice, even when they also clear the target field.

---

### Subject-scoped route ordering rule

When a FastAPI route is explicitly scoped by `subject_id` / course id, validate
that course first:

```python
course = ensure_course_access_http(subject_id, current_user, db)
```

Only apply `get_accessible_class_ids(...)`, `apply_class_id_filter(...)`, or
`Subject.class_id.in_(...)` as the primary authorization filter for class-wide
routes that do **not** have a course scope. Do not return `[]` or raise `403`
just because the derived class-id set is empty before checking course access.

Why this matters:

- `teacher` users often own courses through `Subject.teacher_id` without having
  a `user.class_id`.
- `class_teacher` users may see courses through `subject_class_links`.
- elective courses may have `Subject.class_id = None` and still contain valid
  `CourseEnrollment` rows.
- score, dashboard, homework, material, notification, attendance, discussion,
  and file-download surfaces all need course-owned access to work even when a
  class-only filter would be empty.

Safe pattern:

1. If `subject_id` is present, call `ensure_course_access_http(...)`.
2. If the operation mutates course-owned state, call `is_course_instructor(...)`
   or a route-local wrapper that enforces the assigned-teacher/admin rule.
3. Build the query from the course/subject predicate, for example
   `Score.subject_id == subject_id`.
4. Apply optional `class_id` filters only as additional narrowing, not as the
   initial permission gate.
5. For no-`subject_id` list endpoints, keep class-wide filtering via
   `get_accessible_class_ids(...)` / `apply_class_id_filter(...)`.

---

## 4. Homework & grading (patterns)

Homework routers (`api/routers/homework.py`) generally:

1. Resolve current user (`get_current_user`).
2. Load homework / submission with DB session.
3. Compare `homework.subject_id` / `class_id` against accessible courses or instructor relationship.
4. Return redacted payloads for students (e.g. `rubric_staff_only`, `reference_answer` hidden — see serializers in-router).

**LLM discussion:** `llm_discussion.py` intentionally omits teacher-only homework fields from student-triggered assistant threads. Current invoke matrix:

- **student**: allowed, billed against the student's daily token pool after account↔roster resolution;
- **teacher / class_teacher / admin**: allowed on discussions they can already access, but not limited by student token caps;
- hidden teacher-only homework fields remain hidden from student-triggered context even though staff/admin may also invoke the assistant.

---

## 5. LLM admin vs teacher capabilities

| Surface | Who configures |
|---------|----------------|
| Global endpoint presets, global quota policy | Admin (`/api/llm-settings` family) |
| Per-course LLM enable, endpoints order, prompts | Assigned course teacher (`Subject.teacher_id`) or admin. Class-linked visibility alone is not enough. |

Current implementation note: per-course LLM config is stricter than older
product phrasing in some historical docs. `GET` and `PUT`
`/api/llm-settings/courses/{subject_id}` now require the assigned course teacher
or admin; class-linked visibility alone is not enough to read or change course
LLM config.

**Agent rule:** open the specific router function before assuming UI parity.

---

## 6. E2E dev API (`api/routers/e2e_dev.py`)

- Router always registered from `main.py`, but handlers short-circuit unless `settings.expose_e2e_dev_api()` is true.
- `expose_e2e_dev_api` is false when `APP_ENV` is production-like **or** `E2E_DEV_SEED_ENABLED` is false.
- Powerful endpoints may require **seed token + optional admin JWT** (`E2E_DEV_REQUIRE_ADMIN_JWT`).

This is a **supply-chain sensitive** surface — never weaken checks without security review.

---

## 7. JWT notes

- Tokens include user id + role; password changes bump `token_version` invalidating old JWTs (see auth router + login logging).
- CORS + credentials: wildcard origins disable credential cookies in `main.py` CORS middleware — review when touching auth.

---

## 8. Frontend route `meta` (admin)

`apps/web/school/src/router/index.js` uses flags such as `requiresAdmin`, `requiresTeachingStaff`.

These control **navigation/UI**. They do **not** replace backend checks.

---

## 9. Reference reading

- Vertical traces: [`../architecture/CORE_BUSINESS_FLOWS.md`](../architecture/CORE_BUSINESS_FLOWS.md)
- LLM specifics: [`../product/LLM_HOMEWORK_GUIDE.md`](../product/LLM_HOMEWORK_GUIDE.md)

---

## 10. 待人工确认

- **Exact matrix** for every `subjects` mutation endpoint across `class_teacher` vs `teacher` (product evolves). Agents must grep `is_course_instructor` / `ensure_course_access` at edit time rather than trusting prose alone.
- **Exact matrix** for every newly added course mutation endpoint still needs
  active verification at edit time. A route that calls
  `ensure_course_access_http(...)` is not automatically safe for writes; grep
  for an assigned-teacher/admin guard and add a hardening test when extending
  course-owned mutations.
