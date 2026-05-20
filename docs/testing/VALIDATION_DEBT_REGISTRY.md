# Validation Debt Registry

This document explains
[`validation-debt-registry.csv`](validation-debt-registry.csv).

Use it when:

- classifying a high-cost validation target as active, optional stress, or
  explicit backlog debt;
- deciding whether "not in this lane" is intentional policy or missing
  coverage;
- reviewing future/deep/backlog-style browser suites.

## Meanings

- `active_required_coverage`: still part of the maintained validation surface.
  It may be expensive, but it is not debt by default when the selector routes
  to it.
- `optional_stress_coverage`: a maintained suite kept out of routine lanes for
  cost reasons. Not running it by default means "not in this lane", not "this
  coverage does not matter".
- `explicit_backlog_debt`: intentionally non-routine coverage that should not
  be mistaken for active maintained proof.

## Rule

Do not describe a target as "already covered" just because a file exists in
`tests/e2e/`. If it is backlog debt or optional stress coverage, say so
explicitly.

## Related Files

- [validation-debt-registry.csv](validation-debt-registry.csv)
- [README.md](README.md)
- [CI_AND_VALIDATION.md](CI_AND_VALIDATION.md)
