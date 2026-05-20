<#
.SYNOPSIS
Invoke repository work inside a child Windows PowerShell safe-text session.

.DESCRIPTION
This wrapper is the default Windows PowerShell entrypoint for repository work
that may inspect or edit multilingual or encoding-sensitive files.

It launches a child PowerShell process with `-NoProfile` and
`-ExecutionPolicy Bypass`, enters the repository safe-text session inside that
child process, asserts that the UTF-8-oriented session is active, and can then
run an optional command in the same process.

Use this when the parent PowerShell session may block local script execution or
when agents need one stable command instead of reconstructing the safe-text
subprocess flow ad hoc.

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1 `
  -Path apps\web\school\src\views\Layout.vue -StartLine 1 -EndLine 120

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\invoke-safe-text-command.ps1 `
  -Command "git status --short"
#>

[CmdletBinding()]
param(
    [string]$Path,
    [int]$StartLine,
    [int]$EndLine,
    [switch]$Escape,
    [switch]$FailOnSuspicious,
    [switch]$SkipShow,
    [switch]$Quiet,
    [string]$Command
)

$ErrorActionPreference = 'Stop'

function ConvertTo-SingleQuotedLiteral {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    return "'" + $Text.Replace("'", "''") + "'"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$powershellExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$enterScript = Join-Path $repoRoot 'ops\scripts\windows\enter-safe-text-session.ps1'
$assertScript = Join-Path $repoRoot 'ops\scripts\windows\assert-safe-text-session.ps1'

$enterArgs = @()
if ($PSBoundParameters.ContainsKey('Path')) {
    $enterArgs += "-Path $(ConvertTo-SingleQuotedLiteral $Path)"
}
if ($PSBoundParameters.ContainsKey('StartLine')) {
    $enterArgs += "-StartLine $StartLine"
}
if ($PSBoundParameters.ContainsKey('EndLine')) {
    $enterArgs += "-EndLine $EndLine"
}
if ($Escape) {
    $enterArgs += '-Escape'
}
if ($FailOnSuspicious) {
    $enterArgs += '-FailOnSuspicious'
}
if ($SkipShow) {
    $enterArgs += '-SkipShow'
}
if ($Quiet) {
    $enterArgs += '-Quiet'
}

$innerLines = @(
    '$ErrorActionPreference = ''Stop'''
    '$ProgressPreference = ''SilentlyContinue'''
    "Set-Location -LiteralPath $(ConvertTo-SingleQuotedLiteral $repoRoot)"
    ". $(ConvertTo-SingleQuotedLiteral $enterScript) $($enterArgs -join ' ')"
    "& $(ConvertTo-SingleQuotedLiteral $assertScript)"
)

if ($PSBoundParameters.ContainsKey('Command')) {
    $encodedUserCommand = [System.Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($Command))
    $innerLines += '$global:LASTEXITCODE = 0'
    $innerLines += '$userCommand = [System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String(' + (ConvertTo-SingleQuotedLiteral $encodedUserCommand) + '))'
    $innerLines += '& ([scriptblock]::Create($userCommand))'
    $innerLines += 'if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }'
}

$innerScript = ($innerLines -join "`n") + "`n"
$encodedCommand = [System.Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($innerScript))

& $powershellExe -NoProfile -ExecutionPolicy Bypass -EncodedCommand $encodedCommand
exit $LASTEXITCODE
