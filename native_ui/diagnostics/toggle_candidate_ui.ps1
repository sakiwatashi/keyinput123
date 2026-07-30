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
    if (-not (Test-Path -LiteralPath $configPath)) { return $false }
    try {
        $value = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        return [bool]$value.enabled
    }
    catch {
        # A damaged preference means off, matching the module's own reading.
        return $false
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
    if (Test-Path -LiteralPath $configPath) {
        Remove-Item -LiteralPath $configPath -Force
    }
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
