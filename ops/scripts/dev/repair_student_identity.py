"""Repair new-system/default student identity bindings.

The command is dry-run by default. Use --apply to run the existing canonical
Student/User reconciliation and commit it. Ambiguous audit findings block apply
so default demo accounts can be repaired without pretending this is a complex
historical migration tool.
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
        "--apply",
        action="store_true",
        help="Apply and commit the repair. Without this flag the command only reports planned work.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format. Defaults to json.",
    )
    return parser.parse_args(argv)


def print_text(report: dict[str, Any]) -> None:
    print("Student identity repair")
    print(f"applied: {report['applied']}")
    print(f"blocked: {report['blocked']}")
    print("")
    print("planned:")
    for key, value in report["planned"].items():
        print(f"  {key}: {value}")
    print("")
    print(f"before issues: {json.dumps(report['before']['issues'], ensure_ascii=False, sort_keys=True)}")
    if report["after"] is not None:
        print(f"after issues: {json.dumps(report['after']['issues'], ensure_ascii=False, sort_keys=True)}")
    if report["blocking_issues"]:
        print("")
        print("blocking issues:")
        for issue_id, rows in report["blocking_issues"].items():
            print(f"  {issue_id}: {len(rows)}")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    add_repo_root_to_path()

    from apps.backend.courseeval_backend.db.database import SessionLocal
    from apps.backend.courseeval_backend.domains.roster.repair import repair_student_identity

    db = SessionLocal()
    try:
        report = repair_student_identity(db, apply=args.apply)
        if args.apply and report["applied"]:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
