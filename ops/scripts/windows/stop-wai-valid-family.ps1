param(
    [string] $ProcessTag = "",
    [switch] $DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$stateDir = Join-Path $repoRoot ".agent-run\validation-daemon"

function Invoke-TaskKillTree {
    param(
        [Parameter(Mandatory = $true)]
        [int] $TargetPid,
        [switch] $DryRun
    )

    if ($DryRun) {
        Write-Output "DRY-RUN taskkill /PID $TargetPid /T /F"
        return
    }

    & "$env:SystemRoot\System32\taskkill.exe" /PID $TargetPid /T /F | Out-Null
    Write-Output "Stopped tree PID=$TargetPid"
}

function Test-LiveTrackedProcess {
    param(
        [int] $TargetPid
    )

    if ($TargetPid -le 0) {
        return $false
    }

    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $TargetPid" -ErrorAction Stop
    } catch {
        return $false
    }

    if (-not $proc) {
        return $false
    }

    return Get-WaiValidMarkerMatch -CommandLine $proc.CommandLine -ProcessTag $ProcessTag
}

function Get-TrackedPidFiles {
    @(
        "WAI-VALID-supervisor.pid",
        "WAI-VALID-supervisor-detached.pid",
        "WAI-VALID-monitor.pid",
        "WAI-VALID-monitor-shell.pid"
    ) | ForEach-Object {
        Join-Path $stateDir $_
    }
}

function Get-WaiValidMarkerMatch {
    param(
        [string] $CommandLine,
        [string] $ProcessTag
    )

    if (-not $CommandLine) {
        return $false
    }

    $markers = @(
        "wai_valid_supervisor.py",
        "wai_valid_monitor.py",
        "wai_valid_pytest_worker.py",
        "start-validation-supervisor-detached.ps1",
        "start-validation-monitor.bat",
        "playwright-external-runner.cjs",
        "\vite.js",
        "apps.backend.courseeval_backend.main:app",
        "WAI-VALID-"
    )

    $hasMarker = $false
    foreach ($marker in $markers) {
        if ($CommandLine -like "*$marker*") {
            $hasMarker = $true
            break
        }
    }
    if (-not $hasMarker) {
        return $false
    }

    if ($CommandLine -notlike "*$repoRoot*") {
        return $false
    }

    if ($ProcessTag -and $CommandLine -notlike "*$ProcessTag*") {
        return $false
    }

    return $true
}

$pidCandidates = New-Object System.Collections.Generic.HashSet[int]

foreach ($pidFile in Get-TrackedPidFiles) {
    if (Test-Path $pidFile) {
        $raw = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($raw -match '^\d+$') {
            $trackedPid = [int]$raw
            if (Test-LiveTrackedProcess -TargetPid $trackedPid) {
                [void]$pidCandidates.Add($trackedPid)
            }
        }
    }
}

try {
    $processes = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^(python|py|powershell|pwsh|node)\.exe$'
    }
} catch {
    Write-Output "Could not enumerate process command lines via Win32_Process: $($_.Exception.Message)"
    $processes = @()
}

foreach ($proc in $processes) {
    if (Get-WaiValidMarkerMatch -CommandLine $proc.CommandLine -ProcessTag $ProcessTag) {
        [void]$pidCandidates.Add([int]$proc.ProcessId)
    }
}

if ($pidCandidates.Count -eq 0) {
    Write-Output "No WAI-VALID family processes matched."
    exit 0
}

foreach ($targetPid in ($pidCandidates | Sort-Object)) {
    Invoke-TaskKillTree -TargetPid $targetPid -DryRun:$DryRun
}
