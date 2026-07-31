# Two installer defects that first surfaced on a real user's machine
# (2026-08-01, v0.6.5).
#
# 1. A leftover HKLM PIME registry key pointing at a deleted directory made
#    install.ps1 skip the bundled PIME installer and fail one step later with
#    "A valid PIME installation directory was not found". Detection must
#    validate the directory, not merely read the value.
# 2. install.ps1 and uninstall.ps1 stop their transcript in `finally`, but an
#    uncaught error prints only after that, so the log the failure dialog
#    points at ended up empty. Both scripts must catch, record, and rethrow.
#
# These are source-shape assertions in the spirit of
# installer_payload_smoke.ps1: they cannot run the installer against a fake
# registry, but they stop the guarded pattern from being simplified away.
$ErrorActionPreference = "Stop"

$projectRoot = Join-Path $PSScriptRoot ".."
$install = Get-Content -LiteralPath (Join-Path $projectRoot "installer\install.ps1") -Raw
$uninstall = Get-Content -LiteralPath (Join-Path $projectRoot "installer\uninstall.ps1") -Raw

$problems = @()

# --- 1. Registry detection must validate the directory ---
if ($install -notmatch 'function\s+Find-PimeInstallRoot') {
    $problems += "install.ps1 no longer defines Find-PimeInstallRoot"
}
elseif ($install -match '(?s)function\s+Find-PimeInstallRoot.*?\r?\n\}') {
    if ($Matches[0] -notmatch 'Test-Path\s+-LiteralPath\s+\$root') {
        $problems += "Find-PimeInstallRoot no longer validates the directory it reads from the registry"
    }
}
$uses = [regex]::Matches($install, 'Find-PimeInstallRoot\s+-RegistryPaths').Count
if ($uses -lt 2) {
    $problems += "install.ps1 must resolve the PIME root through Find-PimeInstallRoot both before and after installing the bundled PIME (found $uses call sites)"
}

# --- 2. Failures must reach the log the dialog points at ---
foreach ($entry in @(
    @{ Name = "install.ps1"; Text = $install },
    @{ Name = "uninstall.ps1"; Text = $uninstall }
)) {
    if ($entry.Text -notmatch '(?s)catch\s*\{[^}]*Write-Output[^}]*\bthrow\b') {
        $problems += "$($entry.Name) must catch, write the error into the transcript, and rethrow"
    }
}

if ($problems.Count -gt 0) {
    throw ("Installer resilience problems:`n  " + ($problems -join "`n  "))
}

Write-Output "PASS: stale PIME registry keys count as absent and failures reach the install/uninstall logs"
