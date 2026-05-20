"""Report and enforce lightweight validation lane skip/debt budgets."""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


DEFAULT_BUDGETS = "docs/testing/validation-lane-budgets.json"
COUNT_KEYS = ("tests", "failures", "errors", "skipped", "passed", "deselected", "xfailed", "xpassed")
SUMMARY_RE = re.compile(r"(?P<count>\d+)\s+(?P<label>passed|failed|error|errors|skipped|deselected|xfailed|xpassed)")


def parse_junit_counts(path: Path) -> dict[str, int]:
    counts = {key: 0 for key in COUNT_KEYS}
    if not path.exists():
        raise FileNotFoundError(f"missing junit xml: {path}")
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    if not suites and root.tag == "testsuites":
        suites = [root]
    counts["tests"] = sum(int(suite.get("tests", "0") or 0) for suite in suites)
    counts["failures"] = sum(int(suite.get("failures", "0") or 0) for suite in suites)
    counts["errors"] = sum(int(suite.get("errors", "0") or 0) for suite in suites)
    counts["skipped"] = sum(int(suite.get("skipped", "0") or 0) for suite in suites)
    counts["passed"] = max(counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"], 0)
    return counts


def parse_pytest_log_counts(path: Path) -> dict[str, int]:
    counts = {key: 0 for key in COUNT_KEYS}
    if not path.exists():
        return counts
    text = path.read_text(encoding="utf-8", errors="replace")
    for match in SUMMARY_RE.finditer(text):
        label = match.group("label")
        count = int(match.group("count"))
        key = "errors" if label == "error" else label
        counts[key] = max(counts.get(key, 0), count)
    return counts


def merged_counts(junit_counts: dict[str, int], log_counts: dict[str, int]) -> dict[str, int]:
    merged = dict(junit_counts)
    for key in ("deselected", "xfailed", "xpassed"):
        merged[key] = log_counts.get(key, 0)
    return merged


def load_budgets(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("lanes"), dict):
        raise ValueError("validation lane budgets file must contain a top-level `lanes` object")
    return payload


def evaluate_budget(lane_name: str, lane_config: dict[str, Any], counts: dict[str, int]) -> list[str]:
    thresholds = lane_config.get("thresholds", {})
    if not isinstance(thresholds, dict):
        raise ValueError(f"lane `{lane_name}` thresholds must be an object")
    issues: list[str] = []
    for key, raw_value in thresholds.items():
        if not key.endswith("_max"):
            continue
        metric = key[:-4]
        if metric not in counts:
            continue
        limit = int(raw_value)
        if counts[metric] > limit:
            issues.append(f"{lane_name}: {metric}={counts[metric]} exceeds budget {limit}")
    return issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", required=True, help="Lane name inside validation-lane-budgets.json")
    parser.add_argument("--budgets", default=DEFAULT_BUDGETS, help="Budget JSON path.")
    parser.add_argument("--junitxml", help="JUnit XML path for the lane run.")
    parser.add_argument("--log", help="Pytest stdout/stderr log path for deselected/xfail parsing.")
    parser.add_argument("--validate-only", action="store_true", help="Only validate the budget config for the named lane.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        budgets = load_budgets(Path(args.budgets))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}")
        return 2

    lanes = budgets["lanes"]
    if args.lane not in lanes:
        print(f"ERROR unknown lane `{args.lane}` in {args.budgets}")
        return 2
    lane_config = lanes[args.lane]

    if args.validate_only:
        try:
            _ = evaluate_budget(args.lane, lane_config, {key: 0 for key in COUNT_KEYS})
        except ValueError as exc:
            print(f"ERROR {exc}")
            return 2
        print(f"Validation lane budget config passed for lane={args.lane}")
        return 0

    if not args.junitxml:
        print("ERROR --junitxml is required unless --validate-only is used")
        return 2

    try:
        junit_counts = parse_junit_counts(Path(args.junitxml))
        log_counts = parse_pytest_log_counts(Path(args.log)) if args.log else {key: 0 for key in COUNT_KEYS}
        counts = merged_counts(junit_counts, log_counts)
        issues = evaluate_budget(args.lane, lane_config, counts)
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"ERROR {exc}")
        return 2

    summary = " ".join(f"{key}={counts[key]}" for key in COUNT_KEYS if key in counts)
    if issues:
        print(f"Validation lane budget failed. lane={args.lane} {summary}")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print(f"Validation lane budget passed. lane={args.lane} {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
