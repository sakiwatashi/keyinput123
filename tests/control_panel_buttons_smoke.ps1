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

# 按下去會跳對話框的按鈕會把測試整個卡住：MessageBox.Show 是同步的模態迴圈，
# PerformClick 要等它關掉才會回來，而測試環境裡沒有人去按確定。所以自備一個
# 看門狗，在模態迴圈跑起來的時候把對話框關掉，順便記下它的標題。
#
# 記標題不只是為了不卡住。使用者回報過「我啥都沒輸入按了一下就跳錯誤框」，
# 那正是這支測試要抓的東西——所以標題帶「失敗」或「錯誤」的一律算失敗。
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class DialogWatch {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr PostMessageW(IntPtr h, uint msg, IntPtr w, IntPtr l);

    public static string CloseFirstDialog() {
        string caption = null;
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
            if (!IsWindowVisible(hWnd)) return true;
            StringBuilder cls = new StringBuilder(64);
            GetClassNameW(hWnd, cls, cls.Capacity);
            if (cls.ToString() != "#32770") return true;   // #32770 = 標準對話框類別
            StringBuilder text = new StringBuilder(512);
            GetWindowTextW(hWnd, text, text.Capacity);
            caption = text.ToString();
            PostMessageW(hWnd, 0x0010, IntPtr.Zero, IntPtr.Zero);   // WM_CLOSE
            return false;
        }, IntPtr.Zero);
        return caption;
    }
}
"@

# 每次按鈕都用它包起來：先武裝看門狗，按下去，再解除。
$script:dialogSeen = $null
$watchdog = New-Object System.Windows.Forms.Timer
$watchdog.Interval = 250
$watchdog.Add_Tick({
    $caption = [DialogWatch]::CloseFirstDialog()
    if ($caption) { $script:dialogSeen = $caption }
})

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

    # 先確認 PerformClick 在這個環境下真的會叫到處理程序。
    #
    # 這一段不是多餘的：本測試原本把每個分頁掛到一個沒有 Show 過的 Form 底下，
    # 而 Button.PerformClick 會先問 CanSelect，CanSelect 往上走訪父控制項時碰到
    # Visible=false 的 Form 就回傳 false，PerformClick 於是靜靜地什麼也不做。
    # 測試照樣「通過」，但一個處理程序都沒執行過。空轉的測試比沒有測試更糟，
    # 所以現在每次都先驗一次自己。
    $probeFired = $false
    $probe = New-Object System.Windows.Forms.Button
    $probe.Add_Click({ $script:probeFired = $true })
    $probe.PerformClick()
    if (-not $probeFired) {
        $failures.Add("PerformClick 沒有觸發處理程序，這支測試等於空轉（請檢查控制項是否掛在未顯示的 Form 底下）")
    }

    $clicked = 0
    foreach ($file in Get-ChildItem -LiteralPath $moduleDirectory -Filter *.ps1 -File | Sort-Object Name) {
        $definition = & $file.FullName
        if ($definition -is [array]) { $definition = $definition[-1] }

        try {
            # 不掛 Form：見上面 probe 的說明。無父控制項時 Visible 預設為 true，
            # 按鈕才按得動。
            $control = & $definition.Build $context
            if (-not $control) { continue }

            foreach ($button in (Get-Buttons $control)) {
                $label = "$($definition.Name) / $($button.Text)"
                # PerformClick 不會把錯誤往外拋：PowerShell 的事件處理程序
                # 把例外寫進錯誤串流，WinForms 再自己彈出對話框。第一版用
                # try/catch 包起來，結果重現使用者的錯誤時仍然通過。改成比對
                # $Error 的變化。
                $before = $Error.Count
                # 空狀態下按。使用者第一次打開面板看到的就是這個狀態，
                # 而那正是回報發生的時機。
                $script:dialogSeen = $null
                $watchdog.Start()
                try { $button.PerformClick() } finally { $watchdog.Stop() }
                $clicked++
                if ($Error.Count -gt $before) {
                    $failures.Add("$label -> $($Error[0].Exception.Message)")
                }
                if ($script:dialogSeen -and $script:dialogSeen -match "失敗|錯誤") {
                    $failures.Add("$label -> 跳出錯誤對話框「$script:dialogSeen」")
                }
            }
        }
        catch {
            $failures.Add("$($file.Name) 建構失敗 -> $($_.Exception.Message)")
        }
        finally {
            if ($control) { $control.Dispose() }
        }
    }

    $watchdog.Dispose()

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
