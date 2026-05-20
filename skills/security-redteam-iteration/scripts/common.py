from __future__ import annotations

import subprocess
from pathlib import Path


def repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise SystemExit("Could not locate repository root from current directory.")


def run_git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=str(cwd), text=True, encoding="utf-8").strip()


def current_branch(root: Path) -> str:
    return run_git(["branch", "--show-current"], root) or "unknown"


def current_commit(root: Path) -> str:
    return run_git(["log", "-1", "--format=%h"], root)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


PRIVATE_MARKERS = (
    "C:\\Users\\",
    r"C:/Users/",
    ".agent-run/logs/",
    ".agent-run\\logs\\",
)


def reject_private_markers(value: str, field_name: str) -> None:
    allowed = ("C:\\Users\\<user>", "C:/Users/<user>")
    for marker in PRIVATE_MARKERS:
        if marker in value and not any(token in value for token in allowed):
            raise SystemExit(f"{field_name} appears to contain a private local path or artifact marker: {marker}")
