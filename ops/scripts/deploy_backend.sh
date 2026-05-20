#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run this script as root."
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
APP_ROOT="${APP_ROOT:-/opt/courseeval}"
SOURCE_DIR="${SOURCE_DIR:-${APP_ROOT}/source}"
VENV_DIR="${VENV_DIR:-${APP_ROOT}/venv}"
SHARED_DIR="${SHARED_DIR:-${APP_ROOT}/shared}"
ENV_FILE="${ENV_FILE:-${SHARED_DIR}/.env.production}"
APP_USER="${APP_USER:-courseeval}"
SERVICE_FILE="/etc/systemd/system/courseeval-backend.service"
PYTHON_BIN="${PYTHON_BIN:-}"
SHARED_UPLOADS_DIR="${SHARED_DIR}/uploads"
LEGACY_UPLOADS_DIR="${SOURCE_DIR}/uploads"

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  echo "System user '${APP_USER}' does not exist. Run ops/scripts/setup_server.sh first."
  exit 1
fi

install -d -m 0755 "${APP_ROOT}" "${SHARED_DIR}" "${SHARED_UPLOADS_DIR}" "${SHARED_UPLOADS_DIR}/attachments"

if [[ "${REPO_ROOT}" != "${SOURCE_DIR}" ]]; then
  install -d -m 0755 "${SOURCE_DIR}"
  rsync -a --delete \
    --exclude ".git" \
    --exclude "__pycache__" \
    --exclude ".pytest_cache" \
    --exclude "apps/web/school/node_modules" \
    --exclude "apps/web/school/dist" \
    --exclude "apps/web/parent/node_modules" \
    --exclude "apps/web/parent/dist" \
    --exclude "uploads" \
    "${REPO_ROOT}/" "${SOURCE_DIR}/"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  install -m 0640 "${SOURCE_DIR}/.env.production" "${ENV_FILE}"
  echo "Created ${ENV_FILE}. Update all CHANGE_ME values, then rerun this script."
  exit 1
fi

if grep -q "CHANGE_ME" "${ENV_FILE}"; then
  echo "Please replace every CHANGE_ME placeholder in ${ENV_FILE} before deploying."
  exit 1
fi

if [[ -z "${PYTHON_BIN}" ]]; then
  for candidate in python3.11 python3.10 python3.9 python3.8 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      if "${candidate}" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 8) else 1)
PY
      then
        PYTHON_BIN="${candidate}"
        break
      fi
    fi
  done
fi

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "Could not find a supported Python interpreter (>= 3.8)."
  exit 1
fi

if [[ -d "${LEGACY_UPLOADS_DIR}" ]]; then
  echo "Syncing legacy uploads from ${LEGACY_UPLOADS_DIR} into ${SHARED_UPLOADS_DIR}"
  rsync -a "${LEGACY_UPLOADS_DIR}/" "${SHARED_UPLOADS_DIR}/"
  echo "Legacy uploads were copied into ${SHARED_UPLOADS_DIR}; the old directory was left in place for manual cleanup."
fi

echo "Using Python interpreter: ${PYTHON_BIN}"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip wheel
"${VENV_DIR}/bin/pip" install -r "${SOURCE_DIR}/requirements.txt"

install -m 0644 "${SOURCE_DIR}/ops/systemd/courseeval-backend.service" "${SERVICE_FILE}"

chown -R "${APP_USER}:${APP_USER}" "${APP_ROOT}"

systemctl daemon-reload
systemctl enable courseeval-backend.service
systemctl restart courseeval-backend.service
systemctl --no-pager --full status courseeval-backend.service || true
