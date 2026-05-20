#!/usr/bin/env bash
set -euo pipefail

USERNAME="${1:-${ADMIN_USER:-admin}}"
NEW_PASSWORD="${2:-${ADMIN_PASS:-}}"
REAL_NAME="${REAL_NAME:-System Administrator}"

REPO_DIR="${REPO_DIR:-/opt/courseeval/source}"
VENV_DIR="${VENV_DIR:-/opt/courseeval/venv}"
ENV_FILE="${ENV_FILE:-/opt/courseeval/shared/.env.production}"

if [[ -z "${NEW_PASSWORD}" ]]; then
  echo "Usage: bash ops/scripts/set-password.sh <username> <new_password>"
  echo "       ADMIN_USER=<username> ADMIN_PASS=<new_password> bash ops/scripts/set-password.sh"
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Environment file not found: ${ENV_FILE}"
  exit 1
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Python interpreter not found: ${VENV_DIR}/bin/python"
  exit 1
fi

load_env_file() {
  local line key value
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line}" || "${line}" == \#* || "${line}" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key//[[:space:]]/}"
    [[ "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "${value}" == \'*\' && "${value}" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "${key}=${value}"
  done < "${ENV_FILE}"
}

load_env_file

cd "${REPO_DIR}"

"${VENV_DIR}/bin/python" - "${USERNAME}" "${NEW_PASSWORD}" "${REAL_NAME}" <<'PY'
import sys

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import User, UserRole

username = sys.argv[1]
new_password = sys.argv[2]
real_name = sys.argv[3]

db = SessionLocal()
try:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        user = User(
            username=username,
            hashed_password=get_password_hash(new_password),
            real_name=real_name,
            role=UserRole.ADMIN.value,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Created admin '{username}'.")
    else:
        user.hashed_password = get_password_hash(new_password)
        user.real_name = user.real_name or real_name
        user.role = UserRole.ADMIN.value
        user.is_active = True
        user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
        db.add(user)
        db.commit()
        print(f"Updated admin '{username}'.")
finally:
    db.close()
PY
