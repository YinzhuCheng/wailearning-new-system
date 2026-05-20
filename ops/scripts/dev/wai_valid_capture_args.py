from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: wai_valid_capture_args.py <output-json> [args...]")
    out_path = Path(sys.argv[1])
    args = sys.argv[2:]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(args, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
