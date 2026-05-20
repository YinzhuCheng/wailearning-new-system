"""Lint the machine-readable validation target registry.

This script validates the registry structure and repository references so
selector/runtime errors are caught before a real validation pass depends on the
broken entry.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY = "tests/TEST_SELECTION_TARGETS.json"
DEFAULT_LEDGER = "docs/testing/test-execution-targets.csv"
ALLOWED_RISKS = {"static", "targeted", "broad", "full"}
ALLOWED_CATEGORIES = {
    "static-check",
    "backend-pytest",
    "behavior-pytest",
    "security-pytest",
    "postgres-pytest",
    "frontend-build",
    "frontend-node-test",
    "school-playwright",
    "parent-playwright",
    "full-suite",
}
ALLOWED_POLICY_REQUIREMENTS = {"required", "required-review", "recommended"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"registry root must be a JSON object: {path}")
    return data


def parse_ledger_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return {
                str(row.get("test_id") or "").strip()
                for row in csv.DictReader(handle)
                if str(row.get("test_id") or "").strip()
            }
    ids: set[str] = set()
    prefix = "### Test ID: `"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix) and line.endswith("`"):
            ids.add(line[len(prefix) : -1])
    return ids


def is_literal_repo_path(path: str) -> bool:
    return not any(ch in path for ch in "*?[")


def check_repo_path_exists(repo_root: Path, value: str) -> bool:
    normalized = value.replace("\\", "/")
    if normalized.endswith("/"):
        return (repo_root / normalized.rstrip("/")).is_dir()
    return (repo_root / normalized).exists()


def check_playwright_command_target_exists(repo_root: Path, argv: list[str]) -> list[str]:
    issues: list[str] = []
    if len(argv) < 2:
        return issues
    if argv[0] in {"npx", "npx.cmd"} and argv[1:3] == ["playwright", "test"]:
        spec_args = argv[3:]
    elif (
        argv[0] == "node"
        and len(argv) >= 2
        and argv[1].replace("\\", "/").endswith("scripts/playwright-external-runner.cjs")
    ):
        spec_args = argv[2:]
    else:
        return issues
    for part in spec_args:
        if part.startswith("-"):
            continue
        if not part.endswith((".spec.js", ".cjs")):
            continue
        candidate = repo_root / "tests" / "e2e" / "web-school" / part
        if not candidate.exists():
            issues.append(f"referenced Playwright file does not exist: tests/e2e/web-school/{part}")
    return issues


def lint_registry(repo_root: Path, registry_path: str, ledger_path: str) -> list[str]:
    registry_file = repo_root / registry_path
    registry = load_json(registry_file)
    ledger_ids = parse_ledger_ids(repo_root / ledger_path)
    issues: list[str] = []

    targets = registry.get("targets")
    if not isinstance(targets, list):
        return [f"`targets` must be a list in {registry_path}"]

    fallback_rules = registry.get("fallback_rules", [])
    if not isinstance(fallback_rules, list):
        issues.append(f"`fallback_rules` must be a list in {registry_path}")
        fallback_rules = []

    target_ids = [str(target.get("id")) for target in targets if isinstance(target, dict)]
    seen_ids: set[str] = set()
    duplicates: set[str] = set()
    for target_id in target_ids:
        if target_id in seen_ids:
            duplicates.add(target_id)
        seen_ids.add(target_id)
    for target_id in sorted(duplicates):
        issues.append(f"duplicate target id: {target_id}")

    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            issues.append(f"target[{index}] is not an object")
            continue

        target_id = str(target.get("id") or f"<target-{index}>")
        risk = str(target.get("risk") or "")
        category = str(target.get("category") or "")
        working_directory = str(target.get("working_directory") or "")
        policy_requirement = target.get("policy_requirement")
        policy_class = target.get("policy_class")
        required_capabilities = target.get("required_capabilities")

        if not target.get("id"):
            issues.append(f"{target_id}: missing `id`")
        if category not in ALLOWED_CATEGORIES:
            issues.append(f"{target_id}: invalid category `{category}`")
        if risk not in ALLOWED_RISKS:
            issues.append(f"{target_id}: invalid risk `{risk}`")
        if policy_requirement is not None and (
            not isinstance(policy_requirement, str) or policy_requirement not in ALLOWED_POLICY_REQUIREMENTS
        ):
            issues.append(f"{target_id}: invalid policy_requirement `{policy_requirement}`")
        if policy_requirement == "required-review" and not target.get("requires_review_reason"):
            issues.append(f"{target_id}: required-review targets must define requires_review_reason")
        if policy_class is not None and (not isinstance(policy_class, str) or not policy_class.strip()):
            issues.append(f"{target_id}: policy_class must be a non-empty string when present")
        if required_capabilities is not None and (
            not isinstance(required_capabilities, list)
            or not all(isinstance(value, str) and value.strip() for value in required_capabilities)
        ):
            issues.append(f"{target_id}: required_capabilities must be a string list when present")
        if not working_directory:
            issues.append(f"{target_id}: missing `working_directory`")
        elif not (repo_root / working_directory).exists():
            issues.append(f"{target_id}: working_directory does not exist: {working_directory}")

        ledger_id = target.get("ledger_id")
        if ledger_id is not None and not isinstance(ledger_id, str):
            issues.append(f"{target_id}: ledger_id must be a string or null")
        if isinstance(ledger_id, str) and ledger_id != target_id:
            issues.append(f"{target_id}: ledger_id must match target id unless an explicit alias mechanism is added: {ledger_id}")
        if isinstance(ledger_id, str) and ledger_id not in ledger_ids:
            issues.append(f"{target_id}: ledger_id not found in ledger: {ledger_id}")
        if target_id in ledger_ids and ledger_id is None:
            issues.append(f"{target_id}: target has a committed ledger row but ledger_id is null")
        if target_id in ledger_ids and isinstance(ledger_id, str) and ledger_id != target_id:
            issues.append(
                f"{target_id}: target has its own committed ledger row but ledger_id points elsewhere: {ledger_id}"
            )

        commands = target.get("commands")
        if not isinstance(commands, list) or not commands:
            issues.append(f"{target_id}: commands must be a non-empty list")
            commands = []
        for command_index, command in enumerate(commands):
            if not isinstance(command, dict):
                issues.append(f"{target_id}: command[{command_index}] is not an object")
                continue
            label = command.get("label")
            argv = command.get("argv")
            if not isinstance(label, str) or not label.strip():
                issues.append(f"{target_id}: command[{command_index}] missing non-empty label")
            if not isinstance(argv, list) or not argv or not all(isinstance(part, str) and part for part in argv):
                issues.append(f"{target_id}: command[{command_index}] argv must be a non-empty string list")
                argv = []
            requires_env = command.get("requires_env")
            if requires_env is not None and (
                not isinstance(requires_env, list)
                or not all(isinstance(value, str) and value for value in requires_env)
            ):
                issues.append(f"{target_id}: command[{command_index}] requires_env must be a string list when present")
            if argv:
                issues.extend(f"{target_id}: {message}" for message in check_playwright_command_target_exists(repo_root, argv))

        triggers = target.get("triggers")
        if not isinstance(triggers, dict):
            issues.append(f"{target_id}: triggers must be an object")
            triggers = {}
        for key in ("paths", "globs"):
            values = triggers.get(key, [])
            if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
                issues.append(f"{target_id}: triggers.{key} must be a string list")
                continue
            if key == "paths":
                for value in values:
                    if is_literal_repo_path(value) and not check_repo_path_exists(repo_root, value):
                        issues.append(f"{target_id}: trigger path does not exist: {value}")

    for index, rule in enumerate(fallback_rules):
        if not isinstance(rule, dict):
            issues.append(f"fallback_rules[{index}] is not an object")
            continue
        rule_id = str(rule.get("id") or f"<fallback-{index}>")
        recommend = rule.get("recommend", [])
        if not isinstance(recommend, list) or not recommend:
            issues.append(f"{rule_id}: recommend must be a non-empty list")
        else:
            for target_id in recommend:
                if not isinstance(target_id, str) or target_id not in seen_ids:
                    issues.append(f"{rule_id}: recommend references unknown target id: {target_id}")

        for key in ("unless_recommended_targets",):
            values = rule.get(key, [])
            if values and (not isinstance(values, list) or not all(isinstance(value, str) for value in values)):
                issues.append(f"{rule_id}: {key} must be a string list")
                continue
            for value in values:
                if value not in seen_ids:
                    issues.append(f"{rule_id}: {key} references unknown target id: {value}")

        categories = rule.get("unless_recommended_categories", [])
        if categories and (not isinstance(categories, list) or not all(isinstance(value, str) for value in categories)):
            issues.append(f"{rule_id}: unless_recommended_categories must be a string list")
        else:
            for value in categories:
                if value not in ALLOWED_CATEGORIES:
                    issues.append(f"{rule_id}: unless_recommended_categories references invalid category: {value}")

    return issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help=f"Registry path. Defaults to {DEFAULT_REGISTRY}.")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER, help=f"Ledger path. Defaults to {DEFAULT_LEDGER}.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    try:
        issues = lint_registry(repo_root, args.registry, args.ledger)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}")
        return 2

    if issues:
        print("Validation registry lint failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Validation registry lint passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
