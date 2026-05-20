#!/usr/bin/env bash
# 在 ECS 上从 Git 更新代码并执行完整部署（后端 venv + 管理端前端 + 家长端 + Nginx + 重启后端）。
# 用法（需 root）：
#   sudo bash /path/to/repo/scripts/redeploy.sh
# 可选环境变量：
#   REPO_DIR=/opt/courseeval/source  代码仓库路径（未设置时：若存在 /opt/courseeval/source/.git 则用之，否则为脚本所在仓库根）
#   GIT_BRANCH=main               要检出的分支
#   GIT_REMOTE=origin             远端名称
#   GIT_CLEAN=1                   是否在同步末尾 git clean -ffd（0=跳过，保留未跟踪文件时请慎用）
#   GIT_RESET_WORKTREE_BEFORE_FETCH=0  设为 1 时：先备份 git diff 到 BACKUP_DIR，再 reset --hard + clean -ffd，再 fetch（解决服务器手工改文件导致 checkout 被拒）
#   BACKUP_DIR=/opt/courseeval/backups   GIT_RESET 为 1 时写入 working-tree patch 的目录
#   SKIP_GIT=1                    跳过 git 同步（仅当已在 REPO_DIR 放好目标代码时使用；否则会旧代码重打前端）
#   FRONTEND_ONLY=1               只跑 deploy_frontend.sh（仍会 npm run build 管理端；须保证 REPO_DIR 已是目标版本）
#   APP_URL=https://你的域名       部署后 post_deploy_check 使用的公网健康检查地址
#   DD_DEFAULT_REPO_DIR=/opt/courseeval/source  未设置 REPO_DIR 时的首选 clone 路径（与 docs/DEPLOYMENT_AND_OPERATIONS.md 一致）
#   GIT_AUTO_STASH_ON_CHECKOUT_CONFLICT=1  checkout 因本地改动被拒时自动 patch + stash -u 并重试（0=关闭）
#   SAFE_BACKUP_BEFORE_DEPLOY=0  设为 1 时在 Git 同步前备份 PostgreSQL 与 shared（pg_dump 在 /tmp 下执行，减轻 postgres 无法 cd /root 的告警）
#   DB_NAME=courseeval  SHARED_DIR=/opt/courseeval/shared  与备份路径相关
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "请使用 root 执行：sudo bash $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/lib/deploy_repo_dir.sh
source "${SCRIPT_DIR}/lib/deploy_repo_dir.sh"
__dd_resolve_repo_dir "${SCRIPT_DIR}"
GIT_BRANCH="${GIT_BRANCH:-main}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_CLEAN="${GIT_CLEAN:-1}"
GIT_RESET_WORKTREE_BEFORE_FETCH="${GIT_RESET_WORKTREE_BEFORE_FETCH:-0}"
BACKUP_DIR="${BACKUP_DIR:-/opt/courseeval/backups}"
SKIP_GIT="${SKIP_GIT:-0}"
FRONTEND_ONLY="${FRONTEND_ONLY:-0}"
APP_URL="${APP_URL:-}"
SAFE_BACKUP_BEFORE_DEPLOY="${SAFE_BACKUP_BEFORE_DEPLOY:-0}"
DB_NAME="${DB_NAME:-courseeval}"
SHARED_DIR="${SHARED_DIR:-/opt/courseeval/shared}"

echo "==> 仓库目录: ${REPO_DIR}"
echo "==> 分支: ${GIT_BRANCH}"
if [[ "${SKIP_GIT}" == "1" ]]; then
  echo "==> 警告: SKIP_GIT=1 — 不会拉取远端代码。若 REPO_DIR 不是目标版本，deploy_frontend 只会用旧源码重打包，管理端界面会看似「没更新」。" >&2
fi
if [[ "${FRONTEND_ONLY}" == "1" ]]; then
  echo "==> 提示: FRONTEND_ONLY=1 — 仅部署管理端静态资源，不跑后端/家长端。请确认已用正确分支更新 ${REPO_DIR}。" >&2
fi

if [[ "${SAFE_BACKUP_BEFORE_DEPLOY}" == "1" ]]; then
  install -d -m 0755 "${BACKUP_DIR}"
  local_ts="$(date +%F-%H%M%S)"
  echo "==> SAFE_BACKUP_BEFORE_DEPLOY=1: pg_dump ${DB_NAME} + tar shared -> ${BACKUP_DIR}"
  (cd /tmp && sudo -u postgres pg_dump -Fc "${DB_NAME}" >"${BACKUP_DIR}/${DB_NAME}-${local_ts}.dump")
  if [[ -d "${SHARED_DIR}" ]]; then
    tar -czf "${BACKUP_DIR}/shared-${local_ts}.tar.gz" "${SHARED_DIR}"
  else
    echo "==> 警告: SHARED_DIR=${SHARED_DIR} 不存在，跳过 shared 归档" >&2
  fi
fi

if [[ "${SKIP_GIT}" != "1" ]]; then
  if [[ ! -d "${REPO_DIR}/.git" ]]; then
    echo "错误: ${REPO_DIR} 不是 git 仓库。设置 REPO_DIR 或先 clone，或使用 SKIP_GIT=1。"
    exit 1
  fi
  cd "${REPO_DIR}"
  # shellcheck source=scripts/lib/git_sync_server.sh
  source "${SCRIPT_DIR}/lib/git_sync_server.sh"
  git_final_clean_flag="0"
  if [[ "${GIT_CLEAN}" == "1" ]]; then
    git_final_clean_flag="1"
  else
    echo "==> GIT_CLEAN=0，跳过末尾 git clean"
  fi
  __dd_git_sync_to_remote_branch \
    "${GIT_REMOTE}" \
    "${GIT_BRANCH}" \
    "${GIT_RESET_WORKTREE_BEFORE_FETCH}" \
    "${BACKUP_DIR}" \
    "${git_final_clean_flag}"
else
  echo "==> 已 SKIP_GIT=1，跳过 git 更新"
fi

cd "${REPO_DIR}"
if [[ -d .git ]]; then
  echo "==> 当前用于构建/部署的提交: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
fi

if [[ "${FRONTEND_ONLY}" == "1" ]]; then
  echo "==> FRONTEND_ONLY=1，仅部署管理端前端"
  bash "${SCRIPT_DIR}/deploy_frontend.sh"
else
  echo "==> 完整部署（后端 + 管理端 + 家长端）"
  bash "${SCRIPT_DIR}/deploy_all.sh"
fi

if [[ -n "${APP_URL}" ]]; then
  echo "==> 公网检查 APP_URL=${APP_URL}"
  APP_URL="${APP_URL}" bash "${SCRIPT_DIR}/post_deploy_check.sh"
else
  echo "==> 仅本机健康检查（未设置 APP_URL 则跳过公网 /health）"
  API_HEALTH_URL="http://127.0.0.1:8001/health" bash "${SCRIPT_DIR}/post_deploy_check.sh"
fi

echo "==> 重新部署完成。"
