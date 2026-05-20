#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run this script as root."
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
APP_ROOT="${APP_ROOT:-/opt/courseeval}"
SOURCE_DIR="${SOURCE_DIR:-${APP_ROOT}/source}"
if [[ -d "${SOURCE_DIR}/.git" ]]; then
  echo "==> deploy_frontend: source ${SOURCE_DIR} at commit $(git -C "${SOURCE_DIR}" rev-parse --short HEAD) ($(git -C "${SOURCE_DIR}" rev-parse --abbrev-ref HEAD))"
fi
ADMIN_WEB_ROOT="${ADMIN_WEB_ROOT:-/var/www/courseeval.example/admin}"
APP_USER="${APP_USER:-courseeval}"
CERT_NAME="${CERT_NAME:-www.courseeval.example}"
HTTP_TEMPLATE="${SOURCE_DIR}/ops/nginx/courseeval.example.http.conf"
HTTPS_TEMPLATE="${SOURCE_DIR}/ops/nginx/courseeval.example.conf"
CERT_DIR="/etc/letsencrypt/live/${CERT_NAME}"

if [[ -d /etc/nginx/sites-available ]]; then
  NGINX_SITE="/etc/nginx/sites-available/courseeval.example.conf"
  NGINX_LINK="/etc/nginx/sites-enabled/courseeval.example.conf"
else
  NGINX_SITE="/etc/nginx/conf.d/courseeval.example.conf"
  NGINX_LINK=""
fi

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
    "${REPO_ROOT}/" "${SOURCE_DIR}/"
fi

find "${SOURCE_DIR}" -type d -exec chmod 0755 {} +
find "${SOURCE_DIR}" -type f -exec chmod 0644 {} +
find "${SOURCE_DIR}/ops/scripts" -type f -name "*.sh" -exec chmod 0755 {} +
chown -R "${APP_USER}:${APP_USER}" "${APP_ROOT}"

pushd "${SOURCE_DIR}/apps/web/school" >/dev/null
npm ci
npm run build
popd >/dev/null

install -d -m 0755 /var/www/certbot
install -d -m 0755 "${ADMIN_WEB_ROOT}"
rsync -a --delete "${SOURCE_DIR}/apps/web/school/dist/" "${ADMIN_WEB_ROOT}/"

if [[ -f "${CERT_DIR}/fullchain.pem" && -f "${CERT_DIR}/privkey.pem" ]]; then
  install -m 0644 "${HTTPS_TEMPLATE}" "${NGINX_SITE}"
else
  install -m 0644 "${HTTP_TEMPLATE}" "${NGINX_SITE}"
fi
if [[ -n "${NGINX_LINK}" ]]; then
  ln -sfn "${NGINX_SITE}" "${NGINX_LINK}"
  rm -f /etc/nginx/sites-enabled/default
fi

nginx -t
systemctl reload nginx
