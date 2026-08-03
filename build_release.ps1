param(
    [string]$MakensisPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$releaseRoot = Join-Path $projectRoot "release"
$stagingRoot = Join-Path $projectRoot "release-staging"
$noticeSource = Join-Path $projectRoot "THIRD_PARTY_NOTICES.txt"
$pimeLicense = Join-Path $stagingRoot "PIME-LICENSE.txt"
$chewingLicense = Join-Path $stagingRoot "libchewing-COPYING.txt"
$rimeEssayLicense = Join-Path $stagingRoot "rime-essay-LICENSE.txt"
$moeDataNotice = Join-Path $stagingRoot "MOE-OPEN-DATA-NOTICE.txt"
$mcBopomofoLicense = Join-Path $stagingRoot "McBopomofo-LICENSE.txt"

function Reset-ProjectDirectory([string]$Path) {
    $resolvedProject = [IO.Path]::GetFullPath($projectRoot).TrimEnd("\")
    $resolvedTarget = [IO.Path]::GetFullPath($Path).TrimEnd("\")
    if (-not $resolvedTarget.StartsWith($resolvedProject + "\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean a path outside the project: $resolvedTarget"
    }
    if (Test-Path -LiteralPath $resolvedTarget) {
        Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
    }
    New-Item -ItemType Directory -Path $resolvedTarget -Force | Out-Null
}

function Get-VerifiedFile(
    [string]$LocalCandidate,
    [string]$Uri,
    [string]$Destination,
    [string[]]$ExpectedSha256
) {
    if (Test-Path -LiteralPath $LocalCandidate) {
        Copy-Item -LiteralPath $LocalCandidate -Destination $Destination -Force
    }
    else {
        Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Destination
    }
    $actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash
    if ($ExpectedSha256 -notcontains $actual) {
        throw "License checksum mismatch for $Destination (got $actual)."
    }
}

Reset-ProjectDirectory $releaseRoot
Reset-ProjectDirectory $stagingRoot

& (Join-Path $projectRoot "build_pime_overlay.ps1") | Out-Null
Copy-Item -LiteralPath $noticeSource -Destination (Join-Path $stagingRoot "THIRD_PARTY_NOTICES.txt") -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "licenses\MOE-OPEN-DATA-NOTICE.txt") -Destination $moeDataNotice -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "licenses\McBopomofo-LICENSE.txt") -Destination $mcBopomofoLicense -Force

$workspaceRoot = Split-Path -Parent $projectRoot
Get-VerifiedFile `
    (Join-Path $workspaceRoot "tmp\PIME-upstream\LICENSE.txt") `
    "https://raw.githubusercontent.com/EasyIME/PIME/571759f471c93e288682305148df751a12f5415e/LICENSE.txt" `
    $pimeLicense `
    @(
        "8383DBC7C8938F879BDBFBB6366DF57B3E2B9612B631714D14F0D5FA7F158A8F",
        "BA6EA5AFA38BA866AB2CD0D27119B9421EFEC40A2132C4EB98F8C70C81660744"
    )
Get-VerifiedFile `
    (Join-Path $workspaceRoot "tmp\libchewing-upstream\COPYING") `
    "https://raw.githubusercontent.com/chewing/libchewing/3c4a93aa03d574c7f011ff84e8a2437c2f79b2cf/COPYING" `
    $chewingLicense `
    @(
        "1E7E6BAE5A5BDE32F1AE5A7C37A082D1AB03CF89354F7F936AC40BE9E39A6531",
        "DC626520DCD53A22F727AF3EE42C770E56C97A64FE3ADB063799D8AB032FE551"
    )
Get-VerifiedFile `
    (Join-Path $projectRoot "licenses\rime-essay-LICENSE.txt") `
    "https://raw.githubusercontent.com/rime/rime-essay/e9b1a374a6ea015fca5bdd04318924b4483ac35a/LICENSE" `
    $rimeEssayLicense `
    @(
        "EA7D049C7705DC13AFC202DD18E1827F3484F8212FD3FA7B82FC4A0C363432C9",
        "DA7EABB7BAFDF7D3AE5E9F223AA5BDC1EECE45AC569DC21B3B037520B4464768"
    )

if (-not $MakensisPath) {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "NSIS\makensis.exe"),
        (Join-Path $env:ProgramFiles "NSIS\makensis.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    $MakensisPath = $candidates | Select-Object -First 1
}
if (-not $MakensisPath -or -not (Test-Path -LiteralPath $MakensisPath)) {
    throw "NSIS makensis.exe was not found. Install NSIS 3.12 or pass -MakensisPath."
}

& $MakensisPath "/INPUTCHARSET" "UTF8" (Join-Path $projectRoot "installer\SmartPriorityBopomofo.nsi")
if ($LASTEXITCODE -ne 0) { throw "NSIS build failed with exit code $LASTEXITCODE." }

$artifact = Join-Path $releaseRoot "Smart-Priority-Bopomofo-Setup-0.6.9.exe"
if (-not (Test-Path -LiteralPath $artifact)) {
    throw "The installer artifact was not created."
}
$hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash
Set-Content -LiteralPath (Join-Path $releaseRoot "SHA256SUMS.txt") `
    -Value "$hash  $([IO.Path]::GetFileName($artifact))" -Encoding ASCII
Write-Output $artifact
Write-Output "SHA256=$hash"
