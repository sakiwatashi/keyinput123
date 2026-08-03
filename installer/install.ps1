param(
    [Parameter(Mandatory = $true)]
    [string]$PayloadRoot,
    [switch]$EnableUnsignedNativeUi,
    [switch]$DisableUnsignedNativeUi
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "native_ui_preference.ps1")
. (Join-Path $PSScriptRoot "restore_signed_text_service.ps1")

function Find-PimeInstallRoot {
    param([string[]]$RegistryPaths)
    foreach ($registryPath in $RegistryPaths) {
        if (Test-Path -LiteralPath $registryPath) {
            $root = (Get-Item -LiteralPath $registryPath).GetValue("")
            # A leftover key whose directory was deleted by hand must count as
            # "not installed". Trusting the bare value skipped the bundled
            # PIME installer and failed one step later with "A valid PIME
            # installation directory was not found" (first real-user report).
            if ($root -and (Test-Path -LiteralPath $root)) {
                return $root
            }
        }
    }
    return $null
}

function Stop-SmartPriorityCandidateUiAndWait {
    # Stop-Process only signals termination; the executable stays locked
    # until the process has actually exited, and touching the module
    # directory inside that window fails with "file in use" (real uninstall
    # failure report, 2026-08-01 — the helper runs on every machine now
    # that the out-of-process window ships enabled).
    $helpers = @(Get-Process SmartPriorityCandidateUI -ErrorAction SilentlyContinue)
    foreach ($helper in $helpers) {
        Stop-Process -Id $helper.Id -Force -ErrorAction SilentlyContinue
    }
    foreach ($helper in $helpers) {
        try { $helper.WaitForExit(5000) | Out-Null } catch {}
    }
}

function Remove-DirectoryWithRetry {
    param([string]$Path)
    # Just-terminated processes and antivirus scans can hold a lock for a
    # beat longer; a few short retries beat failing the whole run.
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        if (-not (Test-Path -LiteralPath $Path)) { return }
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return
        }
        catch {
            if ($attempt -eq 10) { throw }
            Start-Sleep -Milliseconds 500
        }
    }
}
$tip = "0404:{35F67E9D-A54D-4177-9697-8B0AB71A9E04}{26EA5CF3-D515-40BE-9535-E7E98D5EE554}"
$moduleName = "pinned_bopomofo"
$logRoot = Join-Path $env:ProgramData "SmartPriorityBopomofo"
$logPath = Join-Path $logRoot "install.log"
$nativeStateRoot = Join-Path $logRoot "native-state"
$nativePreferencePath = Join-Path $logRoot "native-ui-preference.json"
$installedPimeThisRun = $false
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
Start-Transcript -LiteralPath $logPath -Force | Out-Null

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Administrator privileges are required."
    }

    $overlayModule = Join-Path $PayloadRoot "overlay\python\input_methods\$moduleName"
    $pimeInstaller = Join-Path $PayloadRoot "PIME-1.3.0-stable-setup.exe"
    if (-not (Test-Path -LiteralPath (Join-Path $overlayModule "ime.json"))) {
        throw "The input-method payload is missing."
    }
    if (-not (Test-Path -LiteralPath $pimeInstaller)) {
        throw "The bundled PIME installer is missing."
    }

    $signature = Get-AuthenticodeSignature -LiteralPath $pimeInstaller
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "The bundled PIME installer signature is invalid: $($signature.Status)"
    }

    $registryPaths = @(
        "HKLM:\Software\PIME",
        "HKLM:\Software\WOW6432Node\PIME"
    )
    $installRoot = Find-PimeInstallRoot -RegistryPaths $registryPaths

    # PIME is shared infrastructure. Install the bundled signed version only
    # when no usable PIME is present; never downgrade or replace an existing
    # version.
    if (-not $installRoot) {
        $process = Start-Process -FilePath $pimeInstaller -ArgumentList "/S" -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "PIME installation failed with exit code $($process.ExitCode)."
        }
        $installedPimeThisRun = $true
        $installRoot = Find-PimeInstallRoot -RegistryPaths $registryPaths
    }

    if (-not $installRoot -or -not (Test-Path -LiteralPath $installRoot)) {
        throw "A valid PIME installation directory was not found."
    }
    $resolvedRoot = (Resolve-Path -LiteralPath $installRoot).Path.TrimEnd("\")
    $allowedRoots = @(
        [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles),
        [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFilesX86)
    ) | Where-Object { $_ }
    if (-not ($allowedRoots | Where-Object {
        $resolvedRoot.StartsWith($_.TrimEnd("\") + "\", [StringComparison]::OrdinalIgnoreCase)
    })) {
        throw "The PIME directory is outside Program Files: $resolvedRoot"
    }

    $launcher = Join-Path $resolvedRoot "PIMELauncher.exe"
    if (Test-Path -LiteralPath $launcher) {
        Start-Process -FilePath $launcher -ArgumentList "/quit" -Wait
    }

    # The out-of-process candidate window lives inside the module directory and
    # holds its own executable open, which would block replacing that
    # directory. It is disposable and the input method relaunches it on demand.
    Stop-SmartPriorityCandidateUiAndWait

    $targetParent = Join-Path $resolvedRoot "python\input_methods"
    $targetModule = Join-Path $targetParent $moduleName
    $expectedTarget = [IO.Path]::GetFullPath((Join-Path $resolvedRoot "python\input_methods\$moduleName"))
    if ([IO.Path]::GetFullPath($targetModule) -ne $expectedTarget) {
        throw "Refusing to write to an unexpected module path."
    }
    Remove-DirectoryWithRetry -Path $targetModule
    New-Item -ItemType Directory -Path $targetModule -Force | Out-Null
    Get-ChildItem -LiteralPath $overlayModule -Force |
        Copy-Item -Destination $targetModule -Recurse -Force

    $feedbackTool = Join-Path $targetModule "feedback-report.ps1"
    if (Test-Path -LiteralPath $feedbackTool) {
        $programs = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
        $shortcutRoot = Join-Path $programs "智慧優先注音"
        New-Item -ItemType Directory -Path $shortcutRoot -Force | Out-Null
        $shortcutPath = Join-Path $shortcutRoot "轉換錯誤回報工具.lnk"
        $powershell = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $powershell
        $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $feedbackTool + '"'
        $shortcut.WorkingDirectory = $targetModule
        $shortcut.Description = "檢查、移除或回報智慧優先注音的轉換錯誤"
        $shortcut.Save()
    }

    # 控制台：狀態、功能開關、個人詞庫與按鍵對照。設定原本只能手改 JSON 或
    # 跑腳本，沒有捷徑的話一般使用者根本找不到入口。
    $controlPanel = Join-Path $targetModule "control_panel\SmartPriorityControlPanel.ps1"
    if (Test-Path -LiteralPath $controlPanel) {
        $programs = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
        $shortcutRoot = Join-Path $programs "智慧優先注音"
        New-Item -ItemType Directory -Path $shortcutRoot -Force | Out-Null
        $powershell = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut((Join-Path $shortcutRoot "智慧優先注音 控制台.lnk"))
        $shortcut.TargetPath = $powershell
        # WinForms 需要 STA；控制台自己會偵測並重啟，這裡直接指定省一次重啟。
        $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File "' + $controlPanel + '"'
        $shortcut.WorkingDirectory = Join-Path $targetModule "control_panel"
        $shortcut.Description = "檢視狀態、開關功能、管理個人詞庫與查看按鍵對照"
        $shortcut.Save()
    }

    # A fresh PIME installation bundles New Chewing. This product needs PIME
    # as infrastructure but exposes only Smart Priority Bopomofo. Never remove
    # New Chewing from a PIME installation that existed before this setup.
    if ($installedPimeThisRun) {
        $chewingModule = Join-Path $resolvedRoot "python\input_methods\chewing"
        $expectedChewing = [IO.Path]::GetFullPath((Join-Path $resolvedRoot "python\input_methods\chewing"))
        if ([IO.Path]::GetFullPath($chewingModule) -ne $expectedChewing) {
            throw "Refusing to remove an unexpected New Chewing path."
        }
        if (Test-Path -LiteralPath $chewingModule) {
            Remove-Item -LiteralPath $chewingModule -Recurse -Force
        }
    }

    $embeddedPython = Join-Path $resolvedRoot "python\python3\python.exe"
    if (Test-Path -LiteralPath $embeddedPython) {
        & $embeddedPython -m compileall -q $targetModule
        if ($LASTEXITCODE -ne 0) { throw "The module compile check failed." }
    }

    # A fresh installation keeps PIME's signed DLL. Once a user explicitly
    # enables the custom UI, remember that choice across source, EXE, and AI-
    # assisted updates so a routine Python-layer update cannot silently revert
    # the appearance. The signed UI remains explicitly recoverable.
    $useUnsignedNativeUi = Resolve-SmartPriorityNativeUiPreference `
        -PreferencePath $nativePreferencePath `
        -PimeRoot $resolvedRoot `
        -StateRoot $nativeStateRoot `
        -EnableUnsignedNativeUi:$EnableUnsignedNativeUi `
        -DisableUnsignedNativeUi:$DisableUnsignedNativeUi
    if (-not $useUnsignedNativeUi) {
        Restore-OriginalPimeTextService -PimeRoot $resolvedRoot -StateRoot $nativeStateRoot
    }

    # Apply the optional native candidate window only when explicitly enabled
    # and when this PIME installation contains no unrelated input methods.
    # Preserve the original DLLs so a safe reinstall/uninstall can restore them.
    $pythonMethods = Join-Path $resolvedRoot "python\input_methods"
    $nodeMethods = Join-Path $resolvedRoot "node\input_methods"
    $otherPythonModules = @(
        Get-ChildItem -LiteralPath $pythonMethods -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notin @($moduleName, "__pycache__") }
    )
    $otherNodeModules = @(
        Get-ChildItem -LiteralPath $nodeMethods -Directory -ErrorAction SilentlyContinue
    )
    $nativeUiPayload = Join-Path $PayloadRoot "overlay\native_ui\bin"
    $canInstallNativeUi = (
        $useUnsignedNativeUi -and
        $otherPythonModules.Count -eq 0 -and $otherNodeModules.Count -eq 0 -and
        (Test-Path -LiteralPath (Join-Path $nativeUiPayload "x86\PIMETextService.dll")) -and
        (Test-Path -LiteralPath (Join-Path $nativeUiPayload "x64\PIMETextService.dll"))
    )
    if ($useUnsignedNativeUi -and -not $canInstallNativeUi) {
        throw ("The remembered custom candidate UI cannot be installed. " +
            "The published installer no longer carries the unsigned in-process " +
            "DLL; the candidate window now runs out of process instead. Either " +
            "build the overlay from a source tree that still has " +
            "native_ui\bin, or run this installer with -DisableUnsignedNativeUi " +
            "to return to the signed PIME binaries. Unrelated PIME input-method " +
            "modules also block it.")
    }
    if ($canInstallNativeUi) {
        # An earlier rollback may still hold a reboot-time signed restore in
        # the queue; cancel it so this explicit enable survives the restart.
        Clear-SmartPriorityScheduledSignedRestore -StateRoot $nativeStateRoot
        $backupRoot = Join-Path $nativeStateRoot "backup"
        $pendingRoot = Join-Path $nativeStateRoot "pending"
        New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
        $nativeHashes = @{}
        $nativeUpdatePending = $false
        if (-not ("SmartPriorityNativeMethods" -as [type])) {
            Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class SmartPriorityNativeMethods {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool MoveFileEx(
        string existingFile,
        string newFile,
        int flags
    );
}
"@
        }
        foreach ($architecture in @("x86", "x64")) {
            $sourceDll = Join-Path $nativeUiPayload "$architecture\PIMETextService.dll"
            $targetDll = Join-Path $resolvedRoot "$architecture\PIMETextService.dll"
            $backupDll = Join-Path $backupRoot "$architecture\PIMETextService.dll"
            $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceDll).Hash
            New-Item -ItemType Directory -Path (Split-Path -Parent $backupDll) -Force | Out-Null
            if ((Test-Path -LiteralPath $targetDll) -and -not (Test-Path -LiteralPath $backupDll)) {
                Copy-Item -LiteralPath $targetDll -Destination $backupDll -Force
            }
            # Reinstalling the Python layer is common during development. Do
            # not touch or re-queue a native DLL that is already current.
            if ((Test-Path -LiteralPath $targetDll) -and
                (Get-FileHash -Algorithm SHA256 -LiteralPath $targetDll).Hash -eq $sourceHash) {
                $nativeHashes[$architecture] = $sourceHash
                continue
            }
            try {
                Copy-Item -LiteralPath $sourceDll -Destination $targetDll -Force
            }
            catch [System.IO.IOException], [System.UnauthorizedAccessException] {
                # TSF loads this DLL into every text application, so Windows
                # commonly keeps it locked. Stage a persistent copy and ask
                # the kernel to replace it safely at the next reboot.
                $pendingDll = Join-Path $pendingRoot "$architecture\PIMETextService.dll"
                New-Item -ItemType Directory -Path (Split-Path -Parent $pendingDll) -Force | Out-Null
                Copy-Item -LiteralPath $sourceDll -Destination $pendingDll -Force
                $sessionManager = "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager"
                $pendingMoves = (Get-ItemProperty -LiteralPath $sessionManager `
                    -Name PendingFileRenameOperations -ErrorAction SilentlyContinue).PendingFileRenameOperations
                $pendingText = @($pendingMoves) -join "`n"
                $alreadyScheduled = (
                    $pendingText.IndexOf($pendingDll, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
                    $pendingText.IndexOf($targetDll, [StringComparison]::OrdinalIgnoreCase) -ge 0
                )
                if (-not $alreadyScheduled) {
                    $moveFileDelayUntilReboot = 0x4
                    $moveFileReplaceExisting = 0x1
                    $scheduled = [SmartPriorityNativeMethods]::MoveFileEx(
                        $pendingDll,
                        $targetDll,
                        $moveFileDelayUntilReboot -bor $moveFileReplaceExisting
                    )
                    if (-not $scheduled) {
                        $win32Error = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
                        throw "Unable to schedule the $architecture native UI update (Win32 $win32Error)."
                    }
                }
                $nativeUpdatePending = $true
                $nativeHashes[$architecture + "Pending"] = $true
            }
            $nativeHashes[$architecture] = $sourceHash
        }
        $nativeHashes | ConvertTo-Json | Set-Content `
            -LiteralPath (Join-Path $nativeStateRoot "native-ui.json") -Encoding UTF8
        if ($nativeUpdatePending) {
            Write-Output "The modern candidate UI will finish installing after the next Windows restart."
        }
    }
    Save-SmartPriorityNativeUiPreference `
        -PreferencePath $nativePreferencePath -Enabled $useUnsignedNativeUi

    $x86Dll = Join-Path $resolvedRoot "x86\PIMETextService.dll"
    $x64Dll = Join-Path $resolvedRoot "x64\PIMETextService.dll"
    if (Test-Path -LiteralPath $x86Dll) {
        & (Join-Path $env:WINDIR "SysWOW64\regsvr32.exe") /s $x86Dll
        if ($LASTEXITCODE -ne 0) { throw "The 32-bit PIME profile registration failed." }
    }
    if (Test-Path -LiteralPath $x64Dll) {
        & (Join-Path $env:WINDIR "System32\regsvr32.exe") /s $x64Dll
        if ($LASTEXITCODE -ne 0) { throw "The 64-bit PIME profile registration failed." }
    }

    $languages = Get-WinUserLanguageList
    $language = $languages | Where-Object {
        $_.LanguageTag -in @("zh-Hant-TW", "zh-TW")
    } | Select-Object -First 1
    if (-not $language) {
        $language = (New-WinUserLanguageList "zh-Hant-TW")[0]
        $languages.Add($language)
    }
    $languageListChanged = $false
    if ($language.InputMethodTips -contains $tip) {
        if ($language.InputMethodTips[0] -ne $tip) {
            $language.InputMethodTips.Remove($tip) | Out-Null
            $language.InputMethodTips.Insert(0, $tip)
            $languageListChanged = $true
        }
    }
    else {
        $language.InputMethodTips.Insert(0, $tip)
        $languageListChanged = $true
    }
    if ($languageListChanged) {
        Set-WinUserLanguageList -LanguageList $languages -Force
    }
    Set-WinDefaultInputMethodOverride -InputTip $tip
    if ($installedPimeThisRun) {
        $chewingTip = "0404:{35F67E9D-A54D-4177-9697-8B0AB71A9E04}{F80736AA-28DB-423A-92C9-5540F501C939}"
        $chewingListChanged = $false
        foreach ($item in $languages) {
            if ($item.InputMethodTips -contains $chewingTip) {
                $item.InputMethodTips.Remove($chewingTip) | Out-Null
                $chewingListChanged = $true
            }
        }
        if ($chewingListChanged) {
            Set-WinUserLanguageList -LanguageList $languages -Force
        }
        $chewingGuid = "{F80736AA-28DB-423A-92C9-5540F501C939}"
        $textServiceGuid = "{35F67E9D-A54D-4177-9697-8B0AB71A9E04}"
        $profileKeys = @(
            "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\CTF\TIP\$textServiceGuid\LanguageProfile\0x00000404\$chewingGuid",
            "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\CTF\TIP\$textServiceGuid\LanguageProfile\0x00000404\$chewingGuid"
        )
        foreach ($profileKey in $profileKeys) {
            if (Test-Path -LiteralPath $profileKey) {
                Remove-Item -LiteralPath $profileKey -Recurse -Force
            }
        }
    }

    # Explorer owns the normal desktop token, so this starts PIME without
    # accidentally leaving the launcher elevated.
    if (Test-Path -LiteralPath $launcher) {
        Start-Process -FilePath "explorer.exe" -ArgumentList ('"' + $launcher + '"')
    }
    Write-Output "Installed: $targetModule"
}
catch {
    # The failure dialog points users at this log, but an uncaught error only
    # prints after the finally below has stopped the transcript, so the log
    # ended empty on the first real-user failure. Record the error, then
    # rethrow: the NSIS details pane still shows it and the exit code stays
    # nonzero.
    Write-Output "安裝失敗: $($_.Exception.Message)"
    Write-Output $_.InvocationInfo.PositionMessage
    Write-Output $_.ScriptStackTrace
    throw
}
finally {
    Stop-Transcript | Out-Null
}
