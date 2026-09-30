# install.ps1 從原始碼更新時，「應用程式」清單的版本號也要跟上。
#
# 實際跑 Sync-UninstallEntry，用 HKCU 底下的暫存登錄鍵與暫存資料夾，不碰真的 HKLM。
# 守的是 tools/sync_uninstall_entry.ps1 開頭寫的那幾條：兩個檢視都找、不憑空建紀錄、
# 沒有 Uninstall.exe 不動、檔案全部換好才改版本號。
$ErrorActionPreference = "Stop"

$projectRoot = Join-Path $PSScriptRoot ".."
. (Join-Path (Join-Path $projectRoot "tools") "sync_uninstall_entry.ps1")

$problems = @()
$tag = [Guid]::NewGuid().ToString("N")
$registryRoot = "HKCU:\Software\SmartPriorityBopomofoTest-$tag"
$fileRoot = Join-Path $env:TEMP "uninstall-entry-$tag"

function New-Entry {
    param([string]$Name, [bool]$WithUninstaller)
    $dir = Join-Path $fileRoot $Name
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $dir "uninstall.ps1") -Value "old" -Encoding ASCII
    if ($WithUninstaller) {
        Set-Content -LiteralPath (Join-Path $dir "Uninstall.exe") -Value "stub" -Encoding ASCII
    }
    $key = Join-Path $registryRoot $Name
    New-Item -Path $key -Force | Out-Null
    New-ItemProperty -LiteralPath $key -Name "DisplayVersion" -Value "0.6.5" -PropertyType String -Force | Out-Null
    New-ItemProperty -LiteralPath $key -Name "InstallLocation" -Value $dir -PropertyType String -Force | Out-Null
    return @{ Key = $key; Dir = $dir }
}

function Read-Version([string]$Key) { (Get-ItemProperty -LiteralPath $Key).DisplayVersion }
function Read-Script([string]$Dir) { (Get-Content -LiteralPath (Join-Path $Dir "uninstall.ps1") -Raw).Trim() }

try {
    $payloadDir = Join-Path $fileRoot "payload"
    New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null
    $newUninstall = Join-Path $payloadDir "uninstall.ps1"
    Set-Content -LiteralPath $newUninstall -Value "new" -Encoding ASCII

    # --- 1. 存在的紀錄：腳本換新、版本號更新；不存在的那個檢視不能被建立 ---
    $good = New-Entry -Name "Good" -WithUninstaller $true
    $missing = Join-Path $registryRoot "Missing"
    $result = Sync-UninstallEntry -Version "0.8.1" -RegistryPaths @($missing, $good.Key) -PayloadFiles @($newUninstall)
    if ((Read-Version $good.Key) -ne "0.8.1") { $problems += "存在的紀錄沒有被更新成 0.8.1" }
    if ((Read-Script $good.Dir) -ne "new") { $problems += "安裝目錄裡的 uninstall.ps1 沒有換成新版" }
    if (Test-Path -LiteralPath $missing) { $problems += "不存在的登錄檢視被憑空建立了" }
    if ($result.Updated -notcontains $good.Key) { $problems += "回傳值沒有列出更新的紀錄" }

    # --- 2. 安裝目錄裡沒有 Uninstall.exe：什麼都不動 ---
    $orphan = New-Entry -Name "NoUninstaller" -WithUninstaller $false
    $result = Sync-UninstallEntry -Version "0.8.1" -RegistryPaths @($orphan.Key) -PayloadFiles @($newUninstall)
    if ((Read-Version $orphan.Key) -ne "0.6.5") { $problems += "沒有 Uninstall.exe 的紀錄版本號被改了" }
    if ((Read-Script $orphan.Dir) -ne "old") { $problems += "沒有 Uninstall.exe 的安裝目錄被寫入了" }
    if ($result.Skipped.Count -ne 1) { $problems += "跳過的紀錄沒有被回報" }

    # --- 3. 檔案換到一半失敗：版本號不能先改 ---
    $broken = New-Entry -Name "BrokenPayload" -WithUninstaller $true
    $threw = $false
    try {
        Sync-UninstallEntry -Version "0.8.1" -RegistryPaths @($broken.Key) `
            -PayloadFiles @($newUninstall, (Join-Path $payloadDir "does-not-exist.ps1")) | Out-Null
    }
    catch { $threw = $true }
    if (-not $threw) { $problems += "缺檔時沒有丟出錯誤" }
    if ((Read-Version $broken.Key) -ne "0.6.5") { $problems += "檔案沒換完，版本號卻先改成新版了" }

    # --- 4. install.ps1 真的有接上，而且兩個檢視都有找 ---
    $install = Get-Content -LiteralPath (Join-Path $projectRoot "install.ps1") -Raw
    foreach ($needle in @("Sync-UninstallEntry", "WOW6432Node", "ime.json")) {
        if ($install -notmatch [regex]::Escape($needle)) { $problems += "install.ps1 少了 $needle" }
    }
}
finally {
    Remove-Item -LiteralPath $registryRoot -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $fileRoot -Recurse -Force -ErrorAction SilentlyContinue
}

if ($problems.Count -gt 0) {
    $problems | ForEach-Object { Write-Output "FAIL: $_" }
    throw "uninstall_entry_smoke 有 $($problems.Count) 項失敗。"
}
Write-Output "PASS: install.ps1 keeps the Apps list version and uninstall scripts in step"
