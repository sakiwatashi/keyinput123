$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distRoot = Join-Path $projectRoot "dist\PIME-overlay"
$moduleRoot = Join-Path $distRoot "python\input_methods\pinned_bopomofo"
$coreDest = Join-Path $moduleRoot "bopomofo_core"
$chewingDest = Join-Path $moduleRoot "pinned_libchewing"

# A helper launched from a previous build keeps its own executable open, which
# blocks the clean below. It is a disposable UI process, so stopping it costs
# nothing; the input method relaunches it on demand.
Get-Process SmartPriorityCandidateUI -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }

if (Test-Path -LiteralPath $distRoot) {
    $resolvedProject = [IO.Path]::GetFullPath($projectRoot).TrimEnd("\")
    $resolvedDist = [IO.Path]::GetFullPath($distRoot).TrimEnd("\")
    if (-not $resolvedDist.StartsWith($resolvedProject + "\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean a distribution path outside the project."
    }
    Remove-Item -LiteralPath $resolvedDist -Recurse -Force
}

New-Item -ItemType Directory -Path $coreDest -Force | Out-Null
New-Item -ItemType Directory -Path $chewingDest -Force | Out-Null

Copy-Item -LiteralPath (Join-Path $projectRoot "pime_module\input_methods_init.py") -Destination (Join-Path $distRoot "python\input_methods\__init__.py") -Force

Copy-Item -LiteralPath (Join-Path $projectRoot "pime_module\__init__.py") -Destination $moduleRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "pime_module\ime.json") -Destination $moduleRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "pime_module\pinned_bopomofo_ime.py") -Destination $moduleRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "feedback-report.ps1") -Destination $moduleRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "control_panel") -Destination $moduleRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "THIRD_PARTY_NOTICES.txt") -Destination $moduleRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "licenses\rime-essay-LICENSE.txt") -Destination $moduleRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "licenses\MOE-OPEN-DATA-NOTICE.txt") -Destination $moduleRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "licenses\McBopomofo-LICENSE.txt") -Destination $moduleRoot -Force

Get-ChildItem -LiteralPath (Join-Path $projectRoot "bopomofo_core") -Filter "*.py" -File |
    Copy-Item -Destination $coreDest -Force
$coreData = Join-Path $projectRoot "bopomofo_core\data"
if (Test-Path -LiteralPath $coreData) {
    Copy-Item -LiteralPath $coreData -Destination $coreDest -Recurse -Force
}

$runtimeChewing = Join-Path $projectRoot "pime_runtime\libchewing"
Copy-Item -LiteralPath (Join-Path $runtimeChewing "__init__.py") -Destination $chewingDest -Force
Copy-Item -LiteralPath (Join-Path $runtimeChewing "libchewing.py") -Destination $chewingDest -Force
Copy-Item -LiteralPath (Join-Path $runtimeChewing "chewing.dll") -Destination $chewingDest -Force
New-Item -ItemType Directory -Path (Join-Path $chewingDest "data") -Force | Out-Null
foreach ($name in "word.dat", "tsi.dat", "swkb.dat", "symbols.dat") {
    Copy-Item -LiteralPath (Join-Path $runtimeChewing "data\$name") -Destination (Join-Path $chewingDest "data") -Force
}

# The out-of-process candidate window ships inside the module directory so the
# installer carries it with the Python layer and the module can locate it
# relative to its own path. It is a plain executable in its own process, so
# unlike PIMETextService.dll it never enters a host application.
$helperSource = Join-Path $projectRoot "native_ui\helper\bin\x64\SmartPriorityCandidateUI.exe"
if (-not (Test-Path -LiteralPath $helperSource)) {
    throw "The candidate UI helper is missing; run native_ui\helper\build_helper.ps1: $helperSource"
}
$helperDest = Join-Path $moduleRoot "helper"
New-Item -ItemType Directory -Path $helperDest -Force | Out-Null
Copy-Item -LiteralPath $helperSource -Destination $helperDest -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "native_ui\LGPL-2.0.txt") -Destination $helperDest -Force

# The legacy in-process candidate DLL is no longer tracked in the repository:
# the out-of-process helper replaced it, and shipping an unsigned text-service
# DLL is what got a game killed by its anti-cheat. A developer may still keep
# a local build to use `-EnableUnsignedNativeUi`, so the payload is optional
# rather than absent.
#
# Its source ships with it or not at all. The DLL is LGPL-derived, so a build
# that carries the binary must also carry the source it was built from.
$nativeUiSource = Join-Path $projectRoot "native_ui"
$nativeUiDest = Join-Path $distRoot "native_ui"
New-Item -ItemType Directory -Path $nativeUiDest -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $nativeUiSource "LGPL-2.0.txt") -Destination $nativeUiDest -Force
Copy-Item -LiteralPath (Join-Path $nativeUiSource "README.md") -Destination $nativeUiDest -Force

$legacyParts = @(
    (Join-Path $nativeUiSource "bin\x86\PIMETextService.dll"),
    (Join-Path $nativeUiSource "bin\x64\PIMETextService.dll"),
    (Join-Path $nativeUiSource "src\CandidateWindow.cpp")
)
$presentParts = @($legacyParts | Where-Object { Test-Path -LiteralPath $_ })
if ($presentParts.Count -eq $legacyParts.Count) {
    Copy-Item -LiteralPath (Join-Path $nativeUiSource "bin") `
        -Destination (Join-Path $nativeUiDest "bin") -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $nativeUiSource "src") `
        -Destination (Join-Path $nativeUiDest "src") -Recurse -Force
    if (Test-Path -LiteralPath (Join-Path $nativeUiSource "build_native_ui.ps1")) {
        Copy-Item -LiteralPath (Join-Path $nativeUiSource "build_native_ui.ps1") `
            -Destination $nativeUiDest -Force
    }
    Write-Output "Included the local legacy in-process candidate DLL."
}
elseif ($presentParts.Count -gt 0) {
    throw ("The legacy candidate DLL payload is incomplete. Ship the binary " +
        "and its LGPL source together, or neither: " +
        (($legacyParts | Where-Object { -not (Test-Path -LiteralPath $_) }) -join ", "))
}

Write-Output $distRoot
