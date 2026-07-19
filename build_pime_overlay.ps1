$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distRoot = Join-Path $projectRoot "dist\PIME-overlay"
$moduleRoot = Join-Path $distRoot "python\input_methods\pinned_bopomofo"
$coreDest = Join-Path $moduleRoot "bopomofo_core"
$chewingDest = Join-Path $moduleRoot "pinned_libchewing"

New-Item -ItemType Directory -Path $coreDest -Force | Out-Null
New-Item -ItemType Directory -Path $chewingDest -Force | Out-Null

Copy-Item -LiteralPath (Join-Path $projectRoot "pime_module\input_methods_init.py") -Destination (Join-Path $distRoot "python\input_methods\__init__.py") -Force

Copy-Item -LiteralPath (Join-Path $projectRoot "pime_module\__init__.py") -Destination $moduleRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "pime_module\ime.json") -Destination $moduleRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "pime_module\pinned_bopomofo_ime.py") -Destination $moduleRoot -Force

Get-ChildItem -LiteralPath (Join-Path $projectRoot "bopomofo_core") -Filter "*.py" -File |
    Copy-Item -Destination $coreDest -Force

$runtimeChewing = Join-Path $projectRoot "pime_runtime\libchewing"
Copy-Item -LiteralPath (Join-Path $runtimeChewing "__init__.py") -Destination $chewingDest -Force
Copy-Item -LiteralPath (Join-Path $runtimeChewing "libchewing.py") -Destination $chewingDest -Force
Copy-Item -LiteralPath (Join-Path $runtimeChewing "chewing.dll") -Destination $chewingDest -Force
New-Item -ItemType Directory -Path (Join-Path $chewingDest "data") -Force | Out-Null
foreach ($name in "word.dat", "tsi.dat", "swkb.dat", "symbols.dat") {
    Copy-Item -LiteralPath (Join-Path $runtimeChewing "data\$name") -Destination (Join-Path $chewingDest "data") -Force
}

Write-Output $distRoot
