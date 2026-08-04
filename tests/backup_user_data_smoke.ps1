# 備份要真的能還原，要輪替，而且不能每次跑都多一份一樣的。
#
# 「有備份」跟「還原得回來」是兩件事。這支測試會把壓縮檔解開，確認 JSON 解析
# 得出來——沒驗證過能還原的備份只是佔空間。
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $root "tools\backup_user_data.ps1"
$failures = New-Object System.Collections.Generic.List[string]
if (-not (Test-Path -LiteralPath $tool)) { throw "找不到 tools\backup_user_data.ps1" }

$sandbox = Join-Path ([IO.Path]::GetTempPath()) ("backup-" + [Guid]::NewGuid().ToString("N"))
$state = Join-Path $sandbox "state"
$backups = Join-Path $sandbox "backups"
New-Item -ItemType Directory -Path $state -Force | Out-Null
try {
    $phrases = Join-Path $state "phrases.json"
    [IO.File]::WriteAllText($phrases, '{"ㄋㄧˇ ㄏㄠˇ":"你好"}', (New-Object Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText((Join-Path $state "pins.json"), '{"ㄉㄜ˙":["的"]}', (New-Object Text.UTF8Encoding($false)))
    # 可再生的大檔案不該被收進備份。
    [IO.File]::WriteAllText((Join-Path $state "keyevent-trace.log"), ("x" * 5000), (New-Object Text.UTF8Encoding($false)))

    & $tool -StateRoot $state -BackupRoot $backups -Keep 3 | Out-Null
    $made = @(Get-ChildItem -LiteralPath $backups -Filter "*.zip" -File)
    if ($made.Count -ne 1) { $failures.Add("第一次備份應該產生 1 個壓縮檔，實際 $($made.Count) 個") }

    # --- 真的還原得回來嗎 ---------------------------------------------------
    if ($made.Count -ge 1) {
        $restore = Join-Path $sandbox "restore"
        Expand-Archive -LiteralPath $made[0].FullName -DestinationPath $restore -Force
        $restored = Join-Path $restore "phrases.json"
        if (-not (Test-Path -LiteralPath $restored)) {
            $failures.Add("備份裡沒有 phrases.json")
        }
        else {
            try {
                $value = Get-Content -LiteralPath $restored -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($value.'ㄋㄧˇ ㄏㄠˇ' -ne "你好") { $failures.Add("還原出來的內容不對") }
            }
            catch { $failures.Add("還原出來的 phrases.json 解析失敗：$($_.Exception.Message)") }
        }
        if (Test-Path -LiteralPath (Join-Path $restore "keyevent-trace.log")) {
            $failures.Add("可再生的追蹤記錄檔被收進備份了，會白白撐大每一份")
        }
    }

    # --- 內容沒變就不該再產生一份 -------------------------------------------
    & $tool -StateRoot $state -BackupRoot $backups -Keep 3 | Out-Null
    if (@(Get-ChildItem -LiteralPath $backups -Filter "*.zip" -File).Count -ne 1) {
        $failures.Add("資料沒變動卻又產生一份備份")
    }

    # --- 內容變了就要有新的一份 ---------------------------------------------
    Start-Sleep -Seconds 1   # 檔名用到秒，同一秒會撞名
    [IO.File]::WriteAllText($phrases, '{"ㄋㄧˇ ㄏㄠˇ":"妳好"}', (New-Object Text.UTF8Encoding($false)))
    & $tool -StateRoot $state -BackupRoot $backups -Keep 3 | Out-Null
    if (@(Get-ChildItem -LiteralPath $backups -Filter "*.zip" -File).Count -ne 2) {
        $failures.Add("資料變動了卻沒有產生新的備份")
    }

    # --- 輪替：超過 Keep 就要刪掉最舊的 -------------------------------------
    foreach ($index in 3..5) {
        Start-Sleep -Seconds 1
        [IO.File]::WriteAllText($phrases, ('{"a":"' + $index + '"}'), (New-Object Text.UTF8Encoding($false)))
        & $tool -StateRoot $state -BackupRoot $backups -Keep 3 | Out-Null
    }
    $kept = @(Get-ChildItem -LiteralPath $backups -Filter "*.zip" -File)
    if ($kept.Count -ne 3) { $failures.Add("Keep 3 之下應該只剩 3 份，實際 $($kept.Count) 份") }

    # --- 清理前備份也要輪替 -------------------------------------------------
    foreach ($index in 1..6) {
        [IO.File]::WriteAllText((Join-Path $state "phrases.json.before-prune-2026080$index-000000"), "{}",
            (New-Object Text.UTF8Encoding($false)))
    }
    Start-Sleep -Seconds 1
    [IO.File]::WriteAllText($phrases, '{"a":"z"}', (New-Object Text.UTF8Encoding($false)))
    & $tool -StateRoot $state -BackupRoot $backups -Keep 3 | Out-Null
    $strays = @(Get-ChildItem -LiteralPath $state -Filter "*.before-prune-*" -File)
    if ($strays.Count -gt 3) {
        $failures.Add("清理前備份沒有輪替，還剩 $($strays.Count) 份")
    }
}
finally {
    Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) { Write-Output "FAIL: $failure" }
    throw "backup_user_data_smoke 有 $($failures.Count) 項失敗。"
}
Write-Output "PASS: 備份能還原、內容沒變不重複產生、超過保留數會輪替"
