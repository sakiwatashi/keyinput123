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

# A stray control character inside a path literal is invisible in an editor and
# in a diff, but it breaks the path at run time. This shipped once: an escaping
# slip while editing install.ps1 turned "WindowsPowerShell1.0" into a vertical
# tab, so the Start-menu shortcut refused the target and the whole install
# aborted with a bare exit code 1. Nothing else here reaches shortcut creation.
$corrupt = @()
foreach ($script in Get-ChildItem -LiteralPath $installerRoot -Filter *.ps1 -File) {
    $text = [IO.File]::ReadAllText($script.FullName)
    for ($index = 0; $index -lt $text.Length; $index++) {
        $code = [int][char]$text[$index]
        if ($code -lt 0x20 -and $text[$index] -notin @("`t", "`r", "`n")) {
            $corrupt += ("{0}: 位置 {1} 有控制字元 0x{2:X2}" -f $script.Name, $index, $code)
        }
    }
}
if ($corrupt.Count -gt 0) {
    throw ("Installer scripts contain control characters:`n  " + ($corrupt -join "`n  "))
}

# Every Windows path the installer builds from $env:WINDIR must actually exist.
# The broken shortcut target was still a syntactically valid string; only
# resolving it revealed the damage.
$unresolved = @()
foreach ($script in Get-ChildItem -LiteralPath $installerRoot -Filter *.ps1 -File) {
    $text = [IO.File]::ReadAllText($script.FullName)
    foreach ($match in [regex]::Matches($text, 'Join-Path\s+\$env:WINDIR\s+"([^"]+)"')) {
        $candidate = Join-Path $env:WINDIR $match.Groups[1].Value
        if (-not (Test-Path -LiteralPath $candidate)) {
            $unresolved += "$($script.Name): $candidate"
        }
    }
}
if ($unresolved.Count -gt 0) {
    throw ("Installer builds Windows paths that do not exist:`n  " + ($unresolved -join "`n  "))
}

Write-Output "PASS: installer scripts are packaged, free of control characters, and their Windows paths resolve"
