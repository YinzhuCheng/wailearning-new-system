param(
    [Parameter(Mandatory = $true)]
    [string]$GitHubRepoUrl,

    [string]$GitHubUpstreamUrl = "https://github.com/joyapple/CourseEval.git",
    [string]$GiteeUpstreamUrl = "https://gitee.com/joyapple2020/CourseEval.git"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

function Get-RemoteUrl {
    param([string]$Name)

    $remotes = @(git -C $RepoRoot remote)
    if (-not ($remotes -contains $Name)) {
        return $null
    }

    $result = git -C $RepoRoot remote get-url $Name
    return $result.Trim()
}

function Ensure-Remote {
    param(
        [string]$Name,
        [string]$Url
    )

    $existing = Get-RemoteUrl -Name $Name
    if ($existing) {
        if ($existing -ne $Url) {
            git -C $RepoRoot remote set-url $Name $Url
        }
    } else {
        git -C $RepoRoot remote add $Name $Url
    }
}

$currentOrigin = Get-RemoteUrl -Name "origin"

if ($currentOrigin -and $currentOrigin -ne $GitHubRepoUrl -and $currentOrigin -eq $GiteeUpstreamUrl) {
    git -C $RepoRoot remote rename origin gitee
}

Ensure-Remote -Name "origin" -Url $GitHubRepoUrl
Ensure-Remote -Name "upstream" -Url $GitHubUpstreamUrl
Ensure-Remote -Name "gitee" -Url $GiteeUpstreamUrl

git -C $RepoRoot fetch --all --prune

Write-Host ""
Write-Host "Configured remotes:"
git -C $RepoRoot remote -v
Write-Host ""
Write-Host "Next steps:"
Write-Host "  git -C `"$RepoRoot`" push -u origin main"
Write-Host "  git -C `"$RepoRoot`" push origin --tags"
