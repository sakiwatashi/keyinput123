$ErrorActionPreference = "Stop"
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
        if (Test-Path -LiteralPath $targetModule) {
            Remove-Item -LiteralPath $targetModule -Recurse -Force
        }

        $nativeMarker = Join-Path $nativeStateRoot "native-ui.json"
        $backupRoot = Join-Path $nativeStateRoot "backup"
        $pendingRoot = Join-Path $nativeStateRoot "pending"
        if ((Test-Path -LiteralPath $nativeMarker) -and (Test-Path -LiteralPath $backupRoot)) {
            $nativeHashes = Get-Content -LiteralPath $nativeMarker -Raw -Encoding UTF8 |
                ConvertFrom-Json
            $nativeStateCanBeRemoved = $true
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
                $targetDll = Join-Path $resolvedRoot "$architecture\PIMETextService.dll"
                $backupDll = Join-Path $backupRoot "$architecture\PIMETextService.dll"
                $pendingDll = Join-Path $pendingRoot "$architecture\PIMETextService.dll"
                $expectedHash = $nativeHashes.$architecture
                if ((Test-Path -LiteralPath $targetDll) -and
                    (Test-Path -LiteralPath $backupDll) -and
                    $expectedHash -and
                    (Get-FileHash -Algorithm SHA256 -LiteralPath $targetDll).Hash -eq $expectedHash) {
                    try {
                        Copy-Item -LiteralPath $backupDll -Destination $targetDll -Force
                    }
                    catch [System.IO.IOException], [System.UnauthorizedAccessException] {
                        $restoreDll = Join-Path $nativeStateRoot "restore\$architecture\PIMETextService.dll"
                        New-Item -ItemType Directory -Path (Split-Path -Parent $restoreDll) -Force | Out-Null
                        Copy-Item -LiteralPath $backupDll -Destination $restoreDll -Force
                        $scheduled = [SmartPriorityNativeMethods]::MoveFileEx(
                            $restoreDll,
                            $targetDll,
                            0x4 -bor 0x1
                        )
                        if (-not $scheduled) {
                            $win32Error = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
                            throw "Unable to schedule the $architecture native UI restore (Win32 $win32Error)."
                        }
                        $nativeStateCanBeRemoved = $false
                    }
                }
                elseif ($nativeHashes.($architecture + "Pending") -and
                    (Test-Path -LiteralPath $pendingDll)) {
                    # Removing the persistent source cancels a replacement
                    # that Windows has not performed yet.
                    Remove-Item -LiteralPath $pendingDll -Force
                }
                else {
                    # A third party changed the shared DLL. Preserve our
                    # backup rather than overwriting or deleting evidence.
                    $nativeStateCanBeRemoved = $false
                }
            }
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
            if ($nativeStateCanBeRemoved -and (Test-Path -LiteralPath $nativeStateRoot)) {
                Remove-Item -LiteralPath $nativeStateRoot -Recurse -Force
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
    $shortcutPath = Join-Path $shortcutRoot "轉換錯誤回報工具.lnk"
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
    }
    if ((Test-Path -LiteralPath $shortcutRoot) -and
        -not (Get-ChildItem -LiteralPath $shortcutRoot -Force)) {
        Remove-Item -LiteralPath $shortcutRoot -Force
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
finally {
    Stop-Transcript | Out-Null
}
