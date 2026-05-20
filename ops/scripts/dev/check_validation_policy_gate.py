"""Fail when selector-required validation classes are unavailable in the CI lane."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_AVAILABLE_POLICY_CLASSES = (
    "static-check",
    "backend-pytest",
    "behavior-pytest",
    "security-pytest",
    "frontend-build",
    "frontend-node-test",
)


def load_selection(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("selection payload must be a JSON object")
    return payload


def evaluate_policy_gate(selection: dict[str, Any], available_policy_classes: set[str]) -> list[str]:
    required_validation = selection.get("required_validation")
    if not isinstance(required_validation, dict):
        return ["selection payload does not contain required_validation"]

    issues: list[str] = []
    for bucket_name in ("required_targets", "required_review_targets"):
        items = required_validation.get(bucket_name, [])
        if not isinstance(items, list):
            issues.append(f"required_validation.{bucket_name} must be a list")
            continue
        for item in items:
            if not isinstance(item, dict):
                issues.append(f"required_validation.{bucket_name} contains a non-object entry")
                continue
            target_id = str(item.get("id") or "<unknown-target>")
            policy_class = str(item.get("policy_class") or "unknown")
            if policy_class not in available_policy_classes:
                issues.append(
                    f"{target_id}: required policy class `{policy_class}` is unavailable in this CI lane"
                )
    return issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-file", required=True, help="Selector JSON payload file to evaluate.")
    parser.add_argument(
        "--available-policy-classes",
        nargs="*",
        default=list(DEFAULT_AVAILABLE_POLICY_CLASSES),
        help="Policy classes available in this CI lane.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        selection = load_selection(Path(args.selection_file))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}")
        return 2

    available_policy_classes = {value for value in args.available_policy_classes if value}
    issues = evaluate_policy_gate(selection, available_policy_classes)
    if issues:
        print("Validation policy gate failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    classes = ", ".join(sorted(available_policy_classes))
    print(f"Validation policy gate passed. available_policy_classes={classes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
