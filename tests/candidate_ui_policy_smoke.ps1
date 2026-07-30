# Checks the rule that keeps the out-of-process candidate window away from
# anti-cheat protected games.
#
# The window itself never enters another process, but drawing over a protected
# game and synthesising selection keys there is exactly the kind of behaviour
# this redesign exists to avoid. These assertions pin that decision without
# needing any of the games installed.
$ErrorActionPreference = "Stop"

$helper = Join-Path $PSScriptRoot "..\native_ui\helper\bin\x64\SmartPriorityCandidateUI.exe"
if (-not (Test-Path -LiteralPath $helper)) {
    throw "The candidate UI helper is missing; run native_ui\helper\build_helper.ps1"
}

function Get-PolicyVerdict {
    param([string]$ImageName)
    # The value must be quoted: real image paths contain spaces, and an
    # unquoted argument would be split before the policy ever sees it.
    $process = Start-Process -FilePath $helper -ArgumentList "--check-policy=`"$ImageName`"" `
        -Wait -PassThru -WindowStyle Hidden
    switch ($process.ExitCode) {
        0 { return "allowed" }
        2 { return "blocked" }
        default { throw "Unexpected policy exit code $($process.ExitCode) for '$ImageName'." }
    }
}

$blocked = @(
    "VALORANT-Win64-Shipping.exe",
    "valorant.exe",
    "cs2.exe",
    "r5apex.exe",
    # Path-qualified and mixed case must resolve the same way, because the
    # foreground query returns a full path in whatever case Windows records.
    "C:\Riot Games\VALORANT\live\VALORANT-Win64-Shipping.exe",
    "VaLoRaNt.EXE"
)
$allowed = @(
    "notepad.exe",
    "chrome.exe",
    "Code.exe",
    "explorer.exe",
    "C:\Windows\System32\notepad.exe"
)

foreach ($name in $blocked) {
    $verdict = Get-PolicyVerdict $name
    if ($verdict -ne "blocked") {
        throw "Expected '$name' to be blocked but the policy said $verdict."
    }
}
foreach ($name in $allowed) {
    $verdict = Get-PolicyVerdict $name
    if ($verdict -ne "allowed") {
        throw "Expected '$name' to be allowed but the policy said $verdict."
    }
}

# An unnameable foreground process is the signature of a protected application,
# so the conservative reading must be to stay out.
if ((Get-PolicyVerdict "") -ne "blocked") {
    throw "An empty process name must be treated as blocked."
}

Write-Output "PASS: candidate UI stays out of anti-cheat protected foreground applications"
