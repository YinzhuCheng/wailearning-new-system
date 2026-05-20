"""Check documentation links and governance index basics."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from governance_common import Finding, has_error, print_findings, read_text, text_paths, tracked_or_walked_paths


MD_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
BARE_DOC_PATH_RE = re.compile(
    r"(?P<path>(?:docs|skills|ops|tests|apps)/[A-Za-z0-9_./@%+~#=-]+"
    r"\.(?:json|yaml|service|conf|cjs|vue|ps1|bat|md|py|js|yml|sh))"
    r"(?![A-Za-z0-9_.-])"
)

REQUIRED_DOCS = (
    "README.md",
    "AGENTS.md",
    "docs/README.md",
    "docs/agents/README.md",
    "docs/agents/agent-playbook.md",
    "docs/architecture/REPOSITORY_STRUCTURE.md",
    "docs/architecture/BACKEND_PACKAGE_STRUCTURE.md",
    "docs/contributing/README.md",
    "docs/frontend/README.md",
    "docs/governance/README.md",
    "docs/reference/CODE_MAP_AND_ENTRYPOINTS.md",
    "docs/governance/known-issues-and-risks.md",
    "docs/testing/README.md",
)

REQUIRED_SKILL_LINKS = (
    "skills/docs-governance/SKILL.md",
    "skills/boundary-governance/SKILL.md",
    "skills/structure-governance/SKILL.md",
)

EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#")


def strip_anchor(target: str) -> str:
    return target.split("#", 1)[0]


def is_external(target: str) -> bool:
    return target.startswith(EXTERNAL_PREFIXES) or "://" in target


def resolve_link(source: str, target: str) -> str | None:
    if is_external(target):
        return None
    path = strip_anchor(target).strip()
    if not path:
        return None
    path = path.replace("%20", " ")
    return Path(Path(source).parent / path).as_posix()


def check_markdown_links(repo_root: Path, docs: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for source in docs:
        text = read_text(repo_root, source)
        if text is None:
            continue
        for match in MD_LINK_RE.finditer(text):
            target = match.group(1).split(" ", 1)[0].strip("<>")
            resolved = resolve_link(source, target)
            if resolved is None:
                continue
            if not (repo_root / resolved).exists():
                findings.append(
                    Finding("error", "broken-md-link", source, f"missing target `{target}` -> `{resolved}`")
                )
        for match in BARE_DOC_PATH_RE.finditer(text):
            target = match.group("path")
            if "..." in target:
                continue
            if not (repo_root / target).exists():
                findings.append(Finding("warning", "bare-missing-path", source, f"mentions missing `{target}`"))
    return findings


def check_required_indexes(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in REQUIRED_DOCS:
        if not (repo_root / path).exists():
            findings.append(Finding("error", "missing-required-doc", path, "required governance entrypoint missing"))

    agents = read_text(repo_root, "AGENTS.md") or ""
    docs_readme = read_text(repo_root, "docs/README.md") or ""
    for link in REQUIRED_SKILL_LINKS:
        if link not in agents:
            findings.append(Finding("warning", "skill-not-in-agents", "AGENTS.md", f"missing `{link}`"))
        if f"../{link}" not in docs_readme and link not in docs_readme:
            findings.append(Finding("warning", "skill-not-in-docs-index", "docs/README.md", f"missing `{link}`"))
    return findings


def check_docs_directory_readmes(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    docs_root = repo_root / "docs"
    if not docs_root.exists():
        return findings
    for directory in sorted(path for path in docs_root.rglob("*") if path.is_dir()):
        rel = directory.relative_to(repo_root).as_posix()
        if not (directory / "README.md").exists():
            findings.append(Finding("error", "missing-directory-readme", rel, "docs directory lacks README.md"))
    return findings


def check_docs_root_files(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    docs_root = repo_root / "docs"
    if not docs_root.exists():
        return findings
    for path in sorted(item for item in docs_root.iterdir() if item.is_file()):
        if path.name != "README.md":
            rel = path.relative_to(repo_root).as_posix()
            findings.append(
                Finding("error", "unexpected-docs-root-file", rel, "docs root files must move into a topic folder")
            )
    return findings


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--json", action="store_true", help="Emit JSON findings.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    paths = tracked_or_walked_paths(repo_root, include_untracked=True)
    docs = [path for path in text_paths(repo_root, paths) if Path(path).suffix in {".md", ".rst"}]
    findings = check_required_indexes(repo_root)
    findings.extend(check_docs_directory_readmes(repo_root))
    findings.extend(check_docs_root_files(repo_root))
    findings.extend(check_markdown_links(repo_root, docs))
    print_findings(findings, json_output=args.json)
    print(f"checked_docs={len(docs)} findings={len(findings)}")
    return 1 if has_error(findings) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
