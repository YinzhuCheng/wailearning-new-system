<#
.SYNOPSIS
Enter the repository's default safe Windows text workflow for multilingual files.

.DESCRIPTION
This is the higher-level entrypoint for Windows PowerShell text work in this
repository. It applies UTF-8-oriented console settings and, when a target path
is provided, routes through the safe multilingual inspection workflow before
editing.

Use this instead of calling set-utf8-session.ps1 directly when the session is
about to inspect or edit repository files that may contain non-ASCII text.

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\enter-safe-text-session.ps1

.EXAMPLE
. .\ops\scripts\windows\enter-safe-text-session.ps1 -Path apps\web\school\src\views\Layout.vue -StartLine 1 -EndLine 120
#>

[CmdletBinding()]
param(
    [string]$Path,
    [int]$StartLine,
    [int]$EndLine,
    [switch]$Escape,
    [switch]$FailOnSuspicious,
    [switch]$SkipShow,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

$setUtf8Script = Join-Path $PSScriptRoot 'set-utf8-session.ps1'
$safeWorkflowScript = Join-Path $PSScriptRoot 'safe-text-workflow.ps1'

. $setUtf8Script -Quiet:$Quiet
$env:COURSEEVAL_SAFE_TEXT_SESSION = '1'

if (-not $Quiet) {
    Write-Output 'Safe text session entered.'
    Write-Output 'Use this shell for multilingual repository inspection and patch-based edits.'
}

if ($PSBoundParameters.ContainsKey('Path')) {
    $safeWorkflowArgs = @{
        Path = $Path
    }
    if ($PSBoundParameters.ContainsKey('StartLine')) {
        $safeWorkflowArgs.StartLine = $StartLine
    }
    if ($PSBoundParameters.ContainsKey('EndLine')) {
        $safeWorkflowArgs.EndLine = $EndLine
    }
    if ($Escape) {
        $safeWorkflowArgs.Escape = $true
    }
    if ($FailOnSuspicious) {
        $safeWorkflowArgs.FailOnSuspicious = $true
    }
    if ($SkipShow) {
        $safeWorkflowArgs.SkipShow = $true
    }
    if ($Quiet) {
        $safeWorkflowArgs.Quiet = $true
    }

    & $safeWorkflowScript @safeWorkflowArgs
} elseif (-not $Quiet) {
    Write-Output 'No target path supplied. UTF-8 session is ready.'
    Write-Output 'When inspecting a multilingual file, rerun this script with -Path <repo-relative-path>.'
}
