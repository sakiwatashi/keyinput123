param(
    [switch]$Elevated,
    [switch]$EnableUnsignedNativeUi,
    [switch]$DisableUnsignedNativeUi
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$scriptPath = $MyInvocation.MyCommand.Path

if ($EnableUnsignedNativeUi -and $DisableUnsignedNativeUi) {
    throw "EnableUnsignedNativeUi and DisableUnsignedNativeUi cannot be used together."
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $elevatedArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"' + $scriptPath + '"'),
        "-Elevated"
    )
    if ($EnableUnsignedNativeUi) {
        $elevatedArguments += "-EnableUnsignedNativeUi"
    }
    if ($DisableUnsignedNativeUi) {
        $elevatedArguments += "-DisableUnsignedNativeUi"
    }
    $process = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru -ArgumentList $elevatedArguments
    if ($process.ExitCode -ne 0) {
        throw "Installation failed with exit code $($process.ExitCode)."
    }
    # Start the candidate-window helper here, after elevation has returned and
    # in the user's own session. It hosts the notification-area icon, which is
    # the only obvious way into the control panel; without this the icon was
    # missing after every install until the user happened to type something,
    # because the input method only launches the helper on the first keystroke.
    #
    # Not from the elevated script: that would leave the tray icon -- and the
    # control panel it opens -- running as administrator, and a long-running
    # child holding the elevated process's output handles made the installer
    # appear to hang long after it had finished.
    $helperExecutable = Join-Path $projectRoot "dist\PIME-overlay\python\input_methods\pinned_bopomofo\helper\SmartPriorityCandidateUI.exe"
    $installedHelper = Join-Path ${env:ProgramFiles(x86)} "PIME\python\input_methods\pinned_bopomofo\helper\SmartPriorityCandidateUI.exe"
    if (Test-Path -LiteralPath $installedHelper) {
        try {
            # The helper takes a single-instance lock, so a second copy exits
            # immediately; starting it unconditionally is safe.
            Start-Process -FilePath $installedHelper -ErrorAction Stop | Out-Null
        }
        catch {
            # Disposable: the input method starts it on demand anyway.
            Write-Output "Note: could not start the candidate window helper ($($_.Exception.Message))."
        }
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
    & $formalInstaller -PayloadRoot $resolvedStaging `
        -EnableUnsignedNativeUi:$EnableUnsignedNativeUi `
        -DisableUnsignedNativeUi:$DisableUnsignedNativeUi

    # Keep the Windows Apps list in step with what was just installed. Only the
    # NSIS installer writes that entry, so after a source update it kept showing
    # the last EXE's version. See tools/sync_uninstall_entry.ps1 for why the
    # uninstall scripts are refreshed first and why both registry views are
    # searched.
    . (Join-Path (Join-Path $projectRoot "tools") "sync_uninstall_entry.ps1")
    $imeJson = Join-Path (Join-Path $projectRoot "pime_module") "ime.json"
    $version = (Get-Content -LiteralPath $imeJson -Raw | ConvertFrom-Json).version
    $installerRoot = Join-Path $projectRoot "installer"
    $uninstallKey = "Microsoft\Windows\CurrentVersion\Uninstall\SmartPriorityBopomofo"
    $sync = Sync-UninstallEntry -Version $version -RegistryPaths @(
        ("HKLM:\SOFTWARE\WOW6432Node\" + $uninstallKey),
        ("HKLM:\SOFTWARE\" + $uninstallKey)
    ) -PayloadFiles @(
        (Join-Path $installerRoot "install.ps1"),
        (Join-Path $installerRoot "native_ui_preference.ps1"),
        (Join-Path $installerRoot "restore_signed_text_service.ps1"),
        (Join-Path $installerRoot "uninstall.ps1"),
        (Join-Path $projectRoot "THIRD_PARTY_NOTICES.txt")
    )
    foreach ($key in $sync.Updated) {
        Write-Output "Updated the Apps list entry to $version ($key)."
    }
    foreach ($note in $sync.Skipped) {
        Write-Output "Left an Apps list entry unchanged: $note"
    }
}
finally {
    Set-Location -LiteralPath $env:TEMP
    if (Test-Path -LiteralPath $resolvedStaging) {
        Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
    }
}
