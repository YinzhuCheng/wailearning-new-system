#!/usr/bin/env bash
# Server-side Git sync helpers (sourced by redeploy.sh / pull_and_deploy.sh).
# See docs/DEPLOYMENT_AND_OPERATIONS.md — explicit refspec fetch so refs/remotes/<remote>/<branch> exists.

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "This file is meant to be sourced from other scripts, not executed directly." >&2
  exit 1
fi

# Args: remote_name branch_name reset_worktree(0|1) backup_dir git_final_clean(0|1)
# When reset_worktree=1: save git diff to backup_dir, then reset --hard and clean -ffd before fetch.
# Env: GIT_AUTO_STASH_ON_CHECKOUT_CONFLICT (default 1) — if checkout -B fails because local changes
#       would be overwritten, backup patch + git stash -u and retry once.
__dd_git_sync_to_remote_branch() {
  local git_remote="$1"
  local branch="$2"
  local reset_worktree="${3:-0}"
  local backup_dir="${4:-/opt/courseeval/backups}"
  local git_final_clean="${5:-1}"
  local auto_stash="${GIT_AUTO_STASH_ON_CHECKOUT_CONFLICT:-1}"

  if [[ "${reset_worktree}" == "1" ]]; then
    mkdir -p "${backup_dir}"
    local stamp
    stamp="$(date +%F-%H%M%S)"
    echo "==> Git: backup local diff -> ${backup_dir}/source-working-tree-${stamp}.patch (if any)"
    git diff >"${backup_dir}/source-working-tree-${stamp}.patch" || true
    echo "==> Git: reset --hard + clean -ffd (discard local commits/changes to tracked files)"
    git reset --hard
    git clean -ffd
  fi

  echo "==> Git: ls-remote + fetch explicit refspec refs/heads/${branch} -> refs/remotes/${git_remote}/${branch}"
  git ls-remote --exit-code --heads "${git_remote}" "${branch}" >/dev/null
  git fetch "${git_remote}" "refs/heads/${branch}:refs/remotes/${git_remote}/${branch}"

  __dd_git_checkout_and_reset() {
    local gr="$1" br="$2" bdir="$3" ast="$4"
    local co_err
    co_err="$(mktemp)"
    if git checkout -B "${br}" "${gr}/${br}" 2>"${co_err}"; then
      rm -f "${co_err}"
      git reset --hard "${gr}/${br}"
      return 0
    fi
    if [[ "${ast}" == "1" ]] && grep -qE 'would be overwritten|local changes' "${co_err}"; then
      echo "==> Git: checkout 被未提交/未跟踪文件阻止，备份 patch 并 stash -u 后重试（可设 GIT_AUTO_STASH_ON_CHECKOUT_CONFLICT=0 关闭）" >&2
      mkdir -p "${bdir}"
      local stamp
      stamp="$(date +%F-%H%M%S)"
      git diff >"${bdir}/checkout-conflict-${stamp}.patch" || true
      git stash push -u -m "deploy-auto-stash-${stamp}" >/dev/null 2>&1 || true
      rm -f "${co_err}"
      git checkout -B "${br}" "${gr}/${br}"
      git reset --hard "${gr}/${br}"
      return 0
    fi
    cat "${co_err}" >&2
    rm -f "${co_err}"
    return 1
  }

  echo "==> Git: checkout -B ${branch} + reset --hard ${git_remote}/${branch}"
  __dd_git_checkout_and_reset "${git_remote}" "${branch}" "${backup_dir}" "${auto_stash}"
  if [[ -f .gitmodules ]]; then
    git submodule sync --recursive
    git submodule update --init --recursive
  fi
  if [[ "${git_final_clean}" == "1" ]]; then
    git clean -ffd
  fi
}
