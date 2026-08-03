# 分頁：候選字過濾
#
# 第一版要使用者把不想要的字一個一個貼進來。使用者的評語是「如果要一個一個
# 打，那有何用」——完全正確：冷僻字之所以煩人，正是因為你叫不出它們的名字。
# 從字出發是錯的方向。
#
# 改成從分數出發：選一個字頻門檻，就列出所有低於它的字，看過之後一鍵套用。
# 逐字勾選退居為「例外」——把門檻誤殺、但你其實要留的字勾起來。
#
# 兩種設定寫進 hidden-characters.json，判斷規則在
# bopomofo_core\hidden_characters.py，優先序：
#     always_show（一律保留）> hidden（一律隱藏）> minimum_frequency（門檻）

$hiddenFileName = "hidden-characters.json"

# 台灣字頻分不出「冷僻沒用」和「冷僻但想要」：恣 是 5 分而 祐 只有 1 分，
# 孳 6 分而 珮 7 分。所以門檻只是快速的第一刀，勾選才是判準。
$suggestedThreshold = 7

# 可隱藏的字共 294 個，門檻 20 已涵蓋 289 個。更高只會開始砍到詞庫漏掉的
# 常用字，所以數字鈕就到這裡為止。
$maximumThreshold = 20

@{
    Name  = "候選字過濾"
    Order = 40
    Build = {
        param($Context)

        $hiddenPath = Join-Path $Context.StateRoot $hiddenFileName

        # ---- 設定的讀寫 ----------------------------------------------------
        $readSettings = {
            $result = @{
                Floor  = 0
                Hidden = New-Object System.Collections.Generic.HashSet[string]
                Keep   = New-Object System.Collections.Generic.HashSet[string]
            }
            if (-not (Test-Path -LiteralPath $hiddenPath)) { return $result }
            try {
                $value = Get-Content -LiteralPath $hiddenPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($null -ne $value.minimum_frequency) { $result.Floor = [int]$value.minimum_frequency }
                foreach ($entry in @($value.hidden)) {
                    if ($entry -and $entry.Length -eq 1) { [void]$result.Hidden.Add([string]$entry) }
                }
                foreach ($entry in @($value.always_show)) {
                    if ($entry -and $entry.Length -eq 1) { [void]$result.Keep.Add([string]$entry) }
                }
            }
            catch { }
            return $result
        }.GetNewClosure()

        $writeSettings = {
            param($floor, $hidden, $keep)
            New-Item -ItemType Directory -Path $Context.StateRoot -Force | Out-Null
            $payload = @{
                minimum_frequency = [int]$floor
                hidden            = @($hidden | Sort-Object)
                always_show       = @($keep | Sort-Object)
                version           = 1
            } | ConvertTo-Json
            # UTF-8 **不含** BOM：Python 以 json 讀，BOM 會讓解析靜默失敗，
            # 設定看起來就像從來沒存過。
            [IO.File]::WriteAllText($hiddenPath, $payload, (New-Object Text.UTF8Encoding($false)))
        }.GetNewClosure()

        # ---- 字頻表 --------------------------------------------------------
        # 由輸入法模組提供。讀不到就照實說明，門檻仍然會生效。
        $frequency = @{}
        if ($Context.ModuleRoot) {
            $dataDirectory = Join-Path $Context.ModuleRoot (Join-Path "bopomofo_core" "data")
            $frequencyPath = Join-Path $dataDirectory "taiwan_frequency.json"
            if (Test-Path -LiteralPath $frequencyPath) {
                try {
                    $raw = Get-Content -LiteralPath $frequencyPath -Raw -Encoding UTF8 | ConvertFrom-Json
                    $node = if ($null -ne $raw.characters) { $raw.characters } else { $raw }
                    foreach ($property in $node.PSObject.Properties) {
                        $frequency[$property.Name] = [int]$property.Value
                    }
                }
                catch { }
            }
        }

        # 預覽用的計算交給輸入法自己的 Python，規則才不會有第二份。
        $python = if ($Context.PimeRoot) {
            $candidate = Join-Path $Context.PimeRoot (Join-Path "python" (Join-Path "python3" "python.exe"))
            if (Test-Path -LiteralPath $candidate) { $candidate } else { $null }
        } else { $null }
        $lister = if ($Context.ModuleRoot) {
            $candidate = Join-Path $Context.ModuleRoot "list_hidden.py"
            if (Test-Path -LiteralPath $candidate) { $candidate } else { $null }
        } else { $null }

        # 一次取得「不受保護的字 + 分數」。之後改門檻只是在這份集合上篩，
        # 不再重跑 Python。用一個高門檻叫出全部，因為「是否受保護」與門檻無關。
        # 一般區域變數，不用 $script:。GetNewClosure 捕捉的是「呼叫它時那一層」
        # 的變數，$script: 指的是模組檔的腳本作用域，閉包裡拿到的會是 $null——
        # 這個陷阱在這個控制台已經咬過三次。
        $hidable = $null
        $protectedScores = @()
        if ($python -and $lister) {
            try {
                # 高門檻＝叫出全部，因為「是否受保護」與門檻無關。
                $everything = & $python $lister 100000 2>$null | ConvertFrom-Json
                $hidable = @($everything.hidden)
                $protectedScores = @($everything.protected_scores)
            }
            catch { $hidable = $null }
        }

        $settings = & $readSettings
        $keepSet = $settings.Keep
        $hiddenSet = $settings.Hidden

        # ---- 版面 ----------------------------------------------------------
        $layout = New-Object System.Windows.Forms.TableLayoutPanel
        $layout.Dock = "Fill"
        $layout.ColumnCount = 1
        $layout.RowCount = 4
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("Percent", 100)))
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))

        $top = New-Object System.Windows.Forms.FlowLayoutPanel
        $top.Dock = "Fill"
        $top.AutoSize = $true
        $top.WrapContents = $false

        $label = New-Object System.Windows.Forms.Label
        $label.Text = "隱藏字頻低於"
        $label.AutoSize = $true
        $label.Margin = New-Object System.Windows.Forms.Padding(4, 9, 2, 4)

        $threshold = New-Object System.Windows.Forms.NumericUpDown
        $threshold.Minimum = 0
        # 上限 20 是量出來的，不是隨手取的。可隱藏的字總共 294 個，門檻 20 就
        # 拿到 289 個；再往上幾乎沒有收穫，卻開始碰到詞庫沒保護到的常用字——
        # 秘(122)、濕(62)、抬(32)、兇(26)、雇(24) 都在可隱藏集合裡，只是分數高
        # 才碰不到。沒有上限的數字鈕等於把那個地雷留給使用者踩。
        $threshold.Maximum = $maximumThreshold
        $threshold.Width = 70
        $threshold.Value = $settings.Floor
        $threshold.Margin = New-Object System.Windows.Forms.Padding(2, 5, 2, 4)

        $labelAfter = New-Object System.Windows.Forms.Label
        $labelAfter.Text = "分的字"
        $labelAfter.AutoSize = $true
        $labelAfter.Margin = New-Object System.Windows.Forms.Padding(2, 9, 12, 4)

        $summary = New-Object System.Windows.Forms.Label
        $summary.AutoSize = $true
        $summary.Margin = New-Object System.Windows.Forms.Padding(4, 9, 4, 4)

        [void]$top.Controls.Add($label)
        [void]$top.Controls.Add($threshold)
        [void]$top.Controls.Add($labelAfter)
        [void]$top.Controls.Add($summary)

        $grid = New-Object System.Windows.Forms.DataGridView
        $grid.Dock = "Fill"
        $grid.AllowUserToAddRows = $false
        $grid.RowHeadersVisible = $false
        $grid.SelectionMode = "FullRowSelect"
        $grid.AutoSizeColumnsMode = "Fill"
        $grid.BackgroundColor = [System.Drawing.SystemColors]::Window
        $keepColumn = New-Object System.Windows.Forms.DataGridViewCheckBoxColumn
        $keepColumn.Name = "keep"
        $keepColumn.HeaderText = "保留"
        $keepColumn.FillWeight = 10
        [void]$grid.Columns.Add($keepColumn)
        [void]$grid.Columns.Add("character", "字")
        [void]$grid.Columns.Add("score", "台灣字頻")
        $grid.Columns["character"].ReadOnly = $true
        $grid.Columns["character"].FillWeight = 14
        $grid.Columns["character"].DefaultCellStyle.Font =
            New-Object System.Drawing.Font("Microsoft JhengHei UI", 14)
        $grid.Columns["score"].ReadOnly = $true
        $grid.Columns["score"].FillWeight = 76

        $hint = New-Object System.Windows.Forms.Label
        $hint.AutoSize = $true
        $hint.MaximumSize = New-Object System.Drawing.Size(880, 0)
        $hint.ForeColor = [System.Drawing.Color]::FromArgb(90, 90, 90)
        $hint.Margin = New-Object System.Windows.Forms.Padding(4, 8, 4, 4)

        $bottom = New-Object System.Windows.Forms.FlowLayoutPanel
        $bottom.Dock = "Fill"
        $bottom.AutoSize = $true
        $bottom.WrapContents = $false

        $applyButton = New-Object System.Windows.Forms.Button
        $applyButton.Text = "套用並重啟 PIME"
        $applyButton.Width = 150
        $applyButton.Height = 30
        $applyButton.Margin = New-Object System.Windows.Forms.Padding(4)

        $offButton = New-Object System.Windows.Forms.Button
        $offButton.Text = "關閉過濾"
        $offButton.Width = 110
        $offButton.Height = 30
        $offButton.Margin = New-Object System.Windows.Forms.Padding(4)

        $status = New-Object System.Windows.Forms.Label
        $status.AutoSize = $true
        $status.Margin = New-Object System.Windows.Forms.Padding(12, 10, 4, 4)
        $status.ForeColor = [System.Drawing.Color]::FromArgb(90, 90, 90)

        [void]$bottom.Controls.Add($applyButton)
        [void]$bottom.Controls.Add($offButton)
        [void]$bottom.Controls.Add($status)

        # ---- 列出低於門檻的字 ----------------------------------------------
        # 依分數由高到低：最接近門檻的排最前面，那正是最需要確認的一批。
        # 分數遠低於門檻的沒有爭議，不必先看到。
        $refresh = {
            $cut = [int]$threshold.Value
            $grid.Rows.Clear()

            if ($frequency.Count -eq 0) {
                $summary.Text = "讀不到字頻表"
                $hint.Text = "找不到 taiwan_frequency.json，無法依分數列出。門檻仍然會生效，只是這裡看不到會被隱藏哪些字。"
                return
            }
            if ($cut -le 0) {
                $summary.Text = "過濾已關閉，所有字都會出現"
                $hint.Text = "把門檻設成大於 0 的數字，就會列出低於它的字讓你先確認。建議從 $suggestedThreshold 開始試。"
                return
            }

            if ($null -eq $hidable) {
                $summary.Text = "算不出實際會隱藏哪些字"
                $hint.Text = "找不到 PIME 的 Python 或 list_hidden.py，無法預覽。門檻仍然會生效。"
                return
            }

            # 名單在開頁時取一次，這裡只是依門檻篩。先前每次數字變動都重跑一次
            # Python（啟動加讀 2 MB 索引），從 0 按到 7 就是七次，UI 整個卡住，
            # 看起來就像按鈕壞掉。判斷規則仍然只有 Python 那一份：這裡篩的是
            # 它算出來、已經排除掉受保護字的集合，所以套任何門檻都仍然正確。
            $matching = @($hidable | Where-Object { $_.score -lt $cut })
            $protectedBelow = @($protectedScores | Where-Object { $_ -lt $cut }).Count
            $report = [pscustomobject]@{
                hidden    = $matching
                protected = $protectedBelow
                below     = $matching.Count + $protectedBelow
            }

            foreach ($entry in $report.hidden) {
                $character = [string]$entry.character
                $index = $grid.Rows.Add($keepSet.Contains($character), $character, $entry.score)
                if ($keepSet.Contains($character)) {
                    $grid.Rows[$index].DefaultCellStyle.ForeColor =
                        [System.Drawing.Color]::FromArgb(0, 120, 60)
                }
            }
            $total = if ($hidable) { $hidable.Count } else { 0 }
            $summary.Text = ("會隱藏 $($report.hidden.Count) 個字（可隱藏的總共 $total 個）" +
                             "　低於門檻的有 $($report.below) 個，其中 $($report.protected) 個因為出現在內建詞庫而保留")
            $hint.Text = ("由上而下是最接近門檻的字，最需要看一眼；想留下的勾「保留」。`r`n" +
                          "字頻表是 1996 年的書面語調查，看不到口語和成語用字——嗯 只有 7 分、囫 圇 釜 都是 0 分。" +
                          "所以規則不是單純比分數：**出現在內建詞庫的字、以及語氣詞，一律保留**，門檻只處理剩下的。`r`n" +
                          "門檻拉高的收穫遞減得很快：7 分已經拿到 269 個，20 分是 289 個，全部也才 294 個。" +
                          "所以數字鈕停在 20——再往上碰得到的是詞庫漏保護的常用字（秘、濕、抬、兇、雇），不是冷僻字。" +
                          "它仍然不完美（孳、恣 因為出現在孳生、恣意而被保留；祐 不在詞庫裡而會被隱藏），所以勾選才是最終判準。" +
                          "這裡只是隱藏，內建字典沒有被改。")
        }.GetNewClosure()

        $threshold.Add_ValueChanged($refresh)

        $grid.Add_CellValueChanged({
            param($sender, $eventArgs)
            if ($eventArgs.RowIndex -lt 0) { return }
            if ($grid.Columns[$eventArgs.ColumnIndex].Name -ne "keep") { return }
            $row = $grid.Rows[$eventArgs.RowIndex]
            $character = [string]$row.Cells["character"].Value
            if ([bool]$row.Cells["keep"].Value) { [void]$keepSet.Add($character) }
            else { [void]$keepSet.Remove($character) }
            $status.Text = "已保留 $($keepSet.Count) 個字，按套用才生效"
        }.GetNewClosure())

        # 勾選框要離開儲存格才會提交值；立刻提交，使用者才看得到即時回饋。
        $grid.Add_CurrentCellDirtyStateChanged({
            if ($grid.IsCurrentCellDirty) {
                $grid.CommitEdit([System.Windows.Forms.DataGridViewDataErrorContexts]::Commit)
            }
        }.GetNewClosure())

        $applyButton.Add_Click({
            try {
                & $writeSettings ([int]$threshold.Value) $hiddenSet $keepSet
                $result = & $Context.RestartPime $Context.LauncherPath
                $status.Text = "已套用：門檻 $([int]$threshold.Value)，保留 $($keepSet.Count) 個。$($result.Message)"
            }
            catch {
                $status.Text = "套用失敗：$($_.Exception.Message)"
            }
        }.GetNewClosure())

        $offButton.Add_Click({
            $threshold.Value = 0
            try {
                & $writeSettings 0 $hiddenSet $keepSet
                $result = & $Context.RestartPime $Context.LauncherPath
                $status.Text = "過濾已關閉，所有字都會回來。$($result.Message)"
            }
            catch {
                $status.Text = "關閉失敗：$($_.Exception.Message)"
            }
        }.GetNewClosure())

        & $refresh

        $layout.Controls.Add($top, 0, 0)
        $layout.Controls.Add($grid, 0, 1)
        $layout.Controls.Add($hint, 0, 2)
        $layout.Controls.Add($bottom, 0, 3)
        $layout
    }.GetNewClosure()
}
