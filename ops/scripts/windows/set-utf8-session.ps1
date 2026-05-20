<#
.SYNOPSIS
Configure the current Windows PowerShell session for UTF-8-oriented output.

.DESCRIPTION
This helper reduces mojibake risk when agents inspect multilingual repository
files from Windows PowerShell. It changes only the current console process and
environment variables inherited by child processes launched from that process.

It does not rewrite repository files and does not make terminal-rendered
Chinese text authoritative. Continue to verify sensitive text through git diff
or ops/scripts/dev/safe_show_text.py.

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\set-utf8-session.ps1

.EXAMPLE
. .\ops\scripts\windows\set-utf8-session.ps1
#>

[CmdletBinding()]
param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

try {
    & chcp.com 65001 | Out-Null
} catch {
    if (-not $Quiet) {
        Write-Warning "Unable to set console code page with chcp.com: $($_.Exception.Message)"
    }
}

[Console]::OutputEncoding = $utf8NoBom
[Console]::InputEncoding = $utf8NoBom
$global:OutputEncoding = $utf8NoBom

$env:COURSEEVAL_SAFE_TEXT_SESSION = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:LESSCHARSET = 'utf-8'

if (-not $Quiet) {
    Write-Output 'UTF-8 session settings applied.'
    Write-Output "COURSEEVAL_SAFE_TEXT_SESSION=$env:COURSEEVAL_SAFE_TEXT_SESSION"
    Write-Output "Console.OutputEncoding=$([Console]::OutputEncoding.WebName)"
    Write-Output "Console.InputEncoding=$([Console]::InputEncoding.WebName)"
    Write-Output "PYTHONUTF8=$env:PYTHONUTF8"
    Write-Output "PYTHONIOENCODING=$env:PYTHONIOENCODING"
}
