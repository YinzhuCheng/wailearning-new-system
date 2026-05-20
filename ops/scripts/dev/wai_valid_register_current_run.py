from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
STATE_DIR = REPO_ROOT / ".agent-run" / "validation-daemon"
LOG_ROOT = REPO_ROOT / ".agent-run" / "logs"
ACTIVE_STALE_AFTER_SECONDS = 15


def _run_preference(run_name: str) -> int:
    normalized = run_name.lower()
    if "backend-only-rerun" in normalized:
        return 3
    if "backend-only" in normalized:
        return 2
    if "round2" in normalized:
        return 1
    return 0


def _progress_score(progress_path: Path) -> tuple[int, int, int, float]:
    try:
        payload = json.loads(progress_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return (0, 0, progress_path.stat().st_mtime)

    total = int(payload.get("total") or 0)
    done = int(payload.get("completed_count") or 0)
    running = len(list(payload.get("running") or []))
    queue = int(payload.get("queue_remaining") or 0)
    mtime = progress_path.stat().st_mtime
    age_seconds = max(0.0, time.time() - mtime)
    is_recent = 1 if age_seconds <= ACTIVE_STALE_AFTER_SECONDS else 0
    has_unfinished_work = 1 if (queue > 0 or (total and done < total)) else 0
    has_live_work = 1 if (running > 0 or has_unfinished_work) else 0
    is_active = 1 if (is_recent and has_live_work) else 0
    is_finished = 1 if (total > 0 and done >= total and queue == 0 and running == 0) else 0
    freshness_rank = 2 if is_active else (1 if is_finished else 0)
    return (freshness_rank, _run_preference(progress_path.parent.name), running, mtime)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="Force the current-run pointer to a specific run id.")
    return parser.parse_args()


def _resolve_progress_path(run_id: str) -> Path:
    run_name = run_id if run_id.startswith("WAI-VALID-") else f"WAI-VALID-{run_id}"
    progress_path = LOG_ROOT / run_name / "progress.json"
    if not progress_path.exists():
        raise SystemExit(f"Progress file not found for run id: {run_name}")
    return progress_path


def main() -> int:
    args = parse_args()
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if args.run_id:
        progress_path = _resolve_progress_path(args.run_id)
    else:
        candidates = []
        for progress in LOG_ROOT.glob("*/progress.json"):
            try:
                candidates.append((_progress_score(progress), progress))
            except FileNotFoundError:
                continue
        if not candidates:
            raise SystemExit("No progress.json found under .agent-run/logs/")
        candidates.sort(key=lambda item: item[0], reverse=True)
        progress_path = candidates[0][1]
    run_dir = progress_path.parent
    events_path = run_dir / "events.log"

    payload = {
        "run_id": run_dir.name,
        "progress_file": str(progress_path),
        "events_file": str(events_path),
        "mode": "visible-monitor",
    }
    out = STATE_DIR / "WAI-VALID-current-run.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
