"""Structured local validation run history helpers.

The committed test execution ledger remains the human-reviewed source of
truth. This module handles ignored JSONL history produced by local validation
runners so selectors can make evidence-based freshness decisions before a
ledger row is written.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_HISTORY = ".agent-run/validation-history.jsonl"


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def changed_paths_signature(changed_paths: list[dict[str, str]]) -> str:
    """Return a stable digest for a changed-path snapshot."""

    normalized = [
        {
            "status": str(item.get("status") or "M"),
            "path": normalize_path(str(item.get("path") or "")),
        }
        for item in changed_paths
        if item.get("path")
    ]
    normalized.sort(key=lambda item: (item["path"], item["status"]))
    payload = json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def git_worktree_changed_paths(repo_root: Path) -> list[dict[str, str]]:
    """Read unstaged plus untracked changed paths for local run attribution."""

    changed: dict[str, dict[str, str]] = {}
    try:
        output = _run_git(repo_root, ["diff", "--name-status", "--no-renames"])
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            status = parts[0] if len(parts) >= 2 else "M"
            path = parts[-1]
            changed[normalize_path(path)] = {"status": status, "path": normalize_path(path)}

        output = _run_git(repo_root, ["ls-files", "--others", "--exclude-standard"])
        for line in output.splitlines():
            if line.strip():
                path = normalize_path(line)
                changed[path] = {"status": "??", "path": path}
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    return [changed[path] for path in sorted(changed)]


def append_history_record(repo_root: Path, history_path: str, record: dict[str, Any]) -> Path:
    path = repo_root / history_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def load_history_entries(repo_root: Path, history_path: str) -> list[dict[str, Any]]:
    path = repo_root / history_path
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def latest_records_by_target(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        target_id = entry.get("target_id")
        if not target_id:
            continue
        previous = latest.get(str(target_id))
        if previous is None or str(entry.get("ended_at", "")) >= str(previous.get("ended_at", "")):
            latest[str(target_id)] = entry
    return latest
