"""Audit committed CSV files for suspicious text and recover safe history candidates.

The script is conservative by design:

- it only inspects UTF-8 CSV files;
- it flags suspicious cells using marker-based heuristics plus obvious question-
  mark replacement runs such as ``????``;
- it searches git history for rows with the same leading key columns;
- it only applies a repair when exactly one clean historical candidate exists.

Examples:

    python ops/scripts/dev/audit_csv_mojibake.py
    python ops/scripts/dev/audit_csv_mojibake.py --json
    python ops/scripts/dev/audit_csv_mojibake.py --apply
    python ops/scripts/dev/audit_csv_mojibake.py docs/testing/agent-update-log.csv --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from check_text_encoding import SUSPICIOUS_MARKERS


DEFAULT_CSV_PATHS = [
    "docs/testing/agent-update-log.csv",
    "docs/testing/pitfall-index.csv",
    "docs/testing/test-execution-runs.csv",
    "docs/testing/test-execution-summary.csv",
    "docs/testing/test-execution-targets.csv",
    "docs/testing/validation-debt-registry.csv",
]

QUESTION_MARK_RUN = "????"
MAX_HISTORY_COMMITS = 80


@dataclass(frozen=True)
class SuspiciousCell:
    row_number: int
    column_number: int
    column_name: str
    reason: str
    value: str


@dataclass(frozen=True)
class HistoryCandidate:
    commit: str
    row_text: str
    source: str


@dataclass(frozen=True)
class Finding:
    path: str
    row_number: int
    key: tuple[str, ...]
    suspicious_cells: list[SuspiciousCell]
    history_candidates: list[HistoryCandidate]


@dataclass(frozen=True)
class Repair:
    path: str
    row_number: int
    from_row: str
    to_row: str
    commit: str
    key: tuple[str, ...]


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Optional repo-relative CSV files.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown text.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply only rows that have exactly one clean historical candidate.",
    )
    parser.add_argument(
        "--max-history-commits",
        type=int,
        default=MAX_HISTORY_COMMITS,
        help="Maximum history commits to inspect per file.",
    )
    return parser.parse_args(argv)


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    return result.stdout


def iter_target_paths(repo_root: Path, requested: list[str]) -> list[str]:
    if requested:
        return [normalize_path(item) for item in requested]
    return [path for path in DEFAULT_CSV_PATHS if (repo_root / path).exists()]


def read_csv_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def suspicious_reasons(value: str) -> list[str]:
    reasons: list[str] = []
    if QUESTION_MARK_RUN in value:
        reasons.append("question-mark-run")
    for marker, label in SUSPICIOUS_MARKERS.items():
        if marker in value:
            reasons.append(label)
    return sorted(set(reasons))


def csv_rows_from_text(text: str) -> list[list[str]]:
    return list(csv.reader(text.splitlines()))


def build_key(rows: list[list[str]], row_index: int) -> tuple[str, ...]:
    row = rows[row_index]
    for width in range(1, min(4, len(row)) + 1):
        key = tuple(row[:width])
        if not any(tuple(other[:width]) == key for i, other in enumerate(rows) if i != row_index):
            return key
    return tuple(row[: min(4, len(row))])


def key_matches(row: list[str], key: tuple[str, ...]) -> bool:
    if len(row) < len(key):
        return False
    return tuple(row[: len(key)]) == key


def find_suspicious_rows(path: str, text: str) -> list[Finding]:
    rows = csv_rows_from_text(text)
    if not rows:
        return []
    header = rows[0]
    findings: list[Finding] = []
    for row_index, row in enumerate(rows[1:], start=1):
        suspicious_cells: list[SuspiciousCell] = []
        for column_index, value in enumerate(row):
            reasons = suspicious_reasons(value)
            if not reasons:
                continue
            column_name = header[column_index] if column_index < len(header) else f"column_{column_index + 1}"
            suspicious_cells.append(
                SuspiciousCell(
                    row_number=row_index + 1,
                    column_number=column_index + 1,
                    column_name=column_name,
                    reason=",".join(reasons),
                    value=value,
                )
            )
        if suspicious_cells:
            findings.append(
                Finding(
                    path=path,
                    row_number=row_index + 1,
                    key=build_key(rows, row_index),
                    suspicious_cells=suspicious_cells,
                    history_candidates=[],
                )
            )
    return findings


def iter_history_commits(repo_root: Path, path: str, max_commits: int) -> list[str]:
    output = run_git(repo_root, ["log", "--format=%H", "--", path])
    commits = [line.strip() for line in output.splitlines() if line.strip()]
    return commits[:max_commits]


def file_text_at_commit(repo_root: Path, commit: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return None
    return result.stdout


def row_is_clean(row: list[str]) -> bool:
    return all(not suspicious_reasons(value) for value in row)


def history_candidates_for_finding(
    repo_root: Path,
    finding: Finding,
    max_commits: int,
) -> list[HistoryCandidate]:
    seen_rows: set[str] = set()
    candidates: list[HistoryCandidate] = []
    for commit in iter_history_commits(repo_root, finding.path, max_commits):
        text = file_text_at_commit(repo_root, commit, finding.path)
        if not text:
            continue
        rows = csv_rows_from_text(text)
        for row in rows[1:]:
            if not key_matches(row, finding.key):
                continue
            row_text = ",".join(f'"{cell}"' if "," in cell else cell for cell in row)
            if row_text in seen_rows:
                continue
            seen_rows.add(row_text)
            if row_is_clean(row):
                candidates.append(
                    HistoryCandidate(
                        commit=commit[:7],
                        row_text=row_text,
                        source="git-history-clean-row",
                    )
                )
            break
    return candidates


def enrich_findings(repo_root: Path, findings: list[Finding], max_commits: int) -> list[Finding]:
    enriched: list[Finding] = []
    for finding in findings:
        enriched.append(
            Finding(
                path=finding.path,
                row_number=finding.row_number,
                key=finding.key,
                suspicious_cells=finding.suspicious_cells,
                history_candidates=history_candidates_for_finding(repo_root, finding, max_commits),
            )
        )
    return enriched


def current_row_text(text: str, row_number: int) -> str:
    rows = csv_rows_from_text(text)
    row = rows[row_number - 1]
    return ",".join(f'"{cell}"' if "," in cell else cell for cell in row)


def exact_row_repair(repo_root: Path, finding: Finding) -> Repair | None:
    if len(finding.history_candidates) != 1:
        return None
    path = repo_root / finding.path
    text = read_csv_text(path)
    rows = csv_rows_from_text(text)
    target_index = finding.row_number - 1
    candidate_row = next(csv.reader([finding.history_candidates[0].row_text]))
    if len(candidate_row) != len(rows[target_index]):
        return None
    return Repair(
        path=finding.path,
        row_number=finding.row_number,
        from_row=current_row_text(text, finding.row_number),
        to_row=finding.history_candidates[0].row_text,
        commit=finding.history_candidates[0].commit,
        key=finding.key,
    )


def apply_repairs(repo_root: Path, repairs: list[Repair]) -> None:
    by_path: dict[str, list[Repair]] = {}
    for repair in repairs:
        by_path.setdefault(repair.path, []).append(repair)
    for path, file_repairs in by_path.items():
        full_path = repo_root / path
        rows = csv_rows_from_text(read_csv_text(full_path))
        for repair in sorted(file_repairs, key=lambda item: item.row_number):
            rows[repair.row_number - 1] = next(csv.reader([repair.to_row]))
        with full_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerows(rows)


def render_text(findings: list[Finding], repairs: list[Repair]) -> str:
    lines: list[str] = []
    if not findings:
        lines.append("No suspicious CSV content found.")
    for finding in findings:
        lines.append(f"{finding.path}:{finding.row_number} key={finding.key}")
        for cell in finding.suspicious_cells:
            lines.append(
                f"  cell {cell.column_number} ({cell.column_name}) {cell.reason}: {cell.value}"
            )
        if finding.history_candidates:
            lines.append("  history candidates:")
            for candidate in finding.history_candidates:
                lines.append(f"    {candidate.commit} {candidate.row_text}")
        else:
            lines.append("  history candidates: none")
    if repairs:
        lines.append("")
        lines.append("Auto-repair candidates:")
        for repair in repairs:
            lines.append(
                f"  {repair.path}:{repair.row_number} from {repair.commit} key={repair.key}"
            )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    findings: list[Finding] = []
    for path in iter_target_paths(repo_root, args.paths):
        full_path = repo_root / path
        if not full_path.exists():
            print(f"SKIP missing {path}", file=sys.stderr)
            continue
        findings.extend(enrich_findings(repo_root, find_suspicious_rows(path, read_csv_text(full_path)), args.max_history_commits))

    repairs = [repair for finding in findings if (repair := exact_row_repair(repo_root, finding)) is not None]

    if args.apply and repairs:
        apply_repairs(repo_root, repairs)

    if args.json:
        payload = {
            "findings": [asdict(finding) for finding in findings],
            "repairs": [asdict(repair) for repair in repairs],
            "applied": bool(args.apply and repairs),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(findings, repairs))
        if args.apply:
            print(f"\nApplied repairs: {len(repairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
