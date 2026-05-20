---
name: permission-audit
description: Use this when changing or reviewing CourseEval authorization, role boundaries, course access, subject-scoped teacher routes, parent-code access, homework/file/notification permissions, or security-sensitive backend/API behavior.
---

# Permission Audit

## Purpose

Keep authorization enforced in backend code, not only hidden in frontend UI.
Preserve CourseEval's current role and object-level access contracts.

This skill should route agents quickly to the current permission truth:
role semantics, course access, object ownership, parent-code boundaries, and
the right security validation lane.

## Workflow

1. Read:
   - `docs/reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md`
   - `docs/architecture/CORE_BUSINESS_FLOWS.md`
   - feature-specific docs when the permission rule lives inside a larger flow
2. Trace the request through router dependency, current-user resolution,
   permission helper, domain helper, and query filter.
3. For explicit `subject_id` routes, validate course access with
   `ensure_course_access_http(...)` before applying class-only filters.
4. For no-subject class-wide routes, class visibility checks may be the primary
   gate.
5. Confirm students resolve through `users.student_id`; do not reintroduce
   username/student-number guessing as normal behavior.
6. Route to `api-surface-audit` when the real change is route/client contract
   shape rather than authorization semantics.
7. Route to `frontend-backend-contract-audit` when the issue is a narrow
   frontend/backend request contract rather than permission truth.
8. Use the focused validation docs to choose the right security lane before
   broadening to heavier suites.
9. Add or update tests that prove unauthorized API calls fail at the backend.
10. Update permission docs when the contract changes.

## Document Routing Rules

- Use `PERMISSIONS_AND_SECURITY_BOUNDARIES.md` as the canonical source for
  current permission semantics and ownership rules.
- Use `CORE_BUSINESS_FLOWS.md` when the permission question is embedded in a
  larger product flow.
- Use `VALIDATION_WORKFLOW_AND_TOOLS.md` for selector/runner/profile behavior.
- Use `api-surface-audit` when the issue is route/client shape.
- Use `security-redteam-iteration` when the task is an iterative broad hardening
  round rather than a focused permission audit.

## Commands

```powershell
rg -n "ensure_course_access_http|get_accessible_class_ids|get_accessible_courses_query|UserRole|parent" apps/backend/courseeval_backend tests
python ops/scripts/dev/select_validation_targets.py --worktree
python ops/scripts/dev/run_validation_target.py security.api_regression --timeout-seconds 120
```

## Guardrails

- Frontend hiding is not authorization.
- Do not restore `Subject.class_id` as the effective fallback for required
  course visibility or auto-enrollment.
- Do not weaken `/api/e2e/dev/*` gates.
- Treat parent-code flows separately from staff/student JWT flows.
- Escalate to broader validation for auth helpers, schema, or shared course
  access changes.
- Do not confuse course visibility (`ensure_course_access_http`) with mutation
  authority (`is_course_instructor` and route-local ownership checks).

## Related Files

- `docs/reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md`
- `docs/architecture/CORE_BUSINESS_FLOWS.md`
- `docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md`
- `apps/backend/courseeval_backend/core/permissions.py`
- `apps/backend/courseeval_backend/domains/courses/access.py`
- `apps/backend/courseeval_backend/api/routers/`
- `tests/security/test_security_regression.py`
- `skills/api-surface-audit/SKILL.md`
- `skills/security-redteam-iteration/SKILL.md`
