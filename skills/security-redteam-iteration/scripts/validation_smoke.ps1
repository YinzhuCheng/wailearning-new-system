$ErrorActionPreference = "Stop"

$RepoRoot = (git rev-parse --show-toplevel).Trim()
Set-Location $RepoRoot

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

& $Python -m json.tool tests\TEST_SELECTION_TARGETS.json | Out-Null
& $Python ops\scripts\dev\lint_validation_registry.py
& $Python ops\scripts\dev\check_api_surface_governance.py
& $Python ops\scripts\dev\check_repository_normalization.py

$changed = & $Python skills\security-redteam-iteration\scripts\changed_text_files.py
if ($changed.Count -gt 0) {
  & $Python ops\scripts\dev\check_text_encoding.py --skip-if-empty @changed
} else {
  Write-Host "No changed text files for encoding scan."
}

& $Python ops\scripts\dev\select_validation_targets.py --worktree --json
git diff --check
