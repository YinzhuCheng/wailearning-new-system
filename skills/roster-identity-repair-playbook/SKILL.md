---
name: roster-identity-repair-playbook
description: Use this when auditing, repairing, or changing CourseEval student identity, users.student_id bindings, roster/user synchronization, class moves, legacy username matches, or student-course enrollment repair behavior.
---

# Roster Identity Repair Playbook

## Purpose

Keep student identity changes explicit, auditable, and covered by focused
tests. The canonical binding is `users.student_id`; legacy
`username == student_no` matching is only a repair/audit aid, not normal feature
behavior.

## Workflow

1. Read `docs/reference/DATA_MODEL_ESSENTIALS.md`,
   `docs/reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md`, and the current
   handoff if this branch is still active.
2. Trace both directions of the invariant:
   `User(role=student).student_id -> Student.id` and any `Student` row that
   should or should not have a login account.
3. Keep read-only identity resolution separate from repair:
   `resolve_bound_student_for_user()` should not mutate, while
   `get_bound_student_for_user()` and `prepare_student_course_context()` remain
   repair-capable paths.
4. Before writing repair code, run or inspect the audit report so ambiguous,
   occupied, and repairable cases stay distinct.
5. Add regression tests for the exact identity transition. Prefer focused
   roster tests before broad API or Playwright coverage.
6. Update validation target registry and ledgers if a new durable roster target
   is introduced.

## Commands

```powershell
rg -n "student_id|prepare_student_course_context|resolve_bound_student_for_user|get_bound_student_for_user|legacy_binding" apps/backend/courseeval_backend tests/backend/roster
.venv\Scripts\python.exe ops\scripts\dev\audit_student_identity.py
.venv\Scripts\python.exe -m pytest tests\backend\roster\test_student_identity_guardrails.py -q
.venv\Scripts\python.exe -m pytest tests\backend\roster\test_student_identity_audit.py tests\backend\roster\test_student_identity_repair.py tests\backend\roster\test_student_user_api_roster_sync.py -q
.venv\Scripts\python.exe -m pytest tests\backend\courses\test_student_course_roster_behavior.py -q
```

## Guardrails

- Do not auto-bind a legacy login to a `Student` row already occupied by another
  user.
- Do not turn a read path into a repair path without naming and testing that
  side effect.
- Do not collapse `candidate_count`, `raw_candidate_count`, ambiguous matches,
  and occupied matches into one audit state.
- Preserve required-course enrollment repair behavior unless the task
  explicitly changes the product contract and updates tests.

## Related Files

- `apps/backend/courseeval_backend/domains/roster/identity.py`
- `apps/backend/courseeval_backend/domains/roster/audit.py`
- `apps/backend/courseeval_backend/domains/roster/repair.py`
- `apps/backend/courseeval_backend/domains/roster/reconciliation.py`
- `apps/backend/courseeval_backend/domains/courses/access.py`
- `tests/backend/roster/`
- `tests/backend/courses/test_student_course_roster_behavior.py`
