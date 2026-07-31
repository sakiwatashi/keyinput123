# Every script the installer dot-sources must actually ship in the installer.
#
# install.ps1 and uninstall.ps1 load helpers with `. (Join-Path $PSScriptRoot
# ...)`. A helper missing from the NSIS file list aborts the script on its
# second line -- before Start-Transcript runs -- so install.log records nothing
# and the only symptom is a bare "exit code 1" dialog. Shipping that costs a
# release, so the dependency is asserted here instead of being remembered.
$ErrorActionPreference = "Stop"

$installerRoot = Join-Path $PSScriptRoot "..\installer"
$nsiPath = Join-Path $installerRoot "SmartPriorityBopomofo.nsi"
if (-not (Test-Path -LiteralPath $nsiPath)) {
    throw "The NSIS script is missing: $nsiPath"
}
$nsi = Get-Content -LiteralPath $nsiPath -Raw

# What the NSIS script packages into $INSTDIR.
$packaged = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase)
foreach ($match in [regex]::Matches($nsi, '(?m)^\s*File\s+"([^"]+)"')) {
    $packaged.Add([IO.Path]::GetFileName($match.Groups[1].Value)) | Out-Null
}

# What the entry-point scripts load at run time.
$missing = @()
foreach ($entry in @("install.ps1", "uninstall.ps1")) {
    $entryPath = Join-Path $installerRoot $entry
    if (-not (Test-Path -LiteralPath $entryPath)) {
        throw "Installer entry point is missing: $entryPath"
    }
    if (-not $packaged.Contains($entry)) {
        $missing += "$entry (the entry point itself is not packaged)"
    }
    $text = Get-Content -LiteralPath $entryPath -Raw
    foreach ($match in [regex]::Matches($text, '\.\s*\(Join-Path\s+\$PSScriptRoot\s+"([^"]+)"\)')) {
        $dependency = [IO.Path]::GetFileName($match.Groups[1].Value)
        if (-not (Test-Path -LiteralPath (Join-Path $installerRoot $dependency))) {
            $missing += "$dependency (loaded by $entry, absent from installer\)"
            continue
        }
        if (-not $packaged.Contains($dependency)) {
            $missing += "$dependency (loaded by $entry, not in the NSIS file list)"
        }
    }
}

if ($missing.Count -gt 0) {
    throw ("The installer would ship without these scripts:`n  " + ($missing -join "`n  "))
}

Write-Output "PASS: every script the installer loads at run time is packaged"
