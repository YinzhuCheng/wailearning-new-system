from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
STATE_DIR = REPO_ROOT / ".agent-run" / "validation-daemon"
LOG_ROOT = REPO_ROOT / ".agent-run" / "logs"
CURRENT_RUN_PATH = STATE_DIR / "WAI-VALID-current-run.json"
MONITOR_READY_PATH = STATE_DIR / "WAI-VALID-monitor-ready.json"
MONITOR_HEARTBEAT_PATH = STATE_DIR / "WAI-VALID-monitor-heartbeat.json"
PID_PATHS = {
    "supervisor": STATE_DIR / "WAI-VALID-supervisor.pid",
    "supervisor_detached": STATE_DIR / "WAI-VALID-supervisor-detached.pid",
    "monitor_python": STATE_DIR / "WAI-VALID-monitor.pid",
    "monitor_shell": STATE_DIR / "WAI-VALID-monitor-shell.pid",
}


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def normalize_run_id(run_id: str) -> str:
    return run_id if run_id.startswith("WAI-VALID-") else f"WAI-VALID-{run_id}"


def progress_score(run_dir: Path) -> tuple[int, float]:
    summary_path = run_dir / "summary.json"
    progress_path = run_dir / "progress.json"
    if summary_path.exists():
        return (2, summary_path.stat().st_mtime)
    if progress_path.exists():
        payload = load_json(progress_path) or {}
        status = str(payload.get("status") or "")
        rank = 1 if status else 0
        return (rank, progress_path.stat().st_mtime)
    return (0, run_dir.stat().st_mtime)


def resolve_run_dir(run_id: str | None) -> Path:
    if run_id:
        run_dir = LOG_ROOT / normalize_run_id(run_id)
        if not run_dir.exists():
            raise SystemExit(f"WAI-VALID run not found: {run_dir}")
        return run_dir

    current = load_json(CURRENT_RUN_PATH) if CURRENT_RUN_PATH.exists() else None
    if current and current.get("run_id"):
        run_dir = LOG_ROOT / str(current["run_id"])
        if run_dir.exists():
            return run_dir

    candidates = [path for path in LOG_ROOT.glob("WAI-VALID-*") if path.is_dir()]
    if not candidates:
        raise SystemExit("No WAI-VALID run directories found.")
    candidates.sort(key=progress_score, reverse=True)
    return candidates[0]


def tail_lines(path: Path, count: int) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return lines[-count:]
    except Exception:
        return []


def read_pid(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8-sig").strip().splitlines()[0].strip()
    except Exception:
        return None
    if not raw.isdigit():
        return None
    return int(raw)


def probe_pid(pid: int | None) -> dict[str, Any]:
    if pid is None:
        return {"pid": None, "running": False, "image": "", "note": "no-pid"}

    if os.name == "nt":
        tasklist = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tasklist.exe"
        try:
            result = subprocess.run(
                [str(tasklist), "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
                check=False,
            )
            for row in csv.reader(result.stdout.splitlines()):
                if len(row) >= 2 and row[1].strip() == str(pid):
                    return {"pid": pid, "running": True, "image": row[0], "note": ""}
            if result.returncode == 0:
                return {"pid": pid, "running": False, "image": "", "note": "pid-file-stale"}
        except Exception as exc:
            tasklist_note = f"tasklist-error: {exc}"
        else:
            tasklist_note = (result.stderr or result.stdout or "tasklist-nonzero").strip()

        powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        command = (
            "$ErrorActionPreference='Stop'; "
            f"$p=Get-Process -Id {pid}; "
            "Write-Output ($p.ProcessName + ',' + $p.Id)"
        )
        try:
            fallback = subprocess.run(
                [str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
                check=False,
            )
            line = (fallback.stdout or "").strip().splitlines()
            if fallback.returncode == 0 and line:
                image = line[0].split(",", 1)[0].strip()
                return {"pid": pid, "running": True, "image": image, "note": "tasklist-fallback"}
            return {"pid": pid, "running": False, "image": "", "note": "pid-file-stale"}
        except Exception as exc:
            note = f"{tasklist_note}; fallback-error: {exc}"
            return {"pid": pid, "running": None, "image": "", "note": note}

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return {"pid": pid, "running": False, "image": "", "note": "pid-file-stale"}
    except PermissionError:
        return {"pid": pid, "running": True, "image": "", "note": "permission-denied"}
    except Exception as exc:
        return {"pid": pid, "running": None, "image": "", "note": f"probe-error: {exc}"}
    return {"pid": pid, "running": True, "image": "", "note": ""}


def process_snapshot() -> dict[str, dict[str, Any]]:
    return {label: probe_pid(read_pid(path)) for label, path in PID_PATHS.items()}


def compact_payload(run_dir: Path, failed_limit: int, running_limit: int, events_limit: int) -> dict[str, Any]:
    summary = load_json(run_dir / "summary.json") or {}
    progress = load_json(run_dir / "progress.json") or {}
    block_report = load_json(run_dir / "block-report.json") or {}
    report = progress.get("report") or {}
    report_summary = report.get("summary") or {}
    blocks = report.get("blocks") or {}

    run_id = str(summary.get("run_id") or progress.get("run_id") or run_dir.name)
    status = str(summary.get("status") or progress.get("status") or "unknown")
    block = str(summary.get("block") or progress.get("block") or "n/a")
    regression_mode = str(summary.get("regression_mode") or progress.get("regression_mode") or "n/a")
    total = int(summary.get("total") or progress.get("total") or report_summary.get("total") or 0)
    completed = int(
        summary.get("completed_count")
        or progress.get("completed_count")
        or progress.get("passed_count")
        or report_summary.get("passed")
        or 0
    )
    failed_count = int(summary.get("failed_count") or progress.get("failed_count") or report_summary.get("failed") or 0)
    running_slots = list(progress.get("running_slots") or [])
    running_count = int(report_summary.get("running") or len(running_slots) or len(list(progress.get("running") or [])))
    queue = int(progress.get("queue_remaining") or report_summary.get("queued") or 0)
    failed_shards = list(summary.get("failed_shards") or progress.get("failed") or [])
    if not failed_shards and block_report.get("results"):
        failed_shards = [
            str(item.get("shard") or item.get("target") or "unknown")
            for item in block_report.get("results", [])
            if int(item.get("exit_code") or 0) != 0
        ]

    ready = load_json(MONITOR_READY_PATH) if MONITOR_READY_PATH.exists() else None
    heartbeat = load_json(MONITOR_HEARTBEAT_PATH) if MONITOR_HEARTBEAT_PATH.exists() else None
    monitor = {
        "ready": ready if ready and ready.get("run_id") == run_id else None,
        "heartbeat": heartbeat if heartbeat and heartbeat.get("run_id") == run_id else None,
    }
    if not monitor["ready"] and not monitor["heartbeat"] and status in {"passed", "failed", "timed_out", "supervisor_error"}:
        monitor["note"] = "not-running; final-state monitor cleanup is expected"

    concise_running = []
    for slot in running_slots[:running_limit]:
        concise_running.append(
            {
                "shard": slot.get("shard"),
                "source_path": slot.get("source_path"),
                "pid": slot.get("pid"),
                "origin": slot.get("origin"),
            }
        )

    return {
        "run_id": run_id,
        "status": status,
        "block": block,
        "regression_mode": regression_mode,
        "updated_at": progress.get("updated_at") or summary.get("finished_at") or "",
        "finished_at": summary.get("finished_at") or "",
        "total": total,
        "completed": completed,
        "failed": failed_count,
        "running": running_count,
        "queue": queue,
        "block_concurrency": summary.get("block_concurrency") or progress.get("block_concurrency") or {},
        "blocks": blocks,
        "failed_shards": failed_shards[:failed_limit],
        "failed_shards_truncated": max(0, len(failed_shards) - failed_limit),
        "running_slots": concise_running,
        "running_slots_truncated": max(0, len(running_slots) - running_limit),
        "recent_events": tail_lines(run_dir / "events.log", events_limit),
        "monitor": monitor,
        "processes": process_snapshot(),
        "artifacts": {
            "run_dir": str(run_dir),
            "summary": str(run_dir / "summary.json"),
            "progress": str(run_dir / "progress.json"),
            "block_report": str(run_dir / "block-report.json"),
            "block_summary": str(run_dir / "block-summary.txt"),
            "events": str(run_dir / "events.log"),
        },
    }


def print_text(payload: dict[str, Any]) -> None:
    print(f"run_id: {payload['run_id']}")
    print(f"status: {payload['status']}")
    print(f"block: {payload['block']}")
    print(f"regression_mode: {payload['regression_mode']}")
    print(f"updated_at: {payload['updated_at']}")
    if payload["finished_at"]:
        print(f"finished_at: {payload['finished_at']}")
    print(
        f"summary: passed={payload['completed']}/{payload['total']} "
        f"failed={payload['failed']} running={payload['running']} queue={payload['queue']}"
    )
    print("blocks:")
    blocks = payload.get("blocks") or {}
    if not blocks:
        print(" - none")
    for block_name, block_payload in sorted(blocks.items()):
        print(
            f" - {block_name}: pass={block_payload.get('completed_count', 0)}/{block_payload.get('total', 0)} "
            f"fail={block_payload.get('failed_count', 0)} "
            f"run={block_payload.get('running_count', 0)} "
            f"queue={block_payload.get('queue_remaining', 0)} "
            f"conc={block_payload.get('configured_concurrency', 'n/a')}"
        )
    print("failed_shards:")
    if payload["failed_shards"]:
        for shard in payload["failed_shards"]:
            print(f" - {shard}")
        if payload["failed_shards_truncated"]:
            print(f" - ... truncated {payload['failed_shards_truncated']} more")
    else:
        print(" - none")
    print("running_slots:")
    if payload["running_slots"]:
        for slot in payload["running_slots"]:
            print(f" - pid={slot.get('pid')} {slot.get('shard')} [{slot.get('origin')}]")
        if payload["running_slots_truncated"]:
            print(f" - ... truncated {payload['running_slots_truncated']} more")
    else:
        print(" - none")
    monitor = payload.get("monitor") or {}
    print("monitor:")
    if monitor.get("ready"):
        ready = monitor["ready"]
        print(f" - ready: pid={ready.get('pid')} phase={ready.get('phase')} updated={ready.get('updated_at')}")
    if monitor.get("heartbeat"):
        heartbeat = monitor["heartbeat"]
        print(
            f" - heartbeat: pid={heartbeat.get('pid')} phase={heartbeat.get('phase')} "
            f"updated={heartbeat.get('updated_at')} progress_updated={heartbeat.get('progress_updated_at')}"
        )
    if monitor.get("note"):
        print(f" - {monitor['note']}")
    if not monitor.get("ready") and not monitor.get("heartbeat") and not monitor.get("note"):
        print(" - none")
    print("processes:")
    for label, process in payload.get("processes", {}).items():
        running = process.get("running")
        state = "running" if running is True else "not-running" if running is False else "unknown"
        pid = process.get("pid") if process.get("pid") is not None else "none"
        image = process.get("image") or "n/a"
        note = process.get("note") or ""
        suffix = f" note={note}" if note else ""
        print(f" - {label}: pid={pid} state={state} image={image}{suffix}")
    print("recent_events:")
    if payload["recent_events"]:
        for line in payload["recent_events"]:
            print(f" - {line}")
    else:
        print(" - none")
    print("artifacts:")
    for key, value in payload["artifacts"].items():
        print(f" - {key}: {value}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print a compact WAI-VALID run status without dumping long shard lists.")
    parser.add_argument("--run-id", help="Run id to inspect. Defaults to current run or latest WAI-VALID run.")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--failed-limit", type=int, default=25)
    parser.add_argument("--running-limit", type=int, default=10)
    parser.add_argument("--events-limit", type=int, default=8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = compact_payload(resolve_run_dir(args.run_id), args.failed_limit, args.running_limit, args.events_limit)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
