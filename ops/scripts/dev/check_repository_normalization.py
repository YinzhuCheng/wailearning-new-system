"""Check that repository normalization guardrails still match CourseEval.

This is a lightweight governance check. It catches active documentation or
source paths that reintroduce retired CourseEval predecessor names, while
allowing explicitly historical handoffs and append-only test ledgers to keep
their audit value.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


STALE_TOKENS = {
    "wailearning_backend": "retired backend package name",
    "DD-CLASS": "retired product name",
    "BIMSA-CLASS": "retired product name",
    "wailearning.xyz": "retired domain example",
    "WAILEARNING_AUTO_PG_TESTS": "retired test env var",
    "ddclass": "retired service/name fragment",
    "dd-class": "retired service/name fragment",
}

TOKEN_PATTERNS = {
    token: re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", re.IGNORECASE)
    for token in STALE_TOKENS
}

REQUIRED_PATHS = (
    "apps/backend/courseeval_backend",
    "ops/systemd/courseeval-backend.service",
    "ops/nginx/courseeval.example.conf",
    "ops/nginx/courseeval.example.http.conf",
)

HISTORICAL_PATH_PREFIXES = (
    "docs/handoffs/",
    "docs/testing/",
)

HISTORICAL_PATHS: set[str] = set()

ALLOWED_WARNING_PATHS = {
    "AGENTS.md",
    "ops/scripts/dev/check_repository_normalization.py",
}

TEXT_EXTENSIONS = {
    ".bat",
    ".cjs",
    ".conf",
    ".css",
    ".csv",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".production",
    ".py",
    ".service",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".txt",
    ".vue",
    ".yaml",
    ".yml",
}

TEXT_FILENAMES = {
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "README.md",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    token: str
    reason: str


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


def is_text_path(path: str) -> bool:
    candidate = Path(path)
    return candidate.name in TEXT_FILENAMES or candidate.suffix in TEXT_EXTENSIONS


def is_historical_path(path: str) -> bool:
    return path in HISTORICAL_PATHS or any(path.startswith(prefix) for prefix in HISTORICAL_PATH_PREFIXES)


def iter_candidate_paths(repo_root: Path, requested: list[str]) -> list[str]:
    if requested:
        paths: list[str] = []
        for item in requested:
            item_path = Path(item)
            if item_path.is_absolute():
                paths.append(normalize_path(str(item_path.relative_to(repo_root))))
            else:
                paths.append(normalize_path(item))
        return paths
    return [path for path in git_ls_files(repo_root) if is_text_path(path)]


def scan_tokens(repo_root: Path, paths: Iterable[str]) -> list[Finding]:
    findings: list[Finding] = []
    for rel_path in paths:
        if is_historical_path(rel_path) or rel_path in ALLOWED_WARNING_PATHS:
            continue
        full_path = repo_root / rel_path
        try:
            raw = full_path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        lowered = text.lower()
        if not any(token.lower() in lowered for token in STALE_TOKENS):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for token, reason in STALE_TOKENS.items():
                if TOKEN_PATTERNS[token].search(line):
                    findings.append(Finding(rel_path, line_no, token, reason))
    return findings


def check_required_paths(repo_root: Path) -> list[str]:
    missing: list[str] = []
    for rel_path in REQUIRED_PATHS:
        if not (repo_root / rel_path).exists():
            missing.append(rel_path)
    return missing


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Optional repo-relative files to scan instead of tracked files.")
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    paths = iter_candidate_paths(repo_root, args.paths)
    findings = scan_tokens(repo_root, paths)
    missing = check_required_paths(repo_root)

    for finding in findings:
        print(f"STALE {finding.path}:{finding.line}: {finding.token} ({finding.reason})")
    for rel_path in missing:
        print(f"MISSING required current path: {rel_path}")

    print(f"scanned={len(paths)} stale={len(findings)} missing_required_paths={len(missing)}")
    return 1 if findings or missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
