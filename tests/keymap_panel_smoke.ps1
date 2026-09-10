# 按鍵配置分頁真的改得動鍵位，不只是「按了不會爆」。
#
# 這裡要守住的最重要一件事，不是儲存有沒有成功，而是**壞掉的配置不會被存下來**。
# 控制台存下一份打不出某個音的配置，使用者要到某天打到那個字才會發現，而那時候
# 已經沒有任何東西能把它連回幾天前改過的設定。
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$failures = New-Object System.Collections.Generic.List[string]
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { $failures.Add($Message) }
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$modulePath = Join-Path $projectRoot "control_panel\modules\60-keymap.ps1"
if (-not (Test-Path -LiteralPath $modulePath)) { throw "找不到按鍵配置模組：$modulePath" }

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "找不到 python，無法驗證按鍵配置分頁的接線" }

$sandbox = Join-Path ([IO.Path]::GetTempPath()) ("keymap-panel-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $sandbox -Force | Out-Null

$restartCalled = @{ Count = 0 }
$context = [pscustomobject]@{
    StateRoot    = $sandbox
    PimeRoot     = $projectRoot
    ModuleRoot   = $projectRoot
    PythonPath   = $python
    LauncherPath = "C:\nonexistent\PIMELauncher.exe"
    RestartPime  = { param([string]$LauncherPath)
        $restartCalled.Count++
        return @{ Success = $true; Message = "（測試）已重啟 PIME。" }
    }.GetNewClosure()
    UiFont       = (New-Object System.Drawing.Font("Microsoft JhengHei UI", 9))
    MonoFont     = (New-Object System.Drawing.Font("Consolas", 9))
}

# 分頁預設寫到 %APPDATA%，測試不能去動使用者真正的鍵位設定。改掉 APPDATA 之後
# 子行程也會拿到這一份，因為工具是從環境變數解析路徑的。
# 路徑要跟 keymap.layout_path() 完全一致（多一層 PinnedBopomofo）——第一版少了
# 那一層，於是「被拒絕的配置沒有寫進檔案」這條斷言檢查的是一個永遠不存在的路徑，
# 也就是永遠會通過。
$originalAppData = $env:APPDATA
$env:APPDATA = $sandbox
$layoutPath = Join-Path $sandbox "PinnedBopomofo\keymap.json"

function Get-Descendant {
    # $Text 不能宣告成 [string]：呼叫端傳 $null 會被轉成空字串，於是「不限
    # 文字」變成「只找文字是空的」，找不到目標時回傳 $null，接著每一條依賴
    # 它的斷言都拿空字串去比對——測試看起來在跑，其實什麼都沒檢查到。
    param($Control, [string]$Type, $Text)
    foreach ($child in $Control.Controls) {
        if ($child.GetType().Name -eq $Type -and
            ($null -eq $Text -or $child.Text -like $Text)) { return $child }
        $found = Get-Descendant -Control $child -Type $Type -Text $Text
        if ($found) { return $found }
    }
    return $null
}

try {
    $definition = & $modulePath
    if ($definition -is [array]) { $definition = $definition[-1] }
    $panel = & $definition.Build $context

    $grid = Get-Descendant -Control $panel -Type "DataGridView" -Text $null
    $status = Get-Descendant -Control $panel -Type "Label" -Text $null
    $save = Get-Descendant -Control $panel -Type "Button" -Text "*儲存*"
    $reset = Get-Descendant -Control $panel -Type "Button" -Text "*還原*"

    Assert-True ($null -ne $grid) "找不到鍵位表格"
    Assert-True ($null -ne $save) "找不到儲存按鈕"
    Assert-True ($null -ne $reset) "找不到還原按鈕"

    if ($grid -and $save -and $reset) {
        Assert-True ($grid.Rows.Count -eq 42) "鍵位表格應有 42 列，實際 $($grid.Rows.Count) 列"
        Assert-True ($status.Text -match "大千") "沒有顯示目前使用的是內建大千：$($status.Text)"

        # 注音符號要原封不動地穿過 JSON 抵達表格。子行程的輸出跟著主控台字碼頁
        # 走，CI 上是 cp1252，ㄅ 直接 UnicodeEncodeError 讓輸出整個變空。
        $firstSymbol = [string]$grid.Rows[0].Cells["symbol"].Value
        Assert-True ($firstSymbol -eq "ㄅ") "第一列的注音沒有正確傳回：'$firstSymbol'"
        Assert-True ([string]$grid.Rows[0].Cells["key"].Value -eq "1") `
            "ㄅ 的預設鍵位不是 1：'$($grid.Rows[0].Cells['key'].Value)'"

        # --- 壞掉的配置不能被存下來 -------------------------------------
        # 把 ㄆ 也設成 1。翻轉後 ㄆ 會消失，配置變成打不出 ㄆ。
        $rowForPo = $null
        foreach ($row in $grid.Rows) {
            if ([string]$row.Cells["symbol"].Value -eq "ㄆ") { $rowForPo = $row; break }
        }
        Assert-True ($null -ne $rowForPo) "表格裡找不到 ㄆ"
        if ($rowForPo) {
            $rowForPo.Cells["key"].Value = "1"
            $save.PerformClick()
            Assert-True ($status.Text -match "沒有存檔") "撞鍵的配置竟然被接受了：$($status.Text)"
            Assert-True ($status.Text -match "ㄅ" -and $status.Text -match "ㄆ") `
                "錯誤訊息沒有指出是哪兩個符號撞在一起：$($status.Text)"
            Assert-True (-not (Test-Path -LiteralPath $layoutPath)) "被拒絕的配置竟然寫進了檔案"
            Assert-True ($restartCalled.Count -eq 0) "沒存成功卻重啟了 PIME"
        }

        # --- 合法的配置要存得起來，而且要重啟 PIME ----------------------
        $rowForPo.Cells["key"].Value = "q"     # ㄆ 回到原位
        $grid.Rows[0].Cells["key"].Value = "0" # ㄅ 搬到 0
        $rowForAn = $null
        foreach ($row in $grid.Rows) {
            if ([string]$row.Cells["symbol"].Value -eq "ㄢ") { $rowForAn = $row; break }
        }
        $rowForAn.Cells["key"].Value = "1"     # ㄢ 接手 1，避免撞鍵

        $save.PerformClick()
        Assert-True ($status.Text -match "已儲存") "合法的配置沒有存成功：$($status.Text)"
        Assert-True ($restartCalled.Count -eq 1) "存檔後沒有重啟 PIME，改了鍵位卻看不出差別"
        # 檔案不在就不要再往下讀。硬丟例外會把前面收集到的 FAIL 訊息全部蓋掉，
        # 只留一句「找不到檔案」——真正的原因在那些訊息裡。
        Assert-True (Test-Path -LiteralPath $layoutPath) `
            "配置檔沒有被寫出來（$layoutPath）。狀態列：$($status.Text)"
        if (Test-Path -LiteralPath $layoutPath) {
            $bytes = [IO.File]::ReadAllBytes($layoutPath)
            $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
            Assert-True (-not $hasBom) "寫出的 keymap.json 帶了 BOM，PIMELauncher 會無聲地起不來"

            $written = [IO.File]::ReadAllText($layoutPath, [Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
            Assert-True ($written.keys."0" -eq "ㄅ") "存出來的配置沒有把 ㄅ 放到 0"
        }

        # --- 還原 --------------------------------------------------------
        $reset.PerformClick()
        Assert-True (-not (Test-Path -LiteralPath $layoutPath)) "還原沒有刪掉自訂配置"
        Assert-True ([string]$grid.Rows[0].Cells["key"].Value -eq "1") "還原後表格沒有回到大千鍵位"
    }
    $panel.Dispose()
}
finally {
    $env:APPDATA = $originalAppData
    Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) { Write-Output "FAIL: $failure" }
    throw "keymap_panel_smoke 有 $($failures.Count) 項失敗。"
}
Write-Output "PASS: 按鍵配置分頁拒絕撞鍵、存得下合法配置、重啟 PIME、還原得回大千"
