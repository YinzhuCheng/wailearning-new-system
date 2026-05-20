"""Inventory the large FastAPI/Pydantic schema module before any split.

The CourseEval API schema module is intentionally high blast radius: routers,
domain helpers, tests, and FastAPI response models import names directly from
``apps.backend.courseeval_backend.api.schemas``.  This script gives future
agents a mechanical map of those names before they attempt a domain split.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from governance_common import read_text, tracked_or_walked_paths


SCHEMA_PATH = "apps/backend/courseeval_backend/api/schemas.py"
SCHEMA_MODULE = "apps.backend.courseeval_backend.api.schemas"
SCHEMA_DEFS_PREFIX = "apps.backend.courseeval_backend.api.schema_defs."

DOMAIN_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("auth-users", ("User", "Profile", "Login", "Token", "Password", "Gender", "Role")),
    ("discussions", ("Discussion", "RecentPost")),
    ("learning-notes", ("LearningNote",)),
    ("roster", ("StudentRoster", "UserBatchSetClass", "CourseRoster", "Enrollment")),
    ("classes-courses-subjects", ("Class", "Subject", "Course", "Semester")),
    ("llm", ("LLM", "Quota", "EndpointPreset", "GroupSelection")),
    ("scores", ("Score", "Grade", "ExamWeight")),
    ("attendance", ("Attendance",)),
    ("dashboard", ("Dashboard", "Ranking")),
    ("operations", ("OperationLog", "SystemSetting")),
    ("points", ("Point",)),
    ("appearance", ("Appearance",)),
    ("homework", ("Homework",)),
    ("notifications", ("Notification",)),
    ("materials", ("Material",)),
    ("files", ("Attachment",)),
)


@dataclass(frozen=True)
class SchemaClass:
    name: str
    kind: str
    line_start: int
    line_end: int
    bases: list[str]
    validators: list[str]
    references: list[str]
    domain: str


@dataclass(frozen=True)
class SchemaImport:
    importer: str
    names: list[str]


@dataclass(frozen=True)
class SchemaReExport:
    module: str
    names: list[str]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--json", action="store_true", help="Emit JSON inventory.")
    parser.add_argument("--markdown", action="store_true", help="Emit Markdown inventory. This is the default.")
    parser.add_argument(
        "--fail-on-missing-imports",
        action="store_true",
        help="Exit non-zero if an import from api.schemas references a name not defined in schemas.py.",
    )
    return parser.parse_args(argv)


def node_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = node_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Subscript):
        return node_name(node.value)
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def names_in_annotation(node: ast.AST | None, known_names: set[str]) -> set[str]:
    if node is None:
        return set()
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in known_names:
            found.add(child.id)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            for name in known_names:
                if name in child.value:
                    found.add(name)
    return found


def classify_domain(name: str) -> str:
    for domain, keywords in DOMAIN_KEYWORDS:
        if any(keyword in name for keyword in keywords):
            return domain
    return "shared-or-uncategorized"


def class_kind(node: ast.ClassDef) -> str:
    bases = {node_name(base).split(".")[-1] for base in node.bases}
    if "Enum" in bases:
        return "enum"
    if "BaseModel" in bases or bases:
        return "schema"
    return "class"


def collect_classes(tree: ast.Module) -> list[SchemaClass]:
    known_names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    classes: list[SchemaClass] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [node_name(base) for base in node.bases]
        validators: list[str] = []
        references: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.FunctionDef):
                for decorator in child.decorator_list:
                    decorator_name = node_name(decorator)
                    if "field_validator" in decorator_name or "model_validator" in decorator_name:
                        validators.append(child.name)
            elif isinstance(child, ast.AnnAssign):
                references.update(names_in_annotation(child.annotation, known_names))
            elif isinstance(child, ast.arg):
                references.update(names_in_annotation(child.annotation, known_names))
        references.update(base.split(".")[-1] for base in bases if base.split(".")[-1] in known_names)
        references.discard(node.name)
        classes.append(
            SchemaClass(
                name=node.name,
                kind=class_kind(node),
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
                bases=bases,
                validators=sorted(set(validators)),
                references=sorted(references),
                domain=classify_domain(node.name),
            )
        )
    return classes


def collect_model_rebuilds(tree: ast.Module) -> list[dict[str, Any]]:
    rebuilds: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"model_rebuild", "update_forward_refs"}:
            continue
        owner = node_name(node.func.value)
        rebuilds.append({"name": owner, "method": node.func.attr, "line": node.lineno})
    return sorted(rebuilds, key=lambda item: (item["line"], item["name"]))


def collect_schema_reexports(tree: ast.Module) -> list[SchemaReExport]:
    reexports: list[SchemaReExport] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or not node.module.startswith(SCHEMA_DEFS_PREFIX):
            continue
        reexports.append(SchemaReExport(node.module, sorted(alias.asname or alias.name for alias in node.names)))
    return sorted(reexports, key=lambda item: item.module)


def collect_schema_imports(repo_root: Path, paths: list[str]) -> list[SchemaImport]:
    imports: list[SchemaImport] = []
    for path in paths:
        if path == SCHEMA_PATH or Path(path).suffix != ".py":
            continue
        text = read_text(repo_root, path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError:
            continue
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == SCHEMA_MODULE:
                imported.extend(alias.name for alias in node.names)
        if imported:
            imports.append(SchemaImport(path, sorted(set(imported))))
    return sorted(imports, key=lambda item: item.importer)


def build_inventory(repo_root: Path) -> dict[str, Any]:
    text = read_text(repo_root, SCHEMA_PATH)
    if text is None:
        raise FileNotFoundError(f"cannot read {SCHEMA_PATH}")
    tree = ast.parse(text, filename=SCHEMA_PATH)
    paths = tracked_or_walked_paths(repo_root, include_untracked=True)
    classes = collect_classes(tree)
    reexports = collect_schema_reexports(tree)
    imports = collect_schema_imports(repo_root, paths)
    defined = {item.name for item in classes}
    reexported_names = {name for item in reexports for name in item.names}
    public_names = defined | reexported_names
    imported_names = sorted({name for item in imports for name in item.names})
    missing_imports = sorted(name for name in imported_names if name != "*" and name not in public_names)
    by_domain: dict[str, list[str]] = {}
    for item in classes:
        by_domain.setdefault(item.domain, []).append(item.name)
    for name in reexported_names:
        by_domain.setdefault(classify_domain(name), []).append(name)
    return {
        "schema_path": SCHEMA_PATH,
        "class_count": len(classes),
        "reexport_count": len(reexported_names),
        "public_name_count": len(public_names),
        "importer_count": len(imports),
        "imported_name_count": len(imported_names),
        "model_rebuilds": collect_model_rebuilds(tree),
        "domains": {key: sorted(value) for key, value in sorted(by_domain.items())},
        "classes": [asdict(item) for item in classes],
        "reexports": [asdict(item) for item in reexports],
        "imports": [asdict(item) for item in imports],
        "missing_imports": missing_imports,
    }


def emit_markdown(inventory: dict[str, Any]) -> None:
    print(f"# API Schema Inventory: `{inventory['schema_path']}`")
    print()
    print(f"- schema classes/enums: {inventory['class_count']}")
    print(f"- schema compatibility re-exports: {inventory['reexport_count']}")
    print(f"- public schema names: {inventory['public_name_count']}")
    print(f"- importers: {inventory['importer_count']}")
    print(f"- imported schema names: {inventory['imported_name_count']}")
    print(f"- missing imported names: {len(inventory['missing_imports'])}")
    print()
    print("## Model Rebuild Calls")
    print()
    if inventory["model_rebuilds"]:
        for item in inventory["model_rebuilds"]:
            print(f"- line {item['line']}: `{item['name']}.{item['method']}()`")
    else:
        print("- none")
    print()
    print("## Domain Buckets")
    print()
    for domain, names in inventory["domains"].items():
        preview = ", ".join(f"`{name}`" for name in names[:12])
        suffix = "" if len(names) <= 12 else f", ... +{len(names) - 12}"
        print(f"- `{domain}`: {len(names)} names ({preview}{suffix})")
    print()
    print("## Importers")
    print()
    for item in inventory["imports"]:
        names = ", ".join(f"`{name}`" for name in item["names"])
        print(f"- `{item['importer']}`: {names}")
    if inventory["missing_imports"]:
        print()
        print("## Missing Imports")
        print()
        for name in inventory["missing_imports"]:
            print(f"- `{name}`")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    inventory = build_inventory(repo_root)
    if args.json:
        print(json.dumps(inventory, indent=2, sort_keys=True))
    else:
        emit_markdown(inventory)
    if args.fail_on_missing_imports and inventory["missing_imports"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
