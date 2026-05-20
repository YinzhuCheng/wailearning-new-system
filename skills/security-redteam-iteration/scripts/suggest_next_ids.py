from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from common import current_commit, repo_root, read_text


def max_regex(path: Path, pattern: str) -> int:
    if not path.exists():
        return 0
    text = read_text(path)
    values = [int(match.group(1)) for match in re.finditer(pattern, text)]
    return max(values, default=0)


def max_csv_int(path: Path, field: str) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        values = []
        for row in rows:
            try:
                value = int(row.get(field, "") or 0)
            except ValueError:
                continue
            if value > 0:
                values.append(value)
        return max(values, default=0)


def collect(root: Path) -> dict[str, int | str]:
    hard_file = root / "tests/security/test_security_hardening_followup.py"
    e2e_file = root / "tests/e2e/web-school/e2e-security-hardening-followup.spec.js"
    pitfall_file = root / "docs/testing/pitfall-index.csv"
    update_file = root / "docs/testing/agent-update-log.csv"

    max_hard = max_regex(hard_file, r"def\s+test_hard(\d+)_")
    max_e2e = max_regex(e2e_file, r"test\('(\d+)\s")
    max_pitfall = max_csv_int(pitfall_file, "pitfall_sequence")
    max_update = max_csv_int(update_file, "update_sequence")

    return {
        "source_commit_sha": current_commit(root),
        "next_pytest_hard": max_hard + 1,
        "next_e2e_case": max_e2e + 1,
        "next_pitfall_sequence": max_pitfall + 1,
        "next_agent_update_sequence": max_update + 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest next security hardening IDs and ledger sequences.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of key=value lines.")
    args = parser.parse_args()
    data = collect(repo_root())
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for key, value in data.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
