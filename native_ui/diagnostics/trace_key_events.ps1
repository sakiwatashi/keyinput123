# Turns the key-callback trace on or off and shows what it captured.
#
# Written for one open question: inside a console window or a remote desktop
# client such as AnyDesk, which callbacks does TSF actually deliver? Two fixes
# for the Chinese/English toggle were built on guesses about that and both were
# wrong, so this measures it instead.
#
# The trace records callback names and whether a key was a modifier. It never
# records what was typed and never leaves this machine.
param(
    [switch]$On,
    [switch]$Off,
    [switch]$Show,
    [switch]$Clear
)

$ErrorActionPreference = "Stop"
$stateRoot = Join-Path $env:APPDATA "PinnedBopomofo"
$switchPath = Join-Path $stateRoot "keyevent-trace.json"
$logPath = Join-Path $stateRoot "keyevent-trace.log"
$launcher = Join-Path ${env:ProgramFiles(x86)} "PIME\PIMELauncher.exe"

function Restart-Pime {
    if (-not (Test-Path -LiteralPath $launcher)) {
        Write-Output "找不到 PIMELauncher，請自行重啟 PIME。"
        return
    }
    Get-Process -Name PIMELauncher -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 700
    Start-Process -FilePath $launcher | Out-Null
    Write-Output "已重啟 PIME。"
}

function Write-Switch([bool]$enabled) {
    New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
    # UTF-8 without a BOM: the module reads this with json, and a BOM makes
    # that fail silently, which would leave the switch stuck at its default.
    [IO.File]::WriteAllText($switchPath, (@{ enabled = $enabled } | ConvertTo-Json),
        (New-Object Text.UTF8Encoding($false)))
}

if ($On) {
    Write-Switch $true
    Restart-Pime
    Write-Output ""
    Write-Output "追蹤已開啟。接著請："
    Write-Output "  1. 連進 AnyDesk，在遠端的 CLI 視窗裡短按 Shift 兩三次"
    Write-Output "  2. 再按一次大寫鍵（那個有效，可以當對照）"
    Write-Output "  3. 回來執行： .\trace_key_events.ps1 -Show"
    Write-Output ""
    Write-Output "記錄檔：$logPath"
    Write-Output "測完請執行 -Off 關閉。"
    return
}

if ($Off) {
    Write-Switch $false
    Restart-Pime
    Write-Output "追蹤已關閉。記錄檔仍保留在 $logPath"
    return
}

if ($Clear) {
    if (Test-Path -LiteralPath $logPath) { Remove-Item -LiteralPath $logPath -Force }
    Write-Output "記錄檔已清除。"
    return
}

if ($Show -or $true) {
    $state = "關閉"
    if (Test-Path -LiteralPath $switchPath) {
        try {
            $value = Get-Content -LiteralPath $switchPath -Raw | ConvertFrom-Json
            if ($value.enabled) { $state = "開啟" }
        }
        catch { }
    }
    Write-Output "追蹤狀態: $state"
    Write-Output "記錄檔:   $logPath"
    Write-Output ""
    if (-not (Test-Path -LiteralPath $logPath)) {
        Write-Output "尚無記錄。先執行 .\trace_key_events.ps1 -On"
        return
    }
    $lines = Get-Content -LiteralPath $logPath
    Write-Output "共 $($lines.Count) 筆，以下是最後 60 筆："
    $lines | Select-Object -Last 60 | ForEach-Object { "  $_" }
    Write-Output ""
    Write-Output "判讀方式："
    Write-Output "  有 filterKeyUp + Shift        => 放開事件有送達，問題在別處"
    Write-Output "  只有 filterKeyDown + Shift    => 放開事件沒來，這就是原因"
    Write-Output "  有 onPreservedKey             => 保留鍵有效"
    Write-Output "  只有 onKeyboardStatusChanged  => 只有大寫鍵那條系統路徑會通"
}
