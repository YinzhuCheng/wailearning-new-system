"""Search pitfall docs, structured indexes, troubleshooting notes, and skills.

Use this before classifying a command/test failure or changing product code.
The search is intentionally lightweight and dependency-free: it ranks exact
phrase matches, token overlap, path/title hits, and a few common synonym groups.
It surfaces likely prior art; it does not decide whether a failure is product,
test-contract, harness, or environment.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_PATHS = [
    "docs/testing/TEST_EXECUTION_PITFALLS.md",
    "docs/testing/pitfalls-windows-and-encoding.md",
    "docs/testing/pitfalls-playwright-and-e2e.md",
    "docs/testing/pitfalls-postgres-and-pytest.md",
    "docs/testing/pitfalls-ledger-and-selector-tooling.md",
    "docs/testing/pitfall-index.csv",
    "docs/architecture/TROUBLESHOOTING.md",
    "docs/testing/DEVELOPMENT_AND_TESTING.md",
]

TOKEN_RE = re.compile(r"[a-z0-9_.:/\\-]+|[\u4e00-\u9fff]+", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

SYNONYMS = {
    "pg": {"postgres", "postgresql"},
    "postgres": {"pg", "postgresql"},
    "postgresql": {"pg", "postgres"},
    "e2e": {"playwright", "browser"},
    "playwright": {"e2e", "browser"},
    "browser": {"playwright", "e2e"},
    "sqlite": {"test.sqlite", "pytest"},
    "restricted": {"restricted-token", "token"},
    "token": {"restricted", "restricted-token"},
    "encoding": {"utf8", "utf-8", "mojibake"},
    "utf8": {"encoding", "utf-8", "mojibake"},
    "utf-8": {"encoding", "utf8", "mojibake"},
    "mojibake": {"encoding", "utf8", "utf-8"},
}


@dataclass(frozen=True)
class SearchBlock:
    path: str
    line: int
    source: str
    title: str
    text: str


@dataclass(frozen=True)
class SearchHit:
    score: int
    path: str
    line: int
    source: str
    title: str
    snippet: str


def repo_root_from(path: Path) -> Path:
    current = path.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").exists():
            return candidate
    raise SystemExit("Could not find repository root from current directory.")


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]


def expand_tokens(tokens: list[str]) -> set[str]:
    expanded = set(tokens)
    for token in tokens:
        expanded.update(SYNONYMS.get(token, set()))
    return expanded


def clean_snippet(text: str, max_chars: int = 260) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def iter_default_paths(repo_root: Path) -> list[Path]:
    paths = [repo_root / path for path in DEFAULT_PATHS]
    skills_dir = repo_root / "skills"
    if skills_dir.exists():
        paths.extend(sorted(skills_dir.glob("*/SKILL.md")))
    return [path for path in paths if path.exists()]


def nearest_title(current_title: str, fallback: str) -> str:
    return current_title or fallback


def blocks_from_markdown(repo_root: Path, path: Path, context_lines: int) -> list[SearchBlock]:
    rel = normalize_path(str(path.relative_to(repo_root)))
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    blocks: list[SearchBlock] = []
    current_title = Path(rel).name
    for index, line in enumerate(lines):
        heading = HEADING_RE.match(line)
        if heading:
            current_title = heading.group(2).strip()
        if not line.strip() and not heading:
            continue
        start = max(0, index - context_lines)
        end = min(len(lines), index + context_lines + 1)
        blocks.append(
            SearchBlock(
                path=rel,
                line=index + 1,
                source="markdown",
                title=nearest_title(current_title, Path(rel).name),
                text="\n".join(lines[start:end]),
            )
        )
    return blocks


def blocks_from_csv(repo_root: Path, path: Path) -> list[SearchBlock]:
    rel = normalize_path(str(path.relative_to(repo_root)))
    text = path.read_text(encoding="utf-8-sig")
    blocks: list[SearchBlock] = []
    for line_number, row in enumerate(csv.DictReader(text.splitlines()), start=2):
        if not row:
            continue
        title = row.get("heading") or row.get("test_id") or row.get("target") or Path(rel).name
        rendered = " | ".join(f"{key}={value}" for key, value in row.items() if value)
        blocks.append(
            SearchBlock(
                path=rel,
                line=line_number,
                source="csv",
                title=title,
                text=rendered,
            )
        )
    return blocks


def build_corpus(repo_root: Path, paths: list[Path] | None = None, context_lines: int = 2) -> list[SearchBlock]:
    selected = paths if paths is not None else iter_default_paths(repo_root)
    blocks: list[SearchBlock] = []
    for path in selected:
        if not path.exists() or path.is_dir():
            continue
        if path.suffix.lower() == ".csv":
            blocks.extend(blocks_from_csv(repo_root, path))
        else:
            blocks.extend(blocks_from_markdown(repo_root, path, context_lines))
    return blocks


def score_block(query: str, tokens: set[str], block: SearchBlock) -> int:
    haystack = f"{block.path}\n{block.title}\n{block.text}".lower()
    title = block.title.lower()
    path = block.path.lower()
    score = 0
    query_lower = query.lower().strip()
    if query_lower and query_lower in haystack:
        score += 40
    for token in tokens:
        if len(token) <= 1:
            continue
        if token in block.text.lower():
            score += 6
        if token in title:
            score += 4
        if token in path:
            score += 3
    if block.path.endswith("pitfall-index.csv"):
        score += 2
    if block.path.endswith("TEST_EXECUTION_PITFALLS.md"):
        score += 2
    return score


def search_blocks(query: str, blocks: list[SearchBlock], limit: int) -> list[SearchHit]:
    tokens = expand_tokens(tokenize(query))
    best_by_topic: dict[tuple[str, str, str], SearchHit] = {}
    for block in blocks:
        score = score_block(query, tokens, block)
        if score <= 0:
            continue
        hit = SearchHit(
            score=score,
            path=block.path,
            line=block.line,
            source=block.source,
            title=block.title,
            snippet=clean_snippet(block.text),
        )
        key = (block.path, block.source, block.title)
        previous = best_by_topic.get(key)
        if previous is None or hit.score > previous.score or (hit.score == previous.score and hit.line < previous.line):
            best_by_topic[key] = hit
    hits = list(best_by_topic.values())
    hits.sort(key=lambda hit: (-hit.score, hit.path, hit.line))
    return hits[:limit]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="*", help="Failure text, command name, tool, or symptom keywords.")
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--max-results", type=int, default=12)
    parser.add_argument("--context-lines", type=int, default=2)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    query = " ".join(args.query).strip()
    if not query:
        print("Provide a query, for example: search_pitfalls.py \"initdb restricted token\".", file=sys.stderr)
        return 2
    repo_root = repo_root_from(Path(args.repo_root))
    blocks = build_corpus(repo_root, context_lines=args.context_lines)
    hits = search_blocks(query, blocks, args.max_results)
    if args.json:
        print(json.dumps([asdict(hit) for hit in hits], ensure_ascii=False, indent=2))
        return 0 if hits else 1
    if not hits:
        print("No pitfall candidates found.")
        return 1
    for hit in hits:
        print(f"{hit.score:>3}  {hit.path}:{hit.line}  [{hit.source}] {hit.title}")
        print(f"     {hit.snippet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
