# 分頁：候選字過濾
#
# 台灣字頻分不出「冷僻沒用」和「冷僻但想要」——實測 恣 是 5 分而 祐 是 1 分，
# 孳 6 分而 珮 7 分，昕 與 彤 是 0 分卻和 眥 剚 同級。沒有任何門檻能把它們分開，
# 所以名單由使用者自己勾。字頻只在這裡當批次勾選的輔助，不當判準。
#
# 藏起來不等於刪掉：內建字典是第三方資料，完全沒動，把名單清空就全部回來。

$hiddenFileName = "hidden-characters.json"

@{
    Name  = "候選字過濾"
    Order = 40
    Build = {
        param($Context)

        $hiddenPath = Join-Path $Context.StateRoot $hiddenFileName

        $readHidden = {
            if (-not (Test-Path -LiteralPath $hiddenPath)) {
                return New-Object System.Collections.Generic.HashSet[string]
            }
            try {
                $value = Get-Content -LiteralPath $hiddenPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $set = New-Object System.Collections.Generic.HashSet[string]
                foreach ($entry in @($value.hidden)) {
                    if ($entry -and $entry.Length -eq 1) { [void]$set.Add([string]$entry) }
                }
                $script:loadedFloor = 0
                if ($null -ne $value.minimum_frequency) { $script:loadedFloor = [int]$value.minimum_frequency }
                $script:loadedKeep = New-Object System.Collections.Generic.HashSet[string]
                foreach ($entry in @($value.always_show)) {
                    if ($entry -and $entry.Length -eq 1) { [void]$script:loadedKeep.Add([string]$entry) }
                }
                return $set
            }
            catch { return New-Object System.Collections.Generic.HashSet[string] }
        }

        $writeHidden = {
            param($set)
            New-Item -ItemType Directory -Path $Context.StateRoot -Force | Out-Null
            $payload = @{
                hidden            = @($set | Sort-Object)
                always_show       = @($script:loadedKeep | Sort-Object)
                minimum_frequency = [int]$threshold.Value
                version           = 1
            } | ConvertTo-Json
            # UTF-8 **不含** BOM：Python 以 json 讀這個檔，BOM 會讓解析失敗，
            # 而失敗是靜默的 —— 名單會看起來像空的，沒有任何錯誤訊息。
            [IO.File]::WriteAllText($hiddenPath, $payload, (New-Object Text.UTF8Encoding($false)))
        }

        $script:loadedFloor = 0
        $script:loadedKeep = New-Object System.Collections.Generic.HashSet[string]
        $hidden = & $readHidden

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
        $label.Text = "貼上要檢查的字"
        $label.AutoSize = $true
        $label.Margin = New-Object System.Windows.Forms.Padding(4, 8, 4, 4)

        $input = New-Object System.Windows.Forms.TextBox
        # 這個框就是要輸入中文字的。WinForms 預設 Inherit，而承接到的狀態
        # 不一定開著輸入法，使用者會發現只打得出英文。明確要求開啟。
        $input.ImeMode = [System.Windows.Forms.ImeMode]::On
        $input.Width = 320
        $input.Margin = New-Object System.Windows.Forms.Padding(4, 4, 8, 4)

        $addButton = New-Object System.Windows.Forms.Button
        $addButton.Text = "列出這些字"
        $addButton.Width = 110
        $addButton.Height = 26
        $addButton.Margin = New-Object System.Windows.Forms.Padding(4)

        $showHiddenButton = New-Object System.Windows.Forms.Button
        $showHiddenButton.Text = "只看已隱藏"
        $showHiddenButton.Width = 110
        $showHiddenButton.Height = 26
        $showHiddenButton.Margin = New-Object System.Windows.Forms.Padding(4)

        [void]$top.Controls.Add($label)
        [void]$top.Controls.Add($input)
        [void]$top.Controls.Add($addButton)
        [void]$top.Controls.Add($showHiddenButton)

        $grid = New-Object System.Windows.Forms.DataGridView
        $grid.Dock = "Fill"
        $grid.AllowUserToAddRows = $false
        $grid.RowHeadersVisible = $false
        $grid.SelectionMode = "FullRowSelect"
        $grid.AutoSizeColumnsMode = "Fill"
        $grid.BackgroundColor = [System.Drawing.SystemColors]::Window
        $tick = New-Object System.Windows.Forms.DataGridViewCheckBoxColumn
        $tick.Name = "hide"
        $tick.HeaderText = "隱藏"
        $tick.FillWeight = 12
        [void]$grid.Columns.Add($tick)
        [void]$grid.Columns.Add("character", "字")
        [void]$grid.Columns.Add("frequency", "台灣字頻")
        $grid.Columns["character"].ReadOnly = $true
        $grid.Columns["character"].FillWeight = 20
        $grid.Columns["character"].DefaultCellStyle.Font =
            New-Object System.Drawing.Font("Microsoft JhengHei UI", 14)
        $grid.Columns["frequency"].ReadOnly = $true
        $grid.Columns["frequency"].FillWeight = 68

        $bulk = New-Object System.Windows.Forms.FlowLayoutPanel
        $bulk.Dock = "Fill"
        $bulk.AutoSize = $true
        $bulk.WrapContents = $false
        $bulkLabel = New-Object System.Windows.Forms.Label
        $bulkLabel.Text = "把字頻低於"
        $bulkLabel.AutoSize = $true
        $bulkLabel.Margin = New-Object System.Windows.Forms.Padding(4, 9, 2, 4)
        $threshold = New-Object System.Windows.Forms.NumericUpDown
        $threshold.Minimum = 0
        $threshold.Maximum = 10000
        # 預設 0 = 關閉。開啟面板隨手按儲存不該意外套用一個門檻；
        # 建議值寫在下面的說明裡，由使用者自己填。
        $threshold.Value = 0
        $threshold.Width = 70
        $threshold.Margin = New-Object System.Windows.Forms.Padding(2, 4, 2, 4)
        $bulkLabel2 = New-Object System.Windows.Forms.Label
        $bulkLabel2.Text = "的字一律隱藏（這條規則會被儲存，涵蓋你沒列出來的字）"
        $bulkLabel2.AutoSize = $true
        $bulkLabel2.Margin = New-Object System.Windows.Forms.Padding(2, 9, 8, 4)
        $bulkButton = New-Object System.Windows.Forms.Button
        $bulkButton.Text = "同時勾選已列出的"
        $bulkButton.Width = 70
        $bulkButton.Height = 26
        $bulkButton.Margin = New-Object System.Windows.Forms.Padding(4)
        [void]$bulk.Controls.Add($bulkLabel)
        [void]$bulk.Controls.Add($threshold)
        [void]$bulk.Controls.Add($bulkLabel2)
        [void]$bulk.Controls.Add($bulkButton)

        $bottom = New-Object System.Windows.Forms.FlowLayoutPanel
        $bottom.Dock = "Fill"
        $bottom.AutoSize = $true
        $bottom.WrapContents = $false
        $saveButton = New-Object System.Windows.Forms.Button
        $saveButton.Text = "儲存並重啟 PIME"
        $saveButton.Width = 150
        $saveButton.Height = 30
        $saveButton.Margin = New-Object System.Windows.Forms.Padding(4)
        $clearButton = New-Object System.Windows.Forms.Button
        $clearButton.Text = "全部取消隱藏"
        $clearButton.Width = 120
        $clearButton.Height = 30
        $clearButton.Margin = New-Object System.Windows.Forms.Padding(4)
        $status = New-Object System.Windows.Forms.Label
        $status.AutoSize = $true
        $status.Margin = New-Object System.Windows.Forms.Padding(12, 10, 4, 4)
        $status.ForeColor = [System.Drawing.Color]::FromArgb(90, 90, 90)
        [void]$bottom.Controls.Add($saveButton)
        [void]$bottom.Controls.Add($clearButton)
        [void]$bottom.Controls.Add($status)

        # 字頻表由輸入法模組提供。讀不到就把欄位留白，勾選照樣可用 ——
        # 名單才是判準，字頻只是輔助。
        $frequency = @{}
        if ($Context.ModuleRoot) {
            $frequencyPath = Join-Path $Context.ModuleRoot "bopomofo_core\data\taiwan_frequency.json"
            if (Test-Path -LiteralPath $frequencyPath) {
                try {
                    $raw = Get-Content -LiteralPath $frequencyPath -Raw -Encoding UTF8 | ConvertFrom-Json
                    $node = if ($null -ne $raw.characters) { $raw.characters } else { $raw }
                    foreach ($property in $node.PSObject.Properties) {
                        $frequency[$property.Name] = $property.Value
                    }
                }
                catch { }
            }
        }

        $fill = {
            param($characters)
            $grid.Rows.Clear()
            foreach ($character in $characters) {
                $score = if ($frequency.ContainsKey($character)) { $frequency[$character] } else { 0 }
                $index = $grid.Rows.Add($hidden.Contains($character), $character, $score)
                if ($hidden.Contains($character)) {
                    $grid.Rows[$index].DefaultCellStyle.ForeColor =
                        [System.Drawing.Color]::FromArgb(150, 150, 150)
                }
            }
            $status.Text = "列出 $($grid.Rows.Count) 個字，目前已隱藏 $($hidden.Count) 個"
        }.GetNewClosure()

        $addButton.Add_Click({
            $seen = New-Object System.Collections.Generic.HashSet[string]
            $characters = @()
            foreach ($character in $input.Text.ToCharArray()) {
                $text = [string]$character
                # 空白、標點與注音都不是候選字，略過。
                if ([char]::IsWhiteSpace($character)) { continue }
                if ([int][char]$character -lt 0x3400) { continue }
                if ($seen.Add($text)) { $characters += $text }
            }
            & $fill $characters
        }.GetNewClosure())

        $showHiddenButton.Add_Click({
            & $fill (@($hidden) | Sort-Object)
        }.GetNewClosure())

        $bulkButton.Add_Click({
            $cut = [int]$threshold.Value
            $touched = 0
            foreach ($row in $grid.Rows) {
                $character = [string]$row.Cells["character"].Value
                $score = if ($frequency.ContainsKey($character)) { $frequency[$character] } else { 0 }
                if ($score -lt $cut -and -not [bool]$row.Cells["hide"].Value) {
                    $row.Cells["hide"].Value = $true
                    $touched++
                }
            }
            $status.Text = "字頻低於 $cut 的規則會在儲存時生效；已列出的字順便勾了 $touched 個"
        }.GetNewClosure())

        $clearButton.Add_Click({
            foreach ($row in $grid.Rows) { $row.Cells["hide"].Value = $false }
            $hidden.Clear()
            $status.Text = "已全部取消勾選，按儲存才生效"
        }.GetNewClosure())

        $saveButton.Add_Click({
            try {
                # 表格是目前檢視的字；沒列出來的維持原狀，不會被這次操作清掉。
                $grid.EndEdit()
                foreach ($row in $grid.Rows) {
                    $character = [string]$row.Cells["character"].Value
                    if ([bool]$row.Cells["hide"].Value) { [void]$hidden.Add($character) }
                    else { [void]$hidden.Remove($character) }
                }
                & $writeHidden $hidden

                $result = & $Context.RestartPime $Context.LauncherPath
                $status.Text = "已儲存，共隱藏 $($hidden.Count) 個字。$($result.Message)"
            }
            catch {
                [System.Windows.Forms.MessageBox]::Show(
                    ($_ | Out-String), "儲存失敗",
                    [System.Windows.Forms.MessageBoxButtons]::OK,
                    [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
            }
        }.GetNewClosure())

        $hint = New-Object System.Windows.Forms.Label
        $hint.AutoSize = $true
        $hint.MaximumSize = New-Object System.Drawing.Size(880, 0)
        $hint.ForeColor = [System.Drawing.Color]::FromArgb(90, 90, 90)
        $hint.Margin = New-Object System.Windows.Forms.Padding(4, 6, 4, 4)
        $hint.Text = "兩種手段一起用。字頻門檻負責大量的部分 —— 只靠手勾是打地鼠：實測把 ㄗˋ 的 孳 恣 磧 眥 剚 胔 藏起來之後，胾 扻 倳 牸 芓 絘 立刻遞補上來。逐字勾選則是對門檻的修正，因為字頻分不出好壞：恣 是 5 分而 祐 只有 1 分。門檻設 0 就是關閉（預設）。建議從 7 開始試：那是能砍掉 孳(6) 恣(5) 的最低值。這裡只是隱藏，內建字典沒有被改，把設定清掉就全部回來。一個讀音的候選若被全部隱藏，系統會保留原本的清單，以免打不出那個音。"

        if ($script:loadedFloor -gt 0) { $threshold.Value = $script:loadedFloor }
        & $fill (@($hidden) | Sort-Object)

        $stack = New-Object System.Windows.Forms.FlowLayoutPanel
        $stack.Dock = "Fill"
        $stack.AutoSize = $true
        $stack.FlowDirection = "TopDown"
        $stack.WrapContents = $false
        [void]$stack.Controls.Add($bulk)
        [void]$stack.Controls.Add($hint)

        $layout.Controls.Add($top, 0, 0)
        $layout.Controls.Add($grid, 0, 1)
        $layout.Controls.Add($stack, 0, 2)
        $layout.Controls.Add($bottom, 0, 3)
        $layout
    }.GetNewClosure()
}
