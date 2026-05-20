param(
    [string] $RunId = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$stateDir = Join-Path $repoRoot ".agent-run\validation-daemon"
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$monitorPy = Join-Path $repoRoot "ops\scripts\dev\wai_valid_monitor.py"
$registerPy = Join-Path $repoRoot "ops\scripts\dev\wai_valid_register_current_run.py"
$shellPidPath = Join-Path $stateDir "WAI-VALID-monitor-shell.pid"
$monitorPidPath = Join-Path $stateDir "WAI-VALID-monitor.pid"
$readyPath = Join-Path $stateDir "WAI-VALID-monitor-ready.json"
$heartbeatPath = Join-Path $stateDir "WAI-VALID-monitor-heartbeat.json"
$currentRunFile = Join-Path $stateDir "WAI-VALID-current-run.json"

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

if (Test-Path $shellPidPath) {
    $rawPid = (Get-Content -LiteralPath $shellPidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($rawPid -match '^\d+$') {
        try {
            Stop-Process -Id ([int]$rawPid) -Force -ErrorAction Stop
        } catch {
        }
    }
}

if (Test-Path $monitorPidPath) {
    $rawPid = (Get-Content -LiteralPath $monitorPidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($rawPid -match '^\d+$') {
        try {
            Stop-Process -Id ([int]$rawPid) -Force -ErrorAction Stop
        } catch {
        }
    }
}

foreach ($statusPath in @($readyPath, $heartbeatPath)) {
    if (Test-Path $statusPath) {
        Remove-Item -LiteralPath $statusPath -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path $pythonExe)) {
    throw "Missing repository venv interpreter: $pythonExe"
}

if (-not (Test-Path $monitorPy)) {
    throw "Missing monitor script: $monitorPy"
}

function ConvertTo-WaiValidRunName {
    param([string] $InputRunId)
    if ($InputRunId.StartsWith("WAI-VALID-")) {
        return $InputRunId
    }
    return "WAI-VALID-$InputRunId"
}

function Write-PendingCurrentRun {
    param([string] $InputRunId)
    $runName = ConvertTo-WaiValidRunName $InputRunId
    $runDir = Join-Path $repoRoot ".agent-run\logs\$runName"
    $payload = [ordered]@{
        run_id = $runName
        progress_file = (Join-Path $runDir "progress.json")
        events_file = (Join-Path $runDir "events.log")
        mode = "visible-monitor-pending"
    }
    $payload | ConvertTo-Json -Depth 4 | Set-Content -Path $currentRunFile -Encoding UTF8
}

if ($RunId) {
    & $pythonExe $registerPy --run-id $RunId | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-PendingCurrentRun $RunId
    }
} else {
    & $pythonExe $registerPy | Out-Null
}

$psExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$wrapperPath = Join-Path $stateDir "WAI-VALID-launch-monitor-runtime.ps1"
$processTag = ConvertTo-WaiValidRunName $RunId
$monitorTitle = if ($RunId) { "WAI-VALID-monitor:$processTag" } else { "WAI-VALID-monitor:auto" }
$monitorTitleLiteral = $monitorTitle.Replace("'", "''")
$wrapperBody = if ($RunId) {
@"
`$Host.UI.RawUI.WindowTitle = '$monitorTitleLiteral'
& '$pythonExe' -u '$monitorPy' --run-id '$RunId' --process-tag '$processTag'
`$monitorExitCode = `$LASTEXITCODE
`$Host.UI.RawUI.WindowTitle = '$monitorTitleLiteral finished exit=' + `$monitorExitCode
Write-Host "[WAI-VALID] monitor python exited with code `$monitorExitCode. This PowerShell shell remains open by design for final-state visibility."
exit `$monitorExitCode
"@
} else {
@"
`$Host.UI.RawUI.WindowTitle = '$monitorTitleLiteral'
& '$pythonExe' -u '$monitorPy'
`$monitorExitCode = `$LASTEXITCODE
`$Host.UI.RawUI.WindowTitle = '$monitorTitleLiteral finished exit=' + `$monitorExitCode
Write-Host "[WAI-VALID] monitor python exited with code `$monitorExitCode. This PowerShell shell remains open by design for final-state visibility."
exit `$monitorExitCode
"@
}
Set-Content -Path $wrapperPath -Value $wrapperBody -Encoding UTF8

$monitorArgs = @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapperPath)

$proc = Start-Process `
    -FilePath $psExe `
    -ArgumentList $monitorArgs `
    -WorkingDirectory $repoRoot `
    -WindowStyle Normal `
    -PassThru

Set-Content -Path $shellPidPath -Value $proc.Id -Encoding UTF8

$ready = $false
for ($i = 0; $i -lt 25; $i++) {
    Start-Sleep -Milliseconds 200
    if (Test-Path $readyPath) {
        $ready = $true
        break
    }
    try {
        Get-Process -Id $proc.Id -ErrorAction Stop | Out-Null
    } catch {
        break
    }
}

if (-not $ready) {
    throw "Monitor window started but did not publish ready status."
}

Write-Output $proc.Id
