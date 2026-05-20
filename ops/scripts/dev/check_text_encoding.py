"""Check tracked text files for UTF-8 decode errors and mojibake markers.

The script scans `git ls-files` by default so local artifacts and private notes
are excluded. It is intentionally conservative: UTF-8 decode errors fail the
command; suspicious mojibake markers are reported but do not fail unless
--fail-on-suspicious is supplied.

Examples:

    python ops/scripts/dev/check_text_encoding.py
    python ops/scripts/dev/check_text_encoding.py --fail-on-suspicious
    python ops/scripts/dev/check_text_encoding.py docs/contributing/ENCODING_AND_MOJIBAKE_SAFETY.md
"""

from __future__ import annotations

import argparse
import subprocess
import sys
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
    ".production",
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

SUSPICIOUS_MARKERS = {
    "\ufffd": "replacement-character",
    "\u00c3": "latin1-utf8-marker-A-tilde",
    "\u00c2": "latin1-utf8-marker-A-circumflex",
    "\u951f\u65a4\u62f7": "common-Chinese-mojibake-marker",
    "\u9200": "cp936-mojibake-marker",
    "\u920e": "cp936-mojibake-marker",
    "\u920b": "cp936-mojibake-marker",
    "\u6ec3": "cp936-mojibake-marker",
    "\u7ddf": "cp936-mojibake-marker",
    "\u7ead": "cp936-mojibake-marker",
    "\u6e2e": "cp936-mojibake-marker",
    "\u6e03": "cp936-mojibake-marker",
    "\u6de2": "cp936-mojibake-marker",
    "\u6402": "cp936-mojibake-marker",
    "\u8e47": "cp936-mojibake-marker",
    "\u7025": "cp936-mojibake-marker",
    "\u721c": "cp936-mojibake-marker",
    "\u9422": "cp936-mojibake-marker",
    "\u7ee0": "cp936-mojibake-marker",
    "\u608a": "cp936-mojibake-marker",
    "\u0431\u043a": "mojibake-dash-marker",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    column: int
    marker: str
    label: str


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
    name = Path(path).name
    suffix = Path(path).suffix
    return name in TEXT_FILENAMES or suffix in TEXT_EXTENSIONS


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


def find_marker_positions(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for marker, label in SUSPICIOUS_MARKERS.items():
            start = 0
            while True:
                index = line.find(marker, start)
                if index == -1:
                    break
                findings.append(
                    Finding(
                        path=path,
                        line=line_no,
                        column=index + 1,
                        marker=marker.encode("unicode_escape").decode("ascii"),
                        label=label,
                    )
                )
                start = index + len(marker)
    return findings


def scan_paths(repo_root: Path, paths: Iterable[str]) -> tuple[list[str], list[Finding], int]:
    decode_errors: list[str] = []
    suspicious: list[Finding] = []
    scanned = 0
    for rel_path in paths:
        full_path = repo_root / rel_path
        try:
            raw = full_path.read_bytes()
        except OSError as exc:
            decode_errors.append(f"{rel_path}: unable to read: {exc}")
            continue
        if b"\0" in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            decode_errors.append(f"{rel_path}: UTF-8 decode error at byte {exc.start}: {exc.reason}")
            continue
        scanned += 1
        suspicious.extend(find_marker_positions(rel_path, text))
    return decode_errors, suspicious, scanned


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Optional repo-relative files to scan instead of git ls-files.")
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument(
        "--skip-if-empty",
        action="store_true",
        help="When explicit paths are empty, scan no files instead of falling back to git ls-files.",
    )
    parser.add_argument(
        "--fail-on-suspicious",
        action="store_true",
        help="Return non-zero when suspicious mojibake markers are found.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if args.skip_if_empty and not args.paths:
        paths = []
    else:
        paths = iter_candidate_paths(repo_root, args.paths)
    decode_errors, suspicious, scanned = scan_paths(repo_root, paths)

    for item in decode_errors:
        print(f"ERROR {item}")
    for finding in suspicious:
        print(
            "SUSPICIOUS "
            f"{finding.path}:{finding.line}:{finding.column} "
            f"{finding.label} {finding.marker}"
        )

    skipped = " skipped=empty-input" if args.skip_if_empty and not args.paths else ""
    print(f"scanned={scanned} decode_errors={len(decode_errors)} suspicious={len(suspicious)}{skipped}")

    if decode_errors:
        return 1
    if suspicious and args.fail_on_suspicious:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
