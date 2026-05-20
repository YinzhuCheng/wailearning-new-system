#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="${REPO_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd -P)}"

APP_URL="${APP_URL:-}"
API_HEALTH_URL="${API_HEALTH_URL:-}"
# When the public check is ${APP_URL}/health, also hit Nginx /api/health (unless overridden).
PUBLIC_API_HEALTH_URL="${PUBLIC_API_HEALTH_URL:-}"
_app_url="${APP_URL%/}"
if [[ -z "${API_HEALTH_URL}" && -n "${_app_url}" ]]; then
  API_HEALTH_URL="${_app_url}/health"
fi
if [[ -z "${PUBLIC_API_HEALTH_URL}" && -n "${_app_url}" && "${API_HEALTH_URL}" == "${_app_url}/health" ]]; then
  PUBLIC_API_HEALTH_URL="${_app_url}/api/health"
fi
BACKEND_SERVICE="${BACKEND_SERVICE:-courseeval-backend}"
LOCAL_HEALTH_RETRIES="${LOCAL_HEALTH_RETRIES:-30}"
LOCAL_HEALTH_INTERVAL_SECONDS="${LOCAL_HEALTH_INTERVAL_SECONDS:-1}"

wait_for_local_health() {
  local attempt
  for ((attempt = 1; attempt <= LOCAL_HEALTH_RETRIES; attempt++)); do
    if curl -fsS http://127.0.0.1:8001/health >/dev/null 2>&1; then
      return 0
    fi
    sleep "${LOCAL_HEALTH_INTERVAL_SECONDS}"
  done
  return 1
}

echo "==> Git checkout (server repo)"
if [[ -d "${REPO_DIR}/.git" ]]; then
  echo "    REPO_DIR=${REPO_DIR}"
  echo "    branch: $(git -C "${REPO_DIR}" rev-parse --abbrev-ref HEAD)"
  echo "    HEAD:   $(git -C "${REPO_DIR}" rev-parse HEAD)"
else
  echo "    (no .git under REPO_DIR, skipping commit display)"
fi
echo

echo "==> systemd status"
systemctl --no-pager --full status "${BACKEND_SERVICE}" || true

echo "==> local backend health"
if wait_for_local_health; then
  curl -fsS http://127.0.0.1:8001/health
else
  echo "Local backend health check failed after ${LOCAL_HEALTH_RETRIES} attempts."
  echo "Tip: increase LOCAL_HEALTH_RETRIES / LOCAL_HEALTH_INTERVAL_SECONDS and retry."
  exit 1
fi
echo

if [[ -n "${API_HEALTH_URL}" ]]; then
  echo "==> public health (${API_HEALTH_URL})"
  # Follow HTTP->HTTPS redirects so a 301 from certbot-managed nginx is not a false failure.
  if curl -fsSL "${API_HEALTH_URL}"; then
    :
  else
    echo "Public health check failed. If you use HTTPS only, set API_HEALTH_URL to https://.../health" >&2
    exit 1
  fi
  echo
else
  echo "==> public health skipped (set APP_URL or API_HEALTH_URL to enable)"
  echo
fi

if [[ -n "${PUBLIC_API_HEALTH_URL}" ]]; then
  echo "==> public API health (${PUBLIC_API_HEALTH_URL})"
  if curl -fsSL "${PUBLIC_API_HEALTH_URL}"; then
    :
  else
    echo "Public /api/health check failed." >&2
    exit 1
  fi
  echo
fi

echo "==> nginx config test"
nginx -t

echo "==> recent backend logs"
journalctl -u "${BACKEND_SERVICE}" -n 30 --no-pager || true
