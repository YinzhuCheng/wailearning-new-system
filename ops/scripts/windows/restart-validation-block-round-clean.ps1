param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "static-and-build",
        "backend-sqlite-compatible",
        "behavior",
        "security",
        "backend-postgres-sensitive",
        "playwright-school-e2e"
    )]
    [string] $BlockName,

    [Parameter(Mandatory = $true)]
    [string] $RunId,

    [int] $MaxRuntimeSeconds = 10800,
    [int] $Concurrency = 10,
    [ValidateSet("light", "medium", "heavy")]
    [string] $RegressionMode = "light",
    [int] $StartupTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$stateDir = Join-Path $repoRoot ".agent-run\validation-daemon"
$logsRoot = Join-Path $repoRoot ".agent-run\logs"
$runName = if ($RunId.StartsWith("WAI-VALID-")) { $RunId } else { "WAI-VALID-$RunId" }
$runDir = Join-Path $logsRoot $runName

function Remove-TrackedFile {
    param([string] $Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    }
}

function Stop-RecordedPidTree {
    param(
        [string] $PidPath,
        [string] $Label
    )
    if (-not (Test-Path $PidPath)) {
        return
    }
    $rawPid = (Get-Content -LiteralPath $PidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($rawPid -notmatch '^\d+$') {
        return
    }
    try {
        & "$env:SystemRoot\System32\taskkill.exe" /PID ([int]$rawPid) /T /F 2>$null | Out-Null
        Write-Output "Stopped $Label tree PID=$rawPid"
    } catch {
        Write-Output "Could not stop $Label tree PID=$rawPid :: $($_.Exception.Message)"
    }
}

function Stop-RecordedRunPids {
    $pidSet = New-Object System.Collections.Generic.HashSet[int]

    foreach ($pidPath in @(
        (Join-Path $stateDir "WAI-VALID-supervisor.pid"),
        (Join-Path $stateDir "WAI-VALID-supervisor-detached.pid"),
        (Join-Path $stateDir "WAI-VALID-monitor.pid"),
        (Join-Path $stateDir "WAI-VALID-monitor-shell.pid")
    )) {
        if (Test-Path $pidPath) {
            $rawPid = (Get-Content -LiteralPath $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
            if ($rawPid -match '^\d+$') {
                [void]$pidSet.Add([int]$rawPid)
            }
        }
    }

    foreach ($progressPath in @(
        (Join-Path $runDir "progress.json"),
        (Join-Path $stateDir "WAI-VALID-state.json")
    )) {
        if (-not (Test-Path $progressPath)) {
            continue
        }
        try {
            $payload = Get-Content -LiteralPath $progressPath -Raw | ConvertFrom-Json
        } catch {
            continue
        }
        if ($payload.pid) {
            [void]$pidSet.Add([int]$payload.pid)
        }
        foreach ($slot in @($payload.running_slots)) {
            if ($slot.pid) {
                [void]$pidSet.Add([int]$slot.pid)
            }
        }
        $blocks = $payload.report.blocks
        if ($blocks) {
            foreach ($property in $blocks.PSObject.Properties) {
                foreach ($slot in @($property.Value.running_slots)) {
                    if ($slot.pid) {
                        [void]$pidSet.Add([int]$slot.pid)
                    }
                }
            }
        }
    }

    foreach ($targetPid in ($pidSet | Sort-Object -Descending)) {
        try {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $targetPid /T /F 2>$null | Out-Null
            Write-Output "Stopped recorded WAI-VALID tree PID=$targetPid"
        } catch {
            Write-Output "Recorded PID already gone or not stoppable: $targetPid"
        }
    }
}

function Assert-FreshLaunch {
    param(
        [datetime] $LaunchStartedAt
    )

    $progressPath = Join-Path $runDir "progress.json"
    $readyPath = Join-Path $stateDir "WAI-VALID-monitor-ready.json"
    $heartbeatPath = Join-Path $stateDir "WAI-VALID-monitor-heartbeat.json"
    $currentRunPath = Join-Path $stateDir "WAI-VALID-current-run.json"
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    $seenProgress = $false
    $seenCurrentRun = $false
    $seenReady = $false
    $seenHeartbeat = $false
    $lastProgressUpdatedAt = ""
    $lastHeartbeatProgressUpdatedAt = ""

    while ((Get-Date) -lt $deadline) {
        if (Test-Path $progressPath) {
            try {
                $progress = Get-Content -LiteralPath $progressPath -Raw | ConvertFrom-Json
                $progressMtime = (Get-Item -LiteralPath $progressPath).LastWriteTime
                if ($progress.run_id -eq $runName -and $progressMtime -ge $LaunchStartedAt) {
                    $seenProgress = $true
                    $lastProgressUpdatedAt = [string]$progress.updated_at
                }
            } catch {
            }
        }

        if (Test-Path $currentRunPath) {
            try {
                $currentRun = Get-Content -LiteralPath $currentRunPath -Raw | ConvertFrom-Json
                if ($currentRun.run_id -eq $runName) {
                    $seenCurrentRun = $true
                }
            } catch {
            }
        }

        if (Test-Path $readyPath) {
            try {
                $ready = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
                if ($ready.run_id -eq $runName -and $ready.phase -in @("running", "starting")) {
                    $seenReady = $true
                }
            } catch {
            }
        }

        if (Test-Path $heartbeatPath) {
            try {
                $heartbeat = Get-Content -LiteralPath $heartbeatPath -Raw | ConvertFrom-Json
                $lastHeartbeatProgressUpdatedAt = [string]$heartbeat.progress_updated_at
                if (
                    $heartbeat.run_id -eq $runName `
                    -and $heartbeat.rendered -eq $true `
                    -and $heartbeat.progress_file -eq $progressPath `
                    -and $lastProgressUpdatedAt `
                    -and $heartbeat.progress_updated_at -eq $lastProgressUpdatedAt
                ) {
                    $seenHeartbeat = $true
                }
            } catch {
            }
        }

        if ($seenProgress -and $seenCurrentRun -and $seenReady -and $seenHeartbeat) {
            Write-Output "Fresh launch verified for $runName progress_updated_at=$lastProgressUpdatedAt"
            return
        }
        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for fresh progress/current-run/monitor heartbeat for $runName. seenProgress=$seenProgress seenCurrentRun=$seenCurrentRun seenReady=$seenReady seenHeartbeat=$seenHeartbeat progress_updated_at=$lastProgressUpdatedAt heartbeat_progress_updated_at=$lastHeartbeatProgressUpdatedAt"
}

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
New-Item -ItemType Directory -Force -Path $logsRoot | Out-Null

$processTag = $runName
& (Join-Path $PSScriptRoot "stop-wai-valid-family.ps1") $processTag
Stop-RecordedRunPids

if (Test-Path $runDir) {
    Remove-Item -LiteralPath $runDir -Recurse -Force
    Write-Output "Removed stale run dir: $runDir"
}

foreach ($path in @(
    (Join-Path $stateDir "WAI-VALID-current-run.json"),
    (Join-Path $stateDir "WAI-VALID-monitor-ready.json"),
    (Join-Path $stateDir "WAI-VALID-monitor-heartbeat.json"),
    (Join-Path $stateDir "WAI-VALID-monitor.pid"),
    (Join-Path $stateDir "WAI-VALID-monitor-shell.pid"),
    (Join-Path $stateDir "WAI-VALID-supervisor.pid"),
    (Join-Path $stateDir "WAI-VALID-supervisor-detached.pid"),
    (Join-Path $stateDir "WAI-VALID-state.json"),
    (Join-Path $stateDir "WAI-VALID-queue.json")
)) {
    Remove-TrackedFile $path
}

$launchStartedAt = Get-Date
& (Join-Path $PSScriptRoot "start-validation-block-round.bat") $BlockName $RunId $MaxRuntimeSeconds $Concurrency $RegressionMode
if ($LASTEXITCODE -ne 0) {
    throw "start-validation-block-round.bat failed with exit code $LASTEXITCODE"
}

Assert-FreshLaunch -LaunchStartedAt $launchStartedAt
