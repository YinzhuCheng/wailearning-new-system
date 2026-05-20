"""Generate small docs/testing explainer entrypoints from one source."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


GENERATED_HEADER = (
    "<!-- Generated from ops/scripts/dev/sync_testing_governance_docs.py. "
    "Edit that script instead of editing this file directly. -->\n\n"
)


def generated_docs() -> dict[str, str]:
    return {
        "docs/testing/TEST_EXECUTION_LEDGER.md": GENERATED_HEADER
        + """# Test Execution Ledger

The durable validation ledger facts live in CSV tables under this directory:

- [`test-execution-targets.csv`](test-execution-targets.csv)
- [`test-execution-runs.csv`](test-execution-runs.csv)
- [`test-execution-summary.csv`](test-execution-summary.csv)

Use [`README.md`](README.md) for the full source-of-truth map and maintenance
rules. Keep this file as a stable entrypoint for older links and quick human
routing.

## Counting Semantics

- Increment `run_count` for any started validation command that produced an
  observed result: `passed`, `failed`, `blocked`, `timed out`, `interrupted`,
  or `skipped`.
- Increment `pass_count` only for observed `passed` runs.
- Do not record selector recommendations, dry-run planning, grep/static
  inspection, or commands that never executed.

## Current Source Of Truth

- target metadata and last-run durability signals:
  [`test-execution-targets.csv`](test-execution-targets.csv)
- append-only observed execution history:
  [`test-execution-runs.csv`](test-execution-runs.csv)
- rolling recent/important summary:
  [`test-execution-summary.csv`](test-execution-summary.csv)
""",
        "docs/testing/TEST_EXECUTION_TARGETS.md": GENERATED_HEADER
        + """# Test Execution Targets

This document is the stable explainer for
[`test-execution-targets.csv`](test-execution-targets.csv).

## What The CSV Stores

`test-execution-targets.csv` stores one row per durable validation target,
including:

- target id
- category
- scope
- canonical command
- working directory
- relevant paths
- retest triggers
- last observed result metadata
- pass count
- run count

## When To Update It

Update this CSV when:

- a validation target becomes part of the durable repository target set;
- the canonical command, path surface, or working directory changes;
- a selector registry target needs a matching durable ledger row;
- reviewed observed results should update `last_*`, `pass_count`, or
  `run_count`.

## Related Files

- [test-execution-targets.csv](test-execution-targets.csv)
- [test-execution-runs.csv](test-execution-runs.csv)
- [TEST_EXECUTION_LEDGER.md](TEST_EXECUTION_LEDGER.md)
""",
        "docs/testing/TEST_EXECUTION_RUNS.md": GENERATED_HEADER
        + """# Test Execution Runs

This document is the stable explainer for
[`test-execution-runs.csv`](test-execution-runs.csv).

## What The CSV Stores

`test-execution-runs.csv` is the append-only observed run history.

Each row records a real validation attempt with fields such as:

- target id
- date
- branch
- source commit
- observed command
- result
- summary
- notes

## When To Update It

Append a row when a validation command actually executed and produced an
observable outcome.

Record:

- `passed`
- `failed`
- `blocked`
- `timed out`
- `interrupted`
- `skipped`

Do not record selector recommendations, dry-run planning, or commands that
never ran.

## Related Files

- [test-execution-runs.csv](test-execution-runs.csv)
- [test-execution-targets.csv](test-execution-targets.csv)
- [test-execution-summary.csv](test-execution-summary.csv)
""",
        "docs/testing/TEST_EXECUTION_SUMMARY.md": GENERATED_HEADER
        + """# Test Execution Summary

The concise recent/important validation summary lives in
[`test-execution-summary.csv`](test-execution-summary.csv).

Keep this file as a stable entrypoint for older links. Add new observed summary
rows to the CSV table, and keep detailed target metadata plus execution history
in:

- [`test-execution-targets.csv`](test-execution-targets.csv)
- [`test-execution-runs.csv`](test-execution-runs.csv)

See [`README.md`](README.md) for maintenance rules.
""",
        "docs/testing/PITFALL_INDEX.md": GENERATED_HEADER
        + """# Pitfall Index

This document is the stable explainer for
[`pitfall-index.csv`](pitfall-index.csv).

## What The CSV Stores

`pitfall-index.csv` is the structured companion to the canonical Markdown
pitfall bodies, especially [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)
plus the narrower topic-route docs it now links to.

Each row records:

- `pitfall_sequence`
- `source_commit_sha`
- `document_path`
- `line`
- `heading`
- `category`
- `status`
- `notes`

## Update Rule

Update the CSV in the same change set whenever a genuinely new pitfall is added
or when canonical pitfall bodies move and the structured index must stay in
sync.

## Related Files

- [pitfall-index.csv](pitfall-index.csv)
- [TEST_EXECUTION_PITFALLS.md](TEST_EXECUTION_PITFALLS.md)
- [pitfalls-ledger-and-selector-tooling.md](pitfalls-ledger-and-selector-tooling.md)
""",
    }


def write_docs(repo_root: Path) -> None:
    for rel_path, text in generated_docs().items():
        path = repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def check_docs(repo_root: Path) -> list[str]:
    issues: list[str] = []
    for rel_path, expected in generated_docs().items():
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"missing generated testing governance doc: {rel_path}")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            issues.append(f"stale generated testing governance doc: {rel_path}")
    return issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--check", action="store_true", help="Fail instead of rewriting when generated docs are stale.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if args.check:
        issues = check_docs(repo_root)
        if issues:
            print("Testing governance doc sync check failed:")
            for issue in issues:
                print(f"- {issue}")
            return 1
        print(f"Testing governance doc sync check passed. checked={len(generated_docs())}")
        return 0

    write_docs(repo_root)
    print(f"Wrote {len(generated_docs())} generated testing governance docs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
