# 分頁：個人詞庫管理
#
# 兩份個人資料先前完全看不到內容，學錯了也只能整個砍掉重來：
#   phrases.json  { "ㄉㄧㄢˋ ㄏㄨㄚˋ": "電話" }        讀音（空白分隔）→ 詞
#   pins.json     { "ㄕˋ": ["是", "事"] }              讀音 → 依序排列的候選
# 結構取自 bopomofo_core\phrase_store.py 與 pinned_store.py。
#
# 這裡的資料只留在本機、只給使用者自己看，不上傳也不外送。

# 這兩個輔助工具是 scriptblock 變數而不是 function：按鈕與搜尋框的處理程序
# 都在 Build 回傳之後才執行，那時 function 所在的作用域已經消失，只有被
# GetNewClosure 一起帶走的「變數」還在。用 function 寫會在按下按鈕時才炸。
$saveJsonObject = {
    param([string]$path, $ordered)
    # Python 端以 utf-8 讀寫這兩個檔。BOM 會讓 json 解析失敗，而失敗是靜默的
    # （load_json_object 把檔案當成損壞而改名保存），所以寫入一定要用不含 BOM
    # 的 UTF-8，不能用 Set-Content -Encoding UTF8。
    $json = $ordered | ConvertTo-Json -Depth 5
    if ($ordered.Count -eq 0) { $json = "{}" }
    $directory = Split-Path -Parent $path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    # 先寫暫存再取代，中途當機不會留下半個檔案，與 storage.py 一致。
    $temporary = Join-Path $directory (".{0}.{1}.tmp" -f (Split-Path -Leaf $path), $PID)
    [IO.File]::WriteAllText($temporary, $json, (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $path -Force
}

$readJsonObject = {
    param([string]$path)
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try {
        $text = Get-Content -LiteralPath $path -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($text)) { return $null }
        return ($text | ConvertFrom-Json)
    }
    catch { return $null }
}

@{
    Name  = "個人詞庫"
    Order = 20
    Build = {
        param($Context)

        $tabs = New-Object System.Windows.Forms.TabControl
        $tabs.Dock = "Fill"

        $state = @{}

        function New-LexiconPage([string]$title, [string]$path, [string]$valueHeader, [bool]$valueIsList) {
            # GetNewClosure 只捕捉「呼叫它時的那一層」的變數，不會沿著作用域鏈
            # 往上抓。下面的 $load / 儲存處理程序都是在這個函式裡建立閉包，
            # 所以兩個輔助工具必須先變成本地變數，否則按下按鈕時會是 $null。
            $readJson = $readJsonObject
            $saveJson = $saveJsonObject

            $page = New-Object System.Windows.Forms.TabPage
            $page.Text = $title
            $page.Padding = New-Object System.Windows.Forms.Padding(8)
            $page.BackColor = [System.Drawing.SystemColors]::Window

            $layout = New-Object System.Windows.Forms.TableLayoutPanel
            $layout.Dock = "Fill"
            $layout.ColumnCount = 1
            $layout.RowCount = 3
            [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))
            [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("Percent", 100)))
            [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))

            $top = New-Object System.Windows.Forms.FlowLayoutPanel
            $top.Dock = "Fill"
            $top.AutoSize = $true
            $top.WrapContents = $false
            $searchLabel = New-Object System.Windows.Forms.Label
            $searchLabel.Text = "搜尋"
            $searchLabel.AutoSize = $true
            $searchLabel.Margin = New-Object System.Windows.Forms.Padding(4, 8, 4, 4)
            $search = New-Object System.Windows.Forms.TextBox
            # 詞庫是中文的，搜尋框當然要能打中文。WinForms 預設 Inherit，
            # 承接到的狀態不一定開著輸入法。
            $search.ImeMode = [System.Windows.Forms.ImeMode]::On
            $search.Width = 260
            $search.Margin = New-Object System.Windows.Forms.Padding(4, 4, 12, 4)
            $count = New-Object System.Windows.Forms.Label
            $count.AutoSize = $true
            $count.Margin = New-Object System.Windows.Forms.Padding(4, 8, 4, 4)
            [void]$top.Controls.Add($searchLabel)
            [void]$top.Controls.Add($search)
            [void]$top.Controls.Add($count)

            $grid = New-Object System.Windows.Forms.DataGridView
            $grid.Dock = "Fill"
            $grid.AllowUserToAddRows = $false
            $grid.RowHeadersVisible = $false
            $grid.SelectionMode = "FullRowSelect"
            $grid.AutoSizeColumnsMode = "Fill"
            $grid.BackgroundColor = [System.Drawing.SystemColors]::Window
            [void]$grid.Columns.Add("reading", "讀音")
            [void]$grid.Columns.Add("value", $valueHeader)
            $grid.Columns["reading"].ReadOnly = $true
            $grid.Columns["reading"].FillWeight = 55
            $grid.Columns["value"].FillWeight = 45
            $grid.Columns["value"].DefaultCellStyle.Font = $Context.UiFont

            $bottom = New-Object System.Windows.Forms.FlowLayoutPanel
            $bottom.Dock = "Fill"
            $bottom.AutoSize = $true
            $bottom.WrapContents = $false

            $deleteButton = New-Object System.Windows.Forms.Button
            $deleteButton.Text = "刪除選取的列"
            $deleteButton.Width = 130
            $deleteButton.Height = 30
            $deleteButton.Margin = New-Object System.Windows.Forms.Padding(4)

            $saveButton = New-Object System.Windows.Forms.Button
            $saveButton.Text = "儲存並重啟 PIME"
            $saveButton.Width = 150
            $saveButton.Height = 30
            $saveButton.Margin = New-Object System.Windows.Forms.Padding(4)

            $reloadButton = New-Object System.Windows.Forms.Button
            $reloadButton.Text = "重新載入"
            $reloadButton.Width = 100
            $reloadButton.Height = 30
            $reloadButton.Margin = New-Object System.Windows.Forms.Padding(4)

            # 只有學到的詞需要清理；排名鎖定沒有子字串問題。
            $pruneButton = New-Object System.Windows.Forms.Button
            $pruneButton.Text = "清理重複片段"
            $pruneButton.Width = 130
            $pruneButton.Height = 30
            $pruneButton.Margin = New-Object System.Windows.Forms.Padding(4)
            $pruneButton.Visible = -not $valueIsList

            $status = New-Object System.Windows.Forms.Label
            $status.AutoSize = $true
            $status.Margin = New-Object System.Windows.Forms.Padding(12, 10, 4, 4)
            $status.ForeColor = [System.Drawing.Color]::FromArgb(90, 90, 90)

            [void]$bottom.Controls.Add($deleteButton)
            [void]$bottom.Controls.Add($saveButton)
            [void]$bottom.Controls.Add($reloadButton)
            [void]$bottom.Controls.Add($pruneButton)
            [void]$bottom.Controls.Add($status)

            $entries = New-Object System.Collections.Specialized.OrderedDictionary

            $render = {
                $filter = $search.Text.Trim()
                $grid.Rows.Clear()
                foreach ($key in $entries.Keys) {
                    $value = $entries[$key]
                    if ($filter -and ($key -notlike "*$filter*") -and ($value -notlike "*$filter*")) {
                        continue
                    }
                    [void]$grid.Rows.Add($key, $value)
                }
                $count.Text = "顯示 $($grid.Rows.Count) / 共 $($entries.Count) 筆"
            }.GetNewClosure()

            $load = {
                $entries.Clear()
                $raw = & $readJson $path
                if ($null -eq $raw) {
                    $status.Text = if (Test-Path -LiteralPath $path) { "檔案無法解析" } else { "尚無資料" }
                }
                else {
                    foreach ($property in $raw.PSObject.Properties) {
                        $value = if ($valueIsList) { (@($property.Value) -join "  ") } else { [string]$property.Value }
                        $entries[$property.Name] = $value
                    }
                    $status.Text = "已載入"
                }
                & $render
            }.GetNewClosure()

            $search.Add_TextChanged($render)

            $deleteButton.Add_Click({
                $keys = @()
                foreach ($row in $grid.SelectedRows) {
                    if (-not $row.IsNewRow) { $keys += [string]$row.Cells["reading"].Value }
                }
                if ($keys.Count -eq 0) {
                    $status.Text = "沒有選取任何列"
                    return
                }
                foreach ($key in $keys) { $entries.Remove($key) }
                & $render
                $status.Text = "已移除 $($keys.Count) 筆，尚未儲存"
            }.GetNewClosure())

            # 格子改完值要寫回集合，否則儲存的還是舊資料。
            $grid.Add_CellEndEdit({
                param($sender, $eventArgs)
                $row = $grid.Rows[$eventArgs.RowIndex]
                $key = [string]$row.Cells["reading"].Value
                if ($entries.Contains($key)) {
                    $entries[$key] = [string]$row.Cells["value"].Value
                    $status.Text = "已修改，尚未儲存"
                }
            }.GetNewClosure())

            $reloadButton.Add_Click($load)

            # 清理的判斷規則只有一份，寫在 bopomofo_core\phrase_store.py。
            # 這裡呼叫 PIME 的 Python 執行它，而不是在 PowerShell 裡重寫一遍：
            # 手抄的規則遲早會和真正生效的那份分岔。
            $pruneButton.Add_Click({
                $python = if ($Context.PimeRoot) {
                    Join-Path $Context.PimeRoot "python\python3\python.exe"
                } else { $null }
                $tool = if ($Context.ModuleRoot) {
                    Join-Path $Context.ModuleRoot "prune_phrases.py"
                } else { $null }
                if (-not $python -or -not (Test-Path -LiteralPath $python) -or
                    -not $tool -or -not (Test-Path -LiteralPath $tool)) {
                    $status.Text = "找不到 PIME 的 Python 或清理工具"
                    return
                }
                try {
                    $report = & $python $tool 2>$null | ConvertFrom-Json
                    if ($report.removable -le 0) {
                        $status.Text = "沒有可清理的重複片段（共 $($report.before) 筆）"
                        return
                    }
                    $answer = [System.Windows.Forms.MessageBox]::Show(
                        ("目前 $($report.before) 筆，其中 $($report.removable) 筆的讀音與文字" +
                         "完整包含在更長的詞裡，打那個較長的讀音仍然叫得出來。`r`n`r`n" +
                         "清理後剩 $($report.after) 筆。`r`n`r`n" +
                         "會先自動備份原檔。要清理嗎？"),
                        "清理重複片段",
                        [System.Windows.Forms.MessageBoxButtons]::YesNo,
                        [System.Windows.Forms.MessageBoxIcon]::Question)
                    if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) {
                        $status.Text = "已取消，未變更"
                        return
                    }
                    $done = & $python $tool --apply 2>$null | ConvertFrom-Json
                    & $load
                    $result = & $Context.RestartPime $Context.LauncherPath
                    $status.Text = "已清理 $($done.removable) 筆，剩 $($done.after) 筆。$($result.Message)"
                }
                catch {
                    $status.Text = "清理失敗：$($_.Exception.Message)"
                }
            }.GetNewClosure())

            $saveButton.Add_Click({
                try {
                    $payload = New-Object System.Collections.Specialized.OrderedDictionary
                    foreach ($key in $entries.Keys) {
                        $value = $entries[$key]
                        if ([string]::IsNullOrWhiteSpace($value)) { continue }
                        if ($valueIsList) {
                            $payload[$key] = @($value -split "\s+" | Where-Object { $_ })
                        }
                        else {
                            $payload[$key] = [string]$value
                        }
                    }
                    & $saveJson $path $payload

                    # 執行中的輸入法把整份詞庫存在記憶體裡，任何一次學習都會用
                    # 記憶體內容覆蓋整個檔案。不重啟 PIME，這次編輯遲早被蓋掉。
                    $result = & $Context.RestartPime $Context.LauncherPath
                    $status.Text = "已儲存 $($payload.Count) 筆。$($result.Message)"
                }
                catch {
                    [System.Windows.Forms.MessageBox]::Show(
                        ($_ | Out-String), "儲存失敗",
                        [System.Windows.Forms.MessageBoxButtons]::OK,
                        [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
                }
            }.GetNewClosure())

            & $load

            $layout.Controls.Add($top, 0, 0)
            $layout.Controls.Add($grid, 0, 1)
            $layout.Controls.Add($bottom, 0, 2)
            $page.Controls.Add($layout)
            $page
        }

        [void]$tabs.TabPages.Add((New-LexiconPage "學到的詞（phrases.json）" $Context.PhrasesPath "詞語" $false))
        [void]$tabs.TabPages.Add((New-LexiconPage "排名鎖定（pins.json）" $Context.PinsPath "候選（空白分隔，最前面優先）" $true))

        # ---- 第三頁：使用統計 ----------------------------------------------
        #
        # 詞庫只收多字詞，所以單字永遠是 0——「最常用」不能從 phrases.json 算。
        # 統計來自 usage.json，記錄的是**實際送出過什麼**，單字也算。排名規則
        # 交給 Python，PowerShell 不重寫一份，兩邊才不會各說各話。
        $statsPage = New-Object System.Windows.Forms.TabPage
        $statsPage.Text = "使用統計"
        $statsPage.UseVisualStyleBackColor = $true
        $statsPage.Padding = New-Object System.Windows.Forms.Padding(6)

        $statsLayout = New-Object System.Windows.Forms.TableLayoutPanel
        $statsLayout.Dock = "Fill"
        $statsLayout.ColumnCount = 1
        $statsLayout.RowCount = 3
        [void]$statsLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))
        [void]$statsLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("Percent", 100)))
        [void]$statsLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))

        $statsTop = New-Object System.Windows.Forms.FlowLayoutPanel
        $statsTop.Dock = "Fill"
        $statsTop.AutoSize = $true
        $statsTop.WrapContents = $false

        $statsSummary = New-Object System.Windows.Forms.Label
        $statsSummary.AutoSize = $true
        $statsSummary.Margin = New-Object System.Windows.Forms.Padding(4, 9, 12, 4)

        $statsReload = New-Object System.Windows.Forms.Button
        $statsReload.Text = "重新整理"
        $statsReload.Width = 100
        $statsReload.Height = 28
        $statsReload.Margin = New-Object System.Windows.Forms.Padding(4)

        [void]$statsTop.Controls.Add($statsSummary)
        [void]$statsTop.Controls.Add($statsReload)

        $statsSplit = New-Object System.Windows.Forms.SplitContainer
        $statsSplit.Dock = "Fill"
        $statsSplit.Orientation = "Vertical"
        $statsSplit.SplitterWidth = 8

        $lengthGrid = New-Object System.Windows.Forms.DataGridView
        $lengthGrid.Dock = "Fill"
        $lengthGrid.AllowUserToAddRows = $false
        $lengthGrid.RowHeadersVisible = $false
        $lengthGrid.ReadOnly = $true
        $lengthGrid.SelectionMode = "FullRowSelect"
        $lengthGrid.AutoSizeColumnsMode = "Fill"
        $lengthGrid.BackgroundColor = [System.Drawing.SystemColors]::Window
        [void]$lengthGrid.Columns.Add("length", "字數")
        [void]$lengthGrid.Columns.Add("distinct", "不同的詞")
        [void]$lengthGrid.Columns.Add("commits", "送出次數")

        $lengthLabel = New-Object System.Windows.Forms.Label
        $lengthLabel.Text = "依字數統計（點一列可只看那個長度）"
        $lengthLabel.Dock = "Top"
        $lengthLabel.Height = 22
        $lengthLabel.ForeColor = [System.Drawing.Color]::FromArgb(60, 60, 66)

        $topGrid = New-Object System.Windows.Forms.DataGridView
        $topGrid.Dock = "Fill"
        $topGrid.AllowUserToAddRows = $false
        $topGrid.RowHeadersVisible = $false
        $topGrid.ReadOnly = $true
        $topGrid.SelectionMode = "FullRowSelect"
        $topGrid.AutoSizeColumnsMode = "Fill"
        $topGrid.BackgroundColor = [System.Drawing.SystemColors]::Window
        [void]$topGrid.Columns.Add("text", "詞")
        [void]$topGrid.Columns.Add("count", "次數")
        [void]$topGrid.Columns.Add("last", "最後使用")
        $topGrid.Columns["text"].FillWeight = 40
        $topGrid.Columns["text"].DefaultCellStyle.Font =
            New-Object System.Drawing.Font("Microsoft JhengHei UI", 12)
        $topGrid.Columns["count"].FillWeight = 20
        $topGrid.Columns["last"].FillWeight = 40

        $topLabel = New-Object System.Windows.Forms.Label
        $topLabel.Text = "最常用"
        $topLabel.Dock = "Top"
        $topLabel.Height = 22
        $topLabel.ForeColor = [System.Drawing.Color]::FromArgb(60, 60, 66)

        $statsSplit.Panel1.Controls.Add($lengthGrid)
        $statsSplit.Panel1.Controls.Add($lengthLabel)
        $statsSplit.Panel2.Controls.Add($topGrid)
        $statsSplit.Panel2.Controls.Add($topLabel)

        $statsHint = New-Object System.Windows.Forms.Label
        $statsHint.AutoSize = $true
        $statsHint.MaximumSize = New-Object System.Drawing.Size(880, 0)
        $statsHint.ForeColor = [System.Drawing.Color]::FromArgb(90, 90, 90)
        $statsHint.Margin = New-Object System.Windows.Forms.Padding(4, 8, 4, 4)

        $statsLayout.Controls.Add($statsTop, 0, 0)
        $statsLayout.Controls.Add($statsSplit, 0, 1)
        $statsLayout.Controls.Add($statsHint, 0, 2)
        $statsPage.Controls.Add($statsLayout)

        # 資料放 hashtable：篩選長度時要能改到閉包看得見的那一份。純量做不到，
        # GetNewClosure 給每個閉包自己的快照——這個陷阱在這個控制台咬過五次。
        $stats = @{ Data = $null; Error = $null; Length = $null }

        $loadStats = {
            $stats.Data = $null
            $stats.Error = $null
            $python = if ($Context.PimeRoot) {
                $candidate = Join-Path $Context.PimeRoot (Join-Path "python" (Join-Path "python3" "python.exe"))
                if (Test-Path -LiteralPath $candidate) { $candidate } else { $null }
            } else { $null }
            $reporter = if ($Context.ModuleRoot) {
                $candidate = Join-Path $Context.ModuleRoot "usage_stats.py"
                if (Test-Path -LiteralPath $candidate) { $candidate } else { $null }
            } else { $null }
            if (-not $python) { $stats.Error = "找不到 PIME 的 Python"; return }
            if (-not $reporter) { $stats.Error = "找不到 usage_stats.py，請重新安裝"; return }
            try {
                $raw = (& $python $reporter 200 2>&1 | Out-String)
                if ($LASTEXITCODE -ne 0) {
                    $stats.Error = "usage_stats.py 結束碼 $LASTEXITCODE：$($raw.Trim())"
                    return
                }
                $stats.Data = $raw | ConvertFrom-Json
            }
            catch { $stats.Error = "執行 usage_stats.py 失敗：$($_.Exception.Message)" }
        }.GetNewClosure()

        $renderStats = {
            $lengthGrid.Rows.Clear()
            $topGrid.Rows.Clear()

            if ($null -eq $stats.Data) {
                $statsSummary.Text = "讀不到使用統計"
                $statsHint.Text = [string]$stats.Error
                return
            }

            $data = $stats.Data
            if ([int]$data.tracked -eq 0) {
                $statsSummary.Text = "還沒有任何統計"
                $statsHint.Text = ("使用次數從安裝這版之後才開始記錄，之前打過的字沒有回溯資料——" +
                                   "打一陣子再回來看。統計存在 usage.json，跟詞庫分開放：它壞掉或" +
                                   "不見只損失統計，你的詞庫完全不受影響。")
                return
            }

            foreach ($row in @($data.by_length)) {
                [void]$lengthGrid.Rows.Add([int]$row.length, [int]$row.distinct, [int]$row.commits)
            }

            $epoch = [DateTime]::new(1970, 1, 1, 0, 0, 0, [DateTimeKind]::Utc)
            foreach ($row in @($data.most_used)) {
                $text = [string]$row.text
                if ($null -ne $stats.Length -and $text.Length -ne [int]$stats.Length) { continue }
                $when = if ([int64]$row.last -gt 0) {
                    $epoch.AddSeconds([int64]$row.last).ToLocalTime().ToString("yyyy-MM-dd HH:mm")
                } else { "" }
                [void]$topGrid.Rows.Add($text, [int]$row.count, $when)
            }

            $scope = if ($null -eq $stats.Length) { "全部" } else { "$($stats.Length) 字" }
            $topLabel.Text = "最常用（$scope）"
            $statsSummary.Text = "$([int]$data.tracked) 個不同的詞，共送出 $([int]$data.commits) 次"
            $statsHint.Text = ("統計記錄的是實際送出過什麼，所以單字也算得到——詞庫只收多字詞，" +
                               "用它算不出單字。點左邊某一列可只看那個字數，再點一次取消。" +
                               "這些資料只存在本機。")
        }.GetNewClosure()

        $lengthGrid.Add_SelectionChanged({
            if ($lengthGrid.SelectedRows.Count -eq 0) { return }
            $picked = [int]$lengthGrid.SelectedRows[0].Cells["length"].Value
            $stats.Length = if ($stats.Length -eq $picked) { $null } else { $picked }
            & $renderStats
        }.GetNewClosure())

        $statsReload.Add_Click({
            & $loadStats
            & $renderStats
        }.GetNewClosure())

        & $loadStats
        & $renderStats

        [void]$tabs.TabPages.Add($statsPage)

        $host_ = New-Object System.Windows.Forms.TableLayoutPanel
        $host_.Dock = "Fill"
        $host_.ColumnCount = 1
        $host_.RowCount = 2
        [void]$host_.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("Percent", 100)))
        [void]$host_.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))

        $hint = New-Object System.Windows.Forms.Label
        $hint.AutoSize = $true
        $hint.MaximumSize = New-Object System.Drawing.Size(880, 0)
        $hint.ForeColor = [System.Drawing.Color]::FromArgb(90, 90, 90)
        $hint.Margin = New-Object System.Windows.Forms.Padding(4, 8, 4, 4)
        $hint.Text = "「詞語」欄可直接雙擊修改。輸入法執行中會用記憶體內容覆蓋整個檔案，所以儲存後一定要重啟 PIME —— 儲存鍵已經一併處理。這些資料只存在本機。"

        $host_.Controls.Add($tabs, 0, 0)
        $host_.Controls.Add($hint, 0, 1)
        $host_
    }.GetNewClosure()
}
