"""Check repository structure guardrails and root-file hygiene."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from governance_common import Finding, count_lines, has_error, print_findings, tracked_or_walked_paths


ALLOWED_ROOT_FILES = {
    ".editorconfig",
    ".env.production",
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "LICENSE",
    "README.md",
    "conftest.py",
    "pytest.ini",
    "requirements.txt",
}

ALLOWED_ROOT_DIRS = {
    ".github",
    "apps",
    "docs",
    "ops",
    "skills",
    "tests",
}

ROOT_LOG_NAMES = {"error.txt", "output.txt", "log.txt", "pytest.log", "test.log"}
ROOT_LOG_SUFFIXES = {".log"}

SEMANTIC_DIR_ALIASES = {
    "tooling": {"tools", "scripts", "devtools"},
    "frontend": {"frontend", "web"},
    "artifacts": {"logs", "test-results", "playwright-report"},
}


def check_root_entries(repo_root: Path, paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    tracked_roots = {path.split("/", 1)[0] for path in paths}
    for root in sorted(tracked_roots):
        full_path = repo_root / root
        if full_path.is_dir():
            if root not in ALLOWED_ROOT_DIRS:
                findings.append(Finding("error", "unexpected-root-dir", root, "tracked root directory is not allowed"))
            continue
        if root not in ALLOWED_ROOT_FILES:
            severity = "error" if root in ROOT_LOG_NAMES or full_path.suffix in ROOT_LOG_SUFFIXES else "warning"
            findings.append(Finding(severity, "unexpected-root-file", root, "tracked root file is not in the root contract"))
    return findings


def check_semantic_duplicates(paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    root_dirs = {path.split("/", 1)[0] for path in paths if "/" in path}
    for label, aliases in SEMANTIC_DIR_ALIASES.items():
        hits = sorted(root_dirs & aliases)
        if len(hits) > 1:
            findings.append(
                Finding("warning", "duplicate-root-semantics", ",".join(hits), f"multiple root folders suggest `{label}`")
            )
    return findings


def check_empty_or_small_docs(repo_root: Path, paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if path.startswith("docs/") and Path(path).suffix == ".md":
            lines = count_lines(repo_root, path)
            if lines and lines < 5:
                findings.append(Finding("warning", "tiny-doc", path, f"only {lines} lines; confirm it is useful"))
    return findings


def print_details(repo_root: Path, paths: list[str]) -> None:
    by_root: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        by_root[path.split("/", 1)[0]].append(path)
    print()
    print("Tracked root entries:")
    for root, members in sorted(by_root.items()):
        kind = "dir" if "/" in members[0] or (repo_root / root).is_dir() else "file"
        print(f"- {root} ({kind}, tracked_paths={len(members)})")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--details", action="store_true", help="Print tracked root entry inventory.")
    parser.add_argument("--json", action="store_true", help="Emit JSON findings.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    paths = tracked_or_walked_paths(repo_root, include_untracked=True)
    findings = check_root_entries(repo_root, paths)
    findings.extend(check_semantic_duplicates(paths))
    findings.extend(check_empty_or_small_docs(repo_root, paths))
    print_findings(findings, json_output=args.json)
    if args.details and not args.json:
        print_details(repo_root, paths)
    print(f"checked_paths={len(paths)} findings={len(findings)}")
    return 1 if has_error(findings) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
