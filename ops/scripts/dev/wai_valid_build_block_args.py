from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def discover_test_files(relative_dir: str, suffix: str) -> list[str]:
    base = REPO_ROOT / relative_dir
    if not base.exists():
        return []
    paths: list[str] = []
    for path in sorted(base.rglob(f"*{suffix}")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/__pycache__/" in f"/{rel}/":
            continue
        if suffix == ".py" and not path.name.startswith("test_"):
            continue
        paths.append(rel)
    return paths


def block_paths(block_name: str) -> list[str]:
    if block_name == "static-and-build":
        return ["validation-target:static.validation_selector"]
    if block_name == "backend-sqlite-compatible":
        return discover_test_files("tests/backend", ".py")
    if block_name == "behavior":
        return discover_test_files("tests/behavior", ".py")
    if block_name == "security":
        return discover_test_files("tests/security", ".py")
    if block_name == "backend-postgres-sensitive":
        return discover_test_files("tests/postgres", ".py")
    if block_name == "playwright-school-e2e":
        return discover_test_files("tests/e2e/web-school", ".spec.js")
    raise SystemExit(f"Unsupported block name: {block_name}")


def build_args(run_id: str, block_name: str, concurrency: int, regression_mode: str) -> list[str]:
    paths = block_paths(block_name)
    if not paths:
        raise SystemExit(f"No tasks discovered for block: {block_name}")
    return [
        "--run-id",
        run_id,
        "--regression-mode",
        regression_mode,
        "--replace-run-dir",
        "--block-spec",
        f"{block_name}:{concurrency}:{','.join(paths)}",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--block",
        required=True,
        choices=(
            "static-and-build",
            "backend-sqlite-compatible",
            "behavior",
            "security",
            "backend-postgres-sensitive",
            "playwright-school-e2e",
        ),
    )
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--regression-mode", choices=("light", "medium", "heavy"), default="light")
    parser.add_argument("--output-json", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_args(args.run_id, args.block, args.concurrency, args.regression_mode)
    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
