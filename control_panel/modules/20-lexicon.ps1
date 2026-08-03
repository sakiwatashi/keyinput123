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
