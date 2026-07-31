# Turns the out-of-process candidate window on or off.
#
# The preference is read once when the input method builds its mirror, because
# reading it during a key event would stall the host application's input
# thread. Applying a change therefore requires restarting PIME, which this
# script does.
param(
    [switch]$On,
    [switch]$Off,
    [switch]$Status
)

$ErrorActionPreference = "Stop"
$configDirectory = Join-Path $env:APPDATA "PinnedBopomofo"
$configPath = Join-Path $configDirectory "candidate-ui.json"
$launcher = "C:\Program Files (x86)\PIME\PIMELauncher.exe"

function Get-CandidateUiState {
    # 預設開啟：只有明確的 enabled: false 會關閉，與模組的讀取規則一致。
    if (-not (Test-Path -LiteralPath $configPath)) { return $true }
    try {
        $value = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($null -ne $value.enabled) { return [bool]$value.enabled }
        return $true
    }
    catch {
        # A damaged preference means the default (on), matching the module.
        return $true
    }
}

if ($Status -or (-not $On -and -not $Off)) {
    $state = if (Get-CandidateUiState) { "啟用" } else { "關閉" }
    Write-Output "行程外候選視窗: $state"
    Write-Output "偏好檔: $configPath"
    Write-Output ""
    Write-Output "開啟: ./toggle_candidate_ui.ps1 -On"
    Write-Output "關閉: ./toggle_candidate_ui.ps1 -Off"
    return
}

if ($On -and $Off) {
    throw "-On 與 -Off 不可同時使用。"
}

if ($On) {
    New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null
    @{ enabled = $true; version = 1 } | ConvertTo-Json |
        Set-Content -LiteralPath $configPath -Encoding UTF8
    Write-Output "已開啟。原廠候選框會縮成定位用的小方塊並被覆蓋。"
    Write-Output "若輔助程式未啟動,系統會自動退回原廠候選框,打字不受影響。"
}
else {
    # 預設是開啟，所以「關閉」必須寫入明確的 false；刪除偏好檔等於回到預設（開啟）。
    New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null
    @{ enabled = $false; version = 1 } | ConvertTo-Json |
        Set-Content -LiteralPath $configPath -Encoding UTF8
    Get-Process SmartPriorityCandidateUI -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.Id -Force }
    Write-Output "已關閉。打字行為回到與此功能不存在時完全相同。"
}

# Restart PIME so the input method rebuilds its mirror with the new preference.
if (Test-Path -LiteralPath $launcher) {
    Start-Process -FilePath $launcher -ArgumentList "/quit" -Wait
    Start-Sleep -Milliseconds 800
    # Explorer owns the normal desktop token, so this avoids leaving the
    # launcher running elevated when the script was started from an admin shell.
    Start-Process -FilePath "explorer.exe" -ArgumentList ('"' + $launcher + '"')
    Write-Output "PIME 已重新啟動,設定生效。"
}
else {
    Write-Output "找不到 PIMELauncher,請自行重新啟動 PIME 讓設定生效。"
}
