from __future__ import annotations

import argparse

import pytest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-tag", required=True, help="Marker for WAI-VALID-owned python worker processes.")
    parser.add_argument("--run-id", required=True, help="Owning WAI-VALID run id.")
    parser.add_argument("--target", required=True, help="Single pytest target or nodeid.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return int(pytest.main([args.target, "-q"]))


if __name__ == "__main__":
    raise SystemExit(main())
