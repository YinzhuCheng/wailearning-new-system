<#
.SYNOPSIS
Run pytest inside the repository safe-text Windows PowerShell wrapper.

.DESCRIPTION
Use this instead of long inline pytest commands in Windows PowerShell when the
test target list is long or when additional quoting would otherwise be fragile.

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-pytest.ps1 `
  -Targets "tests/backend/llm/test_llm_group_routing.py" -PytestArgs "-q"

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-pytest.ps1 `
  -Targets "tests/behavior/test_discussion_llm_retry_behavior.py","tests/backend/homework/test_llm_retry_scheduler.py" `
  -PytestArgs "-q","-k","retry"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Targets,
    [string[]]$PytestArgs
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

$pythonExe = '.\.venv\Scripts\python.exe'
$commandParts = @('&', (ConvertTo-SingleQuotedLiteral $pythonExe), '-m', 'pytest')
foreach ($arg in (Expand-ListArg $PytestArgs)) {
    $commandParts += (ConvertTo-SingleQuotedLiteral $arg)
}
foreach ($target in (Expand-ListArg $Targets)) {
    $commandParts += (ConvertTo-SingleQuotedLiteral $target)
}

$repoCommand = $commandParts -join ' '
$wrapper = Join-Path $PSScriptRoot 'invoke-safe-text-command.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wrapper -Command $repoCommand
exit $LASTEXITCODE
