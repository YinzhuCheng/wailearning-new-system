from __future__ import annotations

import argparse
import csv
from pathlib import Path

from common import repo_root


DEFAULT_FILES = [
    "docs/testing/test-execution-runs.csv",
    "docs/testing/test-execution-summary.csv",
    "docs/testing/pitfall-index.csv",
    "docs/testing/agent-update-log.csv",
]


def count_rows(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse CourseEval CSV ledgers and print row counts.")
    parser.add_argument("paths", nargs="*", default=DEFAULT_FILES)
    args = parser.parse_args()
    root = repo_root()
    for rel in args.paths:
        path = root / rel
        print(f"{rel}: {count_rows(path)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
