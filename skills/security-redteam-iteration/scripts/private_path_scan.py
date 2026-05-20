from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from common import repo_root


TEXT_SUFFIXES = {
    ".cjs",
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".sh",
    ".sql",
    ".ts",
    ".txt",
    ".vue",
    ".yaml",
    ".yml",
}

PATTERNS = [
    ("windows-user-path", re.compile(r"C:\\Users\\(?!<user>)[^\\\s,;]+", re.IGNORECASE)),
    ("slash-user-path", re.compile(r"C:/Users/(?!<user>)[^/\s,;]+", re.IGNORECASE)),
    ("agent-run-artifact", re.compile(r"\.agent-run[/\\]logs[/\\][0-9A-Za-z_-]+")),
    ("local-playwright-sqlite", re.compile(r"playwright_e2e_\d+\.sqlite")),
    ("unredacted-local-postgres-url", re.compile(r"postgresql\+psycopg2://[^,\s]*@127\.0\.0\.1:\d+")),
]

ALLOWLIST_SNIPPETS = (
    'r"C:/Users/"',
    'r"C:\\Users\\\\"',
    'C:/Users/(?!<user>',
    'C:\\\\Users\\\\(?!<user>',
    "postgresql+psycopg2://courseeval_test:courseeval_test@127.0.0.1:5432/courseeval_pytest_all",
    "<repo>/.agent-run/logs/",
    "<repo>\\.agent-run\\logs\\",
    "C:/Users/...",
    "C:\\Users\\...",
)


def changed_paths(root: Path, staged: bool, include_untracked: bool) -> list[str]:
    args = ["git", "diff", "--name-only", "--diff-filter=ACMRT"]
    if staged:
        args.insert(2, "--cached")
    output = subprocess.check_output(args, cwd=str(root), text=True, encoding="utf-8")
    paths = [line.strip() for line in output.splitlines() if line.strip()]
    if include_untracked and not staged:
        untracked = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(root),
            text=True,
            encoding="utf-8",
        )
        paths.extend(line.strip() for line in untracked.splitlines() if line.strip())
    return sorted(dict.fromkeys(paths))


def scan_file(root: Path, rel: str) -> list[str]:
    path = root / rel
    if not path.exists() or path.suffix.lower() not in TEXT_SUFFIXES:
        return []
    issues: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_no, line in enumerate(text.splitlines(), 1):
        if any(snippet in line for snippet in ALLOWLIST_SNIPPETS):
            continue
        for label, pattern in PATTERNS:
            if pattern.search(line):
                issues.append(f"{rel}:{line_no}: {label}: {line.strip()[:180]}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan changed files for likely private local paths or artifacts.")
    parser.add_argument("--staged", action="store_true", help="Scan staged diff instead of worktree diff.")
    parser.add_argument("--tracked-only", action="store_true", help="Do not include untracked files in worktree mode.")
    parser.add_argument("--fail", action="store_true", help="Exit non-zero when issues are found.")
    args = parser.parse_args()
    root = repo_root()
    issues: list[str] = []
    for rel in changed_paths(root, args.staged, include_untracked=not args.tracked_only):
        issues.extend(scan_file(root, rel))
    if not issues:
        print("private path scan: no suspects")
        return 0
    print("private path scan suspects:")
    for issue in issues:
        print(f"- {issue}")
    return 1 if args.fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
