from __future__ import annotations

import argparse
import csv

from common import reject_private_markers, repo_root


FIELDS = [
    "update_sequence",
    "source_commit_sha",
    "conversation_scope",
    "changed_files_summary",
    "code_changed",
    "tests_changed",
    "docs_changed",
    "pitfalls_changed",
    "validation_summary",
    "notes",
]


def bool_arg(value: str) -> str:
    lowered = value.strip().lower()
    if lowered not in {"true", "false"}:
        raise argparse.ArgumentTypeError("expected true or false")
    return lowered


def next_sequence(path) -> int:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        values = [int(row["update_sequence"]) for row in rows if row.get("update_sequence")]
    return max(values, default=0) + 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Append one repository-changing conversation round row.")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--changed-files", required=True)
    parser.add_argument("--code", required=True, type=bool_arg)
    parser.add_argument("--tests", required=True, type=bool_arg)
    parser.add_argument("--docs", required=True, type=bool_arg)
    parser.add_argument("--pitfalls", required=True, type=bool_arg)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    root = repo_root()
    path = root / "docs/testing/agent-update-log.csv"
    row = {
        "update_sequence": str(next_sequence(path)),
        "source_commit_sha": args.source_commit,
        "conversation_scope": args.scope,
        "changed_files_summary": args.changed_files,
        "code_changed": args.code,
        "tests_changed": args.tests,
        "docs_changed": args.docs,
        "pitfalls_changed": args.pitfalls,
        "validation_summary": args.validation,
        "notes": args.notes,
    }
    for key, value in row.items():
        reject_private_markers(str(value), key)

    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writerow(row)
    print(f"appended {path.relative_to(root).as_posix()}: update_sequence={row['update_sequence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
