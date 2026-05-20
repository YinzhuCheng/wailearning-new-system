from __future__ import annotations

import argparse
import csv
from datetime import date

from common import current_branch, reject_private_markers, repo_root


RESULTS = {"passed", "failed", "blocked", "timed out", "interrupted", "skipped"}
FIELDS = ["test_id", "date", "branch", "commit", "command", "result", "summary", "notes"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Append one observed validation run row.")
    parser.add_argument("--test-id", required=True)
    parser.add_argument("--result", required=True, choices=sorted(RESULTS))
    parser.add_argument("--command", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--commit", default="this commit")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    root = repo_root()
    row = {
        "test_id": args.test_id,
        "date": args.date,
        "branch": current_branch(root),
        "commit": args.commit,
        "command": args.command,
        "result": args.result,
        "summary": args.summary,
        "notes": args.notes,
    }
    for key, value in row.items():
        reject_private_markers(str(value), key)

    path = root / "docs/testing/test-execution-runs.csv"
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writerow(row)
    print(f"appended {path.relative_to(root).as_posix()}: {args.test_id} {args.result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
