from __future__ import annotations

import argparse
import json
import subprocess

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


def git_paths(root, staged: bool, include_untracked: bool) -> list[str]:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="List changed text files suitable for encoding checks.")
    parser.add_argument("--staged", action="store_true", help="Inspect staged diff instead of worktree diff.")
    parser.add_argument("--tracked-only", action="store_true", help="Do not include untracked files in worktree mode.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = repo_root()
    paths = [
        path
        for path in git_paths(root, args.staged, include_untracked=not args.tracked_only)
        if (root / path).suffix.lower() in TEXT_SUFFIXES
    ]
    if args.json:
        print(json.dumps(paths, ensure_ascii=False, indent=2))
    else:
        for path in paths:
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
