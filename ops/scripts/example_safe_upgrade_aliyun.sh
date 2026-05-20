#!/usr/bin/env bash
set -euo pipefail

# Example only:
# This script demonstrates a safer Alibaba Cloud ECS upgrade flow
# that prioritizes preserving PostgreSQL data and uploaded attachments.
# Review and adapt it to your environment before production use.

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run this script as root."
  exit 1
fi

APP_ROOT="${APP_ROOT:-/opt/courseeval}"
SOURCE_DIR="${SOURCE_DIR:-${APP_ROOT}/source}"
SHARED_DIR="${SHARED_DIR:-${APP_ROOT}/shared}"
BACKUP_DIR="${BACKUP_DIR:-${APP_ROOT}/backups}"
ENV_FILE="${ENV_FILE:-${SHARED_DIR}/.env.production}"
APP_SERVICE="${APP_SERVICE:-courseeval-backend}"
DB_NAME="${DB_NAME:-courseeval}"
UPLOADS_DIR="${UPLOADS_DIR:-${SHARED_DIR}/uploads}"
FRONTEND_BUILD_DIR="${FRONTEND_BUILD_DIR:-/var/www/courseeval.example/admin}"
PARENT_BUILD_DIR="${PARENT_BUILD_DIR:-/var/www/courseeval.example/parent}"
RELEASE_TAG="${RELEASE_TAG:-$(date +%F-%H%M%S)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require rsync
require tar
require pg_dump
require systemctl
require "${PYTHON_BIN}"

echo "==> 1. Prepare backup directories"
install -d -m 0755 "${BACKUP_DIR}" "${BACKUP_DIR}/db" "${BACKUP_DIR}/files" "${BACKUP_DIR}/releases"

echo "==> 2. Verify critical paths"
test -f "${ENV_FILE}" || { echo "Missing env file: ${ENV_FILE}" >&2; exit 1; }
test -d "${SOURCE_DIR}" || { echo "Missing source dir: ${SOURCE_DIR}" >&2; exit 1; }
test -d "${UPLOADS_DIR}" || { echo "Missing uploads dir: ${UPLOADS_DIR}" >&2; exit 1; }

echo "==> 3. Create restore point"
sudo -u postgres pg_dump -Fc "${DB_NAME}" > "${BACKUP_DIR}/db/${DB_NAME}-${RELEASE_TAG}.dump"
tar -czf "${BACKUP_DIR}/files/shared-${RELEASE_TAG}.tar.gz" "${SHARED_DIR}"
tar -czf "${BACKUP_DIR}/files/frontend-${RELEASE_TAG}.tar.gz" "${FRONTEND_BUILD_DIR}" "${PARENT_BUILD_DIR}"

echo "==> 4. Save current release snapshot"
rsync -a --delete "${SOURCE_DIR}/" "${BACKUP_DIR}/releases/${RELEASE_TAG}/source/"

echo "==> 5. Sync new code into a staging directory"
rsync -a --delete \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude ".pytest_cache" \
  --exclude "apps/web/school/node_modules" \
  --exclude "apps/web/school/dist" \
  --exclude "apps/web/parent/node_modules" \
  --exclude "apps/web/parent/dist" \
  --exclude "uploads" \
  "${REPO_ROOT}/" "${TMP_DIR}/source/"

echo "==> 6. Validate Python source"
"${PYTHON_BIN}" -m py_compile \
  "${TMP_DIR}/source/apps/backend/courseeval_backend/core/config.py" \
  "${TMP_DIR}/source/apps/backend/courseeval_backend/main.py" \
  "${TMP_DIR}/source/apps/backend/courseeval_backend/bootstrap.py"

echo "==> 7. Stop backend before replacing source"
systemctl stop "${APP_SERVICE}"

echo "==> 8. Replace source directory atomically enough for single-host deploys"
rsync -a --delete "${TMP_DIR}/source/" "${SOURCE_DIR}/"

echo "==> 9. Rebuild backend environment"
"${APP_ROOT}/venv/bin/pip" install -r "${SOURCE_DIR}/requirements.txt"

echo "==> 10. Run bootstrap/schema sync against existing database"
"${APP_ROOT}/venv/bin/python" -m apps.backend.courseeval_backend.bootstrap

echo "==> 11. Build frontend assets"
(
  cd "${SOURCE_DIR}/apps/web/school"
  npm ci
  npm run build
)
(
  cd "${SOURCE_DIR}/apps/web/parent"
  npm ci
  npm run build
)

echo "==> 12. Publish frontend assets"
rsync -a --delete "${SOURCE_DIR}/apps/web/school/dist/" "${FRONTEND_BUILD_DIR}/"
rsync -a --delete "${SOURCE_DIR}/apps/web/parent/dist/" "${PARENT_BUILD_DIR}/"

echo "==> 13. Start backend"
systemctl start "${APP_SERVICE}"
systemctl --no-pager --full status "${APP_SERVICE}" || true

echo "==> 14. Basic post-upgrade checks"
bash "${SOURCE_DIR}/ops/scripts/post_deploy_check.sh"

cat <<EOF
Upgrade completed.

Restore points created:
- Database dump: ${BACKUP_DIR}/db/${DB_NAME}-${RELEASE_TAG}.dump
- Shared files:  ${BACKUP_DIR}/files/shared-${RELEASE_TAG}.tar.gz
- Frontend files: ${BACKUP_DIR}/files/frontend-${RELEASE_TAG}.tar.gz
- Previous source: ${BACKUP_DIR}/releases/${RELEASE_TAG}/source/

If rollback is needed:
1. systemctl stop ${APP_SERVICE}
2. rsync previous source snapshot back into ${SOURCE_DIR}
3. restore PostgreSQL from the dump if schema/data changed
4. restore ${SHARED_DIR} if uploads or env were damaged
5. systemctl start ${APP_SERVICE}
EOF

# Domain / HTTPS follow-up (manual):
# 1) Point DNS A records to your ECS public IP:
#    - courseeval.example
#    - www.courseeval.example
# 2) Verify DNS resolution from server/client:
#    nslookup courseeval.example
#    nslookup www.courseeval.example
# 3) Issue TLS cert with Certbot (Nginx plugin):
#    certbot --nginx -d courseeval.example -d www.courseeval.example
# 4) Verify renewal timer:
#    systemctl status certbot.timer --no-pager
