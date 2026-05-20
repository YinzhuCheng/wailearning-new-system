"""Audit canonical Student rows and student User bindings before migration.

This command is read-only by default. It reports conflicts and safe legacy
binding candidates so data conversion can be reviewed before any repair step is
introduced.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def add_repo_root_to_path() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    repo_root_text = str(repo_root)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format. Defaults to json.",
    )
    return parser.parse_args(argv)


def print_text(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print("Student identity audit")
    print(f"students: {summary['students']}")
    print(f"users: {summary['users']}")
    print(f"student_users: {summary['student_users']}")
    print("")
    for issue_id, count in summary["issues"].items():
        print(f"{issue_id}: {count}")
        for row in report["issues"][issue_id]:
            print(f"  - {json.dumps(row, ensure_ascii=False, sort_keys=True)}")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    add_repo_root_to_path()

    from apps.backend.courseeval_backend.db.database import SessionLocal
    from apps.backend.courseeval_backend.domains.roster.audit import audit_student_identity

    db = SessionLocal()
    try:
        report = audit_student_identity(db)
    finally:
        db.close()

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
