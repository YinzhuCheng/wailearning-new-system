# Documentation Hub

This directory is the authoritative documentation home for the repository. The
root [`README.md`](../README.md) is the public entry point; everything else
lives here.

---

## Directory map

Every subdirectory under `docs/` has its own `README.md` that defines its
scope. Keep new documents in the most specific topic folder first.

| Directory | Use for |
|-----------|---------|
| [agents/](agents/README.md) | LLM-agent playbooks, local workspace rules, and autonomous-workflow guidance |
| [architecture/](architecture/README.md) | System structure, package boundaries, configuration maps, troubleshooting |
| [assets/](assets/README.md) | Committed documentation assets only |
| [contributing/](contributing/README.md) | Git, encoding, and contributor workflow |
| [development/](development/README.md) | Sparse compatibility bucket; prefer a specific topic folder |
| [frontend/](frontend/README.md) | Browser/UI-state behavior and frontend interaction contracts |
| [governance/](governance/README.md) | Active risks, ownership ambiguity, repository governance, and durable repository rules |
| [handoffs/](handoffs/README.md) | Explicit user-requested committed handoffs |
| [operations/](operations/README.md) | Deployment, bootstrap, runtime operations |
| [product/](product/README.md) | Product behavior and domain concepts |
| [reference/](reference/README.md) | Lookup maps, permissions, and data model references |
| [reports/](reports/README.md) | Dated reports that remain useful historical evidence |
| [testing/](testing/README.md) | Test runbooks, pitfalls, validation maps, CSV ledgers, and CI/validation contracts |

---

## 0. LLM agent bundle (read before autonomous edits)

These files intentionally overlap with human-oriented docs. Verbosity is a
feature when the primary reader is a coding agent that must route work without
guessing.

| Document | Role |
|----------|------|
| [`AGENTS.md`](../AGENTS.md) (repository root) | Short agent startup contract and non-negotiable operating rules |
| [`agents/agent-startup-routing.md`](agents/agent-startup-routing.md) | Detailed startup routing: task matrix, high-risk areas, grep entrypoints, validation/CI entrypoints |
| [`agents/agent-execution-entrypoints.md`](agents/agent-execution-entrypoints.md) | Execution mechanics after routing: Windows safe entry, failure triage, validation, and CI entrypoints |
| [`agents/agent-playbook.md`](agents/agent-playbook.md) | Procedural workflows and autonomous operating defaults: tracing features, bootstrap order, verification |
| [`agents/agent-closeout.md`](agents/agent-closeout.md) | Required closeout procedure: validation, update-log, private-path review, and local artifact cleanup |
| [`agents/local-agent-workspace.md`](agents/local-agent-workspace.md) | `.agent-run/` contract for local-only notes, logs, and machine-specific evidence |
| [`reference/CODE_MAP_AND_ENTRYPOINTS.md`](reference/CODE_MAP_AND_ENTRYPOINTS.md) | File-level map of routers, SPAs, tests, CI YAML, and extended grep entrypoints |
| [`reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md`](reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md) | Roles, course access helpers, JWT vs parent-code |
| [`reference/DATA_MODEL_ESSENTIALS.md`](reference/DATA_MODEL_ESSENTIALS.md) | ORM tables grouped by domain |
| [`architecture/ASYNC_TASKS_AND_WORKERS.md`](architecture/ASYNC_TASKS_AND_WORKERS.md) | LLM grading worker (DB queue + thread pool) |
| [`architecture/HIGH_RISK_MODULES.md`](architecture/HIGH_RISK_MODULES.md) | Expanded notes for the short high-risk list kept in `AGENTS.md` |
| [`governance/repository-governance.md`](governance/repository-governance.md) | Full repository governance model and where durable rules live |
| [`governance/agent-update-log.md`](governance/agent-update-log.md) | Per-round update-log contract and append policy |
| [`governance/known-issues-and-risks.md`](governance/known-issues-and-risks.md) | Open risks, ownership ambiguity, and active hazards |
| [`governance/high-risk-path-metadata.json`](governance/high-risk-path-metadata.json) | Committed owner/risk/validation metadata for the highest-risk repository paths |
| [`testing/CI_AND_VALIDATION.md`](testing/CI_AND_VALIDATION.md) | Current CI entrypoints and how to interpret cloud versus local validation scope |
| [`../skills/README.md`](../skills/README.md) | Full repo-local skill catalog and layering guide |
| [`../skills/repository-normalization/SKILL.md`](../skills/repository-normalization/SKILL.md) | Top-level governance orchestrator for repo normalization, layered agent-document routing, skill taxonomy, and governance routing |
| [`../skills/docs-governance/SKILL.md`](../skills/docs-governance/SKILL.md) | Horizontal docs governance: documentation truth, layered agent-document structure, link checks, reports, and repeated-pitfall-to-rule workflow |
| [`../skills/boundary-governance/SKILL.md`](../skills/boundary-governance/SKILL.md) | Horizontal boundary governance: functional/module/permission/data-flow boundary discovery and low-risk extraction workflow |
| [`../skills/structure-governance/SKILL.md`](../skills/structure-governance/SKILL.md) | Horizontal structure governance: root-file, directory hierarchy, file-move, and structural reference workflow |
| [`../skills/security-redteam-iteration/SKILL.md`](../skills/security-redteam-iteration/SKILL.md) | Iterative red-team hardening workflow with dense tests, fixes, docs, ledgers, pitfalls, validation, and commit discipline |
| [`testing/REDTEAM_PARALLEL_ATTACKS.md`](testing/REDTEAM_PARALLEL_ATTACKS.md) | Parallel red-team batch planning contract: 4 attacks per round with at least 1 browser-backed E2E slot |
| [`../skills/validation-selection/SKILL.md`](../skills/validation-selection/SKILL.md) | Change-scoped validation selection and honest validation reporting |
| [`../skills/validation-ledger-maintenance/SKILL.md`](../skills/validation-ledger-maintenance/SKILL.md) | Validation registry, `ledger_id`, CSV target/run history, and selector-history maintenance |
| [`../skills/utf8-safe-editing/SKILL.md`](../skills/utf8-safe-editing/SKILL.md) | UTF-8-safe editing for multilingual / PowerShell-sensitive files |
| [`../skills/permission-audit/SKILL.md`](../skills/permission-audit/SKILL.md) | Backend authorization, role-boundary, and course-access audit workflow |
| [`../skills/deployment-governance/SKILL.md`](../skills/deployment-governance/SKILL.md) | Deployment script, env template, nginx/systemd, and ops-doc governance |
| [`../skills/local-test-triage/SKILL.md`](../skills/local-test-triage/SKILL.md) | Local pytest / SQLite / Playwright / process hazard triage |
| [`../skills/interruptible-full-validation-rounds/SKILL.md`](../skills/interruptible-full-validation-rounds/SKILL.md) | Block-by-block full validation workflow where each round launches one block, hangs up, and resumes later from durable WAI-VALID artifacts |
| [`../skills/school-playwright-e2e/SKILL.md`](../skills/school-playwright-e2e/SKILL.md) | Repo-supported school Playwright E2E execution, external-runner usage, and browser-harness triage |
| [`../skills/data-migration-audit/SKILL.md`](../skills/data-migration-audit/SKILL.md) | Schema repair, migration audit, and no-Alembic data-governance workflow |
| [`../skills/api-surface-audit/SKILL.md`](../skills/api-surface-audit/SKILL.md) | FastAPI router, frontend API client, API-doc, and route-contract audit workflow |
| [`../skills/frontend-backend-contract-audit/SKILL.md`](../skills/frontend-backend-contract-audit/SKILL.md) | Vue/FastAPI request contract, pagination, bounds, and response-shape audit workflow |
| [`../skills/roster-identity-repair-playbook/SKILL.md`](../skills/roster-identity-repair-playbook/SKILL.md) | Student identity, `users.student_id`, roster drift, and repair workflow |
| [`../skills/postgres-release-validation/SKILL.md`](../skills/postgres-release-validation/SKILL.md) | PostgreSQL-backed package/full-suite validation workflow |
| [`../skills/seed-surface-hardening/SKILL.md`](../skills/seed-surface-hardening/SKILL.md) | E2E dev, default seed, first-admin, public registration, and local/demo surface hardening |

---

## 1. Start here (architecture + operations)

| Document | Purpose |
|----------|---------|
| [architecture/SYSTEM_OVERVIEW.md](architecture/SYSTEM_OVERVIEW.md) | Capabilities, components, route families |
| [architecture/CORE_BUSINESS_FLOWS.md](architecture/CORE_BUSINESS_FLOWS.md) | Vertical slices: how homework grading, notifications, and E2E gates actually run (code anchors) |
| [architecture/CONFIGURATION_REFERENCE.md](architecture/CONFIGURATION_REFERENCE.md) | Single env-var index mapped to `core/config.py` and Vite dev vars |
| [architecture/MAINTAINER_AGENT_GUIDE.md](architecture/MAINTAINER_AGENT_GUIDE.md) | Additional grep keywords, risky modules, and test expectations |
| [architecture/TROUBLESHOOTING.md](architecture/TROUBLESHOOTING.md) | Symptom-first links into pitfalls and ops docs |
| [architecture/REPOSITORY_STRUCTURE.md](architecture/REPOSITORY_STRUCTURE.md) | Source vs artifact; import namespace contract |
| [architecture/BACKEND_PACKAGE_STRUCTURE.md](architecture/BACKEND_PACKAGE_STRUCTURE.md) | Layer model inside `courseeval_backend` |
| [architecture/HIGH_RISK_MODULES.md](architecture/HIGH_RISK_MODULES.md) | Expanded trace guidance for the highest-risk modules |
| [reports/README.md](reports/README.md) | Boundary rules for dated audits and remediation reports |
| [operations/DEPLOYMENT_AND_OPERATIONS.md](operations/DEPLOYMENT_AND_OPERATIONS.md) | Production layout, nginx, systemd, env templates |
| [operations/ADMIN_BOOTSTRAP.md](operations/ADMIN_BOOTSTRAP.md) | Startup ordering and seed behavior |

---

## 2. Product features

| Document | Purpose |
|----------|---------|
| [product/LLM_HOMEWORK_GUIDE.md](product/LLM_HOMEWORK_GUIDE.md) | LLM entities, quotas, async worker behavior |
| [product/PARENT_PORTAL.md](product/PARENT_PORTAL.md) | Parent-code flows vs staff JWT accounts |

---

## 3. Contributing, frontend, testing, and quality

| Document | Purpose |
|----------|---------|
| [testing/TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md](testing/TEST_COVERAGE_MATRIX_AND_RUN_REPORT_2026-05.md) | Matrix + command log for the 2026-05 full-stack test remediation pass |
| [testing/README.md](testing/README.md) | Structured execution tables: CSV target metadata, append-only run history, and recent summary rows for incremental-test decisions |
| [testing/TEST_EXECUTION_LEDGER.md](testing/TEST_EXECUTION_LEDGER.md) | Stable human entry point for the CSV execution ledger |
| [testing/TEST_EXECUTION_SUMMARY.md](testing/TEST_EXECUTION_SUMMARY.md) | Stable human entry point for the CSV recent validation summary |
| [testing/DEVELOPMENT_AND_TESTING.md](testing/DEVELOPMENT_AND_TESTING.md) | Broad local testing handbook: pytest/Playwright workflows, environment context, and historical testing guidance |
| [testing/VALIDATION_WORKFLOW_AND_TOOLS.md](testing/VALIDATION_WORKFLOW_AND_TOOLS.md) | Primary validation entrypoint for diff-based target selection, runner choice, and honest evidence reporting |
| [testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md](testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md) | Heavy validation policy for release-grade, full-suite, and zero-skip claims |
| [testing/CI_AND_VALIDATION.md](testing/CI_AND_VALIDATION.md) | Current cloud entrypoints, CI scope, and validation reporting rules |
| [testing/TEST_SUITE_MAP.md](testing/TEST_SUITE_MAP.md) | What lives where in `tests/` |
| [testing/TEST_EXECUTION_PITFALLS.md](testing/TEST_EXECUTION_PITFALLS.md) | Large execution encyclopedia: Windows/PowerShell, ports, Element Plus, SQLite vs PG, Playwright, CI hazards |
| [testing/pitfalls-windows-and-encoding.md](testing/pitfalls-windows-and-encoding.md) | Narrow route for Windows shell, UTF-8, and local execution traps |
| [testing/pitfalls-playwright-and-e2e.md](testing/pitfalls-playwright-and-e2e.md) | Narrow route for Playwright harness, E2E startup, selector, and UI race traps |
| [testing/pitfalls-postgres-and-pytest.md](testing/pitfalls-postgres-and-pytest.md) | Narrow route for PostgreSQL, pytest environment gates, and SQLite vs PG semantics |
| [testing/pitfalls-ledger-and-selector-tooling.md](testing/pitfalls-ledger-and-selector-tooling.md) | Narrow route for selector, CSV ledger, BOM, and append-tooling pitfalls |
| [testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md](testing/FULL_PLAYWRIGHT_E2E_RUNBOOK.md) | Full school E2E environment contract |
| [frontend/NOTIFICATION_HEADER_AND_REALTIME_SYNC.md](frontend/NOTIFICATION_HEADER_AND_REALTIME_SYNC.md) | Header badge, sync API, and sidebar navigation notes |
| [frontend/HTTP_CLIENT_SLOW_RESPONSE_BUSY_HINT.md](frontend/HTTP_CLIENT_SLOW_RESPONSE_BUSY_HINT.md) | HTTP client UX hint behavior |
| [contributing/ENCODING_AND_MOJIBAKE_SAFETY.md](contributing/ENCODING_AND_MOJIBAKE_SAFETY.md) | UTF-8 / PowerShell display traps |
| [contributing/GIT_WORKFLOW.md](contributing/GIT_WORKFLOW.md) | Branch and contribution conventions |
| [product/CONTENT_FORMAT_MARKDOWN_AND_PLAIN_TEXT.md](product/CONTENT_FORMAT_MARKDOWN_AND_PLAIN_TEXT.md) | Homework/submission `content_format` |
| [testing/TEST_REDUNDANCY_AUDIT.md](testing/TEST_REDUNDANCY_AUDIT.md) | Test merge/delete policy |
| [reports/AGENT_GOVERNANCE_AUTOMATION_EXPERIMENT_2026-05-14.md](reports/AGENT_GOVERNANCE_AUTOMATION_EXPERIMENT_2026-05-14.md) | Record of the prompt-routed agent-governance automation experiment, what worked, and why the repository retained text-first workflow guidance instead of a hard agent-control router |
| [reports/REMOTE_CI_FAILURE_REVIEW_2026-05-15.md](reports/REMOTE_CI_FAILURE_REVIEW_2026-05-15.md) | Dated root-cause review for the 2026-05-15 remote CI failures before remediation, including grading retry-contract analysis and pitfall-index drift classification |

---

## 4. Documentation principles

- These files describe the current implementation in this repository.
- CourseEval treats code as documentation and documentation as governance:
  implementation usually wins when docs conflict with code, while durable rules
  and repeated workflows should be written into docs, scripts, or repo-local
  skills.
- Whenever a workflow becomes common, fragile, or repeatedly useful, create or
  update a repo-local skill as needed so future agents can execute it
  consistently; prefer adding a supporting script when the workflow can be
  automated.
- Keep skill overlap intentional and layered: use
  [../skills/repository-normalization/SKILL.md](../skills/repository-normalization/SKILL.md)
  as the top-level governance orchestrator, then route through
  `docs-governance`, `boundary-governance`, `structure-governance`, or the
  richer specialized skill. When two skills or scripts overlap, preserve the
  more precise and executable one as the source of truth.
- Close repository-normalization work in durable docs: classify accepted,
  active, and deferred boundaries in architecture/handoff/governance docs
  before treating local planning notes or warning lists as complete.
- If behavior changes in code, update these documents in the same change set.
- Contributors, including LLM agents, are expected to read the task-relevant
  documents before changing code, tests, structure, or deployment assets.
- The documentation set is part of the implementation surface, not optional
  commentary.
- For ordinary validation selection and reporting, start with
  [testing/VALIDATION_WORKFLOW_AND_TOOLS.md](testing/VALIDATION_WORKFLOW_AND_TOOLS.md).
- For database-related tests and zero-skip full `pytest` claims, use
  [testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md](testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md)
  together with the broader harness context in
  [testing/DEVELOPMENT_AND_TESTING.md](testing/DEVELOPMENT_AND_TESTING.md).
- Large structured ledgers belong in CSV/JSON/YAML; Markdown should link to
  them and explain interpretation rules. The current test execution ledgers
  live under [testing/](testing/).
- The `docs/` root should contain only this hub README. Put every other
  document in a topic folder with its own `README.md`.
- For repository naming, package, service, and ops-template normalization
  checks, run `python ops/scripts/dev/check_repository_normalization.py`.

---

## 5. Mandatory reading by task

Use this section as an operational gate, not a suggestion.

### Before any repository-structure or path change

Read:

1. [architecture/REPOSITORY_STRUCTURE.md](architecture/REPOSITORY_STRUCTURE.md)
2. [architecture/SYSTEM_OVERVIEW.md](architecture/SYSTEM_OVERVIEW.md)
3. [architecture/BACKEND_PACKAGE_STRUCTURE.md](architecture/BACKEND_PACKAGE_STRUCTURE.md) when touching backend package layout

Why:

- this repository contains intentional compatibility layers
- some directories seen locally are runtime artifacts rather than source layout
- moving files without reading the structure contract can break tests, deploy scripts, or startup commands

### Before backend or feature work

Read:

1. [architecture/SYSTEM_OVERVIEW.md](architecture/SYSTEM_OVERVIEW.md)
2. [architecture/CORE_BUSINESS_FLOWS.md](architecture/CORE_BUSINESS_FLOWS.md)
3. the relevant product document such as [product/LLM_HOMEWORK_GUIDE.md](product/LLM_HOMEWORK_GUIDE.md) or [product/PARENT_PORTAL.md](product/PARENT_PORTAL.md)

Why:

- route shape, bootstrap behavior, and LLM flows are interdependent
- feature work can accidentally break quota, notification, enrollment, or startup assumptions outside the immediate edit area

### Before running tests or diagnosing failures

Read:

1. [testing/VALIDATION_WORKFLOW_AND_TOOLS.md](testing/VALIDATION_WORKFLOW_AND_TOOLS.md)
2. [contributing/ENCODING_AND_MOJIBAKE_SAFETY.md](contributing/ENCODING_AND_MOJIBAKE_SAFETY.md)
3. [testing/TEST_EXECUTION_PITFALLS.md](testing/TEST_EXECUTION_PITFALLS.md)
4. [architecture/TROUBLESHOOTING.md](architecture/TROUBLESHOOTING.md) for a short symptom index
5. [testing/CI_AND_VALIDATION.md](testing/CI_AND_VALIDATION.md) when CI scope or cloud gating matters
6. [testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md](testing/FULL_VALIDATION_ENVIRONMENT_POLICY.md) when the claim is release-grade, full-suite, or zero-skip

Why:

- this repository has known Windows + PowerShell execution traps
- Playwright failures can come from port collisions, stale processes, or sandbox limits rather than product regressions
- cloud and local validation scopes are intentionally different

### Before deployment, environment, or bootstrap changes

Read:

1. [operations/DEPLOYMENT_AND_OPERATIONS.md](operations/DEPLOYMENT_AND_OPERATIONS.md)
2. [operations/ADMIN_BOOTSTRAP.md](operations/ADMIN_BOOTSTRAP.md)
3. [architecture/CONFIGURATION_REFERENCE.md](architecture/CONFIGURATION_REFERENCE.md)
4. [architecture/REPOSITORY_STRUCTURE.md](architecture/REPOSITORY_STRUCTURE.md)

Why:

- startup, service layout, and compatibility entrypoints are coupled
- deploy scripts may depend on current import and directory conventions

---

## 6. Suggested reading paths

### Product or engineering overview

1. [architecture/SYSTEM_OVERVIEW.md](architecture/SYSTEM_OVERVIEW.md)
2. [architecture/CORE_BUSINESS_FLOWS.md](architecture/CORE_BUSINESS_FLOWS.md)
3. [architecture/REPOSITORY_STRUCTURE.md](architecture/REPOSITORY_STRUCTURE.md)
4. [product/LLM_HOMEWORK_GUIDE.md](product/LLM_HOMEWORK_GUIDE.md)

### Local development

1. [testing/VALIDATION_WORKFLOW_AND_TOOLS.md](testing/VALIDATION_WORKFLOW_AND_TOOLS.md)
2. [testing/CI_AND_VALIDATION.md](testing/CI_AND_VALIDATION.md)
3. [contributing/ENCODING_AND_MOJIBAKE_SAFETY.md](contributing/ENCODING_AND_MOJIBAKE_SAFETY.md)
4. [testing/DEVELOPMENT_AND_TESTING.md](testing/DEVELOPMENT_AND_TESTING.md)
5. [testing/TEST_SUITE_MAP.md](testing/TEST_SUITE_MAP.md)
6. [testing/TEST_REDUNDANCY_AUDIT.md](testing/TEST_REDUNDANCY_AUDIT.md)
7. [testing/TEST_EXECUTION_PITFALLS.md](testing/TEST_EXECUTION_PITFALLS.md)
8. [architecture/MAINTAINER_AGENT_GUIDE.md](architecture/MAINTAINER_AGENT_GUIDE.md)

### Autonomous agent onboarding (Codex / Cursor / cloud agents)

1. [AGENTS.md](../AGENTS.md)
2. [agents/agent-startup-routing.md](agents/agent-startup-routing.md)
3. [agents/agent-execution-entrypoints.md](agents/agent-execution-entrypoints.md)
4. [agents/agent-playbook.md](agents/agent-playbook.md)
5. [agents/agent-closeout.md](agents/agent-closeout.md)
6. [agents/local-agent-workspace.md](agents/local-agent-workspace.md)
7. [reference/CODE_MAP_AND_ENTRYPOINTS.md](reference/CODE_MAP_AND_ENTRYPOINTS.md)
8. [governance/repository-governance.md](governance/repository-governance.md)
9. [governance/known-issues-and-risks.md](governance/known-issues-and-risks.md)
10. [architecture/CORE_BUSINESS_FLOWS.md](architecture/CORE_BUSINESS_FLOWS.md)
11. [../skills/README.md](../skills/README.md)

### Production deployment

1. [operations/DEPLOYMENT_AND_OPERATIONS.md](operations/DEPLOYMENT_AND_OPERATIONS.md)
2. [architecture/CONFIGURATION_REFERENCE.md](architecture/CONFIGURATION_REFERENCE.md)
3. [product/LLM_HOMEWORK_GUIDE.md](product/LLM_HOMEWORK_GUIDE.md)

### Parent-facing experience

1. [product/PARENT_PORTAL.md](product/PARENT_PORTAL.md)
2. [architecture/SYSTEM_OVERVIEW.md](architecture/SYSTEM_OVERVIEW.md)
