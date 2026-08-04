# 候選字過濾分頁的左右兩半要各自做對事情。
#
# 使用者的要求是「同頁可以分一半可以檢視現在過濾了哪些字」，所以右
# 一半必須反映**已經存檔**的設定，不能跟著正在調的門檻跑；兩邊一起動
# 就沒有對照的意義了。
#
# 重點是第四個檢查：按下「套用」之後右邊要跟上。$saved 如果是普通純量，
# 每個 GetNewClosure 拿到的是自己那份快照，套用鈕裡改值只改得到自己，右邊
# 永遠停在舊數字。這個陷阱在這個控制台已經咬過四次，所以釘死。
#
# 安全性：$Context 指向暫存資料夾，PIMELauncher 路徑刻意指向不存在的檔案，
# 所以儲存只會寫到暫存區、重啟一律是無操作。不會碰到使用者的個人詞庫。
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$panelRoot = Join-Path $root "control_panel"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
. (Join-Path $panelRoot "restart_pime.ps1")

$failures = New-Object System.Collections.Generic.List[string]

function Find-Descendants {
    param($control, $type)
    $found = @()
    foreach ($child in $control.Controls) {
        if ($child -is $type) { $found += $child }
        if ($child.Controls.Count -gt 0) { $found += Find-Descendants $child $type }
    }
    return $found
}

$sandbox = Join-Path ([IO.Path]::GetTempPath()) ("panel-panes-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $sandbox -Force | Out-Null
try {
    # 先存一筆手動隱藏，這一段不需要 Python 也能跑，CI 上沿用得到。
    $configPath = Join-Path $sandbox "hidden-characters.json"
    $seeded = @{
        minimum_frequency = 0
        hidden            = @("罕", "韃")
        always_show       = @()
        version           = 1
    } | ConvertTo-Json
    [IO.File]::WriteAllText($configPath, $seeded, (New-Object Text.UTF8Encoding($false)))

    # PIME 裝了就用真的，沒裝就只跑不靠 Python 那幾樣。
    $installed = "C:\Program Files (x86)\PIME"
    $hasPime = Test-Path -LiteralPath (Join-Path $installed "python\python3\python.exe")

    $context = [pscustomobject]@{
        StateRoot    = $sandbox
        PimeRoot     = if ($hasPime) { $installed } else { $null }
        ModuleRoot   = $root
        LauncherPath = Join-Path $sandbox "no-such-launcher.exe"
        CandidateUi  = Join-Path $sandbox "candidate-ui.json"
        PhrasesPath  = Join-Path $sandbox "phrases.json"
        PinsPath     = Join-Path $sandbox "pins.json"
        RestartPime  = ${function:Restart-Pime}
        UiFont       = New-Object System.Drawing.Font("Microsoft JhengHei UI", 9)
        MonoFont     = New-Object System.Drawing.Font("Consolas", 9)
    }

    $definition = & (Join-Path $panelRoot (Join-Path "modules" "40-hidden.ps1"))
    if ($definition -is [array]) { $definition = $definition[-1] }

    # 刻意不把 $control 掛到 Form 上。Button.PerformClick 內部先問 CanSelect，
    # 而 CanSelect 會往上走訪父控制項；從來沒有 Show 過的 Form 其 Visible 是
    # false，整串因此判定不可選取，PerformClick 就什麼都不做——處理程序根本
    # 不會被呼叫，測試看起來過了卻什麼也沒驗證。無父控制項時預設 Visible 為
    # true，按鈕才真的按得下去。
    $holder = $null
    try {
        $control = & $definition.Build $context

        $grids = @(Find-Descendants $control ([System.Windows.Forms.DataGridView]))
        if ($grids.Count -ne 2) {
            $failures.Add("應該有左右兩個清單，實際找到 $($grids.Count) 個")
        }
        else {
            $left = $grids[0]
            $right = $grids[1]

            # --- 1. 兩半的欄位要各自相稱 -------------------------------
            $leftColumns = @($left.Columns | ForEach-Object { $_.Name })
            $rightColumns = @($right.Columns | ForEach-Object { $_.Name })
            if (($leftColumns -join ",") -ne "keep,character,score") {
                $failures.Add("左半欄位不對：$($leftColumns -join ',')")
            }
            if (($rightColumns -join ",") -ne "character,score,reason") {
                $failures.Add("右半欄位不對：$($rightColumns -join ',')")
            }
            if (-not $right.ReadOnly) {
                $failures.Add("右半應該是唯讀——它是哪些字被過濾掉的檢視，不是編輯區")
            }

            # --- 2. 開頁時右半反映存檔，不是空的 --------------------
            $manual = @($right.Rows | Where-Object { $_.Cells["reason"].Value -eq "你指定隱藏" })
            if ($manual.Count -ne 2) {
                $failures.Add("存檔裡有 2 個手動隱藏字，右半卻列出 $($manual.Count) 個")
            }

            # --- 3. 門檻拉動了但沒按套用，右半不准動 -------------------
            $spinner = @(Find-Descendants $control ([System.Windows.Forms.NumericUpDown]))[0]
            $rightBefore = $right.Rows.Count
            $spinner.Value = $spinner.Maximum
            if ($right.Rows.Count -ne $rightBefore) {
                $failures.Add("還沒按套用右半就跟著動了，那就分不出「已生效」和「將要套用」")
            }

            # --- 4. 按下套用之後右半必須跟上 --------------------------
            # 這就是 GetNewClosure 快照陷阱：用普通純量的話，套用裡寫的
            # $saved.Floor = N 只會改到套用那份文本，右半列出來的還是舊的開
            # 頁值。只有共用同一個 hashtable 參照才會這樣改得到。
            $apply = @(Find-Descendants $control ([System.Windows.Forms.Button])) |
                     Where-Object { $_.Text -like "套用*" } | Select-Object -First 1
            $errorsBefore = $Error.Count
            $apply.PerformClick()
            if ($Error.Count -gt $errorsBefore) {
                $failures.Add("按套用丟例外：$($Error[0].Exception.Message)")
            }
            if ($hasPime) {
                if ($right.Rows.Count -le $rightBefore) {
                    $failures.Add(("門檻拉到 $($spinner.Value) 並套用了，右半卻還是 " +
                                   "$($right.Rows.Count) 筆（原本 $rightBefore）——套用沒有傳到右半"))
                }
            }

            # --- 5. 挑出來要能寫進 always_show --------------------------
            if ($right.Rows.Count -gt 0) {
                $victim = [string]$right.Rows[0].Cells["character"].Value
                $right.Rows[0].Selected = $true
                $rescue = @(Find-Descendants $control ([System.Windows.Forms.Button])) |
                          Where-Object { $_.Text -like "把選取的挑出來*" } | Select-Object -First 1
                if (-not $rescue) {
                    $failures.Add("找不到挑出來的按鈕")
                }
                else {
                    $countBefore = $right.Rows.Count
                    $rescue.PerformClick()
                    if ($right.Rows.Count -ne ($countBefore - 1)) {
                        $failures.Add("挑出一個字之後右半應該少一筆，實際是 $($right.Rows.Count)（原本 $countBefore）")
                    }
                    $apply.PerformClick()

                    # 存檔必須是無 BOM 的 UTF-8：jsoncpp 拒收帶 BOM 的 JSON，
                    # 而那次崩壞是以 __fastfail 收場，沒有堆疊、沒有事件記錄。
                    # 這是哪裡對的最貴代價，所以這裡查得最緊。
                    $raw = [IO.File]::ReadAllBytes($configPath)
                    if ($raw.Length -ge 3 -and $raw[0] -eq 0xEF -and $raw[1] -eq 0xBB -and $raw[2] -eq 0xBF) {
                        $failures.Add("hidden-characters.json 帶了 UTF-8 BOM，Python 會讀不到")
                    }
                    $stored = [Text.Encoding]::UTF8.GetString($raw) | ConvertFrom-Json
                    if (@($stored.always_show) -notcontains $victim) {
                        $failures.Add("挑出來的字「$victim」沒有寫進 always_show")
                    }
                    if (@($stored.hidden) -contains $victim) {
                        $failures.Add("「$victim」被挑出來了，卻還留在 hidden 裡")
                    }
                }
            }
        }
    }
    finally {
        if ($control) { $control.Dispose() }
    }
}
finally {
    Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) { Write-Output "FAIL: $failure" }
    throw "hidden_filter_panes_smoke 有 $($failures.Count) 項失敗。"
}
Write-Output "PASS: 候選字過濾左右兩半各自正確，套用會傳到右半，挑出來會寫回設定"
