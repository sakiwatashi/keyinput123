# 按下控制台的每一個按鈕，任何一個丟出例外就失敗。
#
# 這支測試來自一次真實回報：什麼都沒輸入就按「列出這些字」，跳出
# 「不可在值為 Null 的運算式上呼叫方法」。原因是那個 TextBox 取名叫
# $input —— 那是 PowerShell 的自動變數（管線輸入列舉器），在事件處理程序
# 這種 scriptblock 裡會蓋掉同名的區域變數，於是 $input.Text 成了 null。
#
# 靜態檢查抓不到這種事，建構分頁也抓不到：控制項全部正常建立，錯誤只在
# 按下去的那一刻才發生。所以這裡真的去按。
#
# 安全性：$Context 指向暫存資料夾，PIMELauncher 路徑刻意指向不存在的檔案，
# 所以儲存只會寫到暫存區、重啟一律是無操作。不會碰到使用者的個人詞庫。
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$panelRoot = Join-Path $root "control_panel"
$moduleDirectory = Join-Path $panelRoot "modules"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
. (Join-Path $panelRoot "restart_pime.ps1")

$failures = New-Object System.Collections.Generic.List[string]

$sandbox = Join-Path ([IO.Path]::GetTempPath()) ("panel-buttons-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $sandbox -Force | Out-Null
try {
    $context = [pscustomobject]@{
        StateRoot    = $sandbox
        PimeRoot     = $null
        ModuleRoot   = $null
        LauncherPath = Join-Path $sandbox "no-such-launcher.exe"
        CandidateUi  = Join-Path $sandbox "candidate-ui.json"
        PhrasesPath  = Join-Path $sandbox "phrases.json"
        PinsPath     = Join-Path $sandbox "pins.json"
        RestartPime  = ${function:Restart-Pime}
        UiFont       = New-Object System.Drawing.Font("Microsoft JhengHei UI", 9)
        MonoFont     = New-Object System.Drawing.Font("Consolas", 9)
    }

    function Get-Buttons {
        param($control)
        $found = @()
        foreach ($child in $control.Controls) {
            if ($child -is [System.Windows.Forms.Button]) { $found += $child }
            if ($child.Controls.Count -gt 0) { $found += Get-Buttons $child }
            # 分頁裡的分頁（個人詞庫有兩頁）也要走進去。
            if ($child -is [System.Windows.Forms.TabControl]) {
                foreach ($page in $child.TabPages) { $found += Get-Buttons $page }
            }
        }
        return $found
    }

    $clicked = 0
    foreach ($file in Get-ChildItem -LiteralPath $moduleDirectory -Filter *.ps1 -File | Sort-Object Name) {
        $definition = & $file.FullName
        if ($definition -is [array]) { $definition = $definition[-1] }

        $holder = New-Object System.Windows.Forms.Form
        try {
            $control = & $definition.Build $context
            if (-not $control) { continue }
            $holder.Controls.Add($control)

            foreach ($button in (Get-Buttons $holder)) {
                $label = "$($definition.Name) / $($button.Text)"
                # PerformClick 不會把錯誤往外拋：PowerShell 的事件處理程序
                # 把例外寫進錯誤串流，WinForms 再自己彈出對話框。第一版用
                # try/catch 包起來，結果重現使用者的錯誤時仍然通過。改成比對
                # $Error 的變化。
                $before = $Error.Count
                # 空狀態下按。使用者第一次打開面板看到的就是這個狀態，
                # 而那正是回報發生的時機。
                $button.PerformClick()
                $clicked++
                if ($Error.Count -gt $before) {
                    $failures.Add("$label -> $($Error[0].Exception.Message)")
                }
            }
        }
        catch {
            $failures.Add("$($file.Name) 建構失敗 -> $($_.Exception.Message)")
        }
        finally {
            $holder.Dispose()
        }
    }

    if ($clicked -lt 8) {
        $failures.Add("只按到 $clicked 個按鈕，控制項走訪可能沒有深入分頁")
    }
}
finally {
    Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}

# --- 保留的自動變數不得拿來當區域變數名 -----------------------------------
#
# 按鈕測試抓不到這一類：$input 之所以爆炸，是因為訊息迴圈在跑時 PowerShell
# 把事件參數當成管線輸入傳進處理程序，自動變數才會蓋掉閉包捕捉到的同名變數。
# 從外面呼叫 PerformClick 重現不出來。這種事只能在寫下名字的當下擋掉。
$reserved = @(
    "input", "args", "error", "host", "home", "matches", "profile", "pwd",
    "this", "true", "false", "null", "PSItem", "PSCmdlet", "foreach", "switch",
    "StackTrace", "ExecutionContext", "MyInvocation", "PSBoundParameters"
)
foreach ($file in @(Get-ChildItem -LiteralPath $moduleDirectory -Filter *.ps1 -File) +
                  @(Get-Item (Join-Path $panelRoot "SmartPriorityControlPanel.ps1")) +
                  @(Get-Item (Join-Path $panelRoot "restart_pime.ps1"))) {
    $text = [IO.File]::ReadAllText($file.FullName)
    foreach ($name in $reserved) {
        if ($text -match ('\$' + $name + '\s*=')) {
            $failures.Add("$($file.Name) 把 `$$name 當成變數名，那是 PowerShell 的自動變數")
        }
    }
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) { Write-Output "FAIL: $failure" }
    throw "control_panel_buttons_smoke 有 $($failures.Count) 項失敗。"
}
Write-Output "PASS: 控制台每個按鈕在空狀態下按下去都不會丟例外"
