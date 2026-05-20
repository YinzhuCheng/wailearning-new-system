param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $SupervisorArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$scriptPath = Join-Path $repoRoot "ops\scripts\dev\wai_valid_supervisor.py"
$stateDir = Join-Path $repoRoot ".agent-run\validation-daemon"
$launchLog = Join-Path $stateDir "WAI-VALID-supervisor-launch.log"

if (-not (Test-Path $pythonExe)) {
    throw "Missing repository venv interpreter: $pythonExe"
}

if (-not (Test-Path $scriptPath)) {
    throw "Missing supervisor script: $scriptPath"
}

$argumentList = @($scriptPath) + $SupervisorArgs
$processArgs = @('-u') + $argumentList
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
Add-Content -Path $launchLog -Value ("START " + (Get-Date -Format o) + " python=" + $pythonExe)
Add-Content -Path $launchLog -Value ("ARGS  " + ($processArgs -join " "))

try {
    $proc = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList $processArgs `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -PassThru
    Set-Content -Path (Join-Path $stateDir "WAI-VALID-supervisor-detached.pid") -Value $proc.Id -Encoding UTF8
    Add-Content -Path $launchLog -Value ("PID   " + $proc.Id)
} catch {
    Add-Content -Path $launchLog -Value ("ERROR " + ($_ | Out-String))
    throw
}
