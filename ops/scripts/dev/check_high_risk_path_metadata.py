"""Validate committed high-risk path metadata and required coverage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_METADATA = "docs/governance/high-risk-path-metadata.json"
DEFAULT_TARGET_REGISTRY = "tests/TEST_SELECTION_TARGETS.json"
ALLOWED_RISK_CLASSES = {"high", "critical"}
ALLOWED_MIGRATION_SENSITIVITY = {"medium", "high"}
REQUIRED_PATHS = {
    "apps/backend/courseeval_backend/db/",
    "apps/backend/courseeval_backend/api/schema_defs/",
    "apps/backend/courseeval_backend/domains/roster/",
    "tests/e2e/web-school/",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def check_high_risk_path_metadata(repo_root: Path, metadata_path: str, target_registry_path: str) -> list[str]:
    metadata = load_json(repo_root / metadata_path)
    target_registry = load_json(repo_root / target_registry_path)
    targets = target_registry.get("targets", [])
    if not isinstance(targets, list):
        raise ValueError("target registry `targets` must be a list")
    target_ids = {str(target.get("id")) for target in targets if isinstance(target, dict) and target.get("id")}

    rows = metadata.get("paths")
    if not isinstance(rows, list):
        raise ValueError("high-risk path metadata `paths` must be a list")

    issues: list[str] = []
    seen_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            issues.append("non-object row in high-risk path metadata")
            continue
        path = str(row.get("path") or "").strip().replace("\\", "/")
        owner_area = str(row.get("owner_area") or "").strip()
        risk_class = str(row.get("risk_class") or "").strip()
        migration_sensitivity = str(row.get("migration_sensitivity") or "").strip()
        families = row.get("required_validation_families")

        if not path:
            issues.append("metadata row missing path")
            continue
        if path in seen_paths:
            issues.append(f"duplicate metadata path: {path}")
        seen_paths.add(path)
        if not (repo_root / path.rstrip("/")).exists():
            issues.append(f"metadata path does not exist: {path}")
        if not owner_area:
            issues.append(f"{path}: missing owner_area")
        if risk_class not in ALLOWED_RISK_CLASSES:
            issues.append(f"{path}: invalid risk_class `{risk_class}`")
        if migration_sensitivity not in ALLOWED_MIGRATION_SENSITIVITY:
            issues.append(f"{path}: invalid migration_sensitivity `{migration_sensitivity}`")
        if not isinstance(families, list) or not families or not all(isinstance(item, str) and item.strip() for item in families):
            issues.append(f"{path}: required_validation_families must be a non-empty string list")
        else:
            for family in families:
                if family not in target_ids:
                    issues.append(f"{path}: unknown required_validation_family `{family}`")

    for required_path in sorted(REQUIRED_PATHS - seen_paths):
        issues.append(f"missing required high-risk metadata path: {required_path}")
    return issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--metadata", default=DEFAULT_METADATA, help="High-risk metadata JSON path.")
    parser.add_argument("--target-registry", default=DEFAULT_TARGET_REGISTRY, help="Selector target registry JSON path.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    try:
        issues = check_high_risk_path_metadata(repo_root, args.metadata, args.target_registry)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}")
        return 2

    if issues:
        print("High-risk path metadata check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("High-risk path metadata check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
