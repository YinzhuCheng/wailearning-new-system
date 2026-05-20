param(
    [Parameter(Mandatory = $true)]
    [string] $ProcessTag
)

$ErrorActionPreference = "Stop"

$targets = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -match '^(python|py)\.exe$' -and
        $_.CommandLine -and
        $_.CommandLine -like "*$ProcessTag*"
    }

if (-not $targets) {
    Write-Output "No tagged python processes found for: $ProcessTag"
    exit 0
}

$targets | ForEach-Object {
    try {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
        Write-Output "Stopped PID=$($_.ProcessId) TAG=$ProcessTag"
    } catch {
        Write-Output "Failed PID=$($_.ProcessId) TAG=$ProcessTag :: $($_.Exception.Message)"
    }
}
