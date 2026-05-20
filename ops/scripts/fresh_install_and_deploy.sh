#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run this script as root."
  exit 1
fi

GIT_REPO="${GIT_REPO:-https://github.com/YinzhuCheng/wailearning-new-system.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
APP_ROOT="${APP_ROOT:-/opt/courseeval}"
WEB_ROOT="${WEB_ROOT:-/var/www/courseeval.example}"
APP_USER="${APP_USER:-courseeval}"
SOURCE_DIR="${SOURCE_DIR:-${APP_ROOT}/source}"
SHARED_DIR="${SHARED_DIR:-${APP_ROOT}/shared}"
ENV_FILE="${ENV_FILE:-${SHARED_DIR}/.env.production}"
DB_NAME="${DB_NAME:-courseeval}"
DB_USER="${DB_USER:-courseeval}"
DB_PASSWORD="${DB_PASSWORD:-CHANGE_ME_DB_PASSWORD}"
SECRET_KEY="${SECRET_KEY:-CHANGE_ME_TO_A_LONG_RANDOM_SECRET}"
INIT_ADMIN_USERNAME="${INIT_ADMIN_USERNAME:-admin}"
INIT_ADMIN_PASSWORD="${INIT_ADMIN_PASSWORD:-CHANGE_ME_TO_A_STRONG_ADMIN_PASSWORD}"
INIT_ADMIN_REAL_NAME="${INIT_ADMIN_REAL_NAME:-System Administrator}"
PUBLIC_HOST="${PUBLIC_HOST:-courseeval.example}"
PUBLIC_WWW_HOST="${PUBLIC_WWW_HOST:-www.courseeval.example}"
PUBLIC_IP="${PUBLIC_IP:-}"
FRONTEND_ADMIN_BASE_URL="${FRONTEND_ADMIN_BASE_URL:-}"
ALLOW_PUBLIC_REGISTRATION="${ALLOW_PUBLIC_REGISTRATION:-false}"
INIT_DEFAULT_DATA="${INIT_DEFAULT_DATA:-false}"
DEFAULT_LLM_API_KEY="${DEFAULT_LLM_API_KEY:-}"
ENABLE_CERTBOT="${ENABLE_CERTBOT:-0}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
CERTBOT_CERT_NAME="${CERTBOT_CERT_NAME:-${PUBLIC_WWW_HOST}}"
BACKEND_PORT="${BACKEND_PORT:-8001}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

assert_not_placeholder() {
  local name="$1"
  local value="$2"
  if [[ -z "${value}" || "${value}" == CHANGE_ME* ]]; then
    echo "Required variable ${name} is unset or still uses a CHANGE_ME placeholder." >&2
    exit 1
  fi
}

write_env_file() {
  local cors_origins trusted_hosts admin_base_url
  if [[ -n "${PUBLIC_IP}" ]]; then
    cors_origins="http://${PUBLIC_IP}"
    trusted_hosts="${PUBLIC_IP},127.0.0.1,localhost"
    admin_base_url="${FRONTEND_ADMIN_BASE_URL:-http://${PUBLIC_IP}}"
  else
    cors_origins="https://${PUBLIC_HOST},https://${PUBLIC_WWW_HOST}"
    trusted_hosts="${PUBLIC_HOST},${PUBLIC_WWW_HOST},127.0.0.1,localhost"
    admin_base_url="${FRONTEND_ADMIN_BASE_URL:-https://${PUBLIC_WWW_HOST}}"
  fi

  install -d -m 0755 "${SHARED_DIR}"
  cat >"${ENV_FILE}" <<EOF
APP_NAME="CourseEval API"
APP_ENV=production
DEBUG=false
HOST=127.0.0.1
PORT=${BACKEND_PORT}

DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@127.0.0.1:5432/${DB_NAME}
SECRET_KEY=${SECRET_KEY}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
UPLOADS_DIR=${APP_ROOT}/shared/uploads

BACKEND_CORS_ORIGINS=${cors_origins}
TRUSTED_HOSTS=${trusted_hosts}

INIT_ADMIN_USERNAME=${INIT_ADMIN_USERNAME}
INIT_ADMIN_PASSWORD=${INIT_ADMIN_PASSWORD}
INIT_ADMIN_REAL_NAME="${INIT_ADMIN_REAL_NAME}"
INIT_DEFAULT_DATA=${INIT_DEFAULT_DATA}
ALLOW_PUBLIC_REGISTRATION=${ALLOW_PUBLIC_REGISTRATION}
PUBLIC_REGISTRATION_VALIDATE_CLASS_EXISTS=true
FRONTEND_ADMIN_BASE_URL=${admin_base_url}
FORGOT_PASSWORD_USERNAME_COOLDOWN_SECONDS=600
FORGOT_PASSWORD_MAX_REQUESTS_PER_IP_PER_HOUR=40

GUNICORN_WORKERS=3
LOG_LEVEL=info
ENABLE_LLM_GRADING_WORKER=true
LLM_GRADING_WORKER_LEADER=true
LLM_GRADING_WORKER_POLL_SECONDS=2
LLM_GRADING_TASK_STALE_SECONDS=600
DEFAULT_LLM_API_KEY=${DEFAULT_LLM_API_KEY}
REQUIRE_STRONG_SECRETS=true
EOF
  chmod 0640 "${ENV_FILE}"
}

install_repo() {
  if [[ -d "${SOURCE_DIR}/.git" ]]; then
    echo "==> Reusing existing git clone under ${SOURCE_DIR}"
    git config --global --add safe.directory "${SOURCE_DIR}" || true
    git -C "${SOURCE_DIR}" remote set-url origin "${GIT_REPO}"
    git -C "${SOURCE_DIR}" fetch origin "${GIT_BRANCH}"
    git -C "${SOURCE_DIR}" checkout -B "${GIT_BRANCH}" "origin/${GIT_BRANCH}"
    git -C "${SOURCE_DIR}" reset --hard "origin/${GIT_BRANCH}"
    git -C "${SOURCE_DIR}" clean -ffd
  else
    echo "==> Cloning ${GIT_REPO} into ${SOURCE_DIR}"
    rm -rf "${SOURCE_DIR}"
    git clone --branch "${GIT_BRANCH}" --single-branch "${GIT_REPO}" "${SOURCE_DIR}"
  fi
}

maybe_issue_cert() {
  if [[ "${ENABLE_CERTBOT}" != "1" ]]; then
    return
  fi

  if [[ -z "${CERTBOT_EMAIL}" ]]; then
    echo "ENABLE_CERTBOT=1 requires CERTBOT_EMAIL." >&2
    exit 1
  fi

  echo "==> Issuing or refreshing Let's Encrypt certificate"
  certbot --nginx \
    --non-interactive \
    --agree-tos \
    --redirect \
    --cert-name "${CERTBOT_CERT_NAME}" \
    -m "${CERTBOT_EMAIL}" \
    -d "${PUBLIC_HOST}" \
    -d "${PUBLIC_WWW_HOST}"
}

assert_not_placeholder "DB_PASSWORD" "${DB_PASSWORD}"
assert_not_placeholder "SECRET_KEY" "${SECRET_KEY}"
assert_not_placeholder "INIT_ADMIN_PASSWORD" "${INIT_ADMIN_PASSWORD}"

require_cmd git

echo "==> 1/8 Install server prerequisites"
APP_ROOT="${APP_ROOT}" WEB_ROOT="${WEB_ROOT}" APP_USER="${APP_USER}" bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/setup_server.sh"

echo "==> 2/8 Sync repository"
install_repo

echo "==> 3/8 Write production env file"
write_env_file

echo "==> 4/8 Initialize PostgreSQL"
sudo -u postgres psql \
  -v db_name="${DB_NAME}" \
  -v db_user="${DB_USER}" \
  -v db_password="${DB_PASSWORD}" \
  -f "${SOURCE_DIR}/ops/scripts/init_db.sql"

echo "==> 5/8 Deploy backend and static assets"
APP_ROOT="${APP_ROOT}" \
SOURCE_DIR="${SOURCE_DIR}" \
APP_USER="${APP_USER}" \
WEB_ROOT="${WEB_ROOT}" \
ENV_FILE="${ENV_FILE}" \
bash "${SOURCE_DIR}/ops/scripts/deploy_all.sh"

echo "==> 6/8 Validate nginx and backend locally"
bash "${SOURCE_DIR}/ops/scripts/post_deploy_check.sh"

echo "==> 7/8 Optional TLS issuance"
maybe_issue_cert

echo "==> 8/8 Final summary"
echo "Branch: $(git -C "${SOURCE_DIR}" rev-parse --abbrev-ref HEAD)"
echo "Commit: $(git -C "${SOURCE_DIR}" rev-parse --short HEAD)"
echo "Backend local health: http://127.0.0.1:${BACKEND_PORT}/health"
if [[ -n "${PUBLIC_IP}" ]]; then
  echo "HTTP URL: http://${PUBLIC_IP}/"
  echo "Parent URL: http://${PUBLIC_IP}/parent/"
  echo "Public health: http://${PUBLIC_IP}/health"
else
  echo "HTTP URL: http://${PUBLIC_HOST}/"
  echo "Parent URL: http://${PUBLIC_HOST}/parent/"
  echo "Public health: http://${PUBLIC_HOST}/health"
fi
echo "Env file: ${ENV_FILE}"
echo "If DNS already points to this host, you can rerun with ENABLE_CERTBOT=1 CERTBOT_EMAIL=<you@example.com> to switch nginx to HTTPS."
