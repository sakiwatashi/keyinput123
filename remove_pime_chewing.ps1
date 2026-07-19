$ErrorActionPreference = "Stop"
$chewingTip = "0404:{35F67E9D-A54D-4177-9697-8B0AB71A9E04}{F80736AA-28DB-423A-92C9-5540F501C939}"
$profileGuid = "{F80736AA-28DB-423A-92C9-5540F501C939}"
$textServiceGuid = "{35F67E9D-A54D-4177-9697-8B0AB71A9E04}"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $process = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"' + $MyInvocation.MyCommand.Path + '"')
    )
    if ($process.ExitCode -ne 0) {
        throw "Removal failed with exit code $($process.ExitCode)."
    }
    $launcher = "C:\Program Files (x86)\PIME\PIMELauncher.exe"
    if (Test-Path -LiteralPath $launcher) {
        Start-Process -FilePath $launcher -WindowStyle Hidden
    }
    exit 0
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
if (-not $installRoot -or -not (Test-Path -LiteralPath $installRoot)) {
    throw "A valid PIME installation was not found."
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

$chewingModule = Join-Path $resolvedRoot "python\input_methods\chewing"
$expectedModule = [IO.Path]::GetFullPath((Join-Path $resolvedRoot "python\input_methods\chewing"))
if ([IO.Path]::GetFullPath($chewingModule) -ne $expectedModule) {
    throw "Refusing to remove an unexpected module path."
}
if (Test-Path -LiteralPath $chewingModule) {
    Remove-Item -LiteralPath $chewingModule -Recurse -Force
}

$languages = Get-WinUserLanguageList
$changed = $false
foreach ($language in $languages) {
    if ($language.InputMethodTips -contains $chewingTip) {
        $language.InputMethodTips.Remove($chewingTip) | Out-Null
        $changed = $true
    }
}
if ($changed) {
    Set-WinUserLanguageList -LanguageList $languages -Force
}

$profileKeys = @(
    "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\CTF\TIP\$textServiceGuid\LanguageProfile\0x00000404\$profileGuid",
    "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\CTF\TIP\$textServiceGuid\LanguageProfile\0x00000404\$profileGuid"
)
foreach ($profileKey in $profileKeys) {
    if (Test-Path -LiteralPath $profileKey) {
        Remove-Item -LiteralPath $profileKey -Recurse -Force
    }
}
