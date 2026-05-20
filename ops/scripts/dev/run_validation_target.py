"""Run one machine-readable validation target and write local run artifacts.

This runner is intentionally small. Target selection stays in
``select_validation_targets.py``; this script executes one target id from
``tests/TEST_SELECTION_TARGETS.json`` and records what happened under the
ignored local agent workspace.

The runner does not edit committed ledgers automatically. It writes a
ledger-ready snippet for review.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validation_history import (
    DEFAULT_HISTORY,
    append_history_record,
    changed_paths_signature,
    git_worktree_changed_paths,
)
from check_validation_capabilities import build_capabilities, evaluate_target_capabilities, required_capability_names


DEFAULT_REGISTRY = "tests/TEST_SELECTION_TARGETS.json"
DEFAULT_ARTIFACT_ROOT = ".agent-run/logs"
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
RESULT_PASSED = "passed"
RESULT_FAILED = "failed"
RESULT_BLOCKED = "blocked"
RESULT_TIMED_OUT = "timed out"
RESULT_INTERRUPTED = "interrupted"
RESULT_SKIPPED = "skipped"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "target"


def repo_placeholder_path(repo_root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return "<artifact-dir>"
    return "<repo>/" + rel.as_posix()


def load_registry(repo_root: Path, registry_path: str) -> dict[str, Any]:
    with (repo_root / registry_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def target_by_id(registry: dict[str, Any], target_id: str) -> dict[str, Any]:
    for target in registry.get("targets", []):
        if target.get("id") == target_id:
            return target
    raise KeyError(f"unknown target id: {target_id}")


def git_value(repo_root: Path, args: list[str], default: str = "unknown") -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return default
    value = result.stdout.strip()
    return value or default


def repo_python(repo_root: Path) -> Path | None:
    for candidate in (repo_root / ".venv" / "Scripts" / "python.exe", repo_root / ".venv" / "bin" / "python"):
        if candidate.exists():
            return candidate
    return None


def resolve_python_argv(repo_root: Path, argv: list[str]) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    if not argv:
        return argv, notes
    first = argv[0].replace("\\", "/")
    first_lower = first.lower()
    if first_lower in {".venv/scripts/python.exe", ".venv/bin/python", "python", "python.exe"}:
        configured = repo_python(repo_root)
        if configured is not None:
            return [str(configured), *argv[1:]], notes
        if first_lower in {".venv/scripts/python.exe", ".venv/bin/python"}:
            notes.append("configured repository venv interpreter was not found; using the current interpreter")
        return [sys.executable, *argv[1:]], notes
    return argv, notes


def resolve_platform_command_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    if not argv:
        return argv, notes
    first = argv[0].lower()
    platform_names = {
        "npm": "npm.cmd" if os.name == "nt" else "npm",
        "npm.cmd": "npm.cmd" if os.name == "nt" else "npm",
        "npx": "npx.cmd" if os.name == "nt" else "npx",
        "npx.cmd": "npx.cmd" if os.name == "nt" else "npx",
    }
    resolved = platform_names.get(first)
    if resolved is None:
        return argv, notes
    if resolved != argv[0]:
        notes.append(f"normalized command executable `{argv[0]}` to `{resolved}` for this platform")
    return [resolved, *argv[1:]], notes


def resolve_command_argv(repo_root: Path, argv: list[str]) -> tuple[list[str], list[str]]:
    resolved, notes = resolve_python_argv(repo_root, argv)
    if resolved != argv:
        return resolved, notes
    platform_resolved, platform_notes = resolve_platform_command_argv(argv)
    return platform_resolved, [*notes, *platform_notes]


def selected_python_has_module(python_executable: str, module: str) -> bool:
    if Path(python_executable).resolve() == Path(sys.executable).resolve():
        return importlib.util.find_spec(module) is not None
    try:
        result = subprocess.run(
            [
                python_executable,
                "-c",
                "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)",
                module,
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def command_should_be_preflighted(args: argparse.Namespace) -> bool:
    return not args.dry_run or args.preflight


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def normalize_changed_paths(changed_paths: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in changed_paths:
        raw_path = str(item.get("path") or "")
        path = normalize_path(raw_path)
        if not path:
            continue
        normalized.append(
            {
                "status": str(item.get("status") or "M"),
                "path": path,
            }
        )
    return normalized


def resolve_changed_paths(repo_root: Path, args: argparse.Namespace) -> tuple[list[dict[str, str]], list[str]]:
    if args.changed_paths_json:
        parsed = json.loads(args.changed_paths_json)
        if not isinstance(parsed, list):
            raise ValueError("--changed-paths-json must decode to a list")
        return normalize_changed_paths(parsed), ["using explicitly provided changed-path snapshot"]
    return git_worktree_changed_paths(repo_root), []


def is_text_path(path: str) -> bool:
    candidate = Path(path)
    return candidate.name in TEXT_FILENAMES or candidate.suffix in TEXT_EXTENSIONS


def changed_text_files(repo_root: Path, changed_paths: list[dict[str, str]]) -> list[str]:
    paths: list[str] = []
    for item in changed_paths:
        path = normalize_path(str(item.get("path") or ""))
        status = str(item.get("status") or "M")
        if not path or status.startswith("D") or not is_text_path(path):
            continue
        if (repo_root / path).exists():
            paths.append(path)
    return sorted(set(paths))


def expand_command_placeholders(
    repo_root: Path,
    argv: list[str],
    changed_paths: list[dict[str, str]],
) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    expanded: list[str] = []
    for part in argv:
        if part == "<changed-text-files>":
            files = changed_text_files(repo_root, changed_paths)
            expanded.extend(files)
            notes.append(f"expanded <changed-text-files> to {len(files)} file(s)")
        else:
            expanded.append(part)
    return expanded, notes


def command_has_unresolved_placeholder(argv: list[str]) -> str | None:
    for part in argv:
        if "<" in str(part) and ">" in str(part):
            return str(part)
    return None


def classify_command_blocker(argv: list[str]) -> tuple[str, str] | None:
    if not argv:
        return "empty command argv", "orchestrator"

    placeholder = command_has_unresolved_placeholder(argv)
    if placeholder:
        return f"unresolved command placeholder {placeholder}", "orchestrator"

    if len(argv) >= 3 and argv[1:3] == ["-m", "pytest"] and not selected_python_has_module(argv[0], "pytest"):
        return "pytest is not importable in the selected Python interpreter", "environment"

    executable = argv[0]
    executable_lower = executable.lower()
    if executable_lower.endswith((".exe", ".cmd", ".bat")) or "/" in executable or "\\" in executable:
        if not Path(executable).exists() and shutil.which(executable) is None:
            return f"executable not found: {executable}", "environment"
    elif shutil.which(executable) is None:
        return f"executable not found on PATH: {executable}", "environment"

    return None


def is_pytest_command(argv: list[str]) -> bool:
    return len(argv) >= 3 and argv[1:3] == ["-m", "pytest"]


def has_junitxml_arg(argv: list[str]) -> bool:
    return any(part == "--junitxml" or part.startswith("--junitxml=") for part in argv)


def with_pytest_junitxml(argv: list[str], output_path: Path) -> list[str]:
    if not is_pytest_command(argv) or has_junitxml_arg(argv):
        return argv
    return [*argv, f"--junitxml={output_path}"]


def target_needs_playwright_preflight(target: dict[str, Any]) -> bool:
    return target.get("category") == "school-playwright"


def target_needs_capability_preflight(target: dict[str, Any]) -> bool:
    return bool(required_capability_names(target))


def parse_junit_xml(path: Path, repo_root: Path | None = None) -> dict[str, Any] | None:
    if not path.exists():
        return None

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return {
            "format": "junit-xml",
            "path": None,
            "parse_error": str(exc),
            "tests": 0,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "cases": [],
        }

    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    tests = sum(int(suite.get("tests", "0") or 0) for suite in suites)
    failures = sum(int(suite.get("failures", "0") or 0) for suite in suites)
    errors = sum(int(suite.get("errors", "0") or 0) for suite in suites)
    skipped = sum(int(suite.get("skipped", "0") or 0) for suite in suites)
    cases: list[dict[str, Any]] = []

    for case in root.findall(".//testcase"):
        status = "passed"
        if case.find("failure") is not None:
            status = "failed"
        elif case.find("error") is not None:
            status = "error"
        elif case.find("skipped") is not None:
            status = "skipped"
        cases.append(
            {
                "classname": case.get("classname", ""),
                "name": case.get("name", ""),
                "file": redact_report_path(repo_root, case.get("file", "")),
                "time_seconds": float(case.get("time", "0") or 0),
                "status": status,
            }
        )

    if not suites and root.tag == "testsuites":
        tests = int(root.get("tests", "0") or 0)
        failures = int(root.get("failures", "0") or 0)
        errors = int(root.get("errors", "0") or 0)
        skipped = int(root.get("skipped", "0") or 0)

    return {
        "format": "junit-xml",
        "path": None,
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "passed": max(tests - failures - errors - skipped, 0),
        "cases": cases,
    }


def redact_report_path(repo_root: Path | None, path: str) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if candidate.is_absolute():
        if repo_root is not None:
            try:
                return "<repo>/" + candidate.resolve().relative_to(repo_root.resolve()).as_posix()
            except ValueError:
                pass
        return f"<absolute-{candidate.name or 'path'}>"
    return path.replace("\\", "/")


def command_to_string(argv: list[str]) -> str:
    return " ".join(str(part) for part in argv)


def redact_argv(repo_root: Path, argv: list[str]) -> list[str]:
    redacted: list[str] = []
    for index, part in enumerate(argv):
        candidate = Path(part)
        if candidate.is_absolute():
            try:
                redacted.append("<repo>/" + candidate.resolve().relative_to(repo_root.resolve()).as_posix())
            except ValueError:
                if index == 0 and candidate.name.lower().startswith("python"):
                    redacted.append("<python>")
                else:
                    redacted.append(f"<absolute-{candidate.name or 'path'}>")
        else:
            redacted.append(part)
    return redacted


def make_command_record(
    *,
    repo_root: Path,
    label: str,
    execution_argv: list[str],
    raw_argv: list[str],
    working_directory: Path,
    result: str,
    failure_class: str | None,
    return_code: int | None,
    duration: float,
    stdout_path: Path,
    stderr_path: Path,
    test_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "argv": redact_argv(repo_root, execution_argv),
        "raw_argv": raw_argv,
        "working_directory": repo_placeholder_path(repo_root, working_directory),
        "result": result,
        "failure_class": failure_class,
        "return_code": return_code,
        "duration_seconds": round(duration, 3),
        "stdout": repo_placeholder_path(repo_root, stdout_path),
        "stderr": repo_placeholder_path(repo_root, stderr_path),
        "summary": summarize_stdout(stdout_path),
        "test_results": test_results,
    }


def run_command(
    argv: list[str],
    cwd: Path,
    timeout_seconds: int,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[str, str | None, int | None, float]:
    started = utc_now()
    with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_file, stderr_path.open(
        "w", encoding="utf-8", errors="replace"
    ) as stderr_file:
        try:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                text=True,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            ended = utc_now()
            return RESULT_TIMED_OUT, "timeout", None, (ended - started).total_seconds()
        except KeyboardInterrupt:
            ended = utc_now()
            return RESULT_INTERRUPTED, "interrupted", None, (ended - started).total_seconds()
        except OSError as exc:
            ended = utc_now()
            stderr_file.write(f"\nrunner error: {exc}\n")
            return RESULT_BLOCKED, "environment", None, (ended - started).total_seconds()
    ended = utc_now()
    if completed.returncode == 0:
        return RESULT_PASSED, None, completed.returncode, (ended - started).total_seconds()
    output_tail = load_output_tail(stdout_path, stderr_path)
    failure_class = infer_failure_class(argv, output_tail)
    if failure_class == "environment":
        return RESULT_BLOCKED, failure_class, completed.returncode, (ended - started).total_seconds()
    return RESULT_FAILED, "product", completed.returncode, (ended - started).total_seconds()


def load_output_tail(stdout_path: Path, stderr_path: Path, max_chars: int = 4000) -> str:
    parts: list[str] = []
    for path in (stdout_path, stderr_path):
        try:
            parts.append(path.read_text(encoding="utf-8", errors="replace")[-max_chars:])
        except OSError:
            continue
    return "\n".join(parts)


def infer_failure_class(argv: list[str], output_tail: str) -> str:
    text = output_tail.lower()
    executable = str(argv[0]).lower() if argv else ""

    environment_markers = (
        "spawn eperm",
        "address already in use",
        "only one usage of each socket address",
        "eaddrinuse",
        "browser executable doesn't exist",
        "failed to launch browser",
        "please run the following command to download new browsers",
        "playwright was just installed or updated",
        "cannot find module",
        "module not found",
        "no module named",
        "command not found",
        "is not recognized as an internal or external command",
        "connection refused",
    )
    if any(marker in text for marker in environment_markers):
        return "environment"

    if executable.endswith("npm.cmd") or executable.endswith("npx.cmd") or executable in {"npm", "npx", "node"}:
        node_env_markers = (
            "missing script:",
            "could not determine executable to run",
            "npm err! enoent",
            "requires playwright",
        )
        if any(marker in text for marker in node_env_markers):
            return "environment"

    return "product"


def run_playwright_preflight(
    *,
    repo_root: Path,
    artifact_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    label = "playwright preflight"
    stdout_path = artifact_dir / "00-playwright-preflight-stdout.log"
    stderr_path = artifact_dir / "00-playwright-preflight-stderr.log"
    argv = [
        sys.executable,
        "ops/scripts/dev/playwright_preflight.py",
        "--json",
        "--repo-root",
        str(repo_root),
    ]
    result, failure_class, return_code, duration = run_command(
        argv,
        repo_root,
        min(timeout_seconds, 60),
        stdout_path,
        stderr_path,
    )

    if return_code == 1:
        result = RESULT_BLOCKED
        failure_class = "environment"
    elif return_code == 2:
        result = RESULT_BLOCKED
        failure_class = "environment"
        existing = stderr_path.read_text(encoding="utf-8", errors="replace")
        stderr_path.write_text(
            existing
            + "playwright preflight completed with warnings; confirm the environment before running this target\n",
            encoding="utf-8",
        )

    return make_command_record(
        repo_root=repo_root,
        label=label,
        execution_argv=argv,
        raw_argv=argv,
        working_directory=repo_root,
        result=result,
        failure_class=failure_class,
        return_code=return_code,
        duration=duration,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def run_capability_preflight(
    *,
    repo_root: Path,
    artifact_dir: Path,
    target: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    label = "validation capabilities"
    stdout_path = artifact_dir / "00-validation-capabilities-stdout.log"
    stderr_path = artifact_dir / "00-validation-capabilities-stderr.log"
    report = build_capabilities(repo_root, include_private=False)
    stdout_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    evaluations = evaluate_target_capabilities(report, target)
    failing = [item for item in evaluations if str(item.get("status")) == "fail"]
    warnings = [item for item in evaluations if str(item.get("status")) == "warn"]
    if failing:
        result = RESULT_BLOCKED
        failure_class = "environment"
        return_code = 1
        summary = "required capability is unavailable: " + "; ".join(
            f"{item['name']} ({item['reason']})" for item in failing
        )
        stderr_path.write_text(summary + "\n", encoding="utf-8")
    else:
        result = RESULT_PASSED
        failure_class = None
        return_code = 0
        if warnings:
            summary = "capability warnings: " + "; ".join(
                f"{item['name']} ({item['reason']})" for item in warnings
            )
            stderr_path.write_text(summary + "\n", encoding="utf-8")
        else:
            summary = ""
            stderr_path.write_text("", encoding="utf-8")

    record = make_command_record(
        repo_root=repo_root,
        label=label,
        execution_argv=[sys.executable, "ops/scripts/dev/check_validation_capabilities.py", "--json"],
        raw_argv=[sys.executable, "ops/scripts/dev/check_validation_capabilities.py", "--json"],
        working_directory=repo_root,
        result=result,
        failure_class=failure_class,
        return_code=return_code,
        duration=0.0,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    if summary:
        record["summary"] = summary
    record["required_capabilities"] = evaluations
    record["capability_report"] = report
    return record, report


def summarize_stdout(path: Path) -> str:
    if not path.exists():
        return ""
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    interesting = [
        line
        for line in lines
        if any(token in line.lower() for token in ("passed", "failed", "skipped", "error", "built in", "warning"))
    ]
    selected = interesting[-3:] if interesting else lines[-3:]
    return " | ".join(selected)[:500]


def write_ledger_snippet(run: dict[str, Any], path: Path) -> None:
    lines = [
        f"- Target: `{run['target_id']}`",
        f"  - Result: `{run['result']}`",
        f"  - Summary: `{run['summary'] or '<observed output summary>'}`",
        f"  - Notes: `{run['notes'] or '<environment/product/orchestrator notes with private paths redacted>'}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_target(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    registry = load_registry(repo_root, args.registry)
    target = target_by_id(registry, args.target)
    branch = git_value(repo_root, ["branch", "--show-current"])
    commit = git_value(repo_root, ["rev-parse", "--short", "HEAD"])

    started_at = utc_now()
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = repo_root / args.artifact_root / f"{stamp}-{sanitize(args.target)}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    working_directory = repo_root / str(target.get("working_directory") or ".")
    command_records: list[dict[str, Any]] = []
    overall_result = RESULT_PASSED
    failure_class: str | None = None
    notes: list[str] = []
    capability_report: dict[str, Any] | None = None

    changed_paths, changed_path_notes = resolve_changed_paths(repo_root, args)
    notes.extend(changed_path_notes)
    commands = list(target.get("commands", []))
    if not commands:
        overall_result = RESULT_BLOCKED
        failure_class = "orchestrator"
        notes.append("target has no commands")

    if target_needs_capability_preflight(target) and command_should_be_preflighted(args) and commands:
        capability_record, capability_report = run_capability_preflight(
            repo_root=repo_root,
            artifact_dir=artifact_dir,
            target=target,
        )
        command_records.append(capability_record)
        if capability_record["result"] != RESULT_PASSED:
            overall_result = capability_record["result"]
            failure_class = capability_record["failure_class"]
            commands = []

    if target_needs_playwright_preflight(target) and command_should_be_preflighted(args) and commands:
        preflight_record = run_playwright_preflight(
            repo_root=repo_root,
            artifact_dir=artifact_dir,
            timeout_seconds=args.timeout_seconds,
        )
        command_records.append(preflight_record)
        if preflight_record["result"] != RESULT_PASSED:
            overall_result = preflight_record["result"]
            failure_class = preflight_record["failure_class"]
            commands = []

    for index, command in enumerate(commands, start=1):
        raw_argv = [str(part) for part in command.get("argv", [])]
        expanded_argv, placeholder_notes = expand_command_placeholders(repo_root, raw_argv, changed_paths)
        notes.extend(placeholder_notes)
        resolved_argv, resolve_notes = resolve_command_argv(repo_root, expanded_argv)
        notes.extend(resolve_notes)
        label = str(command.get("label") or f"command-{index}")
        stdout_path = artifact_dir / f"{index:02d}-{sanitize(label)}-stdout.log"
        stderr_path = artifact_dir / f"{index:02d}-{sanitize(label)}-stderr.log"
        junit_path = artifact_dir / f"{index:02d}-{sanitize(label)}-junit.xml"
        execution_argv = with_pytest_junitxml(resolved_argv, junit_path)

        blocker = classify_command_blocker(execution_argv) if command_should_be_preflighted(args) else None
        if blocker:
            reason, blocker_class = blocker
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text(reason + "\n", encoding="utf-8")
            command_result = RESULT_BLOCKED
            command_failure_class = blocker_class
            return_code = None
            duration = 0.0
        elif args.dry_run:
            stdout_path.write_text("dry run: command was not executed\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            command_result = RESULT_SKIPPED
            command_failure_class = None
            return_code = None
            duration = 0.0
        else:
            command_result, command_failure_class, return_code, duration = run_command(
                execution_argv,
                working_directory,
                args.timeout_seconds,
                stdout_path,
                stderr_path,
            )

        test_results = parse_junit_xml(junit_path, repo_root)
        if test_results is not None:
            test_results["path"] = repo_placeholder_path(repo_root, junit_path)

        command_records.append(
            make_command_record(
                repo_root=repo_root,
                label=label,
                execution_argv=execution_argv,
                raw_argv=raw_argv,
                working_directory=working_directory,
                result=command_result,
                failure_class=command_failure_class,
                return_code=return_code,
                duration=duration,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                test_results=test_results,
            )
        )

        if command_result == RESULT_SKIPPED and args.dry_run:
            overall_result = RESULT_SKIPPED
            continue

        if command_result != RESULT_PASSED:
            overall_result = command_result
            failure_class = command_failure_class
            break

    ended_at = utc_now()
    summary = command_records[-1]["summary"] if command_records else ""
    if overall_result == RESULT_BLOCKED and command_records:
        summary = Path(repo_root / command_records[-1]["stderr"].replace("<repo>/", "")).read_text(
            encoding="utf-8", errors="replace"
        ).strip()

    run = {
        "schema_version": 1,
        "target_id": args.target,
        "category": target.get("category"),
        "branch": branch,
        "commit": commit,
        "started_at": iso(started_at),
        "ended_at": iso(ended_at),
        "duration_seconds": round((ended_at - started_at).total_seconds(), 3),
        "working_directory": repo_placeholder_path(repo_root, working_directory),
        "result": overall_result,
        "failure_class": failure_class,
        "summary": summary,
        "notes": "; ".join(sorted(set(notes))),
        "commands": command_records,
        "capability_report": capability_report,
        "artifact_dir": repo_placeholder_path(repo_root, artifact_dir),
        "private_paths_redacted": True,
    }
    history_record = {
        "schema_version": 1,
        "target_id": args.target,
        "category": target.get("category"),
        "risk": target.get("risk"),
        "branch": branch,
        "commit": commit,
        "started_at": run["started_at"],
        "ended_at": run["ended_at"],
        "duration_seconds": run["duration_seconds"],
        "result": overall_result,
        "failure_class": failure_class,
        "summary": summary,
        "artifact_dir": run["artifact_dir"],
        "run_json": repo_placeholder_path(repo_root, artifact_dir / "run.json"),
        "ledger_snippet": repo_placeholder_path(repo_root, artifact_dir / "ledger-snippet.md"),
        "changed_paths": changed_paths,
        "changed_paths_signature": changed_paths_signature(changed_paths),
        "command_count": len(command_records),
        "test_results": [
            {
                "label": record["label"],
                "result": record["result"],
                "test_results": record.get("test_results"),
            }
            for record in command_records
            if record.get("test_results") is not None
        ],
        "private_paths_redacted": True,
    }
    if not args.no_history:
        history_path = append_history_record(repo_root, args.history, history_record)
        run["history"] = repo_placeholder_path(repo_root, history_path)
    else:
        run["history"] = None
    (artifact_dir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_ledger_snippet(run, artifact_dir / "ledger-snippet.md")
    sys.stdout.buffer.write((json.dumps(run, ensure_ascii=False, indent=2) + "\n").encode("utf-8", errors="replace"))

    if overall_result == RESULT_PASSED:
        return 0
    if overall_result == RESULT_SKIPPED and args.dry_run:
        return 0
    if overall_result == RESULT_FAILED:
        return 1
    if overall_result == RESULT_BLOCKED:
        return 2
    if overall_result == RESULT_TIMED_OUT:
        return 4
    if overall_result == RESULT_INTERRUPTED:
        return 5
    return 3


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Target id from tests/TEST_SELECTION_TARGETS.json")
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help=f"Target registry path. Defaults to {DEFAULT_REGISTRY}.")
    parser.add_argument("--artifact-root", default=DEFAULT_ARTIFACT_ROOT, help="Ignored artifact root for logs.")
    parser.add_argument("--history", default=DEFAULT_HISTORY, help=f"Ignored JSONL run history path. Defaults to {DEFAULT_HISTORY}.")
    parser.add_argument("--no-history", action="store_true", help="Do not append a structured JSONL history record.")
    parser.add_argument("--timeout-seconds", type=int, default=900, help="Per-command timeout. Defaults to 900 seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve and record commands without executing them.")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="With --dry-run, also run command/environment preflight checks. Normal execution always preflights.",
    )
    parser.add_argument(
        "--changed-paths-json",
        help="Explicit JSON array of changed path objects, each with `path` and optional `status`. Defaults to the current worktree snapshot.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        return run_target(parse_args(argv))
    except KeyError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 6
    except json.JSONDecodeError as exc:
        print(f"ERROR registry is not valid JSON: {exc}", file=sys.stderr)
        return 6
    except ValueError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
