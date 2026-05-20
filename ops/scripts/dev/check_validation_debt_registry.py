"""Validate the test debt registry against known targets and files."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_DEBT_REGISTRY = "docs/testing/validation-debt-registry.csv"
DEFAULT_TARGET_REGISTRY = "tests/TEST_SELECTION_TARGETS.json"
ALLOWED_ITEM_TYPES = {"target", "file"}
ALLOWED_CLASSIFICATIONS = {"active_required_coverage", "optional_stress_coverage", "explicit_backlog_debt"}
REQUIRED_TARGET_IDS = {
    "school.e2e.docs_gap_tier15",
    "school.e2e.agent_hazard_tier15",
    "school.e2e.learning_notes_attendance_cover_tier20",
    "school.e2e.notification_sync_deep_tier",
    "school.e2e.scenario_resilience",
    "school.e2e.future_advanced_coverage_part1",
    "school.e2e.future_advanced_coverage_part2",
}
REQUIRED_FILE_PATHS = {
    "tests/e2e/web-school/e2e-tier4-stress-backlog.spec.js",
}


def load_target_ids(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("target registry root must be an object")
    targets = payload.get("targets", [])
    if not isinstance(targets, list):
        raise ValueError("target registry `targets` must be a list")
    return {str(target.get("id")) for target in targets if isinstance(target, dict) and target.get("id")}


def check_validation_debt_registry(
    repo_root: Path,
    debt_registry_path: str,
    target_registry_path: str,
) -> list[str]:
    target_ids = load_target_ids(repo_root / target_registry_path)
    registry_path = repo_root / debt_registry_path
    issues: list[str] = []
    if not registry_path.exists():
        return [f"missing validation debt registry: {debt_registry_path}"]

    with registry_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    seen_entry_ids: set[str] = set()
    seen_targets: set[str] = set()
    seen_files: set[str] = set()

    for row in rows:
        entry_id = str(row.get("entry_id") or "").strip()
        item_type = str(row.get("item_type") or "").strip()
        target_id = str(row.get("target_id") or "").strip()
        file_path = str(row.get("file_path") or "").strip().replace("\\", "/")
        classification = str(row.get("classification") or "").strip()
        default_lane = str(row.get("default_lane") or "").strip()
        rationale = str(row.get("rationale") or "").strip()
        exit_criteria = str(row.get("exit_criteria") or "").strip()

        if not entry_id:
            issues.append("row missing entry_id")
        elif entry_id in seen_entry_ids:
            issues.append(f"duplicate entry_id: {entry_id}")
        seen_entry_ids.add(entry_id)

        if item_type not in ALLOWED_ITEM_TYPES:
            issues.append(f"{entry_id or '<missing-entry-id>'}: invalid item_type `{item_type}`")
            continue

        if classification not in ALLOWED_CLASSIFICATIONS:
            issues.append(f"{entry_id}: invalid classification `{classification}`")
        if not default_lane:
            issues.append(f"{entry_id}: missing default_lane")
        if not rationale:
            issues.append(f"{entry_id}: missing rationale")
        if not exit_criteria:
            issues.append(f"{entry_id}: missing exit_criteria")

        if item_type == "target":
            if not target_id:
                issues.append(f"{entry_id}: target item missing target_id")
            elif target_id not in target_ids:
                issues.append(f"{entry_id}: unknown target_id `{target_id}`")
            else:
                seen_targets.add(target_id)
            if file_path:
                issues.append(f"{entry_id}: target item should not set file_path")
        else:
            if not file_path:
                issues.append(f"{entry_id}: file item missing file_path")
            elif not (repo_root / file_path).exists():
                issues.append(f"{entry_id}: file_path does not exist: {file_path}")
            else:
                seen_files.add(file_path)
            if target_id:
                issues.append(f"{entry_id}: file item should not set target_id")

    for target_id in sorted(REQUIRED_TARGET_IDS - seen_targets):
        issues.append(f"missing required target debt classification: {target_id}")
    for file_path in sorted(REQUIRED_FILE_PATHS - seen_files):
        issues.append(f"missing required file debt classification: {file_path}")
    return issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--debt-registry", default=DEFAULT_DEBT_REGISTRY, help="Debt registry CSV path.")
    parser.add_argument("--target-registry", default=DEFAULT_TARGET_REGISTRY, help="Selector target registry JSON path.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    try:
        issues = check_validation_debt_registry(repo_root, args.debt_registry, args.target_registry)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}")
        return 2

    if issues:
        print("Validation debt registry check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Validation debt registry check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
