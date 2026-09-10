# 按鍵配置分頁：改注音符號落在哪個鍵上。
#
# 驗證規則全部在 bopomofo_core/keymap.py，這裡透過 tools/keymap_layout.py 呼叫它。
# PowerShell 不重寫一份「什麼樣的配置算合法」——兩邊各說各話，使用者就會存下一份
# 控制台說沒問題、輸入法卻拒絕載入的配置。
#
# 只改「打字用」的那一半。送進 libchewing 查候選的鍵位是另一張表，永遠維持大千，
# 理由寫在 keymap.py 的模組說明裡。

@{
    Name  = "按鍵配置"
    Order = 60
    Build = {
        param($Context)

        # 空白鍵在格子裡跟空格子長得一模一樣，使用者無從分辨自己是清空了還是設成
        # 空白。所以畫面上用文字表示，存檔前再翻回去。
        #
        # 一定要宣告在 Build 裡面。放在模組檔的腳本作用域時 GetNewClosure 抓不到
        # ——它捕捉的是「呼叫它的那一層」——閉包裡拿到的是 $null，於是一聲 ˉ 在
        # 表格上顯示成空白格，按儲存就被擋下來說「按鍵必須是單一字元」。
        $spaceLabel = "空白"

        $python = $Context.PythonPath
        $tool = if ($Context.ModuleRoot) {
            $candidate = Join-Path $Context.ModuleRoot (Join-Path "tools" "keymap_layout.py")
            if (Test-Path -LiteralPath $candidate) { $candidate } else { $null }
        } else { $null }

        $layout = New-Object System.Windows.Forms.TableLayoutPanel
        $layout.Dock = "Fill"
        $layout.ColumnCount = 1
        $layout.RowCount = 3
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("Percent", 100)))
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))

        $status = New-Object System.Windows.Forms.Label
        $status.AutoSize = $true
        $status.MaximumSize = New-Object System.Drawing.Size(860, 0)
        $status.Font = $Context.UiFont
        $status.Text = "讀取中…"

        $grid = New-Object System.Windows.Forms.DataGridView
        $grid.Dock = "Fill"
        $grid.Font = $Context.UiFont
        $grid.AllowUserToAddRows = $false
        $grid.AllowUserToDeleteRows = $false
        $grid.RowHeadersVisible = $false
        $grid.AutoSizeColumnsMode = "Fill"
        [void]$grid.Columns.Add("symbol", "注音")
        [void]$grid.Columns.Add("key", "按鍵")
        $grid.Columns["symbol"].ReadOnly = $true
        $grid.Columns["symbol"].FillWeight = 40
        $grid.Columns["key"].FillWeight = 60

        $buttons = New-Object System.Windows.Forms.FlowLayoutPanel
        $buttons.Dock = "Fill"
        $buttons.AutoSize = $true
        $buttons.WrapContents = $false

        $saveButton = New-Object System.Windows.Forms.Button
        $saveButton.Text = "儲存並重啟 PIME"
        $saveButton.AutoSize = $true
        $saveButton.Font = $Context.UiFont

        $resetButton = New-Object System.Windows.Forms.Button
        $resetButton.Text = "還原為大千"
        $resetButton.AutoSize = $true
        $resetButton.Font = $Context.UiFont

        $reloadButton = New-Object System.Windows.Forms.Button
        $reloadButton.Text = "重新載入"
        $reloadButton.AutoSize = $true
        $reloadButton.Font = $Context.UiFont

        $buttons.Controls.Add($saveButton)
        $buttons.Controls.Add($resetButton)
        $buttons.Controls.Add($reloadButton)

        # hashtable：重新載入要能改到閉包看得見的那一份，純量做不到（GetNewClosure
        # 給每個閉包自己的快照）。這個陷阱在這個控制台已經咬過好幾次。
        $state = @{ Ready = $false }

        $runTool = {
            param([string[]]$ToolArguments)

            if (-not $python) {
                return @{ ok = $false; error = if ($Context.PimeRoot) {
                    "找不到 PIME 的 Python：" + (Join-Path $Context.PimeRoot "python\python3\python.exe")
                } else {
                    "找不到 PIME 安裝位置（登錄檔 Software\PIME 沒有有效路徑）"
                } }
            }
            if (-not $tool) {
                return @{ ok = $false; error = if ($Context.ModuleRoot) {
                    "找不到 keymap_layout.py：" + (Join-Path $Context.ModuleRoot "tools\keymap_layout.py")
                } else {
                    "找不到輸入法模組（PIME 底下沒有 pinned_bopomofo）"
                } }
            }
            try {
                $raw = (& $python (@($tool) + $ToolArguments) 2>&1 | Out-String)
                $line = @($raw -split "`r?`n" | Where-Object { $_.Trim().StartsWith("{") })
                if ($line.Count -eq 0) {
                    return @{ ok = $false; error = "工具沒有回傳結果：$($raw.Trim())" }
                }
                return ($line[-1] | ConvertFrom-Json)
            }
            catch {
                return @{ ok = $false; error = "執行 keymap_layout.py 失敗：$($_.Exception.Message)" }
            }
        }.GetNewClosure()

        $load = {
            $grid.Rows.Clear()
            $state.Ready = $false
            $result = & $runTool @("--dump")
            if (-not $result.ok) {
                $status.Text = [string]$result.error
                return
            }

            # 反轉成「符號 → 按鍵」，也就是畫面上的形狀。
            $keyFor = @{}
            foreach ($property in $result.active.PSObject.Properties) {
                $keyFor[[string]$property.Value] = [string]$property.Name
            }
            foreach ($symbol in $result.symbols) {
                $key = [string]$keyFor[[string]$symbol]
                if ($key -eq " ") { $key = $spaceLabel }
                [void]$grid.Rows.Add([string]$symbol, $key)
            }

            $state.Ready = $true
            $status.Text = "目前配置：$($result.name)　（$($result.symbols.Count) 個符號）"
            if ($result.problem) {
                # 輸入法會安靜地退回大千，控制台是唯一能說出原因的地方。使用者
                # 改了設定卻毫無反應，就是從這裡查起。
                $status.Text += "`r`n自訂配置沒有生效：$($result.problem)"
            }
        }.GetNewClosure()

        $saveButton.Add_Click({
            if (-not $state.Ready) {
                $status.Text = "配置還沒讀進來，沒有東西可以存。"
                return
            }
            $symbols = New-Object System.Collections.Specialized.OrderedDictionary
            foreach ($row in $grid.Rows) {
                $symbol = [string]$row.Cells["symbol"].Value
                $key = [string]$row.Cells["key"].Value
                if ($key -eq $spaceLabel) { $key = " " }
                $symbols[$symbol] = $key
            }

            $candidate = Join-Path $env:TEMP ("keymap-candidate-" + [Guid]::NewGuid().ToString("N") + ".json")
            try {
                $json = ([pscustomobject]@{ name = "自訂"; symbols = $symbols } | ConvertTo-Json -Depth 5)
                # 這份是暫存檔，但 keymap_layout.py 用 utf-8-sig 讀，兩種都吃得下。
                # 仍然不寫 BOM——習慣一致比較不會有人照著抄到真正的設定檔上。
                [IO.File]::WriteAllText($candidate, $json, (New-Object Text.UTF8Encoding($false)))

                $result = & $runTool @("--apply", $candidate)
                if (-not $result.ok) {
                    $status.Text = "沒有存檔：$($result.error)"
                    return
                }
                # 執行中的輸入法在啟動時才讀鍵位，不重啟就完全看不出有改過。
                $restart = & $Context.RestartPime $Context.LauncherPath
                $status.Text = "已儲存 $($result.count) 個鍵位。$($restart.Message)"
            }
            finally {
                Remove-Item -LiteralPath $candidate -Force -ErrorAction SilentlyContinue
            }
        }.GetNewClosure())

        $resetButton.Add_Click({
            $result = & $runTool @("--reset")
            if (-not $result.ok) {
                $status.Text = "還原失敗：$($result.error)"
                return
            }
            $restart = & $Context.RestartPime $Context.LauncherPath
            & $load
            $status.Text = "已還原為內建大千鍵位。$($restart.Message)"
        }.GetNewClosure())

        $reloadButton.Add_Click({ & $load }.GetNewClosure())

        & $load

        $layout.Controls.Add($status, 0, 0)
        $layout.Controls.Add($grid, 0, 1)
        $layout.Controls.Add($buttons, 0, 2)
        $layout
    }
}
