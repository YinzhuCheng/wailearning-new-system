---
name: structure-governance
description: Use when organizing CourseEval directory hierarchy, root files, duplicate semantic folders, mixed-responsibility directories, unreferenced scripts/docs, file moves, path references, test entrypoints, or structural guardrails without changing product behavior.
---

# Structure Governance

## Goal

Keep the repository tree obvious: root files are repository contracts, source
code lives under `apps/`, docs under `docs/`, deploy/maintenance automation
under `ops/`, and tests plus test-tree tooling under `tests/`.

## Layer Role

This is a horizontal structure skill. Use it for layout hygiene, root policy,
safe file moves, and reference updates. Do not use it to bypass specialized
skills for package roots, deploy flows, schema/bootstrap, or validation
evidence.

## Workflow

1. Read `AGENTS.md`, `docs/README.md`,
   `docs/architecture/REPOSITORY_STRUCTURE.md`, and, for backend package
   layout, `docs/architecture/BACKEND_PACKAGE_STRUCTURE.md`.
2. Run:
   `python ops/scripts/dev/check_structure_governance.py --details`.
3. Apply low-risk structural cleanup first:
   - move raw logs or dated run evidence out of the root;
   - update stale path references;
   - add guardrails for root-file policy;
   - consolidate documentation index links.
4. Use `git mv` for tracked file moves. After every move, update imports,
   docs links, scripts, test entrypoints, and agent guidance.
5. Do not move process entrypoints, router modules, or package roots as part of
   a broad cleanup. Record those as follow-up plans unless a dedicated task and
   tests cover the risk.
6. Route specialized structural moves:
   - backend package/import root changes: `skills/repository-normalization/SKILL.md`;
   - deployment files: `skills/deployment-governance/SKILL.md`;
   - tests and validation registry/ledgers:
     `skills/validation-selection/SKILL.md` and
     `skills/validation-ledger-maintenance/SKILL.md`;
   - schema/bootstrap files: `skills/data-migration-audit/SKILL.md`.

## Checks

```powershell
python ops/scripts/dev/check_structure_governance.py --details
python ops/scripts/dev/check_docs_governance.py
python ops/scripts/dev/check_repository_normalization.py
python ops/scripts/dev/select_validation_targets.py --worktree
git diff --check
```

## Placement Rules

- `tests/devtools/`: scripts that analyze or regenerate test-corpus artifacts.
- `ops/scripts/dev/`: repository governance, validation, and maintenance scripts.
- `docs/reports/artifacts/`: committed historical logs only when they are
  intentionally preserved evidence and contain no private paths or secrets.
- `.agent-run/`: local-only logs, screenshots, databases, and machine paths.
- When a simple structure rule overlaps a richer specialized skill, keep the
  richer skill as the source of truth and leave only routing guidance here.
