# CourseEval

CourseEval is a multi-role school and classroom management platform with a
FastAPI backend, a Vue 3 school web app, a separate parent portal, PostgreSQL
as the production reference database, and LLM-assisted homework grading built
around database-backed grading-task rows plus an in-process worker.

## Who should start here

- Developers: start with this README, then use [docs/README.md](docs/README.md)
  for task-specific reading.
- Operators: start with
  [docs/operations/DEPLOYMENT_AND_OPERATIONS.md](docs/operations/DEPLOYMENT_AND_OPERATIONS.md).
- LLM coding agents: start with [AGENTS.md](AGENTS.md), then use
  [docs/README.md](docs/README.md).

## What CourseEval provides

- Roles: admin, class teacher, subject teacher, student, and parent-code users
  with distinct access paths.
- Course operations: class, student, user, roster, required-course, elective,
  and enrollment-management workflows.
- Homework workflows: publication, submission attempts, review, regrade, and
  appeal flows.
- LLM-assisted grading: endpoint presets, course-level grading configuration,
  quota policy, async task processing, and teacher review tools.
- School workflows: materials, discussions, notifications, attendance,
  semesters, scores, and points.
- Parent portal: a separate read-oriented SPA for parent-code access to student
  information.

## LLM-assisted homework grading

LLM grading is a first-class product workflow, not a sidecar demo. Admins
manage reusable endpoint presets and quota policy, teachers configure grading
behavior per course, and async grading runs through `HomeworkGradingTask` rows
drained by the in-process worker.

For architecture and behavior details, use:

- [docs/product/LLM_HOMEWORK_GUIDE.md](docs/product/LLM_HOMEWORK_GUIDE.md)
- [docs/architecture/CORE_BUSINESS_FLOWS.md](docs/architecture/CORE_BUSINESS_FLOWS.md)

## Tech stack

- Backend: FastAPI, SQLAlchemy, PostgreSQL, Pydantic v2
- School frontend: Vue 3, Vite, Element Plus, Pinia, ECharts
- Parent portal: Vue 3 + Vite
- Testing: `pytest`, Playwright
- Operations: Nginx, `gunicorn`, `uvicorn`, `systemd`

## Repository layout

```text
apps/backend/courseeval_backend/   Canonical FastAPI backend package
apps/web/school/                   School SPA and Playwright config
apps/web/parent/                   Parent-facing SPA
docs/                              Documentation hub
ops/                               CI, deployment, and runtime operations
tests/                             Backend, behavior, and browser E2E suites
```

For repository boundary and placement rules, use
[docs/architecture/REPOSITORY_STRUCTURE.md](docs/architecture/REPOSITORY_STRUCTURE.md).

## Quick start

Commands below assume the repository root as the working directory unless the
section says otherwise.

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn apps.backend.courseeval_backend.main:app --host 127.0.0.1 --port 8001 --reload
```

Windows convenience launcher:

```bat
ops\scripts\windows\start-backend.bat
```

Local API docs:

- Swagger UI: `http://127.0.0.1:8001/docs`
- ReDoc: `http://127.0.0.1:8001/redoc`

### School frontend

```bash
cd apps/web/school
npm install
npm run dev
```

Windows convenience launcher:

```bat
ops\scripts\windows\start-school-frontend.bat
```

### Parent portal

```bash
cd apps/web/parent
npm install
npm run dev
```

Windows convenience launcher:

```bat
ops\scripts\windows\start-parent-frontend.bat
```

## Configuration

Use [docs/architecture/CONFIGURATION_REFERENCE.md](docs/architecture/CONFIGURATION_REFERENCE.md)
as the authoritative configuration reference for backend settings, frontend dev
variables, bootstrap flags, and E2E-only environment variables.

## Testing

Backend:

```bash
python3 -m pytest
```

School E2E:

```bash
cd apps/web/school
npm install
npx playwright install chromium
npm run test:e2e
```

For detailed validation workflow, PostgreSQL-aligned runs, Playwright
environment setup, and suite maps, use:

- [docs/testing/DEVELOPMENT_AND_TESTING.md](docs/testing/DEVELOPMENT_AND_TESTING.md)
- [docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md](docs/testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md)
- [docs/testing/TEST_SUITE_MAP.md](docs/testing/TEST_SUITE_MAP.md)

## Documentation

Use [docs/README.md](docs/README.md) as the documentation hub. It routes to
architecture, product, operations, testing, governance, and agent-specific
workflow docs.

## License and credits

This project is open source under the Apache License 2.0. See
[LICENSE](LICENSE).

Original author and initial contributor: `joyapple`

Subsequent contributors: `HaihuaXie`, `YinzhuCheng`

Third-party components include FastAPI, Vue.js, Element Plus, SQLAlchemy,
PostgreSQL, and ECharts, each under its own license.
