<#
.SYNOPSIS
Run the repository's safe Windows text-inspection workflow before editing.

.DESCRIPTION
This helper codifies the repository rule for multilingual or encoding-sensitive
files on Windows PowerShell:

1. Enter a UTF-8-oriented session.
2. Inspect the file through safe_show_text.py.
3. Verify the file with check_text_encoding.py.
4. Only then edit with patch-based changes or a deliberate full-file write.

The script does not edit repository files. It prepares the shell, shows the
selected file through UTF-8-safe tooling, and runs the encoding check for that
path. Use it before touching Chinese UI copy, mixed-language Markdown, or any
file whose console rendering may be suspicious.

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ops\scripts\windows\enter-safe-text-session.ps1 `
  -Path apps\web\school\src\views\Layout.vue -StartLine 1 -EndLine 120

.EXAMPLE
. .\ops\scripts\windows\enter-safe-text-session.ps1 -Path docs\contributing\ENCODING_AND_MOJIBAKE_SAFETY.md -Escape
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [int]$StartLine,
    [int]$EndLine,
    [switch]$Escape,
    [switch]$FailOnSuspicious,
    [switch]$SkipShow,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..\..')
$python = 'python'
$showScript = Join-Path $repoRoot 'ops\scripts\dev\safe_show_text.py'
$checkScript = Join-Path $repoRoot 'ops\scripts\dev\check_text_encoding.py'
$utf8Script = Join-Path $PSScriptRoot 'set-utf8-session.ps1'

if ($env:COURSEEVAL_SAFE_TEXT_SESSION -ne '1') {
    . $utf8Script -Quiet
    $env:COURSEEVAL_SAFE_TEXT_SESSION = '1'
    if (-not $Quiet) {
        Write-Warning 'safe-text-workflow.ps1 was run directly. Prefer enter-safe-text-session.ps1 as the default Windows text-workflow entrypoint.'
    }
}

$candidatePath = $Path
if (-not [System.IO.Path]::IsPathRooted($candidatePath)) {
    $candidatePath = Join-Path $repoRoot $candidatePath
}

$resolvedPath = Resolve-Path -LiteralPath $candidatePath
$repoRootWithSlash = ($repoRoot.Path.TrimEnd('\') + '\')
$resolvedFullPath = $resolvedPath.Path
if ($resolvedFullPath.StartsWith($repoRootWithSlash, [System.StringComparison]::OrdinalIgnoreCase)) {
    $repoRelativePath = $resolvedFullPath.Substring($repoRootWithSlash.Length)
} else {
    $repoRelativePath = $resolvedFullPath
}

if (-not $Quiet) {
    Write-Output 'PowerShell safe-text rule:'
    Write-Output '1. Keep this shell in UTF-8 mode.'
    Write-Output '2. Inspect multilingual text only through safe_show_text.py.'
    Write-Output '3. Run check_text_encoding.py on the exact file before editing.'
    Write-Output '4. Edit tracked source with patch-based changes; use safe_write_text.py only for intentional full-file writes.'
    Write-Output ''
    Write-Output "Target: $repoRelativePath"
}

if (-not $SkipShow) {
    $showArgs = @($showScript, $repoRelativePath)
    if ($PSBoundParameters.ContainsKey('StartLine')) {
        $showArgs += @('--start-line', $StartLine)
    }
    if ($PSBoundParameters.ContainsKey('EndLine')) {
        $showArgs += @('--end-line', $EndLine)
    }
    if ($Escape) {
        $showArgs += '--escape'
    }

    if (-not $Quiet) {
        Write-Output ''
        Write-Output '== Safe file view =='
    }
    & $python @showArgs
}

$checkArgs = @($checkScript, $repoRelativePath)
if ($FailOnSuspicious) {
    $checkArgs += '--fail-on-suspicious'
}

if (-not $Quiet) {
    Write-Output ''
    Write-Output '== Encoding check =='
}
& $python @checkArgs
