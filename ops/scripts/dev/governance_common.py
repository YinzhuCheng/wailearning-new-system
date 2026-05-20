"""Shared helpers for repository governance checks."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
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
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "LICENSE",
    "README.md",
}

SKIPPED_WALK_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "ENV",
    "node_modules",
    "dist",
    "build",
    ".pytest_tmp",
    ".pytest_tmpbasetemp",
    ".pytest-db",
    ".pytest_cache",
    ".agent-run",
    ".e2e-run",
    "playwright-report",
    "test-results",
    "__pycache__",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    detail: str


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def git_ls_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [normalize_path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def git_ls_untracked(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [normalize_path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def fallback_walk(repo_root: Path) -> list[str]:
    paths: list[str] = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [name for name in dirs if name not in SKIPPED_WALK_DIRS]
        root_path = Path(root)
        for file_name in files:
            rel = root_path.joinpath(file_name).relative_to(repo_root)
            paths.append(normalize_path(str(rel)))
    return sorted(paths)


def tracked_or_walked_paths(repo_root: Path, include_untracked: bool = False) -> list[str]:
    try:
        tracked = git_ls_files(repo_root)
        if include_untracked:
            return sorted(set(tracked + git_ls_untracked(repo_root)))
        return tracked
    except (FileNotFoundError, subprocess.CalledProcessError):
        return fallback_walk(repo_root)


def is_text_path(path: str) -> bool:
    candidate = Path(path)
    return candidate.name in TEXT_FILENAMES or candidate.suffix in TEXT_EXTENSIONS


def read_text(repo_root: Path, path: str) -> str | None:
    full_path = repo_root / path
    try:
        raw = full_path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None


def text_paths(repo_root: Path, paths: Iterable[str]) -> list[str]:
    return [path for path in paths if is_text_path(path) and read_text(repo_root, path) is not None]


def count_lines(repo_root: Path, path: str) -> int:
    text = read_text(repo_root, path)
    if text is None:
        return 0
    lines = text.count("\n")
    if text and not text.endswith("\n"):
        lines += 1
    return lines


def print_findings(findings: list[Finding], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps([asdict(finding) for finding in findings], indent=2, sort_keys=True))
        return
    if not findings:
        print("No governance findings.")
        return
    for finding in findings:
        print(f"{finding.severity.upper()} {finding.code} {finding.path}: {finding.detail}")


def has_error(findings: Iterable[Finding]) -> bool:
    return any(finding.severity == "error" for finding in findings)
