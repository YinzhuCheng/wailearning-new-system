"""Static governance checks for production operator scripts.

The checks here are intentionally lightweight and cross-platform. They do not
execute Bash, call systemd, contact network hosts, or require PostgreSQL. Their
job is to catch drift in script contracts that documentation and deployment
handoffs rely on.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


TOP_LEVEL_SHELL_SCRIPTS = (
    "ops/scripts/deploy_all.sh",
    "ops/scripts/deploy_backend.sh",
    "ops/scripts/deploy_frontend.sh",
    "ops/scripts/deploy_parent_portal.sh",
    "ops/scripts/example_safe_upgrade_aliyun.sh",
    "ops/scripts/post_deploy_check.sh",
    "ops/scripts/pull_and_deploy.sh",
    "ops/scripts/redeploy.sh",
    "ops/scripts/reset_user_password.sh",
    "ops/scripts/set-password.sh",
    "ops/scripts/setup_server.sh",
)

SOURCED_HELPERS = (
    "ops/scripts/lib/deploy_repo_dir.sh",
    "ops/scripts/lib/git_sync_server.sh",
)


def read_text(repo_root: Path, rel_path: str) -> str:
    return (repo_root / rel_path).read_text(encoding="utf-8")


def require_contains(issues: list[str], rel_path: str, text: str, needle: str, message: str) -> None:
    if needle not in text:
        issues.append(f"{rel_path}: {message}")


def require_not_contains(issues: list[str], rel_path: str, text: str, needle: str, message: str) -> None:
    if needle in text:
        issues.append(f"{rel_path}: {message}")


def check_shell_headers(repo_root: Path, issues: list[str]) -> None:
    for rel_path in TOP_LEVEL_SHELL_SCRIPTS:
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"{rel_path}: missing required operator script")
            continue
        text = read_text(repo_root, rel_path)
        if not text.startswith("#!/usr/bin/env bash\n"):
            issues.append(f"{rel_path}: missing '#!/usr/bin/env bash' shebang")
        require_contains(issues, rel_path, text, "set -euo pipefail", "missing 'set -euo pipefail'")

    for rel_path in SOURCED_HELPERS:
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"{rel_path}: missing required sourced helper")
            continue
        text = read_text(repo_root, rel_path)
        if not text.startswith("#!/usr/bin/env bash\n"):
            issues.append(f"{rel_path}: missing '#!/usr/bin/env bash' shebang")
        require_contains(
            issues,
            rel_path,
            text,
            'if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then',
            "sourced helper must reject direct execution",
        )


def check_frontend_deploy_contract(repo_root: Path, issues: list[str]) -> None:
    for rel_path in ("ops/scripts/deploy_frontend.sh", "ops/scripts/deploy_parent_portal.sh"):
        text = read_text(repo_root, rel_path)
        require_contains(issues, rel_path, text, "npm ci", "frontend deploy must use reproducible 'npm ci'")
        require_contains(issues, rel_path, text, "npm run build", "frontend deploy must build static assets")
        require_contains(issues, rel_path, text, "systemctl reload nginx", "frontend deploy must reload nginx")
        require_not_contains(
            issues,
            rel_path,
            text,
            "systemctl restart courseeval-backend",
            "frontend-only deploy must not restart the backend service",
        )
        require_not_contains(
            issues,
            rel_path,
            text,
            "systemctl restart ${BACKEND_SERVICE}",
            "frontend-only deploy must not restart the backend service",
        )


def check_full_stack_deploy_contract(repo_root: Path, issues: list[str]) -> None:
    rel_path = "ops/scripts/deploy_all.sh"
    text = read_text(repo_root, rel_path)
    for script in ("deploy_backend.sh", "deploy_frontend.sh", "deploy_parent_portal.sh"):
        require_contains(issues, rel_path, text, script, f"full deploy must run {script}")
    require_contains(
        issues,
        rel_path,
        text,
        "post_deploy_check.sh",
        "full deploy must point operators to the shared post-deploy check",
    )


def check_backend_deploy_contract(repo_root: Path, issues: list[str]) -> None:
    rel_path = "ops/scripts/deploy_backend.sh"
    text = read_text(repo_root, rel_path)
    require_contains(issues, rel_path, text, "SHARED_UPLOADS_DIR", "must use shared uploads directory")
    require_contains(issues, rel_path, text, "LEGACY_UPLOADS_DIR", "must preserve legacy uploads migration path")
    require_contains(issues, rel_path, text, 'rsync -a "${LEGACY_UPLOADS_DIR}/"', "must copy legacy uploads non-destructively")
    require_contains(issues, rel_path, text, "systemctl restart courseeval-backend.service", "backend deploy must restart backend service")


def check_setup_server_contract(repo_root: Path, issues: list[str]) -> None:
    rel_path = "ops/scripts/setup_server.sh"
    text = read_text(repo_root, rel_path)
    require_contains(issues, rel_path, text, 'APP_ROOT="${APP_ROOT:-/opt/courseeval}"', "must keep documented APP_ROOT default")
    require_contains(issues, rel_path, text, 'WEB_ROOT="${WEB_ROOT:-/var/www/courseeval.example}"', "must keep documented WEB_ROOT default")
    require_contains(issues, rel_path, text, "install_nodejs", "must install or validate Node.js")
    require_contains(issues, rel_path, text, "systemctl enable --now postgresql", "must enable PostgreSQL")
    require_contains(issues, rel_path, text, "systemctl enable --now nginx", "must enable nginx")
    require_contains(issues, rel_path, text, "-f ops/scripts/init_db.sql", "next steps must show init_db.sql invocation")
    require_contains(issues, rel_path, text, "deploy_all.sh", "next steps must point to full deploy script")
    require_contains(issues, rel_path, text, "post_deploy_check.sh", "next steps must point to shared post-deploy check")


def check_health_check_contract(repo_root: Path, issues: list[str]) -> None:
    rel_path = "ops/scripts/post_deploy_check.sh"
    text = read_text(repo_root, rel_path)
    require_contains(issues, rel_path, text, 'APP_URL="${APP_URL:-}"', "APP_URL must default empty")
    require_contains(issues, rel_path, text, 'API_HEALTH_URL="${API_HEALTH_URL:-}"', "API_HEALTH_URL must default empty")
    require_contains(
        issues,
        rel_path,
        text,
        "public health skipped (set APP_URL or API_HEALTH_URL to enable)",
        "public health must be opt-in",
    )
    require_contains(issues, rel_path, text, "wait_for_local_health", "must wait for local backend health")
    require_contains(issues, rel_path, text, "nginx -t", "must validate nginx configuration")


def check_password_script_contract(repo_root: Path, issues: list[str]) -> None:
    reset_path = "ops/scripts/reset_user_password.sh"
    reset_text = read_text(repo_root, reset_path)
    require_contains(issues, reset_path, reset_text, 'source "${ENV_FILE}"', "must load production env file")
    require_contains(issues, reset_path, reset_text, "get_password_hash", "must hash the new password")
    require_contains(issues, reset_path, reset_text, "token_version", "must increment token_version to invalidate JWT sessions")
    require_not_contains(issues, reset_path, reset_text, "UserRole.ADMIN", "reset script must not promote users to admin")

    set_path = "ops/scripts/set-password.sh"
    set_text = read_text(repo_root, set_path)
    require_contains(issues, set_path, set_text, 'source "${ENV_FILE}"', "must load production env file")
    require_contains(issues, set_path, set_text, "ADMIN_PASS", "must support environment-driven password input")
    require_contains(issues, set_path, set_text, "UserRole.ADMIN.value", "must create or promote the target admin")
    require_contains(issues, set_path, set_text, "user is None", "must create a missing admin user")
    require_contains(issues, set_path, set_text, "token_version", "must increment token_version for existing admins")


def check_git_update_contract(repo_root: Path, issues: list[str]) -> None:
    rel_path = "ops/scripts/lib/git_sync_server.sh"
    text = read_text(repo_root, rel_path)
    require_contains(issues, rel_path, text, "git ls-remote --exit-code --heads", "must verify remote branch exists")
    require_contains(
        issues,
        rel_path,
        text,
        'git fetch "${git_remote}" "refs/heads/${branch}:refs/remotes/${git_remote}/${branch}"',
        "must fetch the explicit branch refspec",
    )
    require_contains(issues, rel_path, text, "GIT_AUTO_STASH_ON_CHECKOUT_CONFLICT", "must keep checkout-conflict control")
    require_contains(issues, rel_path, text, "git stash push -u", "must preserve auto-stash fallback")

    rel_path = "ops/scripts/lib/deploy_repo_dir.sh"
    text = read_text(repo_root, rel_path)
    require_contains(issues, rel_path, text, 'DD_DEFAULT_REPO_DIR:=/opt/courseeval/source', "must prefer documented production clone path")
    require_contains(issues, rel_path, text, '/root/courseeval', "must warn about legacy server clone path")


def check_database_bootstrap_contract(repo_root: Path, issues: list[str]) -> None:
    rel_path = "ops/scripts/init_db.sql"
    text = read_text(repo_root, rel_path)
    for variable in ("db_name", "db_user", "db_password"):
        require_contains(issues, rel_path, text, f"Missing required variable: {variable}", f"must fail fast when {variable} is missing")
    require_contains(issues, rel_path, text, "\\set ON_ERROR_STOP on", "must stop on SQL errors")
    require_contains(issues, rel_path, text, "ALTER DEFAULT PRIVILEGES", "must grant default schema privileges")


def check_safe_upgrade_example_contract(repo_root: Path, issues: list[str]) -> None:
    rel_path = "ops/scripts/example_safe_upgrade_aliyun.sh"
    text = read_text(repo_root, rel_path)
    for command in ("rsync", "tar", "pg_dump", "systemctl"):
        require_contains(issues, rel_path, text, f"require {command}", f"must preflight required command: {command}")
    require_contains(issues, rel_path, text, "pg_dump -Fc", "must create a compressed database restore point")
    require_contains(issues, rel_path, text, "shared-${RELEASE_TAG}.tar.gz", "must back up shared files")
    require_contains(issues, rel_path, text, "frontend-${RELEASE_TAG}.tar.gz", "must back up frontend publish directories")
    require_contains(issues, rel_path, text, "-m py_compile", "must compile critical Python entrypoints before replacement")
    require_contains(issues, rel_path, text, "-m apps.backend.courseeval_backend.bootstrap", "must run bootstrap/schema sync")
    require_contains(issues, rel_path, text, "npm ci", "must use reproducible frontend installs")
    require_contains(issues, rel_path, text, "post_deploy_check.sh", "must use the shared post-deploy check")


def check_scripts(repo_root: Path) -> list[str]:
    issues: list[str] = []
    check_shell_headers(repo_root, issues)
    check_full_stack_deploy_contract(repo_root, issues)
    check_frontend_deploy_contract(repo_root, issues)
    check_backend_deploy_contract(repo_root, issues)
    check_setup_server_contract(repo_root, issues)
    check_health_check_contract(repo_root, issues)
    check_password_script_contract(repo_root, issues)
    check_git_update_contract(repo_root, issues)
    check_database_bootstrap_contract(repo_root, issues)
    check_safe_upgrade_example_contract(repo_root, issues)
    return issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    issues = check_scripts(repo_root)
    if issues:
        print("Operator script governance check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    checked = len(TOP_LEVEL_SHELL_SCRIPTS) + len(SOURCED_HELPERS) + 1
    print(f"Operator script governance check passed. checked={checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
