$ErrorActionPreference = "Stop"
$tip = "0404:{35F67E9D-A54D-4177-9697-8B0AB71A9E04}{26EA5CF3-D515-40BE-9535-E7E98D5EE554}"
$profileGuid = "{26EA5CF3-D515-40BE-9535-E7E98D5EE554}"
$textServiceGuid = "{35F67E9D-A54D-4177-9697-8B0AB71A9E04}"
$moduleName = "pinned_bopomofo"
$logRoot = Join-Path $env:ProgramData "SmartPriorityBopomofo"
$logPath = Join-Path $logRoot "uninstall.log"
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
