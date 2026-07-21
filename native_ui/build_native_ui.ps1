param()

$ErrorActionPreference = "Stop"
$nativeRoot = $PSScriptRoot
$pimeCommit = "26fcf6ac8874e76b8f75f6826811b03bfdfc2e89"
$temporaryRoot = Join-Path $env:TEMP ("SmartPriorityPimeUi-" + [Guid]::NewGuid().ToString("N"))
$cmake = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"

if (-not (Test-Path -LiteralPath $cmake)) {
    throw "Visual Studio 2022 CMake was not found: $cmake"
}

$resolvedTemp = [IO.Path]::GetFullPath($env:TEMP).TrimEnd("\")
$resolvedBuild = [IO.Path]::GetFullPath($temporaryRoot).TrimEnd("\")
if (-not $resolvedBuild.StartsWith($resolvedTemp + "\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to build outside the temporary directory."
}

try {
    & git clone --quiet https://github.com/EasyIME/PIME.git $resolvedBuild
    & git -C $resolvedBuild checkout --quiet $pimeCommit
    & git -C $resolvedBuild submodule update --init --depth 1 libIME2 jsoncpp
    if ($LASTEXITCODE -ne 0) { throw "Unable to fetch the pinned PIME source." }

    Copy-Item -LiteralPath (Join-Path $nativeRoot "src\CandidateWindow.cpp") `
        -Destination (Join-Path $resolvedBuild "libIME2\src\CandidateWindow.cpp") -Force
    Copy-Item -LiteralPath (Join-Path $nativeRoot "src\CMakeLists.txt") `
        -Destination (Join-Path $resolvedBuild "CMakeLists.txt") -Force

    foreach ($architecture in @(
        @{ Name = "x86"; Platform = "Win32" },
        @{ Name = "x64"; Platform = "x64" }
    )) {
        $buildDir = Join-Path $resolvedBuild ("build-" + $architecture.Name)
        & $cmake -S $resolvedBuild -B $buildDir -G "Visual Studio 17 2022" `
            -A $architecture.Platform "-DCMAKE_POLICY_VERSION_MINIMUM=3.5"
        if ($LASTEXITCODE -ne 0) { throw "CMake configure failed for $($architecture.Name)." }
        & $cmake --build $buildDir --config Release --target PIMETextService
        if ($LASTEXITCODE -ne 0) { throw "Native UI build failed for $($architecture.Name)." }
        $dll = Join-Path $buildDir "PIMETextService\Release\PIMETextService.dll"
        $destination = Join-Path $nativeRoot ("bin\" + $architecture.Name)
        New-Item -ItemType Directory -Path $destination -Force | Out-Null
        Copy-Item -LiteralPath $dll -Destination $destination -Force
    }

    Get-FileHash -Algorithm SHA256 -LiteralPath `
        (Join-Path $nativeRoot "bin\x86\PIMETextService.dll"), `
        (Join-Path $nativeRoot "bin\x64\PIMETextService.dll")
}
finally {
    if (Test-Path -LiteralPath $resolvedBuild) {
        Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
    }
}
