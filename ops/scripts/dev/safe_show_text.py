"""Display UTF-8 text files without trusting PowerShell's glyph rendering.

The default mode decodes bytes as UTF-8 and writes the resulting text to stdout.
Use --escape when the terminal may still render Unicode incorrectly; escaped
output is noisy for humans but reliable for agents because every non-ASCII code
point is shown as a Python escape sequence.

Examples:

    python ops/scripts/dev/safe_show_text.py docs/contributing/ENCODING_AND_MOJIBAKE_SAFETY.md
    python ops/scripts/dev/safe_show_text.py apps/web/school/src/views/Layout.vue --escape --start-line 1 --end-line 80
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def decode_utf8(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"{path}: not valid UTF-8 at byte {exc.start}: {exc.reason}") from exc


def select_lines(text: str, start_line: int | None, end_line: int | None) -> str:
    if start_line is None and end_line is None:
        return text

    lines = text.splitlines(keepends=True)
    start = 1 if start_line is None else start_line
    end = len(lines) if end_line is None else end_line
    if start < 1:
        raise SystemExit("--start-line must be >= 1")
    if end < start:
        raise SystemExit("--end-line must be >= --start-line")
    return "".join(lines[start - 1 : end])


def escape_non_ascii(text: str) -> str:
    return text.encode("unicode_escape").decode("ascii")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="UTF-8 text file to display.")
    parser.add_argument("--start-line", type=int, help="First 1-based line to display.")
    parser.add_argument("--end-line", type=int, help="Last 1-based line to display.")
    parser.add_argument(
        "--escape",
        action="store_true",
        help="Print non-ASCII as escape sequences so terminal mojibake cannot hide the bytes.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=0,
        help="Optional maximum output characters after line slicing. 0 means no limit.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    path = Path(args.path)
    text = select_lines(decode_utf8(path), args.start_line, args.end_line)
    if args.max_chars and len(text) > args.max_chars:
        text = text[: args.max_chars]
    if args.escape:
        text = escape_non_ascii(text)
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
