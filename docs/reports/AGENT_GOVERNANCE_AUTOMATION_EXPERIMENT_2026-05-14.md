# Agent Governance Automation Experiment 2026-05-14

## Purpose

Record the current state, lessons, and limitations of the repository agent
governance automation experiments completed during this round.

This report exists because the repository explored several generations of
automation-heavy governance routing and then deliberately chose to retain the
**workflow ideas** while removing the most fragile automation layers.

## What Was Attempted

The repository implemented and tested a governance stack that included:

- governance gate scripts
- profile-driven route matching
- unified governance-first validation entrypoints
- prompt-driven document candidate routing
- full skill exposure
- incremental document/skill/pitfall candidate loops

The design goal was to make repository agent behavior more explicit, more
governed, and more repeatable.

## What Worked

These ideas proved useful and should survive as durable workflow guidance:

1. Separate `strict` and `guided` governance modes.
2. Keep `strict` as the default.
3. Lock a startup reading bundle for strict-mode work.
4. Use repository-native docs and skills as the source of workflow truth.
5. Keep pitfall memory searchable and reusable before guessing root causes.
6. Distinguish selected validation from executed validation.
7. Treat documentation updates, validation evidence, and update-log maintenance
   as part of the same repository-changing round.

## What Did Not Work Well Enough

The automation-heavy routing approach is **not reliable enough as the primary
execution model for agent systems**.

### Main reason

The repository uses an **agent**, not a fully deterministic schema-bound
function caller.

That means the system cannot safely assume the agent will always:

- choose exactly one recommended document;
- answer "read enough / not enough" in a stable machine-friendly way;
- follow a loop protocol step-by-step;
- emit structured continuation state without drift;
- keep autonomous reasoning aligned with the routing script's expectations.

### Practical consequence

The more the workflow depends on the agent returning exactly the expected
continuation signal, the less reliable the workflow becomes.

That is acceptable for hints and state panels.
It is not robust enough for hard execution control.

## Conclusion

The repository should keep the **workflow concepts** but not rely on these
automation layers as the primary agent control mechanism.

More specifically:

- the repository should keep `strict` / `guided` semantics;
- it should keep pitfall-first failure triage;
- it should keep validation honesty and durable ledger rules;
- it should keep startup reading, docs updates, and update-log closeout;
- but it should prefer **text-first, repository-native instructions** over a
  hard scripted multi-round agent router.

## Durable Outcome

The durable outcome of this experiment is:

1. Preserve the governance ideas in `AGENTS.md` and the topic docs.
2. Preserve the distinction between strict and guided workflow contracts.
3. Preserve pitfall search and validation selector as supporting tools.
4. Remove the fragile route-control scripts that expect agent behavior to be
   machine-stable.

## Why This Is Better

This keeps:

- clarity,
- repeatability,
- and repository memory

without pretending that an autonomous agent will behave like a deterministic
form-filling state machine across many steps.

That is the correct engineering tradeoff for the repository at this stage.
