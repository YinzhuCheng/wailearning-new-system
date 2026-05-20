"""Clean safe, reproducible local Python test/cache artifacts.

This script intentionally uses a narrow allowlist. It does not remove logs,
CSV ledgers, handoffs, pitfall records, validation history, Playwright traces,
uploads, node_modules, virtualenvs, generated frontend bundles, or other files
that may be needed for later investigation. Local `.agent-run` root files are
archived instead of deleted unless they are fixed entrypoint files that should
stay at stable paths. Bare screenshots under `.agent-run/screenshots` are moved
into a timestamped subdirectory so screenshots stay grouped by task or run.
Legacy top-level `.agent-run` directories are consolidated into `archive/`,
`logs/`, `screenshots/`, or `tools/` to keep the local workspace navigable.
"""

from __future__ import annotations

import argparse
import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


SAFE_ROOT_DIRS = {
    ".pytest_cache",
    ".pytest_tmp",
    ".pytest_tmpbasetemp",
    ".pytest-db",
}

PYTHON_CACHE_SCAN_ROOTS = (
    ".",
    "apps",
    "ops",
    "skills",
    "tests",
)

PYTHON_CACHE_FILE_PATTERNS = {
    ".pyc",
    ".pyo",
}

SAFE_ROOT_COVERAGE_NAMES = {
    ".coverage",
}

EVIDENCE_FILE_SUFFIXES = {
    ".csv",
    ".log",
    ".json",
    ".jsonl",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".txt",
    ".webm",
    ".yml",
    ".yaml",
    ".zip",
}

PROTECTED_DIR_PARTS = {
    ".agent-run",
    ".e2e-run",
    ".git",
    ".github",
    ".venv",
    ".vite",
    "ENV",
    "dist",
    "docs",
    "env",
    "htmlcov",
    "node_modules",
    "playwright-report",
    "test-results",
    "uploads",
    "venv",
}

AGENT_RUN_ROOT_KEEP_FILES = {
    "local-private-paths.md",
    "run-postgres-pytest.ps1",
    "use-local-env.cmd",
    "use-local-env.ps1",
    "validation-history.jsonl",
}

AGENT_RUN_TMP_DIR_PREFIXES = (
    "pg-validation-",
    "tmp",
)

AGENT_RUN_SCREENSHOT_SUFFIXES = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".webm",
}

AGENT_RUN_TOP_LEVEL_DIR_ARCHIVES = {
    "debug-playwright-runner-logs": ("logs", "legacy"),
    "debug-runner-logs": ("logs", "legacy"),
    "test-selector-playwright-preflight-logs": ("logs", "legacy"),
    "test-selector-runner-logs": ("logs", "legacy"),
    "local-tools": ("tools", "local-tools"),
    "pg-initdb-probe": ("archive", "postgres"),
    "postgres-validation": ("archive", "postgres"),
    "playwright-timeout-triage": ("archive", "triage"),
    "test-selector-spawn-eperm": ("archive", "triage"),
}

AGENT_RUN_EMPTY_TOP_LEVEL_DIRS = {
    "tmp",
}


@dataclass(frozen=True)
class CleanupAction:
    operation: str
    source: Path
    destination: Path | None = None
    allow_protected: bool = False


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def iter_python_cache_targets(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in PROTECTED_DIR_PARTS and not dirname.startswith(".vite")
        ]

        if current.name == "__pycache__":
            yield current
            dirnames[:] = []
            continue

        for filename in filenames:
            path = current / filename
            if path.suffix in PYTHON_CACHE_FILE_PATTERNS:
                yield path


def collect_cache_targets(repo_root: Path) -> list[Path]:
    targets: set[Path] = set()

    for dirname in SAFE_ROOT_DIRS:
        path = repo_root / dirname
        if path.exists():
            targets.add(path)

    for filename in SAFE_ROOT_COVERAGE_NAMES:
        path = repo_root / filename
        if path.is_file():
            targets.add(path)

    for path in repo_root.glob(".coverage.*"):
        if path.is_file() and path.suffix.lower() not in EVIDENCE_FILE_SUFFIXES:
            targets.add(path)

    for root_name in PYTHON_CACHE_SCAN_ROOTS:
        root = repo_root if root_name == "." else repo_root / root_name
        if not root.exists() or not root.is_dir():
            continue
        for path in iter_python_cache_targets(root):
            if path.is_dir() or path.is_file():
                targets.add(path)

    return sorted(targets, key=lambda item: (len(item.parts), str(item).lower()), reverse=True)


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 1
    while True:
        candidate = path.with_name(f"{path.name}.{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def collect_agent_run_root_archives(repo_root: Path, archive_stamp: str) -> list[CleanupAction]:
    agent_run = repo_root / ".agent-run"
    if not agent_run.is_dir():
        return []

    archive_root = agent_run / "archive" / "root-files" / archive_stamp
    actions: list[CleanupAction] = []
    for path in sorted(agent_run.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        if path.name in AGENT_RUN_ROOT_KEEP_FILES:
            continue
        destination = unique_destination(archive_root / path.name)
        actions.append(
            CleanupAction(
                operation="archive",
                source=path,
                destination=destination,
                allow_protected=True,
            )
        )
    return actions


def collect_agent_run_tmp_removals(repo_root: Path, min_age_hours: float) -> list[CleanupAction]:
    tmp_root = repo_root / ".agent-run" / "tmp"
    if not tmp_root.is_dir():
        return []

    cutoff = datetime.now(UTC) - timedelta(hours=min_age_hours)
    actions: list[CleanupAction] = []
    for path in sorted(tmp_root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_dir():
            continue
        if not path.name.startswith(AGENT_RUN_TMP_DIR_PREFIXES):
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if mtime > cutoff:
            continue
        actions.append(CleanupAction(operation="remove", source=path, allow_protected=True))
    return actions


def collect_agent_run_screenshot_archives(repo_root: Path, archive_stamp: str) -> list[CleanupAction]:
    screenshot_root = repo_root / ".agent-run" / "screenshots"
    if not screenshot_root.is_dir():
        return []

    destination_root = screenshot_root / "unfiled" / archive_stamp
    actions: list[CleanupAction] = []
    for path in sorted(screenshot_root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in AGENT_RUN_SCREENSHOT_SUFFIXES:
            continue
        destination = unique_destination(destination_root / path.name)
        actions.append(
            CleanupAction(
                operation="archive",
                source=path,
                destination=destination,
                allow_protected=True,
            )
        )
    return actions


def collect_agent_run_directory_archives(repo_root: Path, archive_stamp: str) -> list[CleanupAction]:
    agent_run = repo_root / ".agent-run"
    if not agent_run.is_dir():
        return []

    actions: list[CleanupAction] = []
    for dirname, destination_parts in AGENT_RUN_TOP_LEVEL_DIR_ARCHIVES.items():
        source = agent_run / dirname
        if not source.is_dir():
            continue
        destination = unique_destination(agent_run.joinpath(*destination_parts, archive_stamp, dirname))
        if destination_parts[0] == "tools":
            destination = unique_destination(agent_run.joinpath(*destination_parts))
        actions.append(
            CleanupAction(
                operation="archive",
                source=source,
                destination=destination,
                allow_protected=True,
            )
        )
    return actions


def collect_agent_run_empty_dir_removals(repo_root: Path) -> list[CleanupAction]:
    agent_run = repo_root / ".agent-run"
    if not agent_run.is_dir():
        return []

    actions: list[CleanupAction] = []
    for dirname in AGENT_RUN_EMPTY_TOP_LEVEL_DIRS:
        path = agent_run / dirname
        if path.is_dir() and not any(path.iterdir()):
            actions.append(CleanupAction(operation="remove", source=path, allow_protected=True))
    return actions


def collect_actions(repo_root: Path, archive_stamp: str, skip_agent_run: bool, tmp_min_age_hours: float) -> list[CleanupAction]:
    actions = [
        CleanupAction(operation="remove", source=target)
        for target in collect_cache_targets(repo_root)
    ]

    if not skip_agent_run:
        actions.extend(collect_agent_run_screenshot_archives(repo_root, archive_stamp))
        actions.extend(collect_agent_run_directory_archives(repo_root, archive_stamp))
        actions.extend(collect_agent_run_root_archives(repo_root, archive_stamp))
        actions.extend(collect_agent_run_tmp_removals(repo_root, tmp_min_age_hours))
        actions.extend(collect_agent_run_empty_dir_removals(repo_root))

    return sorted(
        actions,
        key=lambda action: (
            action.operation,
            len(action.source.parts),
            str(action.source).lower(),
        ),
        reverse=True,
    )


def is_protected(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root)
    if rel.parts and rel.parts[0] in PROTECTED_DIR_PARTS:
        return True
    if any(part in PROTECTED_DIR_PARTS for part in rel.parts):
        return True
    if path.is_file() and path.suffix.lower() in EVIDENCE_FILE_SUFFIXES:
        return True
    return False


def remove_target(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def archive_target(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--apply", action="store_true", help="Actually remove targets. Without this, only print targets.")
    parser.add_argument(
        "--skip-agent-run",
        action="store_true",
        help="Only clean source/test Python caches and root pytest scratch artifacts; skip .agent-run housekeeping.",
    )
    parser.add_argument(
        "--agent-run-archive-stamp",
        default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        help="Archive stamp for .agent-run/root files. Defaults to current UTC timestamp.",
    )
    parser.add_argument(
        "--agent-run-tmp-min-age-hours",
        default=12.0,
        type=float,
        help="Minimum age before removing .agent-run/tmp disposable directories. Defaults to 12 hours.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    actions = collect_actions(
        repo_root,
        args.agent_run_archive_stamp,
        args.skip_agent_run,
        args.agent_run_tmp_min_age_hours,
    )

    removed = 0
    archived = 0
    skipped = 0
    for action in actions:
        resolved = action.source.resolve()
        if not is_relative_to(resolved, repo_root):
            skipped += 1
            print(f"SKIP outside repo: {resolved}")
            continue
        if not action.allow_protected and is_protected(resolved, repo_root):
            skipped += 1
            print(f"SKIP protected: {resolved.relative_to(repo_root).as_posix()}")
            continue
        if action.operation == "archive":
            if action.destination is None:
                skipped += 1
                print(f"SKIP archive missing destination: {resolved.relative_to(repo_root).as_posix()}")
                continue
            destination = action.destination.resolve()
            if not is_relative_to(destination, repo_root):
                skipped += 1
                print(f"SKIP archive outside repo: {destination}")
                continue
            source_rel = resolved.relative_to(repo_root).as_posix()
            destination_rel = destination.relative_to(repo_root).as_posix()
            if args.apply:
                archive_target(resolved, destination)
                archived += 1
                print(f"ARCHIVED {source_rel} -> {destination_rel}")
            else:
                print(f"WOULD_ARCHIVE {source_rel} -> {destination_rel}")
            continue

        if args.apply:
            remove_target(resolved)
            removed += 1
            print(f"REMOVED {resolved.relative_to(repo_root).as_posix()}")
        else:
            print(f"WOULD_REMOVE {resolved.relative_to(repo_root).as_posix()}")

    if args.apply:
        print(f"removed={removed} archived={archived} skipped={skipped}")
    else:
        would_remove = sum(1 for action in actions if action.operation == "remove") - skipped
        would_archive = sum(1 for action in actions if action.operation == "archive")
        print(f"would_remove={would_remove} would_archive={would_archive} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
