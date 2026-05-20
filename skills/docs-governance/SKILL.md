---
name: docs-governance
description: Use when refining CourseEval README, AGENTS.md, docs, testing/contributing/frontend/deployment guidance, documentation links, layered agent-document workflows, or repeatable agent procedures so documentation reflects current implementation and repeated pitfalls become durable rules, skills, or scripts.
---

# Docs Governance

## Goal

Keep CourseEval documentation executable for future agents. Treat code as the
truth source, but preserve detailed governance where it prevents repeated
mistakes.

This skill should optimize for fast, accurate retrieval of the right
repository guidance. The target is not merely “good docs”, but a document
system that lets an agent land on the right layer quickly.

## Layer Role

This is a horizontal governance skill. Use it for documentation truth,
entrypoints, links, reports, and pitfall-to-rule work. Do not duplicate detailed
rules from specialized skills; route to them when the document change touches
their domain.

Use this skill especially when the task is about:

- entrypoint wording;
- layered routing across `AGENTS.md`, `docs/README.md`, and `docs/agents/`;
- de-duplicating agent-facing guidance without deleting durable information;
- deciding whether a repeated workflow belongs in docs, a skill, or a script.

## Workflow

1. Read `AGENTS.md`, `docs/README.md`, and task-scoped docs listed there.
2. Check current implementation before changing a claim:
   - route and API claims: inspect `apps/backend/courseeval_backend/main.py`,
     `api/routers/`, and `api/schemas.py`;
   - config claims: inspect `core/config.py`, Vite config, ops templates;
   - test claims: inspect `tests/`, `pytest.ini`, Playwright config, and
     `tests/TEST_SELECTION_TARGETS.json`.
3. Run the docs guard before and after edits:
   `python ops/scripts/dev/check_docs_governance.py`.
4. Classify the document layer before editing:
   - root startup contract: `AGENTS.md`
   - hub/index: `docs/README.md`
   - agent routing and procedures: `docs/agents/`
   - domain truth: the narrowest topic doc under `docs/`
5. Convert repeated manual pitfalls into one of:
   - a committed script under `ops/scripts/dev/`;
   - a repo-local skill under `skills/`;
   - a precise rule in `AGENTS.md`, `docs/README.md`, or the task-specific doc.
6. Keep dated run reports under `docs/reports/`; keep active guidance in
   the topic directory such as `docs/architecture/`, `docs/contributing/`,
   `docs/frontend/`, `docs/governance/`, `docs/operations/`,
   `docs/product/`, or `docs/testing/`.
7. If documentation is moved, update inbound links and hub indexes in the same
   change.
8. Remove redundancy before reducing detail:
   - keep the narrowest authoritative doc rich enough to act on;
   - keep broader docs as routers and summaries;
   - split by responsibility cluster when a doc gets long, instead of deleting
     operational memory.
9. Route specialized work instead of copying its rules:
   - multilingual or PowerShell-sensitive edits:
     `skills/utf8-safe-editing/SKILL.md`;
   - deployment scripts, env templates, nginx/systemd:
     `skills/deployment-governance/SKILL.md`;
   - validation evidence and CSV ledgers:
     `skills/validation-ledger-maintenance/SKILL.md`;
   - API route/client docs: `skills/api-surface-audit/SKILL.md`.

## Checks

Use these from the repository root:

```powershell
python ops/scripts/dev/check_docs_governance.py
python ops/scripts/dev/check_repository_normalization.py
python ops/scripts/dev/check_text_encoding.py --fail-on-suspicious <changed-file>
git diff --check
```

When editing the agent-facing doc system, also inspect the current layered
bundle directly:

- `AGENTS.md`
- `docs/README.md`
- `docs/agents/agent-startup-routing.md`
- `docs/agents/agent-execution-entrypoints.md`
- `docs/agents/agent-playbook.md`
- `docs/agents/agent-closeout.md`
- `docs/agents/local-agent-workspace.md`

## Decision Rules

- Do not shorten governance docs merely because they are detailed; remove only
  obsolete, contradictory, or duplicated instructions.
- Do not force scripts to become the primary control surface when a text-first
  routing layer is clearer and more durable for agent use.
- Prefer the richer specialized skill or script when this skill and another
  skill cover the same task. Keep this skill as the documentation router.
- Prefer linking to the authoritative active doc over copying large sections.
- Keep private paths, local logs, screenshots, and machine-specific setup under
  ignored `.agent-run/`.
- Root-level raw logs and one-off CI captures should be ignored or archived
  under a dated report location, not left as naked root files.

## Agent-Doc Layering Heuristic

When structuring agent-facing docs:

1. Put contract-level rules in `AGENTS.md`.
2. Put hub/index paths in `docs/README.md`.
3. Put startup routing in `docs/agents/agent-startup-routing.md`.
4. Put execution mechanics in `docs/agents/agent-execution-entrypoints.md`.
5. Put procedural defaults and feature-touch workflow in
   `docs/agents/agent-playbook.md`.
6. Put round closeout in `docs/agents/agent-closeout.md`.
7. Put local-only workflow rules in
   `docs/agents/local-agent-workspace.md`.

If two layers say the same thing, keep the richer and narrower one as the
source of truth and turn the broader one into a pointer.
