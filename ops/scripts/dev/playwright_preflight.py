"""Compatibility wrapper around the shared validation capability probe."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from check_validation_capabilities import build_capabilities, git_repo_root, parse_args as parse_capability_args


def main(argv: list[str]) -> int:
    args = parse_capability_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else git_repo_root(Path.cwd())
    report = build_capabilities(repo_root, args.include_private_paths)
    capability = next(item for item in report["capabilities"] if item["name"] == "playwright-managed")
    status = str(capability["status"])
    exit_code = 1 if status == "fail" else 2 if status == "warn" else 0
    payload = {
        "repo_root": report["repo_root"],
        "school_root": capability.get("school_root"),
        "managed_web_server": capability.get("managed_web_server"),
        "exit_code": exit_code,
        "checks": capability["checks"],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("# School Playwright Preflight")
        print(f"Repository: {payload['repo_root']}")
        print(f"School root: {payload['school_root']}")
        print(f"Managed webServer: {payload['managed_web_server']}")
        for check in payload["checks"]:
            detail = f" ({check['detail']})" if check.get("detail") else ""
            print(f"[{str(check['status']).upper()}] {check['name']}: {check['summary']}{detail}")
        if exit_code == 1:
            print("Result: failed preflight. Fix the failed items or set PLAYWRIGHT_USE_EXTERNAL_SERVERS=1 with known-good servers.")
        elif exit_code == 2:
            print("Result: preflight passed with warnings. Confirm warnings before running Playwright.")
        else:
            print("Result: preflight passed.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
