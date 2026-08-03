$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "restore_signed_text_service.ps1")

function Stop-SmartPriorityCandidateUiAndWait {
    # Stop-Process only signals termination; the executable stays locked
    # until the process has actually exited, and deleting the module
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
$profileGuid = "{26EA5CF3-D515-40BE-9535-E7E98D5EE554}"
$textServiceGuid = "{35F67E9D-A54D-4177-9697-8B0AB71A9E04}"
$moduleName = "pinned_bopomofo"
$logRoot = Join-Path $env:ProgramData "SmartPriorityBopomofo"
$logPath = Join-Path $logRoot "uninstall.log"
$nativeStateRoot = Join-Path $logRoot "native-state"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
Start-Transcript -LiteralPath $logPath -Force | Out-Null

try {
    $registryPaths = @(
        "HKLM:\Software\PIME",
        "HKLM:\Software\WOW6432Node\PIME"
    )
    $installRoot = $null
    foreach ($registryPath in $registryPaths) {
        if (Test-Path -LiteralPath $registryPath) {
            $installRoot = (Get-Item -LiteralPath $registryPath).GetValue("")
            if ($installRoot) { break }
        }
    }

    $launcher = $null
    if ($installRoot -and (Test-Path -LiteralPath $installRoot)) {
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
        $targetModule = Join-Path $resolvedRoot "python\input_methods\$moduleName"
        $expectedTarget = [IO.Path]::GetFullPath((Join-Path $resolvedRoot "python\input_methods\$moduleName"))
        if ([IO.Path]::GetFullPath($targetModule) -ne $expectedTarget) {
            throw "Refusing to remove an unexpected module path."
        }
        $launcher = Join-Path $resolvedRoot "PIMELauncher.exe"
        if (Test-Path -LiteralPath $launcher) {
            Start-Process -FilePath $launcher -ArgumentList "/quit" -Wait
        }
        # The candidate window helper keeps its own executable open inside the
        # module directory that is about to be removed.
        Stop-SmartPriorityCandidateUiAndWait
        Remove-DirectoryWithRetry -Path $targetModule

        if ((Test-Path -LiteralPath (Join-Path $nativeStateRoot "native-ui.json")) -and
            (Test-Path -LiteralPath (Join-Path $nativeStateRoot "backup"))) {
            Restore-OriginalPimeTextService `
                -PimeRoot $resolvedRoot `
                -StateRoot $nativeStateRoot | Out-Null
            foreach ($architecture in @("x86", "x64")) {
                $dll = Join-Path $resolvedRoot "$architecture\PIMETextService.dll"
                if (-not (Test-Path -LiteralPath $dll)) { continue }
                $regsvr = if ($architecture -eq "x86") {
                    Join-Path $env:WINDIR "SysWOW64\regsvr32.exe"
                } else {
                    Join-Path $env:WINDIR "System32\regsvr32.exe"
                }
                & $regsvr /s $dll
            }
        }
    }

    $languages = Get-WinUserLanguageList
    $changed = $false
    foreach ($language in $languages) {
        if ($language.InputMethodTips -contains $tip) {
            $language.InputMethodTips.Remove($tip) | Out-Null
            $changed = $true
        }
    }
    $override = Get-WinDefaultInputMethodOverride
    if ($override -and $override.InputMethodTip -eq $tip) {
        $fallback = $null
        foreach ($language in $languages) {
            if ($language.InputMethodTips.Count -gt 0) {
                $fallback = $language.InputMethodTips[0]
                break
            }
        }
        if ($fallback) {
            Set-WinDefaultInputMethodOverride -InputTip $fallback
        }
    }
    if ($changed) {
        Set-WinUserLanguageList -LanguageList $languages -Force
    }

    $programs = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
    $shortcutRoot = Join-Path $programs "智慧優先注音"
    foreach ($name in @("轉換錯誤回報工具.lnk", "智慧優先注音 控制台.lnk")) {
        $shortcutPath = Join-Path $shortcutRoot $name
        if (Test-Path -LiteralPath $shortcutPath) {
            Remove-Item -LiteralPath $shortcutPath -Force
        }
    }
    if ((Test-Path -LiteralPath $shortcutRoot) -and
        -not (Get-ChildItem -LiteralPath $shortcutRoot -Force)) {
        Remove-Item -LiteralPath $shortcutRoot -Force
    }

    $nativePreferencePath = Join-Path $logRoot "native-ui-preference.json"
    if (Test-Path -LiteralPath $nativePreferencePath) {
        Remove-Item -LiteralPath $nativePreferencePath -Force
    }

    # Remove only this language profile. PIME and every other PIME input
    # method are shared and must remain registered.
    $profileKeys = @(
        "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\CTF\TIP\$textServiceGuid\LanguageProfile\0x00000404\$profileGuid",
        "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\CTF\TIP\$textServiceGuid\LanguageProfile\0x00000404\$profileGuid"
    )
    foreach ($profileKey in $profileKeys) {
        if (Test-Path -LiteralPath $profileKey) {
            Remove-Item -LiteralPath $profileKey -Recurse -Force
        }
    }

    if ($launcher -and (Test-Path -LiteralPath $launcher)) {
        Start-Process -FilePath "explorer.exe" -ArgumentList ('"' + $launcher + '"')
    }
    Write-Output "Smart Priority Bopomofo was removed; PIME and user learning data were preserved."
}
catch {
    # Same reasoning as install.ps1: without this, an uncaught error surfaces
    # only after the transcript below has stopped, and the log the failure
    # dialog points at stays empty.
    Write-Output "解除安裝失敗: $($_.Exception.Message)"
    Write-Output $_.InvocationInfo.PositionMessage
    Write-Output $_.ScriptStackTrace
    throw
}
finally {
    Stop-Transcript | Out-Null
}
