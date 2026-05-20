"""Static governance checks for CI baseline alignment.

This script verifies that repository CI entrypoints use the same documented
runtime baselines and reproducible install/test commands where alignment is
expected. It is intentionally file-based and cross-platform.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


EXPECTED_GITHUB_ACTIONS_PYTHON = '"3.11"'
EXPECTED_GITHUB_ACTIONS_NODE = '"20"'
EXPECTED_EXTERNAL_CI_PYTHON = "'3.11'"
EXPECTED_PIP_UPGRADE = "python -m pip install --upgrade pip"
EXPECTED_PIP_INSTALL = "python -m pip install -r requirements.txt"
EXPECTED_PYTEST = "python -m pytest -q"
EXPECTED_NPM_INSTALL = "npm ci"
EXPECTED_SCHOOL_BUILD = "npm run build"
EXPECTED_PARENT_BUILD = "npm run build"

GITHUB_WORKFLOW = ".github/workflows/lightweight-validation.yml"
EXTERNAL_CI_PIPELINES = (
    "ops/ci/pr-pipeline.yml",
    "ops/ci/master-pipeline.yml",
    "ops/ci/branch-pipeline.yml",
)


def read_text(repo_root: Path, rel_path: str) -> str:
    return (repo_root / rel_path).read_text(encoding="utf-8")


def require_contains(issues: list[str], rel_path: str, text: str, needle: str, message: str) -> None:
    if needle not in text:
        issues.append(f"{rel_path}: {message}")


def require_not_contains(issues: list[str], rel_path: str, text: str, needle: str, message: str) -> None:
    if needle in text:
        issues.append(f"{rel_path}: {message}")


def check_github_actions(repo_root: Path, issues: list[str]) -> None:
    rel_path = GITHUB_WORKFLOW
    text = read_text(repo_root, rel_path)
    if text.count(f'python-version: {EXPECTED_GITHUB_ACTIONS_PYTHON}') < 2:
        issues.append(f"{rel_path}: expected both Python jobs to use python-version {EXPECTED_GITHUB_ACTIONS_PYTHON}")
    if text.count(f'node-version: {EXPECTED_GITHUB_ACTIONS_NODE}') < 2:
        issues.append(f"{rel_path}: expected both frontend jobs to use node-version {EXPECTED_GITHUB_ACTIONS_NODE}")
    require_contains(issues, rel_path, text, EXPECTED_PIP_UPGRADE, "must upgrade pip with the canonical python -m pip form")
    require_contains(issues, rel_path, text, EXPECTED_PIP_INSTALL, "must install backend dependencies with the canonical python -m pip form")
    require_contains(issues, rel_path, text, EXPECTED_PYTEST, "must run quick backend pytest with the canonical python -m pytest form")
    if text.count(EXPECTED_NPM_INSTALL) < 2:
        issues.append(f"{rel_path}: expected both frontend jobs to use reproducible '{EXPECTED_NPM_INSTALL}' installs")
    if text.count(EXPECTED_SCHOOL_BUILD) < 2:
        issues.append(f"{rel_path}: expected both frontend jobs to run '{EXPECTED_SCHOOL_BUILD}' builds")


def check_external_ci(repo_root: Path, issues: list[str]) -> None:
    for rel_path in EXTERNAL_CI_PIPELINES:
        text = read_text(repo_root, rel_path)
        require_contains(issues, rel_path, text, f"pythonVersion: {EXPECTED_EXTERNAL_CI_PYTHON}", f"must use pythonVersion {EXPECTED_EXTERNAL_CI_PYTHON}")
        require_contains(issues, rel_path, text, EXPECTED_PIP_UPGRADE, "must upgrade pip with the canonical python -m pip form")
        require_contains(issues, rel_path, text, EXPECTED_PIP_INSTALL, "must install backend dependencies with the canonical python -m pip form")
        require_contains(issues, rel_path, text, EXPECTED_PYTEST, "must run pytest with the canonical python -m pytest form")
        require_not_contains(issues, rel_path, text, "python3 -m pip install --upgrade pip", "must not use python3-prefixed pip upgrade drift")
        require_not_contains(issues, rel_path, text, "pip3 install -r requirements.txt", "must not use pip3 install drift")
        require_not_contains(issues, rel_path, text, "python3 -m pytest -q", "must not use python3-prefixed pytest drift")


def check_ci_baselines(repo_root: Path) -> list[str]:
    issues: list[str] = []
    check_github_actions(repo_root, issues)
    check_external_ci(repo_root, issues)
    return issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    issues = check_ci_baselines(repo_root)
    if issues:
        print("CI baseline governance check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    checked = 1 + len(EXTERNAL_CI_PIPELINES)
    print(f"CI baseline governance check passed. checked={checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
