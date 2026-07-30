param(
    [ValidateSet("x86", "x64")]
    [string]$Architecture = "x64",
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$helperRoot = $PSScriptRoot
$cmake = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"

if (-not (Test-Path -LiteralPath $cmake)) {
    throw "Visual Studio 2022 CMake was not found: $cmake"
}

$temporaryRoot = Join-Path $env:TEMP ("SmartPriorityHelper-" + [Guid]::NewGuid().ToString("N"))
$resolvedTemp = [IO.Path]::GetFullPath($env:TEMP).TrimEnd("\")
$resolvedBuild = [IO.Path]::GetFullPath($temporaryRoot).TrimEnd("\")
if (-not $resolvedBuild.StartsWith($resolvedTemp + "\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to build outside the temporary directory."
}

$platform = if ($Architecture -eq "x86") { "Win32" } else { "x64" }
$outputRoot = Join-Path $helperRoot "bin\$Architecture"

try {
    New-Item -ItemType Directory -Path $resolvedBuild -Force | Out-Null
    & $cmake -S $helperRoot -B $resolvedBuild -G "Visual Studio 17 2022" -A $platform
    if ($LASTEXITCODE -ne 0) { throw "CMake configuration failed." }

    & $cmake --build $resolvedBuild --config $Configuration
    if ($LASTEXITCODE -ne 0) { throw "CMake build failed." }

    $built = Join-Path $resolvedBuild "$Configuration\SmartPriorityCandidateUI.exe"
    if (-not (Test-Path -LiteralPath $built)) {
        throw "The helper executable was not produced: $built"
    }

    New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
    Copy-Item -LiteralPath $built -Destination $outputRoot -Force
    Write-Output (Join-Path $outputRoot "SmartPriorityCandidateUI.exe")
}
finally {
    Set-Location -LiteralPath $env:TEMP
    if (Test-Path -LiteralPath $resolvedBuild) {
        Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
    }
}
