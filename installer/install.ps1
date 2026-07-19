param(
    [Parameter(Mandatory = $true)]
    [string]$PayloadRoot
)

$ErrorActionPreference = "Stop"
$tip = "0404:{35F67E9D-A54D-4177-9697-8B0AB71A9E04}{26EA5CF3-D515-40BE-9535-E7E98D5EE554}"
$moduleName = "pinned_bopomofo"
$logRoot = Join-Path $env:ProgramData "SmartPriorityBopomofo"
$logPath = Join-Path $logRoot "install.log"
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
    $installRoot = $null
    foreach ($registryPath in $registryPaths) {
        if (Test-Path -LiteralPath $registryPath) {
            $installRoot = (Get-Item -LiteralPath $registryPath).GetValue("")
            if ($installRoot) { break }
        }
    }

    # PIME is shared infrastructure. Install the bundled signed version only
    # when no PIME is present; never downgrade or replace an existing version.
    if (-not $installRoot) {
        $process = Start-Process -FilePath $pimeInstaller -ArgumentList "/S" -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "PIME installation failed with exit code $($process.ExitCode)."
        }
        $installedPimeThisRun = $true
        foreach ($registryPath in $registryPaths) {
            if (Test-Path -LiteralPath $registryPath) {
                $installRoot = (Get-Item -LiteralPath $registryPath).GetValue("")
                if ($installRoot) { break }
            }
        }
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

    $targetParent = Join-Path $resolvedRoot "python\input_methods"
    $targetModule = Join-Path $targetParent $moduleName
    $expectedTarget = [IO.Path]::GetFullPath((Join-Path $resolvedRoot "python\input_methods\$moduleName"))
    if ([IO.Path]::GetFullPath($targetModule) -ne $expectedTarget) {
        throw "Refusing to write to an unexpected module path."
    }
    if (Test-Path -LiteralPath $targetModule) {
        Remove-Item -LiteralPath $targetModule -Recurse -Force
    }
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
finally {
    Stop-Transcript | Out-Null
}
