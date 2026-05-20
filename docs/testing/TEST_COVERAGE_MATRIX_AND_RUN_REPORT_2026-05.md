# Test coverage matrix and full-suite run report — 2026-05

This document satisfies the “coverage matrix + run record” deliverable for the **full testing remediation** round. It is written primarily for LLM agents and maintainers; verbosity is intentional.

---

## Part A — System & test harness summary

| Topic | Fact |
|-------|------|
| Backend framework | FastAPI + SQLAlchemy + Pydantic v2 (`apps/backend/courseeval_backend/`) |
| Primary pytest roots | `tests/backend/`, `tests/behavior/`, `tests/security/`, `tests/backend/e2e_dev/` |
| Default DB under pytest | File-backed SQLite at `<repo-root>/.pytest_tmp/test.sqlite` unless `TEST_DATABASE_URL` overrides (`tests/conftest.py`). |
| Schema bootstrap in tests | `tests/db_reset.reset_test_database_schema()` → imports **`db.models`** then `drop_all`/`create_all`; then `bootstrap.ensure_schema_updates()`. |
| Playwright | Specs in `tests/e2e/web-school/`; config `apps/web/school/playwright.config.cjs`; launches uvicorn on `E2E_API_PORT` (8012) + Vite school UI on `E2E_UI_PORT` (3012) unless `PLAYWRIGHT_USE_EXTERNAL_SERVERS`. |
| CI reference command | `python3 -m pytest -q` (`ops/ci/pr-pipeline.yml` sibling files under `ops/ci/`). |

---

## Part B — Coverage matrix (selected scenarios)

| Scenario | Prior coverage | Added this round | Tests | Strength | Residual risk |
|----------|----------------|------------------|-------|-----------|---------------|
| Health + root JSON | Partial / indirect | Yes | `tests/backend/integration/test_core_api_surface.py` | Medium | Bing proxy routes not covered |
| JWT missing / invalid login | Partial | Yes | same file | Strong | Refresh-token flows not in scope |
| `/api/auth/me` envelope | Weak | Yes | same file | Strong | Avatar upload edge cases |
| Users list unauthenticated | Weak | Yes | same file | Medium | Pagination semantics elsewhere |
| Homework object-level 403 (no enrollment) | Mixed | Yes | same file | Strong | Cross-class teacher unions |
| Effective-score API keys on submission | Covered deep in homework suite | Reinforced surface contract | same file | Medium | Appeals / batch flows |
| Teacher vs student rubric redaction | Covered elsewhere | Duplicate high-value guard | same file | Strong | Admin impersonation not tested |
| Demo seed LLM preset validation status | Outdated expectation (`validated` only) | Updated | `tests/backend/e2e_dev/test_demo_llm_seed_and_student_quota_edges.py` | Strong | Live vendor bootstrap differs |
| SQLite metadata registration order | Missing → flaky | Fixed harness | `tests/db_reset.py` | Strong | Shared sqlite corruption still possible |
| E2E login / invalid password | Partial | Yes | `tests/e2e/web-school/e2e-core-flows-smoke.spec.js` | Strong | MFA not applicable |
| E2E multi-role navigation | Partial | Yes | same file | Medium | Parent SPA separate tree |

---

## Part C — New / materially changed tests

| File | Type | Scenario highlights | Mock / real |
|------|------|----------------------|-------------|
| `tests/db_reset.py` | Harness fix | Forces ORM mapper registration before DDL | Real SQLite engine |
| `tests/backend/integration/test_core_api_surface.py` | API integration ×10 | Auth, homework ACL, rubric redaction, submission metadata keys | Real FastAPI `TestClient`, real DB |
| `tests/backend/e2e_dev/test_demo_llm_seed_and_student_quota_edges.py` | Expectation alignment | Accepts `validated` **or** fallback `pending` preset `gpt-5.4` | Real seed + ORM |
| `tests/e2e/web-school/e2e-core-flows-smoke.spec.js` | Playwright ×10 | Login failure path, student homework grid w/ title match, materials/notifications routes | Real Chromium + dual servers + seeded HTTP |

---

## Part D — Commands executed (baseline pass — see Part I for full verification)

| Command | Purpose | Result |
|---------|---------|--------|
| `python3 -m pytest tests/backend/integration/test_core_api_surface.py -q` | Validate new API suite | PASS |
| `python3 -m pytest tests/backend -q` | Backend regression | **263 passed**, **2 skipped** (missing OS `unrar` **before** follow-up env install) |
| `python3 -m pytest tests/behavior tests/security -q` | Higher-level flows | **158 passed**, **1 skipped** |
| `npm install` + `npx playwright install chromium` (under `apps/web/school`) | Browser deps | Success |
| `npx playwright test e2e-core-flows-smoke.spec.js` | Targeted E2E tier | **10 passed** |
| `npm run build` (`apps/web/school`) | SPA compile check | Success |

---

## Part E — Fixes applied

| Issue | Category | Fix |
|-------|----------|-----|
| `no such table: course_llm_configs` during pytest reset | Test harness / ordering | Import `db.models` inside `reset_test_database_schema()` |
| `test_demo_seed_binds_llm...` expected always `validated` | Outdated test vs bootstrap without API key | Allow `pending` + assert preset name `gpt-5.4` |
| School Playwright expected `/dashboard` but router sends `/students` | Test bug vs real UX | Assert authenticated layout instead of fixed path |

---

## Part F — Follow-up completion (2026-05 second pass — **no intentional tails**)

The items previously listed as “deferred for runtime” were executed in an agent Linux container after provisioning dependencies:

| Former gap | Outcome |
|------------|---------|
| Full Playwright `npm run test:e2e` | **303 tests passed** (~14 minutes, managed uvicorn + Vite + Chromium). Log artifact pattern: `/tmp/playwright-full.log` (example path). |
| Postgres-only suites (`tests/postgres/*`) | PostgreSQL server installed (`postgresql` apt package), cluster started via `pg_ctlcluster 16 main start` when `invoke-rc.d` blocked automatic start during package configure (**policy-rc.d** pattern in minimal containers). Database + role created using `bash ops/scripts/dev/provision_postgres_pytest.sh`. Full tree: `TEST_DATABASE_URL=postgresql+psycopg2://courseeval_test:courseeval_test@127.0.0.1:5432/courseeval_pytest_all python3 -m pytest tests/ -q` → **466 passed, 0 skipped**. |
| `unrar` skips | `apt-get install unrar` — `tests/backend/llm/test_llm_attachment_formats.py` RAR walkers execute on both SQLite and Postgres passes. |
| Vitest/Jest unit tests | Still **not declared** for school SPA beyond Playwright — no change. |

**Dual-database note:** Running `python3 -m pytest tests/` **without** `TEST_DATABASE_URL` still yields **43 skips** — these are **expected** `skipif` gates inside `tests/postgres/*` when `engine.dialect.name != postgresql`. This is not a failure; CI without Postgres mirrors that economy profile. A **complete** verification cycle runs **both** profiles (SQLite-default **and** Postgres-forced).

---

## Part G — Skip / xfail / focus ethics audit (after follow-up)

| Item | Status |
|------|--------|
| New `pytest.mark.skip` / `xfail` / `test.only` | **None introduced** |
| Postgres-forced full pytest | **466 passed, 0 skipped** |
| SQLite-default full pytest | **423 passed, 43 skipped** (Postgres-only modules) |
| Full Playwright | **303 passed** |

---

## Part H — Agent maintenance notes

1. Always prefer `python3 -m pytest` on Linux CI images.
2. When debugging sqlite chaos, delete `.pytest_tmp/test.sqlite` **after** confirming no concurrent pytest.
3. Playwright specs that need seeded IDs **must** call `resetE2eScenario()` — cache lives at `tests/e2e/web-school/.cache/scenario.json`.
4. Container PostgreSQL often requires **manual** `pg_ctlcluster <version> main start` after `apt-get install postgresql` when init scripts are blocked — verify with `pg_isready -h 127.0.0.1 -p 5432`.

---

## Part I — Reproducible “green wall” command block (copy/paste)

```bash
# OS tooling (Debian/Ubuntu-derived agents)
sudo apt-get update
sudo apt-get install -y unrar postgresql postgresql-contrib

# Start DB even when maintainer scripts cannot invoke systemd
sudo pg_ctlcluster 16 main start || true
pg_isready -h 127.0.0.1 -p 5432

# Idempotent throwaway pytest database (see ops/scripts/dev/provision_postgres_pytest.sh)
bash ops/scripts/dev/provision_postgres_pytest.sh

export TEST_DATABASE_URL='postgresql+psycopg2://courseeval_test:courseeval_test@127.0.0.1:5432/courseeval_pytest_all'
python3 -m pytest tests/ -q

unset TEST_DATABASE_URL
python3 -m pytest tests/ -q

cd apps/web/school
npm ci
npx playwright install chromium
npm run test:e2e

cd ../parent
npm ci
npm run build
```

**Observed durations (single agent VM, indicative):** Postgres pytest ~10.5 min; SQLite pytest ~8.9 min; Playwright full ~14 min.

---

## Part F — Follow-up: repository tree hygiene (2026-05)

The **repository-structure optimization** pass relocated the test redundancy auditor from `tools/testing/audit_test_redundancy.py` to `tests/devtools/audit_test_redundancy.py` and removed the redundant top-level `tools/` directory.

Agent notes:

- Regenerate [`TEST_REDUNDANCY_AUDIT.md`](TEST_REDUNDANCY_AUDIT.md) via `python3 tests/devtools/audit_test_redundancy.py` after editing protection rules or performing large test-file churn.
- First-hop rules for this directory: [`tests/devtools/README.md`](../../tests/devtools/README.md).
- This relocation **does not** change pytest discovery rules (`pytest.ini` still selects `test_*.py` only); devtools filenames must remain outside that pattern.
