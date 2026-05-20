from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONCURRENCY = 10


def load_samples(path_text: str) -> list[str]:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    raw = path.read_text(encoding="utf-8-sig")
    stripped = raw.strip()
    if not stripped:
        return []
    if stripped.startswith("[") or stripped.startswith("{"):
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            payload = payload.get("samples") or payload.get("paths") or payload.get("targets")
        if not isinstance(payload, list):
            raise SystemExit(f"JSON sample file must contain a list or samples/paths/targets list: {path}")
        return [str(item).strip() for item in payload if str(item).strip()]
    samples: list[str] = []
    for line in raw.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        samples.append(candidate)
    return samples


def build_args(
    *,
    run_id: str,
    block: str,
    concurrency: int,
    regression_mode: str,
    samples_files: list[str],
    samples: list[str],
) -> list[str]:
    if not samples and not samples_files:
        raise SystemExit("At least one --sample or --samples-file is required.")
    sample_file_args: list[str] = []
    for samples_file in samples_files:
        sample_file_args.extend(["--samples-file", samples_file])
    sample_args: list[str] = []
    for sample in samples:
        sample_args.extend(["--sample", sample])
    return [
        "--run-id",
        run_id,
        "--regression-mode",
        regression_mode,
        "--replace-run-dir",
        "--no-console-report",
        "--block",
        block,
        "--concurrency",
        str(concurrency),
        *sample_file_args,
        *sample_args,
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--block", default="custom-samples")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--regression-mode", choices=("light", "medium", "heavy"), default="light")
    parser.add_argument("--samples-file", action="append", default=[])
    parser.add_argument("--sample", action="append", default=[])
    parser.add_argument("--output-json", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.samples_file and not args.sample:
        file_samples: list[str] = []
        for samples_file in args.samples_file:
            file_samples.extend(load_samples(samples_file))
        if not file_samples:
            raise SystemExit(f"No samples found in {', '.join(args.samples_file)}")
    payload = build_args(
        run_id=args.run_id,
        block=args.block,
        concurrency=args.concurrency,
        regression_mode=args.regression_mode,
        samples_files=args.samples_file,
        samples=args.sample,
    )
    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
