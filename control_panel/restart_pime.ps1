# 重啟 PIME，並且據實回報結果。
#
# 這支存在的原因是一次真實事故：控制台與診斷腳本原本以
# Stop-Process + Start-Process 重啟 PIME，然後**不檢查**就回報「已重啟」。
# PIMELauncher 啟動失敗時（實測結束碼 0xC0000409，Windows 錯誤報告裡什麼
# 都沒有）使用者的輸入法就此消失，而畫面上顯示的是成功。使用者以為自己
# 「卡在英文」，實際上輸入法根本沒在跑，診斷因此往完全錯誤的方向走了很久。
#
# 規則：
#   1. 用 /quit 請它自己收工，不要 Stop-Process 硬砍
#   2. 啟動之後一定要確認行程真的還活著
#   3. 沒起來就明講，並告訴使用者重開機——PIMELauncher 登記在
#      HKLM\...\Run，登入時本來就會自動啟動，那是它被支援的路徑

function Restart-Pime {
    <#
        .SYNOPSIS
        重啟 PIME，回傳 @{ Success = [bool]; Message = [string] }。
        呼叫端必須把 Message 顯示出來，不要自己編一句「已重啟」。
    #>
    param([string]$LauncherPath)

    if (-not $LauncherPath -or -not (Test-Path -LiteralPath $LauncherPath)) {
        return @{
            Success = $false
            Message = "找不到 PIMELauncher.exe，設定要等下次重新啟動 PIME 才會生效。"
        }
    }

    # /quit 讓它自己關閉具名管道並收拾狀態。硬砍會留下半開的連線。
    try {
        Start-Process -FilePath $LauncherPath -ArgumentList "/quit" -Wait -ErrorAction Stop
    }
    catch {
        # 已經沒在跑也算數，繼續往下啟動。
    }
    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline -and (Get-Process -Name PIMELauncher -ErrorAction SilentlyContinue)) {
        Start-Sleep -Milliseconds 200
    }

    try {
        $process = Start-Process -FilePath $LauncherPath -PassThru -ErrorAction Stop
    }
    catch {
        return @{
            Success = $false
            Message = "PIMELauncher 無法啟動：$($_.Exception.Message)。請重新開機——它登記在系統的自動啟動項，登入時會自己起來。"
        }
    }

    # 關鍵的一步。啟動指令成功不等於行程活著。
    #
    # 盯著 Start-Process 回傳的那個行程，而不是用名稱去找：同名的別的行程會
    # 讓判斷失準。也不能一看到它還在就算過關 —— 程式啟動本來就要幾百毫秒，
    # 太早看一定是活的。實測崩潰的 PIMELauncher 在兩秒內就結束，所以等滿再看。
    Start-Sleep -Seconds 2
    $process.Refresh()
    if (-not $process.HasExited) {
        return @{ Success = $true; Message = "PIME 已重啟。" }
    }

    return @{
        Success = $false
        Message = ("PIMELauncher 啟動後立刻結束，輸入法目前沒有在執行。" +
                   "請重新開機——它登記在系統的自動啟動項，登入時會自己起來。" +
                   "（若此電腦有防作弊軟體常駐，它可能正在阻擋這個行程。）")
    }
}
