# tests/devtools — test-tree maintenance utilities

## Purpose

This directory holds **non-pytest** scripts that operate on the repository test corpus or regenerate test-adjacent documentation.

It exists so maintenance tooling stays **inside `tests/`** instead of competing with deployment scripts under `ops/scripts/` or reintroducing a redundant top-level directory.

## Rules for agents and contributors

1. **Filenames must not match pytest discovery.** Repository [`pytest.ini`](../../pytest.ini) collects `test_*.py` under `tests/`. Utilities here must use names like `audit_test_redundancy.py` (no `test_` prefix) so pytest never imports them as tests.
2. **Keep deployment scripts out.** Shell automation meant for servers belongs in `ops/scripts/` (see [`docs/operations/DEPLOYMENT_AND_OPERATIONS.md`](../../docs/operations/DEPLOYMENT_AND_OPERATIONS.md)).
3. **Inventory tools should skip this directory.** The redundancy auditor skips `tests/devtools/` when scanning so category counts stay meaningful — copy that pattern if you add new walkers.

## Current utilities

| Script | Output / effect |
|--------|-----------------|
| [`audit_test_redundancy.py`](audit_test_redundancy.py) | Rewrites [`docs/testing/TEST_REDUNDANCY_AUDIT.md`](../../docs/testing/TEST_REDUNDANCY_AUDIT.md) |

Run from repository root:

```bash
python3 tests/devtools/audit_test_redundancy.py
```

## Deeper documentation

- [`docs/testing/TEST_SUITE_MAP.md`](../../docs/testing/TEST_SUITE_MAP.md) — full `tests/` layout and devtools semantics.
