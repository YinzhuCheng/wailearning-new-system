from __future__ import annotations

import argparse
import csv

from common import current_commit, reject_private_markers, repo_root


FIELDS = ["pitfall_sequence", "source_commit_sha", "document_path", "line", "heading", "category", "status", "notes"]


def next_sequence(path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        values = []
        for row in rows:
            try:
                value = int(row.get("pitfall_sequence", "") or 0)
            except ValueError:
                continue
            if value > 0:
                values.append(value)
    return max(values, default=0) + 1


def find_heading_line(doc_path, heading: str) -> int:
    needle = heading.strip().lstrip("#").strip()
    for index, line in enumerate(doc_path.read_text(encoding="utf-8").splitlines(), 1):
        normalized = line.strip().lstrip("#").strip()
        if normalized == needle:
            return index
    raise SystemExit(f"heading not found in {doc_path}: {heading}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Append one structured pitfall index row.")
    parser.add_argument("--heading", required=True, help="Heading text, usually starting with 'Pitfall:'.")
    parser.add_argument("--category", required=True)
    parser.add_argument("--notes", required=True)
    parser.add_argument("--status", default="active")
    parser.add_argument("--document-path", default="docs/testing/TEST_EXECUTION_PITFALLS.md")
    parser.add_argument("--source-commit")
    args = parser.parse_args()

    root = repo_root()
    index_path = root / "docs/testing/pitfall-index.csv"
    doc_path = root / args.document_path
    line = find_heading_line(doc_path, args.heading)
    row = {
        "pitfall_sequence": str(next_sequence(index_path)),
        "source_commit_sha": args.source_commit or current_commit(root),
        "document_path": args.document_path.replace("\\", "/"),
        "line": str(line),
        "heading": args.heading.strip().lstrip("#").strip(),
        "category": args.category,
        "status": args.status,
        "notes": args.notes,
    }
    for key, value in row.items():
        reject_private_markers(str(value), key)

    with index_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writerow(row)
    print(f"appended {index_path.relative_to(root).as_posix()}: pitfall_sequence={row['pitfall_sequence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
