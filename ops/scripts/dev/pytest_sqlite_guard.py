"""Diagnose local pytest SQLite hazards before reusing test.sqlite.

This guardrail is intentionally read-only. It does not stop processes and does
not delete the SQLite file. Use it before deleting `.pytest_tmp/test.sqlite` or
before starting a long local pytest run after an interrupted session.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def repo_placeholder_path(repo_root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return normalize_path(str(path))
    return "<repo>/" + normalize_path(str(rel))


def git_repo_root(start: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return start.resolve()
    return Path(result.stdout.strip()).resolve()


def active_python_processes() -> list[dict[str, str]]:
    if os.name == "nt":
        return active_python_processes_windows()
    return active_python_processes_posix()


def active_python_processes_windows() -> list[dict[str, str]]:
    ps_script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -match 'python|pytest|py\\.exe' } | "
        "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_script],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    text = result.stdout.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = payload if isinstance(payload, list) else [payload]
    return [
        {
            "pid": str(row.get("ProcessId", "")),
            "name": str(row.get("Name", "")),
            "command": str(row.get("CommandLine", "") or ""),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def active_python_processes_posix() -> list[dict[str, str]]:
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,comm=,args="],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    rows: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 2:
            continue
        pid = parts[0]
        name = parts[1]
        command = parts[2] if len(parts) > 2 else name
        lower = f"{name} {command}".lower()
        if "python" in lower or "pytest" in lower:
            rows.append({"pid": pid, "name": name, "command": command})
    return rows


def is_pytest_process(process: dict[str, str], current_pid: int) -> bool:
    if process.get("pid") == str(current_pid):
        return False
    command = process.get("command", "").lower()
    name = process.get("name", "").lower()
    haystack = f"{name} {command}"
    return "pytest" in haystack or "py.test" in haystack


def discover_sqlite_candidates(repo_root: Path, sqlite_path: Path) -> list[Path]:
    if sqlite_path.is_dir():
        return sorted(path.resolve() for path in sqlite_path.glob("test*.sqlite") if path.is_file())
    if sqlite_path.exists():
        return [sqlite_path.resolve()]
    if sqlite_path.name == "test.sqlite":
        return sorted(path.resolve() for path in sqlite_path.parent.glob("test*.sqlite") if path.is_file())
    return []


def build_report(repo_root: Path, sqlite_path: Path) -> dict[str, Any]:
    processes = active_python_processes()
    pytest_processes = [
        process for process in processes if is_pytest_process(process, os.getpid())
    ]
    candidates = discover_sqlite_candidates(repo_root, sqlite_path)
    exists = bool(candidates)
    sqlite_info: dict[str, Any] = {
        "path": repo_placeholder_path(repo_root, sqlite_path),
        "exists": exists,
    }
    if sqlite_path.is_dir():
        sqlite_info["mode"] = "directory-scan"
    elif sqlite_path.name == "test.sqlite" and not sqlite_path.exists():
        sqlite_info["mode"] = "compat-scan"
    else:
        sqlite_info["mode"] = "single-path"
    sqlite_info["candidates"] = [
        {
            "path": repo_placeholder_path(repo_root, candidate),
            "size_bytes": candidate.stat().st_size,
            "mtime_epoch": int(candidate.stat().st_mtime),
        }
        for candidate in candidates
    ]
    sqlite_info["candidate_count"] = len(candidates)
    if len(candidates) == 1:
        sqlite_info["size_bytes"] = candidates[0].stat().st_size
        sqlite_info["mtime_epoch"] = int(candidates[0].stat().st_mtime)
    return {
        "repo_root": "<repo>",
        "sqlite": sqlite_info,
        "active_pytest_processes": pytest_processes,
        "active_pytest_count": len(pytest_processes),
        "status": "warn" if pytest_processes else "pass",
        "recommendation": (
            "Stop active pytest processes before deleting or reusing the shared SQLite file."
            if pytest_processes
            else "No active pytest process was detected by this guardrail."
        ),
    }


def print_text(report: dict[str, Any]) -> None:
    sqlite_info = report["sqlite"]
    print(f"status={report['status']}")
    print(f"sqlite_path={sqlite_info['path']}")
    print(f"sqlite_exists={sqlite_info['exists']}")
    print(f"sqlite_mode={sqlite_info['mode']}")
    print(f"sqlite_candidate_count={sqlite_info['candidate_count']}")
    if "size_bytes" in sqlite_info:
        print(f"sqlite_size_bytes={sqlite_info['size_bytes']}")
    for candidate in sqlite_info["candidates"]:
        print(
            "sqlite_candidate "
            f"path={candidate['path']} size_bytes={candidate['size_bytes']} mtime_epoch={candidate['mtime_epoch']}"
        )
    print(f"active_pytest_count={report['active_pytest_count']}")
    for process in report["active_pytest_processes"]:
        print(
            "active_pytest "
            f"pid={process['pid']} name={process['name']} command={process['command']}"
        )
    print(f"recommendation={report['recommendation']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only guardrail for local pytest SQLite process hazards."
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to git root.")
    parser.add_argument(
        "--sqlite-path",
        default=".pytest_tmp",
        help="SQLite file or directory to inspect, relative to repo root unless absolute.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--fail-on-active-pytest",
        action="store_true",
        help="Return non-zero when another pytest process is detected.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else git_repo_root(Path.cwd())
    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.is_absolute():
        sqlite_path = repo_root / sqlite_path
    report = build_report(repo_root, sqlite_path.resolve())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(report)
    if args.fail_on_active_pytest and report["active_pytest_count"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
