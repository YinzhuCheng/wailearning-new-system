#!/usr/bin/env bash
set -euo pipefail

USERNAME="${1:-}"
NEW_PASSWORD="${2:-}"

REPO_DIR="${REPO_DIR:-/opt/courseeval/source}"
VENV_DIR="${VENV_DIR:-/opt/courseeval/venv}"
ENV_FILE="${ENV_FILE:-/opt/courseeval/shared/.env.production}"

if [[ -z "${USERNAME}" || -z "${NEW_PASSWORD}" ]]; then
  echo "Usage: bash ops/scripts/reset_user_password.sh <username> <new_password>"
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

set -a
source "${ENV_FILE}"
set +a

cd "${REPO_DIR}"

"${VENV_DIR}/bin/python" - "${USERNAME}" "${NEW_PASSWORD}" <<'PY'
import sys

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.database import SessionLocal
from apps.backend.courseeval_backend.db.models import User

username = sys.argv[1]
new_password = sys.argv[2]

db = SessionLocal()
try:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise SystemExit(f"User '{username}' not found.")

    user.hashed_password = get_password_hash(new_password)
    user.is_active = True
    user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
    db.add(user)
    db.commit()

    print(f"Password reset for '{username}'.")
finally:
    db.close()
PY
