"""Write text files with explicit UTF-8 encoding and predictable newlines.

This utility is for generated text or trusted input where a full-file write is
intentional. It is not a replacement for apply_patch when making small manual
edits to tracked source.

Default behavior is conservative:

- read input from stdin or --from-file as UTF-8;
- normalize newlines to LF;
- refuse to overwrite an existing file unless --replace is supplied;
- write UTF-8 without a byte-order mark.

Examples:

    python ops/scripts/dev/safe_write_text.py .e2e-run/example.md --stdin
    python ops/scripts/dev/safe_write_text.py docs/example.md --from-file draft.md --replace
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


def normalize_newlines(text: str, mode: str) -> str:
    if mode == "preserve":
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if mode == "crlf":
        return text.replace("\n", "\r\n")
    return text


def read_input(args: argparse.Namespace) -> str:
    if args.from_file:
        return Path(args.from_file).read_text(encoding="utf-8")
    if args.stdin:
        raw = sys.stdin.buffer.read()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SystemExit(f"stdin: not valid UTF-8 at byte {exc.start}: {exc.reason}") from exc
    raise SystemExit("Provide --stdin or --from-file.")


def atomic_write_text(path: Path, text: str, replace: bool, mkdirs: bool) -> None:
    if path.exists() and not replace:
        raise SystemExit(f"{path}: exists; pass --replace to overwrite intentionally")
    if mkdirs:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.parent.exists():
        raise SystemExit(f"{path.parent}: parent directory does not exist; pass --mkdirs to create it")

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        finally:
            raise


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Output path.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--stdin", action="store_true", help="Read text from stdin.")
    source.add_argument("--from-file", help="Read UTF-8 text from another file.")
    parser.add_argument("--replace", action="store_true", help="Allow replacing an existing file.")
    parser.add_argument("--mkdirs", action="store_true", help="Create missing parent directories.")
    parser.add_argument(
        "--newline",
        choices=("lf", "crlf", "preserve"),
        default="lf",
        help="Newline handling for output text. Defaults to lf.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    text = normalize_newlines(read_input(args), args.newline)
    atomic_write_text(Path(args.path), text, replace=args.replace, mkdirs=args.mkdirs)
    print(f"wrote {args.path} as UTF-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
