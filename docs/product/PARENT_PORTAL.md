# Parent Portal

## Overview

The parent portal is a separate Vue 3 application under `apps/web/parent/`. In production it is served from `/parent/` and gives parent-code users read-only access to student information relevant to guardians.

## What Parents Can Do

- bind access through a parent code,
- view score summaries and detailed scores,
- read class and school notifications available to the student context,
- view homework lists and due dates,
- read high-level statistics for the linked student.

## Local Development

```bash
cd apps/web/parent
npm install
npm run dev
```

The dev server uses Vite and should proxy API requests to the backend.

Current default local dev port from `apps/web/parent/vite.config.js` is `5174` unless `VITE_DEV_PORT` overrides it.

## Current Shape

The portal is intentionally thinner than the school frontend.

- It is read-oriented.
- It relies on parent-code verification rather than full JWT user login.
- It stores parent-side context in the browser after verification.

## Backend API Family

The portal is backed by `/api/parent`.

Typical endpoints include:

- verification,
- student info,
- scores,
- notifications,
- homework,
- summary statistics.

Parent-code reads are scoped to the linked `Student` row, not merely to the
student's administrative class. Score and statistics endpoints use
`Score.student_id` / `Attendance.student_id`. Homework and notification reads
start from class/global visibility, then apply an additional course-enrollment
filter when a row has `subject_id`: subject-scoped homework or notifications
are returned only when the linked student has a matching `CourseEnrollment`.
Class-only or global rows with `subject_id IS NULL` remain visible when the
class/target-student filters allow them. This is important for same-class
electives: a guardian for a student who did not enroll in an elective must not
see that elective's homework or course notifications just because the course
content also names the student's class.

Parent-code management in the same API family is staff-side and more sensitive
than portal reads. Administrators can manage any student's code. Class teachers
can generate or revoke codes only for students in their own assigned class
(`users.class_id`). Seeing another class through a class-linked course does not
grant parent-code management over that other class. Teacher-role access still
uses the course-accessible class set; change that only with a matching
permission decision, backend test, and documentation update.

Parent-code verification is unauthenticated and therefore rate limited by
client/code bucket. Invalid verification attempts return a normal parent portal
payload with `valid: false` until the limiter is exceeded, while read endpoints
such as `/student`, `/homework`, `/notifications`, `/scores`, and `/stats`
raise HTTP errors for missing, expired, or invalid codes. Generated codes carry
a future expiry; revocation clears both the code and expiry.

The parent SPA treats those read-side HTTP errors as an invalid local binding.
If a stored code is revoked, expired, invalid, or rate-limited, protected
screens clear only parent-session local storage keys and redirect back to
`/login`. Login attempts clear any stale parent-session keys before verifying
the submitted code, so a failed bind must not leave an older student context in
the browser.

Browser coverage for the parent SPA lives in the school Playwright package so it
can reuse the existing seeded FastAPI runner. Use:

```bash
cd apps/web/school
node scripts/playwright-external-runner.cjs e2e-parent-portal-hardening.spec.js --project=chromium
```

The runner starts the normal school Vite app by default and starts the parent
Vite app only for parent-portal specs or when `E2E_PARENT_UI=1` is set.

## Operational Notes

- Parent codes are generated and managed from the main system.
- The portal should be deployed together with the school frontend during production rollouts.
- Because this is a separate SPA, a backend-only deploy does not update parent-facing static assets.

## Related Docs

- [System Overview](../architecture/SYSTEM_OVERVIEW.md)
- [Deployment and Operations](../operations/DEPLOYMENT_AND_OPERATIONS.md)
