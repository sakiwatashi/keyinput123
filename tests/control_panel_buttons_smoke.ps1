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
        PhoneticFix  = Join-Path $sandbox "phonetic-correction.json"
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
            # TabControl 的 Controls 本身就是 TabPages。兩邊都走會讓分頁裡的
            # 每顆按鈕重複出現；個人詞庫那一頁因此被數了四遍，$clicked 的門檻
            # 看起來過得很輕鬆，其實一顆都沒真的按到。
            if ($child -isnot [System.Windows.Forms.TabControl] -and $child.Controls.Count -gt 0) {
                $found += Get-Buttons $child
            }
            # 分頁裡的分頁（個人詞庫有兩頁）也要走進去。
            if ($child -is [System.Windows.Forms.TabControl]) {
                foreach ($page in $child.TabPages) { $found += Get-Buttons $page }
            }
        }
        return $found
    }
    function Get-TextSnapshot {
        # 控制項裡所有看得到的字。用來判斷處理程序有沒有留下話。
        param($control)
        $parts = @()
        foreach ($child in $control.Controls) {
            if ($child -is [System.Windows.Forms.Label] -or
                $child -is [System.Windows.Forms.TextBox]) { $parts += [string]$child.Text }
            if ($child -isnot [System.Windows.Forms.TabControl] -and $child.Controls.Count -gt 0) {
                $parts += Get-TextSnapshot $child
            }
            if ($child -is [System.Windows.Forms.TabControl]) {
                foreach ($page in $child.TabPages) { $parts += Get-TextSnapshot $page }
            }
        }
        return ($parts -join "|")
    }

    # 直接觸發 Click，不走 PerformClick。
    #
    # PerformClick 會先問 CanSelect，而 CanSelect 沿著父鏈碰到沒有 Show 過的容器
    # 就是 false，於是它靜靜地什麼也不做。實測：41 顆按鈕裡有 26 顆——整個個人
    # 詞庫分頁——從來沒有被按過，而測試一路綠燈。20-lexicon.ps1 兩個真的壞掉的
    # 按鈕就是這樣活下來的。
    #
    # OnClick 是 protected，用反射叫它。這不是使用者的路徑，但這支測試要問的是
    # 「處理程序跑起來會不會炸」，不是「這顆按鈕在畫面上按不按得到」。
    $onClick = [System.Windows.Forms.Control].GetMethod(
        "OnClick",
        [System.Reflection.BindingFlags]::Instance -bor [System.Reflection.BindingFlags]::NonPublic)
    if (-not $onClick) {
        $failures.Add("找不到 Control.OnClick，這支測試沒有辦法觸發任何按鈕")
    }
    function Invoke-Click {
        param($Button)
        $onClick.Invoke($Button, @([EventArgs]::Empty))
    }

    # 先證明這個機制真的會叫到處理程序，而且是在容器裡的按鈕上——舊版的探針用
    # 一顆沒有父容器的孤兒按鈕，而孤兒按鈕的 CanSelect 剛好是 true，所以它證明
    # 不了巢狀按鈕按得到。
    $probeFired = $false
    $probePanel = New-Object System.Windows.Forms.Panel
    $probe = New-Object System.Windows.Forms.Button
    [void]$probePanel.Controls.Add($probe)
    $probe.Add_Click({ $script:probeFired = $true })
    Invoke-Click $probe
    if (-not $probeFired) {
        $failures.Add("觸發機制沒有叫到處理程序，這支測試等於空轉")
    }

    # 攔截 Start-Process，不要讓測試在使用者桌面上開視窗。
    #
    # 狀態頁的「開啟資料夾」會叫 explorer 開 $Context.StateRoot，而那是測試的
    # 暫存沙箱；測試結束刪掉沙箱之後，那個 Explorer 視窗就跳「位置無法使用」。
    # 這是把測試從空轉改成真的按之後才冒出來的副作用。
    #
    # 用同名的 global function 遮蔽 cmdlet，按鈕的程式碼路徑照樣走完，只是不會
    # 真的啟動任何東西——比整顆跳過更有價值：漏掉的話這顆鈕就完全沒被測到。
    $script:launched = New-Object System.Collections.Generic.List[string]
    function global:Start-Process {
        param(
            [string]$FilePath,
            $ArgumentList,
            [switch]$Wait,
            [switch]$PassThru,
            $Verb,
            $ErrorAction
        )
        $script:launched.Add("$FilePath $ArgumentList")
        return $null
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
                $launchedBefore = $script:launched.Count
                $textBefore = Get-TextSnapshot $control
                # 空狀態下按。使用者第一次打開面板看到的就是這個狀態，
                # 而那正是回報發生的時機。
                $script:dialogSeen = $null
                $watchdog.Start()
                try { Invoke-Click $button } finally { $watchdog.Stop() }
                $clicked++
                # 事件處理程序裡的例外，$Error 抓不到（實測：非終止錯誤、明確
                # throw、非法路徑，三種都不會讓 $Error 增加）。所以真正在守的是
                # 「該做完的事有沒有做完」：開啟資料夾的終點是叫起 explorer。
                if ($button.Text -match "開啟" -and $button.Text -match "資料夾") {
                    if ($script:launched.Count -eq $launchedBefore -and
                            (Get-TextSnapshot $control) -eq $textBefore) {
                        # 既沒開資料夾也沒留下任何話，就是半路死了。沒設共用資料夾
                        # 時同步那顆會寫「還沒選共用資料夾」再返回，那是正常的。
                        $failures.Add("$label -> 既沒開啟資料夾也沒留下任何訊息，處理程序中途就死了")
                    }
                    elseif ($script:launched.Count -gt $launchedBefore) {
                        $opened = $script:launched[$script:launched.Count - 1]
                        if ($opened -match ("[" + [char]0 + "-" + [char]31 + "]")) {
                            $failures.Add("$label -> 開啟的路徑含控制字元，explorer 打不開：$opened")
                        }
                    }
                }
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
    Remove-Item -LiteralPath "function:global:Start-Process" -ErrorAction SilentlyContinue

    # 「開啟資料夾」有沒有真的試著開對地方。攔截之後仍然要驗它的意圖，
    # 否則遮蔽 cmdlet 就只是把那顆鈕變成永遠不會失敗的按鈕。
    $openedFolder = @($script:launched | Where-Object { $_ -match "explorer" })
    if ($openedFolder.Count -eq 0) {
        $failures.Add("沒有任何按鈕試著開啟資料夾，「開啟資料夾」可能沒被按到")
    }
    elseif (-not ($openedFolder | Where-Object { $_ -like "*$sandbox*" })) {
        # 只看第一個會誤判：個人詞庫的「開啟備份資料夾」修好之後也會叫起
        # explorer，而它開的是 %LOCALAPPDATA%，不是這個沙箱。要問的是「有沒有
        # 任何一顆開到設定資料夾」。
        $failures.Add("沒有任何按鈕開啟設定資料夾：$($openedFolder -join ' | ')")
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
Write-Output "PASS: 控制台每顆按鈕的處理程序都跑得完，開啟資料夾的那幾顆確實開了"
