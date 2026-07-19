param(
    [switch]$Elevated
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$scriptPath = $MyInvocation.MyCommand.Path

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $process = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"' + $scriptPath + '"'),
        "-Elevated"
    )
    if ($process.ExitCode -ne 0) {
        throw "Installation failed with exit code $($process.ExitCode)."
    }
    Write-Output "Smart Priority Bopomofo installation completed."
    exit 0
}

$overlayRoot = Join-Path $projectRoot "dist\PIME-overlay"
$pimeInstaller = Join-Path $projectRoot "vendor\PIME-1.3.0-stable-setup.exe"
$formalInstaller = Join-Path $projectRoot "installer\install.ps1"
foreach ($required in @($pimeInstaller, $formalInstaller)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required installation file is missing: $required"
    }
}

& (Join-Path $projectRoot "build_pime_overlay.ps1") | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $overlayRoot "python\input_methods\pinned_bopomofo\ime.json"))) {
    throw "The PIME overlay build did not produce the expected module."
}

$temporaryRoot = Join-Path $env:TEMP ("SmartPriorityBopomofo-" + [Guid]::NewGuid().ToString("N"))
$resolvedTemp = [IO.Path]::GetFullPath($env:TEMP).TrimEnd("\")
$resolvedStaging = [IO.Path]::GetFullPath($temporaryRoot).TrimEnd("\")
if (-not $resolvedStaging.StartsWith($resolvedTemp + "\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to create staging outside the temporary directory."
}

try {
    New-Item -ItemType Directory -Path $resolvedStaging -Force | Out-Null
    Copy-Item -LiteralPath $overlayRoot -Destination (Join-Path $resolvedStaging "overlay") -Recurse -Force
    Copy-Item -LiteralPath $pimeInstaller -Destination $resolvedStaging -Force
    & $formalInstaller -PayloadRoot $resolvedStaging
}
finally {
    Set-Location -LiteralPath $env:TEMP
    if (Test-Path -LiteralPath $resolvedStaging) {
        Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
    }
}
