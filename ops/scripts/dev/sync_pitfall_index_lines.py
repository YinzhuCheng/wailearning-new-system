"""Synchronize pitfall-index.csv line numbers from the canonical Markdown docs.

This script recalculates the `line` column in docs/testing/pitfall-index.csv by
searching each row's `heading` inside its `document_path`. It preserves row
order and CSV columns, and writes UTF-8 without BOM.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


FIELDS = [
    "pitfall_sequence",
    "source_commit_sha",
    "document_path",
    "line",
    "heading",
    "category",
    "status",
    "notes",
]


def repo_root_from(path: Path) -> Path:
    current = path.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").exists():
            return candidate
    raise SystemExit("Could not find repository root from current directory.")


def find_heading_line(doc_path: Path, heading: str) -> int:
    needle = heading.strip().lstrip("#").strip()
    for index, line in enumerate(doc_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        normalized = line.strip().lstrip("#").strip()
        if normalized == needle:
            return index
    raise ValueError(f"heading not found in {doc_path}: {heading}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument(
        "--index",
        default="docs/testing/pitfall-index.csv",
        help="Pitfall index path relative to repo root.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of rewriting when pitfall-index.csv line numbers are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = repo_root_from(Path(args.repo_root))
    index_path = repo_root / args.index
    if not index_path.exists():
        print(f"pitfall index not found: {index_path}", file=sys.stderr)
        return 2

    with index_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    updated_rows: list[dict[str, str]] = []
    changed = False
    for row in rows:
        document_path = str(row.get("document_path") or "").strip().replace("\\", "/")
        heading = str(row.get("heading") or "").strip()
        if not document_path or not heading:
            updated_rows.append({field: row.get(field, "") for field in FIELDS})
            continue
        doc_path = repo_root / document_path
        if not doc_path.exists():
            raise SystemExit(f"document_path does not exist: {document_path}")
        line_number = find_heading_line(doc_path, heading)
        new_row = {field: str(row.get(field, "") or "") for field in FIELDS}
        if new_row.get("line", "") != str(line_number):
            changed = True
        new_row["line"] = str(line_number)
        updated_rows.append(new_row)

    if args.check:
        if changed:
            print(f"pitfall index line sync check failed: {index_path.relative_to(repo_root).as_posix()} has stale line references")
            return 1
        print(f"pitfall index line sync check passed: rows={len(updated_rows)}")
        return 0

    with index_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(updated_rows)

    print(f"synchronized {index_path.relative_to(repo_root).as_posix()}: rows={len(updated_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
