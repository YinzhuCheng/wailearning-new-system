"""Run a named validation profile and write a profile-level summary.

Profiles orchestrate the lower-level target runner. They are intentionally
policy-bound: expensive or review-required targets are skipped unless the
caller opts in.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_validation_target import DEFAULT_ARTIFACT_ROOT, DEFAULT_REGISTRY, sanitize
from validation_history import DEFAULT_HISTORY


RESULT_PASSED = "passed"
RESULT_PASSED_WITH_DEFERRED_REVIEW = "passed_with_deferred_review"
RESULT_FAILED = "failed"
RESULT_BLOCKED = "blocked"
RESULT_SKIPPED = "skipped"
RESULT_NOT_SUFFICIENT = "not_sufficient"

RISK_ORDER = {
    "static": 0,
    "targeted": 1,
    "broad": 2,
    "full": 3,
}

STATIC_TARGETS = ["static.validation_selector"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def repo_placeholder_path(repo_root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return "<artifact-dir>"
    return "<repo>/" + rel.as_posix()


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


def run_python_json(repo_root: Path, argv: list[str]) -> tuple[int, dict[str, Any] | None, str, str]:
    completed = subprocess.run(
        [sys.executable, *argv],
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    payload: dict[str, Any] | None = None
    if completed.stdout.strip():
        try:
            parsed = json.loads(completed.stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = None
    return completed.returncode, payload, completed.stdout, completed.stderr


def selector_recommendations(repo_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    selector_args = [
        "ops/scripts/dev/select_validation_targets.py",
        "--repo-root",
        str(repo_root),
        "--registry",
        args.registry,
        "--history",
        args.history,
        "--json",
    ]
    if args.no_history:
        selector_args.append("--no-history")
    if args.paths:
        selector_args.append("--paths")
        selector_args.extend(args.paths)
    else:
        if not args.worktree:
            args.worktree = True
        selector_args.append("--worktree")

    return_code, payload, stdout, stderr = run_python_json(repo_root, selector_args)
    if return_code != 0 or payload is None:
        raise RuntimeError(f"selector failed with code {return_code}: {stderr.strip() or stdout.strip()}")
    return payload


def target_ids_for_profile(repo_root: Path, profile: str, args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if profile == "static":
        return [{"id": target_id, "risk": "static", "requires_review_reason": None} for target_id in STATIC_TARGETS], None

    if profile == "selector-recommended":
        selection = selector_recommendations(repo_root, args)
        return list(selection.get("recommendations", [])), selection

    raise ValueError(f"unknown profile: {profile}")


def should_run_target(target: dict[str, Any], args: argparse.Namespace) -> tuple[bool, str | None]:
    risk = str(target.get("risk", "targeted"))
    if RISK_ORDER.get(risk, 99) > RISK_ORDER[args.max_risk]:
        return False, f"risk `{risk}` exceeds max risk `{args.max_risk}`"
    if target.get("requires_review_reason") and not args.include_review_targets:
        return False, "target requires operator review"
    return True, None


def run_target(repo_root: Path, target_id: str, args: argparse.Namespace) -> tuple[int, dict[str, Any] | None, str, str]:
    target_args = [
        "ops/scripts/dev/run_validation_target.py",
        target_id,
        "--repo-root",
        str(repo_root),
        "--registry",
        args.registry,
        "--artifact-root",
        args.artifact_root,
        "--history",
        args.history,
        "--timeout-seconds",
        str(args.timeout_seconds),
    ]
    if args.no_history:
        target_args.append("--no-history")
    if args.dry_run:
        target_args.append("--dry-run")
    if args.preflight:
        target_args.append("--preflight")
    if args.changed_paths_json:
        target_args.extend(["--changed-paths-json", args.changed_paths_json])
    return run_python_json(repo_root, target_args)


def deferred_targets(target_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "target_id": str(run.get("target_id")),
            "risk": run.get("risk"),
            "reason": run.get("reason"),
        }
        for run in target_runs
        if run.get("action") == "skipped" and run.get("reason") == "target requires operator review"
    ]


def profile_result(target_runs: list[dict[str, Any]], selection: dict[str, Any] | None) -> tuple[str, int]:
    non_full_status = None
    if selection:
        non_full_status = selection.get("non_full_validation", {}).get("status")
    if non_full_status == "not_sufficient":
        return RESULT_NOT_SUFFICIENT, 4

    executed = [run for run in target_runs if run.get("action") == "executed"]
    if any(run.get("result") == RESULT_FAILED for run in executed):
        return RESULT_FAILED, 1
    if any(run.get("result") in {"timed out", "interrupted"} for run in executed):
        return RESULT_FAILED, 1
    if any(run.get("result") == RESULT_BLOCKED for run in executed):
        return RESULT_BLOCKED, 2
    if not executed:
        return RESULT_SKIPPED, 0
    if deferred_targets(target_runs):
        return RESULT_PASSED_WITH_DEFERRED_REVIEW, 0
    return RESULT_PASSED, 0


def run_profile(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    started_at = utc_now()
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = repo_root / args.artifact_root / f"{stamp}-profile-{sanitize(args.profile)}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    targets, selection = target_ids_for_profile(repo_root, args.profile, args)
    if selection and selection.get("changed_paths"):
        args.changed_paths_json = json.dumps(selection["changed_paths"], ensure_ascii=False)
    else:
        args.changed_paths_json = None
    target_runs: list[dict[str, Any]] = []

    for target in targets:
        target_id = str(target.get("id"))
        should_run, skip_reason = should_run_target(target, args)
        if not should_run:
            target_runs.append(
                {
                    "target_id": target_id,
                    "risk": target.get("risk"),
                    "action": "skipped",
                    "result": RESULT_SKIPPED,
                    "reason": skip_reason,
                }
            )
            continue

        return_code, payload, stdout, stderr = run_target(repo_root, target_id, args)
        record = {
            "target_id": target_id,
            "risk": target.get("risk"),
            "action": "executed",
            "return_code": return_code,
            "result": payload.get("result") if payload else RESULT_FAILED,
            "failure_class": payload.get("failure_class") if payload else "orchestrator",
            "artifact_dir": payload.get("artifact_dir") if payload else None,
            "summary": payload.get("summary") if payload else (stderr.strip() or stdout.strip())[:500],
        }
        target_runs.append(record)

    ended_at = utc_now()
    result, exit_code = profile_result(target_runs, selection)
    deferred = deferred_targets(target_runs)
    profile = {
        "schema_version": 1,
        "profile": args.profile,
        "branch": git_value(repo_root, ["branch", "--show-current"]),
        "commit": git_value(repo_root, ["rev-parse", "--short", "HEAD"]),
        "started_at": iso(started_at),
        "ended_at": iso(ended_at),
        "duration_seconds": round((ended_at - started_at).total_seconds(), 3),
        "result": result,
        "max_risk": args.max_risk,
        "include_review_targets": args.include_review_targets,
        "dry_run": args.dry_run,
        "preflight": args.preflight,
        "selection": selection,
        "target_runs": target_runs,
        "deferred_targets": deferred,
        "artifact_dir": repo_placeholder_path(repo_root, artifact_dir),
        "private_paths_redacted": True,
    }
    (artifact_dir / "profile-run.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return exit_code


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=["static", "selector-recommended"], help="Validation profile to run.")
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help=f"Target registry path. Defaults to {DEFAULT_REGISTRY}.")
    parser.add_argument("--history", default=DEFAULT_HISTORY, help=f"Ignored JSONL run history path. Defaults to {DEFAULT_HISTORY}.")
    parser.add_argument("--no-history", action="store_true", help="Do not read or write structured run history.")
    parser.add_argument("--artifact-root", default=DEFAULT_ARTIFACT_ROOT, help="Ignored artifact root for logs.")
    parser.add_argument("--timeout-seconds", type=int, default=900, help="Per-command timeout. Defaults to 900 seconds.")
    parser.add_argument("--max-risk", choices=["static", "targeted", "broad", "full"], default="targeted")
    parser.add_argument("--include-review-targets", action="store_true", help="Run targets that declare requires_review_reason.")
    parser.add_argument("--dry-run", action="store_true", help="Record target commands without executing them.")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="With --dry-run, also ask target runs to check command/environment blockers.",
    )
    parser.add_argument("--worktree", action="store_true", help="Use the current worktree diff for selector-recommended. This is the default when --paths is omitted.")
    parser.add_argument("--paths", nargs="*", help="Explicit changed paths for selector-recommended profile.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        return run_profile(parse_args(argv))
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
