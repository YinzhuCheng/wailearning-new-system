"""Migrate Markdown test execution ledgers into CSV tables.

The Markdown files are still kept as human entry points, but the durable
run/target records live in CSV so agents and scripts can append and parse them
without rewriting large narrative tables.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path


LEDGER_MD = Path("docs/testing/TEST_EXECUTION_LEDGER.md")
SUMMARY_MD = Path("docs/testing/TEST_EXECUTION_SUMMARY.md")
OUT_DIR = Path("docs/testing")
TARGETS_CSV = OUT_DIR / "test-execution-targets.csv"
RUNS_CSV = OUT_DIR / "test-execution-runs.csv"
SUMMARY_CSV = OUT_DIR / "test-execution-summary.csv"
README_MD = OUT_DIR / "README.md"


TARGET_FIELDS = [
    "test_id",
    "category",
    "scope",
    "canonical_command",
    "working_directory",
    "relevant_paths",
    "retest_triggers",
    "last_branch",
    "last_commit",
    "last_result",
    "last_run_date",
    "pass_count",
    "run_count",
]

RUN_FIELDS = [
    "test_id",
    "date",
    "branch",
    "commit",
    "command",
    "result",
    "summary",
    "notes",
]

SUMMARY_FIELDS = [
    "date",
    "branch",
    "target",
    "result",
    "scope_why_run",
    "key_outcome",
    "detail_ledger",
]


def strip_inline_markup(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        value = value[1:-1]
    value = value.replace("`", "")
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", value)
    return value.replace("\\|", "|").strip()


def split_markdown_row(line: str) -> list[str]:
    return [strip_inline_markup(part) for part in line.strip().strip("|").split("|")]


def read_fenced_block(lines: list[str], index: int) -> tuple[str, int]:
    while index < len(lines) and not lines[index].startswith("```"):
        index += 1
    if index >= len(lines):
        return "", index
    index += 1
    block: list[str] = []
    while index < len(lines) and not lines[index].startswith("```"):
        block.append(lines[index])
        index += 1
    if index < len(lines):
        index += 1
    return "\n".join(block).strip(), index


def read_bullets(lines: list[str], index: int) -> tuple[str, int]:
    bullets: list[str] = []
    while index < len(lines):
        line = lines[index]
        if line.startswith("**") or line.startswith("### "):
            break
        if line.startswith("- "):
            bullets.append(strip_inline_markup(line[2:].strip()))
        index += 1
    return "\n".join(bullets), index


def parse_ledger(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    targets: list[dict[str, str]] = []
    runs: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    i = 0

    heading_re = re.compile(r"^### Test ID: `([^`]+)`\s*$")
    inline_field_re = re.compile(
        r"^\*\*(Category|Scope|Working directory|Last branch|Last commit|Last result|Last run date|Pass count|Run count):\*\*\s*(.*)$"
    )

    while i < len(lines):
        line = lines[i]
        heading = heading_re.match(line)
        if heading:
            if current:
                targets.append(current)
            current = {field: "" for field in TARGET_FIELDS}
            current["test_id"] = heading.group(1)
            i += 1
            continue

        if current is None:
            i += 1
            continue

        field = inline_field_re.match(line)
        if field:
            key = field.group(1).lower().replace(" ", "_")
            current[key] = strip_inline_markup(field.group(2))
            i += 1
            continue

        if line == "**Canonical command:**":
            block, i = read_fenced_block(lines, i + 1)
            current["canonical_command"] = block
            continue

        if line == "**Relevant paths:**":
            value, i = read_bullets(lines, i + 1)
            current["relevant_paths"] = value
            continue

        if line == "**Retest triggers:**":
            value, i = read_bullets(lines, i + 1)
            current["retest_triggers"] = value
            continue

        if line == "**Runs:**":
            i += 1
            while i < len(lines):
                row = lines[i]
                if row.startswith("### "):
                    break
                if row.startswith("|") and not row.startswith("|---") and not row.startswith("| Date "):
                    cells = split_markdown_row(row)
                    if len(cells) >= 7:
                        runs.append(
                            {
                                "test_id": current["test_id"],
                                "date": cells[0],
                                "branch": cells[1],
                                "commit": cells[2],
                                "command": cells[3],
                                "result": cells[4],
                                "summary": cells[5],
                                "notes": "|".join(cells[6:]).strip(),
                            }
                        )
                i += 1
            continue

        i += 1

    if current:
        targets.append(current)
    return targets, runs


def parse_summary(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| Date "):
            continue
        cells = split_markdown_row(line)
        if len(cells) >= 7:
            rows.append(
                {
                    "date": cells[0],
                    "branch": cells[1],
                    "target": cells[2],
                    "result": cells[3],
                    "scope_why_run": cells[4],
                    "key_outcome": cells[5],
                    "detail_ledger": "|".join(cells[6:]).strip(),
                }
            )
    return rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_markdown_entrypoints() -> None:
    README_MD.write_text(
        """# Structured Test Execution Tables

This directory stores test execution history as CSV tables. The Markdown files
one level up remain human entry points and policy documents; the durable facts
that agents append and tooling parses live here.

## Files

| File | Purpose |
|------|---------|
| `test-execution-targets.csv` | One row per validation target: category, scope, canonical command, last observed result, pass count, run count, relevant paths, and retest triggers. |
| `test-execution-runs.csv` | Append-only observed run history. Add failed, blocked, timed-out, interrupted, and skipped attempts as well as passes. |
| `test-execution-summary.csv` | Short scan aid for recent or important observed validation runs. |

## Rules

1. Record only observed executions. Selector output, dry-run planning, and typed
   but unexecuted commands do not belong in these CSV files.
2. Append run rows; do not rewrite history unless correcting a transcription
   error.
3. Keep committed paths repository-relative. Put private absolute paths and
   machine-local logs under ignored `.agent-run/` or `.e2e-run/` directories.
4. Keep long explanations in Markdown docs such as
   `../TEST_EXECUTION_PITFALLS.md`; keep CSV notes short and factual.
5. Use UTF-8 and the repository safe-text workflow before editing these files
   from Windows PowerShell.
""",
        encoding="utf-8",
        newline="\n",
    )

    LEDGER_MD.write_text(
        """# Test Execution Ledger

The detailed execution ledger has been moved to CSV tables in this directory:

- [`test-execution-targets.csv`](test-execution-targets.csv)
  stores one row per validation target.
- [`test-execution-runs.csv`](test-execution-runs.csv) stores
  append-only observed run history.
- [`test-execution-summary.csv`](test-execution-summary.csv)
  stores the concise recent/important run summary.

Use [`README.md`](README.md) for maintenance rules. Keep this
Markdown file as a stable entry point for existing links and human guidance.

## Counting Semantics

- Increment `run_count` for any started validation command that produced an
  observable result: `passed`, `failed`, `blocked`, `timed out`, `interrupted`,
  or `skipped`.
- Increment `pass_count` only for `passed` target runs.
- Do not record selector recommendations, dry-run planning, grep/static
  inspection, or commands that were written in notes but not executed.

## Current Source Of Truth

For target metadata and last-run fields, use
[`test-execution-targets.csv`](test-execution-targets.csv).
For individual run evidence, use
[`test-execution-runs.csv`](test-execution-runs.csv).
""",
        encoding="utf-8",
        newline="\n",
    )

    SUMMARY_MD.write_text(
        """# Test Execution Summary

The concise recent/important validation summary now lives in
[`test-execution-summary.csv`](test-execution-summary.csv).

Keep this Markdown file as a stable entry point for existing documentation
links. Add new observed summary rows to the CSV table, and keep detailed target
metadata plus run history in:

- [`test-execution-targets.csv`](test-execution-targets.csv)
- [`test-execution-runs.csv`](test-execution-runs.csv)

See [`README.md`](README.md) for maintenance rules.
""",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    if not LEDGER_MD.exists():
        print(f"missing {LEDGER_MD}", file=sys.stderr)
        return 2

    targets, runs = parse_ledger(LEDGER_MD)
    summary = parse_summary(SUMMARY_MD)
    if not targets:
        print(f"no ledger targets parsed from {LEDGER_MD}", file=sys.stderr)
        return 1

    write_csv(TARGETS_CSV, TARGET_FIELDS, targets)
    write_csv(RUNS_CSV, RUN_FIELDS, runs)
    write_csv(SUMMARY_CSV, SUMMARY_FIELDS, summary)
    write_markdown_entrypoints()
    print(f"wrote {len(targets)} targets, {len(runs)} runs, {len(summary)} summary rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
