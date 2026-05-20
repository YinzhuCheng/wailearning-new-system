"""Report CourseEval boundary risks: large files and suspicious imports."""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

from governance_common import Finding, count_lines, has_error, print_findings, read_text, tracked_or_walked_paths


BACKEND_PREFIX = "apps/backend/courseeval_backend/"
LARGE_THRESHOLDS = {
    "apps/backend/courseeval_backend/api/routers/": 900,
    "apps/backend/courseeval_backend/domains/": 700,
    "apps/backend/courseeval_backend/core/": 500,
    "apps/backend/courseeval_backend/db/": 1600,
    "apps/backend/courseeval_backend/": 900,
    "apps/web/school/src/": 900,
    "apps/web/parent/src/": 900,
}


@dataclass(frozen=True)
class ImportEdge:
    source: str
    target: str


def threshold_for(path: str) -> int | None:
    best: tuple[int, int] | None = None
    for prefix, threshold in LARGE_THRESHOLDS.items():
        if path.startswith(prefix):
            score = len(prefix)
            if best is None or score > best[0]:
                best = (score, threshold)
    return best[1] if best else None


def check_large_files(repo_root: Path, paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if Path(path).suffix not in {".py", ".vue", ".js", ".ts"}:
            continue
        threshold = threshold_for(path)
        if threshold is None:
            continue
        lines = count_lines(repo_root, path)
        if lines > threshold:
            findings.append(
                Finding(
                    "warning",
                    "large-boundary-file",
                    path,
                    f"{lines} lines exceeds governance threshold {threshold}; consider ownership split or documented follow-up",
                )
            )
    return findings


def import_name_to_path(name: str) -> str | None:
    prefix = "apps.backend.courseeval_backend."
    if not name.startswith(prefix):
        return None
    relative = name[len(prefix) :].replace(".", "/")
    return f"{BACKEND_PREFIX}{relative}"


def parse_import_edges(repo_root: Path, paths: list[str]) -> list[ImportEdge]:
    edges: list[ImportEdge] = []
    for path in paths:
        if not path.startswith(BACKEND_PREFIX) or Path(path).suffix != ".py":
            continue
        text = read_text(repo_root, path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = import_name_to_path(alias.name)
                    if target:
                        edges.append(ImportEdge(path, target))
            elif isinstance(node, ast.ImportFrom) and node.module:
                target = import_name_to_path(node.module)
                if target:
                    edges.append(ImportEdge(path, target))
    return edges


def check_import_boundaries(edges: list[ImportEdge]) -> list[Finding]:
    findings: list[Finding] = []
    for edge in edges:
        source = edge.source
        target = edge.target
        if "/domains/" in source and "/api/routers/" in target:
            findings.append(Finding("error", "domain-imports-router", source, f"domain code imports `{target}`"))
        if "/core/" in source and ("/api/routers/" in target or "/domains/" in target):
            findings.append(Finding("error", "core-imports-upper-layer", source, f"core code imports `{target}`"))
        if "/db/" in source and ("/api/routers/" in target or "/domains/" in target or "/core/auth" in target):
            findings.append(Finding("error", "db-imports-upper-layer", source, f"db code imports `{target}`"))
        if "/api/routers/" in source and "/api/routers/" in target and source != target:
            findings.append(Finding("warning", "router-imports-router", source, f"router imports `{target}`"))
    return findings


def print_details(repo_root: Path, paths: list[str], edges: list[ImportEdge]) -> None:
    largest = []
    for path in paths:
        if path.startswith(("apps/backend/courseeval_backend/", "apps/web/school/src/", "apps/web/parent/src/")):
            suffix = Path(path).suffix
            if suffix in {".py", ".vue", ".js", ".ts"}:
                largest.append((count_lines(repo_root, path), path))
    print()
    print("Largest implementation files:")
    for lines, path in sorted(largest, reverse=True)[:20]:
        print(f"- {lines:5d} {path}")
    print()
    print(f"backend_import_edges={len(edges)}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--details", action="store_true", help="Print largest files and edge count.")
    parser.add_argument("--json", action="store_true", help="Emit JSON findings.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    paths = tracked_or_walked_paths(repo_root, include_untracked=True)
    edges = parse_import_edges(repo_root, paths)
    findings = check_large_files(repo_root, paths)
    findings.extend(check_import_boundaries(edges))
    print_findings(findings, json_output=args.json)
    if args.details and not args.json:
        print_details(repo_root, paths, edges)
    print(f"checked_paths={len(paths)} findings={len(findings)}")
    return 1 if has_error(findings) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
