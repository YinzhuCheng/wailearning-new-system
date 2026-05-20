#!/usr/bin/env bash
# Full stack: backend venv + school SPA (npm run build) + parent portal + nginx reload.
# If the school UI looks outdated, common causes are: (1) this script was not run to completion,
# (2) deploy ran from the wrong REPO_DIR / branch (SKIP_GIT=1 on stale tree), or (3) browser cache.
# Prefer ops/scripts/redeploy.sh from the server clone so Git + deploy_all stay aligned.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

for script in deploy_backend.sh deploy_frontend.sh deploy_parent_portal.sh; do
  echo "==> Running ${script}"
  bash "${SCRIPT_DIR}/${script}"
done

echo "==> Deployment finished (admin static files updated under /var/www/.../admin if deploy_frontend succeeded)."
echo "Run bash ${SCRIPT_DIR}/post_deploy_check.sh to verify the stack."
