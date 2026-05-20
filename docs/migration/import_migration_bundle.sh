#!/usr/bin/env bash
set -Eeuo pipefail

on_error() {
  local line="$1"
  echo "迁移包导入失败：脚本第 ${line} 行出错。"
  echo "导入工作目录：${WORK_DIR:-尚未创建}"
}
trap 'on_error $LINENO' ERR

APP_NAME="${APP_NAME:-wailearning-new-system}"
ENV_FILE="${ENV_FILE:-/opt/wailearning-new-system/current/.env.production}"
RELEASE_DIR="${RELEASE_DIR:-/opt/wailearning-new-system/current}"
MIGRATION_BUNDLE="${MIGRATION_BUNDLE:-}"
CONFIRM_IMPORT="${CONFIRM_IMPORT:-}"
BACKUP_DIR="${BACKUP_DIR:-/root/wailearning-migration-import-backups}"
BACKEND_PORT="${BACKEND_PORT:-8002}"

load_env_file() {
  local env_file="$1"
  local line key value
  if [ ! -f "${env_file}" ]; then
    echo "找不到环境文件：${env_file}"
    exit 1
  fi
  while IFS= read -r line || [ -n "${line}" ]; do
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
  done < "${env_file}"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少命令：$1"
    exit 1
  fi
}

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 用户运行。"
  exit 1
fi

if [ "${CONFIRM_IMPORT}" != "YES" ]; then
  echo "导入会覆盖新系统数据库。请把 CONFIRM_IMPORT 设置为 YES。"
  exit 1
fi

if [ -z "${MIGRATION_BUNDLE}" ] || [ ! -f "${MIGRATION_BUNDLE}" ]; then
  echo "找不到迁移包：${MIGRATION_BUNDLE}"
  exit 1
fi

load_env_file "${ENV_FILE}"
DATABASE_URL="${DATABASE_URL:-}"
UPLOADS_DIR="${UPLOADS_DIR:-/opt/wailearning-new-system/uploads}"

if [ -z "${DATABASE_URL}" ]; then
  echo "环境文件中缺少 DATABASE_URL。"
  exit 1
fi

require_cmd pg_dump
require_cmd pg_restore
require_cmd tar
require_cmd curl

STAMP="$(date +%Y%m%d%H%M%S)"
WORK_DIR="/tmp/${APP_NAME}-migration-import-${STAMP}"
mkdir -p "${WORK_DIR}" "${BACKUP_DIR}"

echo "解压迁移包。"
tar -xzf "${MIGRATION_BUNDLE}" -C "${WORK_DIR}"
MIGRATION_DIR="$(find "${WORK_DIR}" -mindepth 1 -maxdepth 1 -type d | head -1)"
if [ -z "${MIGRATION_DIR}" ]; then
  echo "迁移包结构不正确：未找到顶层目录。"
  exit 1
fi

if [ ! -f "${MIGRATION_DIR}/old-system.dump" ]; then
  echo "迁移包缺少 old-system.dump。"
  exit 1
fi

echo "导入前备份新系统数据库。"
pg_dump -Fc "${DATABASE_URL}" -f "${BACKUP_DIR}/${APP_NAME}-before-import-${STAMP}.dump"

echo "停止新系统后端服务。"
systemctl stop "${APP_NAME}.service" 2>/dev/null || true

echo "恢复旧系统数据库到新系统数据库。"
pg_restore --clean --if-exists --no-owner --dbname "${DATABASE_URL}" "${MIGRATION_DIR}/old-system.dump"

if [ -f "${MIGRATION_DIR}/old-uploads.tar.gz" ]; then
  echo "恢复附件。"
  mkdir -p "${UPLOADS_DIR}"
  tar -xzf "${MIGRATION_DIR}/old-uploads.tar.gz" -C "$(dirname "${UPLOADS_DIR}")"
fi

echo "运行新系统 bootstrap/兼容性修复。"
cd "${RELEASE_DIR}"
"${RELEASE_DIR}/.venv/bin/python" -m apps.backend.courseeval_backend.bootstrap

echo "启动新系统后端服务并检查健康状态。"
systemctl start "${APP_NAME}.service"
sleep 3
if ! systemctl is-active --quiet "${APP_NAME}.service"; then
  echo "新系统服务启动失败，最近日志如下："
  systemctl status "${APP_NAME}.service" --no-pager || true
  journalctl -u "${APP_NAME}.service" -n 160 --no-pager || true
  exit 1
fi

if ! curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null; then
  echo "新系统健康检查失败，最近日志如下："
  journalctl -u "${APP_NAME}.service" -n 160 --no-pager || true
  exit 1
fi

echo "迁移导入完成。"
echo "导入前数据库备份：${BACKUP_DIR}/${APP_NAME}-before-import-${STAMP}.dump"
echo "请登录管理员、教师、学生、家长入口执行 smoke test。"
