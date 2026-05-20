"""Validate repo-local CourseEval skills without external YAML dependencies."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


NAME_RE = re.compile(r"^[a-z0-9-]{1,63}$")
SKILL_REF_RE = re.compile(r"skills/[a-z0-9-]+/SKILL\.md")


def parse_simple_frontmatter(path: Path) -> tuple[dict[str, str], list[str]]:
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    if not text.startswith("---\n"):
        return {}, [f"{path}: missing opening frontmatter marker"]
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, [f"{path}: missing closing frontmatter marker"]
    data: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            issues.append(f"{path}: invalid frontmatter line: {line}")
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data, issues


def check_skill(skill_dir: Path, repo_root: Path) -> list[str]:
    rel_dir = skill_dir.relative_to(repo_root).as_posix()
    skill_file = skill_dir / "SKILL.md"
    issues: list[str] = []
    if not skill_file.exists():
        return [f"{rel_dir}: missing SKILL.md"]

    frontmatter, frontmatter_issues = parse_simple_frontmatter(skill_file)
    issues.extend(frontmatter_issues)
    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")
    if name != skill_dir.name:
        issues.append(f"{rel_dir}/SKILL.md: name must match directory name")
    if not NAME_RE.match(name):
        issues.append(f"{rel_dir}/SKILL.md: invalid skill name: {name}")
    if len(description) < 40:
        issues.append(f"{rel_dir}/SKILL.md: description is too short or missing")
    skill_text = skill_file.read_text(encoding="utf-8")
    if "TODO" in skill_text:
        issues.append(f"{rel_dir}/SKILL.md: contains TODO placeholder")

    agents_file = skill_dir / "agents" / "openai.yaml"
    if agents_file.exists():
        agents_text = agents_file.read_text(encoding="utf-8")
        for key in ("display_name:", "short_description:", "default_prompt:"):
            if key not in agents_text:
                issues.append(f"{rel_dir}/agents/openai.yaml: missing {key}")
    else:
        issues.append(f"{rel_dir}: missing agents/openai.yaml")

    for match in SKILL_REF_RE.finditer(skill_text):
        ref = match.group(0)
        if not (repo_root / ref).exists():
            issues.append(f"{rel_dir}/SKILL.md: missing referenced skill `{ref}`")
    return issues


def check_repo_skills(repo_root: Path) -> list[str]:
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        return ["skills: directory missing"]
    issues: list[str] = []
    for skill_dir in sorted(path for path in skills_dir.iterdir() if path.is_dir()):
        issues.extend(check_skill(skill_dir, repo_root))
    return issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    issues = check_repo_skills(repo_root)
    if issues:
        print("Repo-local skill check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Repo-local skill check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
