from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def discover_paths(root: Path, relative_dir: str, suffix: str) -> list[str]:
    base = root / relative_dir
    if not base.exists():
        return []
    paths = []
    for path in sorted(base.rglob(f"*{suffix}")):
        rel = path.relative_to(root).as_posix()
        if "/__pycache__/" in f"/{rel}/":
            continue
        paths.append(rel)
    return paths


def build_args(run_id: str, regression_mode: str, concurrency: int) -> list[str]:
    backend = discover_paths(REPO_ROOT, "tests/backend", ".py")
    backend = [path for path in backend if Path(path).name.startswith("test_")]
    behavior = discover_paths(REPO_ROOT, "tests/behavior", ".py")
    behavior = [path for path in behavior if Path(path).name.startswith("test_")]
    security = discover_paths(REPO_ROOT, "tests/security", ".py")
    security = [path for path in security if Path(path).name.startswith("test_")]
    postgres = discover_paths(REPO_ROOT, "tests/postgres", ".py")
    postgres = [path for path in postgres if Path(path).name.startswith("test_")]
    playwright = discover_paths(REPO_ROOT, "tests/e2e/web-school", ".spec.js")

    return [
        "--run-id",
        run_id,
        "--regression-mode",
        regression_mode,
        "--replace-run-dir",
        "--no-console-report",
        "--block-spec",
        f"backend-sqlite-compatible:{concurrency}:{','.join(backend)}",
        "--block-spec",
        f"behavior:{concurrency}:{','.join(behavior)}",
        "--block-spec",
        f"security:{concurrency}:{','.join(security)}",
        "--block-spec",
        f"backend-postgres-sensitive:{concurrency}:{','.join(postgres)}",
        "--block-spec",
        f"playwright-school-e2e:{concurrency}:{','.join(playwright)}",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--regression-mode", choices=("light", "medium", "heavy"), default="light")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--output-json", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_args(args.run_id, args.regression_mode, args.concurrency)
    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
