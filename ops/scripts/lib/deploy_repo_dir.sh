#!/usr/bin/env bash
# Resolve REPO_DIR for server deploy scripts (redeploy.sh, pull_and_deploy.sh).
# Prefer production path /opt/courseeval/source when it is a git clone; avoid silent
# use of legacy /root/courseeval when that tree is missing or empty.

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "This file is meant to be sourced from other scripts, not executed directly." >&2
  exit 1
fi

# Override preferred clone path (default matches docs/DEPLOYMENT_AND_OPERATIONS.md).
: "${DD_DEFAULT_REPO_DIR:=/opt/courseeval/source}"

# Args: SCRIPT_DIR (directory containing ops/scripts/, i.e. .../repo/ops/scripts)
__dd_resolve_repo_dir() {
  local script_dir="$1"
  local fallback_parent
  fallback_parent="$(cd "${script_dir}/../.." && pwd -P)"
  local preferred="${DD_DEFAULT_REPO_DIR}"

  if [[ -n "${REPO_DIR:-}" ]]; then
    if [[ "${REPO_DIR}" == "/root/courseeval" ]] && [[ ! -d "${REPO_DIR}/.git" ]] && [[ -d "${preferred}/.git" ]]; then
      echo "==> 警告: REPO_DIR=/root/courseeval 不是有效 git 仓库，已自动改用 ${preferred}" >&2
      REPO_DIR="${preferred}"
      return
    fi
    if [[ "${REPO_DIR}" == "/root/courseeval" ]] && [[ -d "${preferred}/.git" ]]; then
      echo "==> 提示: 正在使用 REPO_DIR=/root/courseeval。若与文档中的 ${preferred} 不一致，可能导致「已 redeploy 但界面仍是旧版」。请核对实际 clone 路径。" >&2
    fi
    return
  fi

  if [[ -d "${preferred}/.git" ]]; then
    REPO_DIR="${preferred}"
    echo "==> 未设置 REPO_DIR，使用默认生产路径: ${REPO_DIR}" >&2
  else
    REPO_DIR="${fallback_parent}"
    echo "==> 未设置 REPO_DIR 且 ${preferred} 非 git 仓库，使用脚本所在仓库: ${REPO_DIR}" >&2
  fi
}
