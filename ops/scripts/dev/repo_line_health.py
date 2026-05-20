"""Count repository line totals for long-term health tracking.

The script intentionally counts tracked repository files by default. That keeps
local caches, private notes, virtual environments, browser reports, and build
outputs out of the metrics without needing to mirror every ignore rule here.

Run from the repository root:

    python ops/scripts/dev/repo_line_health.py
    python ops/scripts/dev/repo_line_health.py --json
    python ops/scripts/dev/repo_line_health.py --details
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".bat",
    ".cjs",
    ".conf",
    ".css",
    ".csv",
    ".editorconfig",
    ".env",
    ".example",
    ".gitignore",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".rst",
    ".service",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}

TEXT_FILENAMES = {
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "LICENSE",
    "README.md",
}

GENERATED_OR_LOCK_FILENAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}

DOC_EXTENSIONS = {".md", ".rst", ".txt"}

PRIMARY_SOURCE_PREFIXES = (
    "apps/backend/courseeval_backend/",
    "apps/web/school/src/",
    "apps/web/parent/src/",
)

TEST_PREFIXES = (
    "tests/backend/",
    "tests/behavior/",
    "tests/e2e/",
    "tests/postgres/",
    "tests/security/",
    "tests/scenarios/",
)

TOOLING_PREFIXES = (
    "tests/devtools/",
    "ops/scripts/",
)

OPS_PREFIXES = (
    "ops/ci/",
    "ops/nginx/",
    "ops/systemd/",
)

CONFIG_FILENAMES = {
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    "conftest.py",
    "pytest.ini",
    "requirements.txt",
}


@dataclass(frozen=True)
class FileMetric:
    path: str
    category: str
    extension: str
    lines: int
    bytes: int


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def run_git_ls_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [normalize_path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def fallback_walk(repo_root: Path) -> list[str]:
    skipped_dirs = {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "dist",
        "build",
        ".pytest_tmp",
        ".pytest_tmpbasetemp",
        ".pytest-db",
        ".pytest_cache",
        ".e2e-run",
        "test-results",
        "playwright-report",
        "__pycache__",
    }
    paths: list[str] = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [name for name in dirs if name not in skipped_dirs]
        root_path = Path(root)
        for file_name in files:
            rel = root_path.joinpath(file_name).relative_to(repo_root)
            paths.append(normalize_path(str(rel)))
    return sorted(paths)


def is_probably_text(path: str) -> bool:
    file_name = Path(path).name
    suffix = Path(path).suffix
    return file_name in TEXT_FILENAMES or suffix in TEXT_EXTENSIONS


def classify(path: str) -> str:
    file_name = Path(path).name
    suffix = Path(path).suffix

    if file_name in GENERATED_OR_LOCK_FILENAMES:
        return "generated_or_lock"
    if path.startswith("docs/") or file_name in {"AGENTS.md", "README.md"}:
        return "documentation"
    if suffix in DOC_EXTENSIONS and path.startswith(("apps/", "ops/", "tests/")):
        return "documentation"
    if path in {"conftest.py", "pytest.ini"} or path.startswith(TEST_PREFIXES):
        return "test_code"
    if path.startswith(PRIMARY_SOURCE_PREFIXES):
        return "primary_source"
    if path.startswith(TOOLING_PREFIXES):
        return "tooling"
    if path.startswith(OPS_PREFIXES):
        return "operations"
    if path in CONFIG_FILENAMES or path.endswith((".config.js", ".config.cjs", ".config.mjs")):
        return "configuration"
    if path.startswith("apps/"):
        return "application_support"
    return "other"


def count_lines(repo_root: Path, path: str) -> FileMetric | None:
    if not is_probably_text(path):
        return None

    full_path = repo_root / Path(path)
    try:
        raw = full_path.read_bytes()
    except OSError:
        return None

    if b"\0" in raw:
        return None

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None

    lines = text.count("\n")
    if text and not text.endswith("\n"):
        lines += 1

    return FileMetric(
        path=path,
        category=classify(path),
        extension=Path(path).suffix or Path(path).name,
        lines=lines,
        bytes=len(raw),
    )


def collect_metrics(repo_root: Path, include_untracked: bool) -> list[FileMetric]:
    if include_untracked:
        paths = fallback_walk(repo_root)
    else:
        try:
            paths = run_git_ls_files(repo_root)
        except (subprocess.CalledProcessError, FileNotFoundError):
            paths = fallback_walk(repo_root)

    metrics: list[FileMetric] = []
    for path in paths:
        metric = count_lines(repo_root, path)
        if metric is not None:
            metrics.append(metric)
    return metrics


def summarize(metrics: Iterable[FileMetric]) -> dict[str, object]:
    metrics = list(metrics)
    by_category: Counter[str] = Counter()
    files_by_category: Counter[str] = Counter()
    by_extension: Counter[str] = Counter()

    for metric in metrics:
        by_category[metric.category] += metric.lines
        files_by_category[metric.category] += 1
        by_extension[metric.extension] += metric.lines

    total_lines = sum(metric.lines for metric in metrics)
    health_total = total_lines - by_category["generated_or_lock"]

    return {
        "total_text_lines": total_lines,
        "health_text_lines_excluding_generated_or_lock": health_total,
        "total_text_files": len(metrics),
        "category_lines": dict(sorted(by_category.items())),
        "category_files": dict(sorted(files_by_category.items())),
        "top_extensions_by_lines": dict(by_extension.most_common(15)),
    }


def print_markdown(summary: dict[str, object], metrics: list[FileMetric], details: bool) -> None:
    category_lines = summary["category_lines"]
    category_files = summary["category_files"]
    assert isinstance(category_lines, dict)
    assert isinstance(category_files, dict)

    print("# Repository Line Health")
    print()
    print(f"- Total tracked text lines: {summary['total_text_lines']}")
    print(
        "- Health text lines excluding generated/lock files: "
        f"{summary['health_text_lines_excluding_generated_or_lock']}"
    )
    print(f"- Total tracked text files: {summary['total_text_files']}")
    print()
    print("## Required Health Categories")
    print()
    print("| Category | Lines | Files |")
    print("|----------|-------|-------|")
    for category in ("documentation", "test_code", "primary_source"):
        print(f"| `{category}` | {category_lines.get(category, 0)} | {category_files.get(category, 0)} |")

    print()
    print("## Supporting Categories")
    print()
    print("| Category | Lines | Files |")
    print("|----------|-------|-------|")
    for category, lines in category_lines.items():
        if category in {"documentation", "test_code", "primary_source"}:
            continue
        print(f"| `{category}` | {lines} | {category_files.get(category, 0)} |")

    print()
    print("## Top Extensions By Lines")
    print()
    print("| Extension | Lines |")
    print("|-----------|-------|")
    top_extensions = summary["top_extensions_by_lines"]
    assert isinstance(top_extensions, dict)
    for extension, lines in top_extensions.items():
        print(f"| `{extension}` | {lines} |")

    if details:
        print()
        print("## Largest Files")
        print()
        print("| Lines | Category | Path |")
        print("|-------|----------|------|")
        for metric in sorted(metrics, key=lambda item: item.lines, reverse=True)[:50]:
            print(f"| {metric.lines} | `{metric.category}` | `{metric.path}` |")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of Markdown.",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Include the largest 50 files in Markdown output.",
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Walk the working tree instead of using git ls-files. Local artifacts are still skipped.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    metrics = collect_metrics(repo_root, include_untracked=args.include_untracked)
    summary = summarize(metrics)

    if args.json:
        payload = {
            "repo_root": "<repo>",
            "mode": "working-tree-walk" if args.include_untracked else "git-ls-files",
            **summary,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_markdown(summary, metrics, details=args.details)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
