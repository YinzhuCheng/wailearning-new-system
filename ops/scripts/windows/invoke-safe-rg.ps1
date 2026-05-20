<#
.SYNOPSIS
Run ripgrep inside the repository safe-text Windows PowerShell wrapper.

.DESCRIPTION
Use this instead of complex inline `rg` one-liners when the pattern contains
PowerShell-sensitive characters such as pipes, quotes, brackets, or backslashes.
The wrapper keeps quoting stable by building the ripgrep command inside the
safe-text child process instead of asking the parent shell to parse it.

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-rg.ps1 -Pattern "retry_scheduled|processing"

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-rg.ps1 `
  -Pattern "claim_grading_tasks_batch\\(" `
  -Paths "apps/backend/courseeval_backend/llm_grading.py","tests"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Pattern,
    [string[]]$Paths,
    [switch]$FixedStrings,
    [switch]$IgnoreCase,
    [switch]$WordRegexp
)

$ErrorActionPreference = 'Stop'

function ConvertTo-SingleQuotedLiteral {
    param([Parameter(Mandatory = $true)][string]$Text)
    return "'" + $Text.Replace("'", "''") + "'"
}

function Expand-ListArg {
    param([string[]]$Items)
    $expanded = @()
    foreach ($item in ($Items | Where-Object { $_ })) {
        $parts = @($item -split ',')
        foreach ($part in $parts) {
            $trimmed = $part.Trim()
            if ($trimmed) {
                $expanded += $trimmed
            }
        }
    }
    return $expanded
}

$commandParts = @('rg', '--line-number', '--color', 'never')
if ($FixedStrings) {
    $commandParts += '--fixed-strings'
}
if ($IgnoreCase) {
    $commandParts += '--ignore-case'
}
if ($WordRegexp) {
    $commandParts += '--word-regexp'
}
$commandParts += '--'
$commandParts += (ConvertTo-SingleQuotedLiteral $Pattern)
foreach ($path in (Expand-ListArg $Paths)) {
    $commandParts += (ConvertTo-SingleQuotedLiteral $path)
}

$repoCommand = $commandParts -join ' '
$wrapper = Join-Path $PSScriptRoot 'invoke-safe-text-command.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper -Command $repoCommand
exit $LASTEXITCODE
