"""Static guardrail for CourseEval API surface governance.

This is not an OpenAPI exporter. It checks a small set of high-value anchors so
agents do not drift docs, frontend API clients, and FastAPI router wiring apart.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


ROUTER_PREFIXES = {
    "auth": "/api/auth",
    "classes": "/api/classes",
    "students": "/api/students",
    "scores": "/api/scores",
    "attendance": "/api/attendance",
    "appearance": "/api/appearance",
    "dashboard": "/api/dashboard",
    "subjects": "/api/subjects",
    "users": "/api/users",
    "semesters": "/api/semesters",
    "logs": "/api/logs",
    "points": "/api/points",
    "settings": "/api/settings",
    "llm_settings": "/api/llm-settings",
    "files": "/api/files",
    "homework": "/api/homeworks",
    "learning_notes": "/api/learning-notes",
    "discussions": "/api/discussions",
    "material_chapters": "/api/material-chapters",
    "materials": "/api/materials",
    "notifications": "/api/notifications",
    "parent": "/api/parent",
    "e2e_dev": "/api/e2e",
}

MAIN_INCLUDE_NAMES = {
    "settings": "system_settings",
    **{name: name for name in ROUTER_PREFIXES if name != "settings"},
}

ADMIN_CLIENT_ANCHORS = {
    "const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api'": "admin API base must default to /api",
    "export { http, httpQuiet, httpPublic, apiBaseUrl }": "admin client must expose canonical HTTP clients",
    "forgotPassword: data => httpPublic.post('/auth/forgot-password', data)": "forgot-password uses unauthenticated public client",
    "learningNotes: {": "learning-notes API helper family must remain indexed",
    "materialChapters: {": "material-chapter API helper family must remain indexed",
}

PARENT_CLIENT_ANCHORS = {
    "const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api'": "parent API base must default to /api",
    "verifyCode: code => http.get(`/parent/verify/${code}`)": "parent-code verification helper",
    "getHomework: (code, params) => http.get(`/parent/homework/${code}`, { params })": "parent homework helper",
}

DOC_ANCHORS = {
    "docs/reference/CODE_MAP_AND_ENTRYPOINTS.md": {
        "Routers live under `apps/backend/courseeval_backend/api/routers/`.": "router directory statement",
        "`learning_notes.router`": "learning-notes router entry",
        "`e2e_dev.router`": "E2E router entry",
        "OpenAPI `/docs` is authoritative for live enumeration": "OpenAPI authority warning",
    },
    "docs/reference/PERMISSIONS_AND_SECURITY_BOUNDARIES.md": {
        "Vue `meta` flags are **UX hints only**": "frontend route meta is not auth",
        "FastAPI dependencies + domain helpers enforce authorization": "backend authorization source of truth",
        "settings.expose_e2e_dev_api()": "E2E dev API gate",
    },
    "docs/testing/DEVELOPMENT_AND_TESTING.md": {
        "Confirm the contract first": "API test-authoring contract guidance",
        "apps/backend/courseeval_backend/api/routers/*.py": "router path guidance",
    },
}


def read_text(repo_root: Path, relative_path: str) -> str:
    return (repo_root / relative_path).read_text(encoding="utf-8")


def check_main_router_includes(repo_root: Path) -> list[str]:
    rel_path = "apps/backend/courseeval_backend/main.py"
    tree = ast.parse(read_text(repo_root, rel_path), filename=rel_path)
    included: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "include_router"
            and isinstance(func.value, ast.Name)
            and func.value.id == "app"
            and node.args
        ):
            continue
        arg = node.args[0]
        if (
            isinstance(arg, ast.Attribute)
            and arg.attr == "router"
            and isinstance(arg.value, ast.Name)
        ):
            included.add(arg.value.id)
    issues: list[str] = []
    for module_name, include_name in MAIN_INCLUDE_NAMES.items():
        if include_name not in included:
            issues.append(f"{rel_path}: missing app.include_router({include_name}.router) for {module_name}")
    return issues


def check_router_prefixes(repo_root: Path) -> list[str]:
    issues: list[str] = []
    for module_name, prefix in ROUTER_PREFIXES.items():
        rel_path = f"apps/backend/courseeval_backend/api/routers/{module_name}.py"
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"{rel_path}: missing router module")
            continue
        text = path.read_text(encoding="utf-8")
        if "APIRouter(" not in text:
            issues.append(f"{rel_path}: missing APIRouter declaration")
        if f'prefix="{prefix}"' not in text:
            issues.append(f"{rel_path}: missing APIRouter prefix {prefix}")
    return issues


def check_required_tokens(repo_root: Path, rel_path: str, required: dict[str, str]) -> list[str]:
    path = repo_root / rel_path
    if not path.exists():
        return [f"{rel_path}: missing required API governance file"]
    text = path.read_text(encoding="utf-8")
    return [
        f"{rel_path}: missing {description}: {token}"
        for token, description in required.items()
        if token not in text
    ]


def check_api_surface_governance(repo_root: Path) -> list[str]:
    issues: list[str] = []
    issues.extend(check_main_router_includes(repo_root))
    issues.extend(check_router_prefixes(repo_root))
    issues.extend(
        check_required_tokens(
            repo_root,
            "apps/web/school/src/api/index.js",
            ADMIN_CLIENT_ANCHORS,
        )
    )
    issues.extend(
        check_required_tokens(
            repo_root,
            "apps/web/parent/src/api/index.js",
            PARENT_CLIENT_ANCHORS,
        )
    )
    for rel_path, anchors in DOC_ANCHORS.items():
        issues.extend(check_required_tokens(repo_root, rel_path, anchors))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    issues = check_api_surface_governance(repo_root)
    if issues:
        print("API surface governance check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("API surface governance check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
