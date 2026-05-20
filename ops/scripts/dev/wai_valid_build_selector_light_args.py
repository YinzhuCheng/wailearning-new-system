from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def run_profile(paths: list[str], max_risk: str) -> dict:
    cmd = [
        str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"),
        str(REPO_ROOT / "ops" / "scripts" / "dev" / "run_validation_profile.py"),
        "selector-recommended",
        "--max-risk",
        max_risk,
        "--dry-run",
        "--repo-root",
        str(REPO_ROOT),
        "--paths",
        *paths,
    ]
    completed = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise SystemExit(f"selector profile failed ({completed.returncode}):\n{completed.stderr or completed.stdout}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"selector profile did not emit valid JSON:\n{completed.stdout}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("selector profile returned a non-object JSON payload")
    return payload


def build_args(run_id: str, paths: list[str], max_risk: str, concurrency: int) -> list[str]:
    payload = run_profile(paths, max_risk)
    target_runs = payload.get("target_runs") or []
    target_ids = [
        f"validation-target:{item['target_id']}"
        for item in target_runs
        if item.get("action") == "executed"
    ]
    if not target_ids:
        raise SystemExit("selector-derived lightweight run produced no auto-runnable targets")
    return [
        "--run-id",
        run_id,
        "--regression-mode",
        "light",
        "--replace-run-dir",
        "--block-spec",
        f"static-and-build:{concurrency}:{','.join(target_ids)}",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--paths", nargs="+", required=True)
    parser.add_argument("--max-risk", choices=("static", "targeted", "broad", "full"), default="targeted")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--output-json", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_args(args.run_id, args.paths, args.max_risk, args.concurrency)
    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
