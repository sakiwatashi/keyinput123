# Two release defects that only surface in the shipped installer.
#
# 1. NSIS reads a Unicode installer's licence page as the system ANSI codepage
#    unless the file starts with a UTF-8 BOM. Without it the whole page rendered
#    as mojibake, and nothing in the build or the test suite noticed.
# 2. The product version lives in six places. A sweep that only covered
#    ps1/nsi/json/md/yml left THIRD_PARTY_NOTICES.txt announcing an old version
#    on the first page the user ever sees.
$ErrorActionPreference = "Stop"

$projectRoot = Join-Path $PSScriptRoot ".."
$nsiPath = Join-Path $projectRoot "installer\SmartPriorityBopomofo.nsi"
$nsi = Get-Content -LiteralPath $nsiPath -Raw

function Test-Utf8Bom {
    param([string]$Path)
    $bytes = [IO.File]::ReadAllBytes($Path)
    return $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
}

function Test-PureAscii {
    param([string]$Path)
    foreach ($byte in [IO.File]::ReadAllBytes($Path)) {
        if ($byte -gt 0x7F) { return $false }
    }
    return $true
}

$problems = @()

# --- 1. Licence pages must survive the Unicode installer ---
$isUnicode = $nsi -match '(?m)^\s*Unicode\s+True'
foreach ($match in [regex]::Matches($nsi, 'MUI_PAGE_LICENSE\s+"([^"]+)"')) {
    $relative = $match.Groups[1].Value
    # The NSIS path is relative to installer\.
    $licencePath = [IO.Path]::GetFullPath((Join-Path (Join-Path $projectRoot "installer") $relative))
    $sourceName = [IO.Path]::GetFileName($licencePath)
    $source = Join-Path $projectRoot $sourceName
    # Check the tracked source, not release-staging\: that directory is a build
    # artifact refreshed by build_release.ps1, so a stale copy left over from an
    # earlier build would report a problem that no longer exists in the repo.
    $checkPath = if (Test-Path -LiteralPath $source) { $source }
                 elseif (Test-Path -LiteralPath $licencePath) { $licencePath }
                 else { $null }
    if ($null -eq $checkPath) {
        $problems += "licence page source not found for $relative"
        continue
    }
    if ($isUnicode -and -not (Test-PureAscii $checkPath) -and -not (Test-Utf8Bom $checkPath)) {
        $problems += "$sourceName has non-ASCII text but no UTF-8 BOM; the Unicode installer will render it as mojibake"
    }
}

# --- 2. One product version everywhere ---
$imeJson = Get-Content -LiteralPath (Join-Path $projectRoot "pime_module\ime.json") -Raw | ConvertFrom-Json
$version = $imeJson.version
if (-not $version) { throw "ime.json has no version" }

$expected = @{
    "installer\SmartPriorityBopomofo.nsi" = @("!define PRODUCT_VERSION `"$version`"", "VIProductVersion `"$version.0`"")
    "build_release.ps1"                   = @("Smart-Priority-Bopomofo-Setup-$version.exe")
    ".github\workflows\windows.yml"       = @("Smart-Priority-Bopomofo-Setup-$version.exe")
    "README.md"                           = @("Smart-Priority-Bopomofo-Setup-$version.exe")
    "THIRD_PARTY_NOTICES.txt"             = @($version)
}
foreach ($file in $expected.Keys) {
    $path = Join-Path $projectRoot $file
    if (-not (Test-Path -LiteralPath $path)) {
        $problems += "missing $file"
        continue
    }
    $text = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    foreach ($needle in $expected[$file]) {
        if ($text -notmatch [regex]::Escape($needle)) {
            $problems += "$file does not carry version $version (expected to find '$needle')"
        }
    }
}

if ($problems.Count -gt 0) {
    throw ("Release consistency problems:`n  " + ($problems -join "`n  "))
}

Write-Output "PASS: licence pages are BOM-tagged and every version location says $version"
