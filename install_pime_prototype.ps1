$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $projectRoot "vendor\PIME-1.3.0-stable-setup.exe"
$overlayModule = Join-Path $projectRoot "dist\PIME-overlay\python\input_methods\pinned_bopomofo"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"' + $MyInvocation.MyCommand.Path + '"')
    )
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments -Wait
    $installedLauncher = "C:\Program Files (x86)\PIME\PIMELauncher.exe"
    if (Test-Path -LiteralPath $installedLauncher) {
        Start-Process -FilePath $installedLauncher -WindowStyle Hidden
    }
    exit 0
}

$transcriptPath = Join-Path $projectRoot "install.log"
Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
$stagePath = Join-Path $projectRoot "install-stage.log"
$errorPath = Join-Path $projectRoot "install-error.log"
Set-Content -LiteralPath $errorPath -Value "" -Encoding UTF8
Set-Content -LiteralPath $stagePath -Value "admin-start" -Encoding UTF8
trap {
    ($_ | Out-String) | Set-Content -LiteralPath $errorPath -Encoding UTF8
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}

if (-not (Test-Path -LiteralPath $installer)) {
    throw "找不到官方 PIME 安裝程式：$installer"
}
Add-Content -LiteralPath $stagePath -Value "inputs-found" -Encoding UTF8
if (-not (Test-Path -LiteralPath $overlayModule)) {
    throw "找不到已建置的 PIME 模組：$overlayModule"
}

$signature = Get-AuthenticodeSignature -LiteralPath $installer
if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
    throw "PIME 官方安裝程式的數位簽章無效：$($signature.Status)"
}
Add-Content -LiteralPath $stagePath -Value "signature-valid" -Encoding UTF8

$installRoot = $null
$registryPaths = @(
    "HKLM:\Software\PIME",
    "HKLM:\Software\WOW6432Node\PIME"
)
foreach ($registryPath in $registryPaths) {
    if (Test-Path -LiteralPath $registryPath) {
        $installRoot = (Get-Item -LiteralPath $registryPath).GetValue("")
        if ($installRoot) { break }
    }
}

if (-not $installRoot) {
    $process = Start-Process -FilePath $installer -ArgumentList "/S" -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "PIME 安裝失敗，結束碼：$($process.ExitCode)"
    }
    foreach ($registryPath in $registryPaths) {
        if (Test-Path -LiteralPath $registryPath) {
            $installRoot = (Get-Item -LiteralPath $registryPath).GetValue("")
            if ($installRoot) { break }
        }
    }
}

if (-not $installRoot -or -not (Test-Path -LiteralPath $installRoot)) {
    throw "無法取得 PIME 安裝位置"
}
Add-Content -LiteralPath $stagePath -Value "install-root-found:$installRoot" -Encoding UTF8

$resolvedInstallRoot = (Resolve-Path -LiteralPath $installRoot).Path
$allowedRoots = @(
    [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles),
    [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFilesX86)
) | Where-Object { $_ }
$isAllowed = $false
foreach ($allowedRoot in $allowedRoots) {
    if ($resolvedInstallRoot.StartsWith($allowedRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
        $isAllowed = $true
        break
    }
}
if (-not $isAllowed) {
    throw "PIME 安裝路徑不在 Program Files 內，已停止：$resolvedInstallRoot"
}
Add-Content -LiteralPath $stagePath -Value "install-root-allowed" -Encoding UTF8

$launcher = Join-Path $resolvedInstallRoot "PIMELauncher.exe"
if (Test-Path -LiteralPath $launcher) {
    Add-Content -LiteralPath $stagePath -Value "stopping-launcher" -Encoding UTF8
    Start-Process -FilePath $launcher -ArgumentList "/quit" -Wait
}
Add-Content -LiteralPath $stagePath -Value "launcher-stopped" -Encoding UTF8

$targetParent = Join-Path $resolvedInstallRoot "python\input_methods"
$targetModule = Join-Path $targetParent "pinned_bopomofo"
if (-not $targetModule.StartsWith($resolvedInstallRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "模組目標路徑超出 PIME 安裝目錄"
}
New-Item -ItemType Directory -Path $targetModule -Force | Out-Null
Get-ChildItem -LiteralPath $overlayModule -Force |
    Copy-Item -Destination $targetModule -Recurse -Force
Add-Content -LiteralPath $stagePath -Value "module-copied" -Encoding UTF8

$embeddedPython = Join-Path $resolvedInstallRoot "python\python3\python.exe"
if (Test-Path -LiteralPath $embeddedPython) {
    & $embeddedPython -m compileall -q $targetModule
}
Add-Content -LiteralPath $stagePath -Value "module-compiled" -Encoding UTF8

$x86Dll = Join-Path $resolvedInstallRoot "x86\PIMETextService.dll"
$x64Dll = Join-Path $resolvedInstallRoot "x64\PIMETextService.dll"
if (Test-Path -LiteralPath $x86Dll) {
    & (Join-Path $env:WINDIR "SysWOW64\regsvr32.exe") /s $x86Dll
    if ($LASTEXITCODE -ne 0) { throw "32 位元 PIME profile 註冊失敗" }
}
if (Test-Path -LiteralPath $x64Dll) {
    & (Join-Path $env:WINDIR "System32\regsvr32.exe") /s $x64Dll
    if ($LASTEXITCODE -ne 0) { throw "64 位元 PIME profile 註冊失敗" }
}
Add-Content -LiteralPath $stagePath -Value "profiles-registered" -Encoding UTF8

Add-Content -LiteralPath $stagePath -Value "complete" -Encoding UTF8

Write-Output "PIME_ROOT=$resolvedInstallRoot"
Write-Output "MODULE=$targetModule"
Write-Output "GUID={26EA5CF3-D515-40BE-9535-E7E98D5EE554}"
Stop-Transcript | Out-Null
