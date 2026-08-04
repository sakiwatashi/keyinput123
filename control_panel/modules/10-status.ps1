# 分頁：狀態總覽與功能開關
#
# 「輸入法到底有沒有在跑」這個問題，先前只能靠登錄檔快照回答，而那正是
# 兩度誤判的原因（見 HANDOVER.md §3）。這裡採用同一份文件的結論：可信的
# 判準是行程有沒有起來、檔案在不在，所以顯示的全是這類事實。
@{
    Name  = "狀態"
    Order = 10
    Build = {
        param($Context)

        $panel = New-Object System.Windows.Forms.TableLayoutPanel
        $panel.Dock = "Fill"
        $panel.ColumnCount = 1
        $panel.RowCount = 3
        [void]$panel.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("Percent", 100)))
        [void]$panel.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))
        [void]$panel.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))

        $grid = New-Object System.Windows.Forms.DataGridView
        $grid.Dock = "Fill"
        $grid.ReadOnly = $true
        $grid.AllowUserToAddRows = $false
        $grid.AllowUserToDeleteRows = $false
        $grid.AllowUserToResizeRows = $false
        $grid.RowHeadersVisible = $false
        $grid.SelectionMode = "FullRowSelect"
        $grid.AutoSizeColumnsMode = "Fill"
        $grid.BackgroundColor = [System.Drawing.SystemColors]::Window
        [void]$grid.Columns.Add("item", "項目")
        [void]$grid.Columns.Add("state", "狀態")
        [void]$grid.Columns.Add("detail", "依據")
        $grid.Columns["item"].FillWeight = 26
        $grid.Columns["state"].FillWeight = 16
        $grid.Columns["detail"].FillWeight = 58

        $toggle = New-Object System.Windows.Forms.CheckBox
        $toggle.Text = "啟用行程外候選視窗（日式直向候選框）"
        $toggle.AutoSize = $true
        $toggle.Margin = New-Object System.Windows.Forms.Padding(4, 10, 4, 2)

        $note = New-Object System.Windows.Forms.Label
        $note.AutoSize = $true
        $note.MaximumSize = New-Object System.Drawing.Size(860, 0)
        $note.ForeColor = [System.Drawing.Color]::FromArgb(90, 90, 90)
        $note.Margin = New-Object System.Windows.Forms.Padding(4, 0, 4, 8)
        $note.Text = "偏好在輸入法啟動時讀取一次（在按鍵事件中讀檔會卡住應用程式的輸入執行緒），所以改完要重啟 PIME 才生效。"

        $buttons = New-Object System.Windows.Forms.FlowLayoutPanel
        $buttons.Dock = "Fill"
        $buttons.AutoSize = $true
        $buttons.WrapContents = $false

        function New-Button([string]$text, [int]$width) {
            $button = New-Object System.Windows.Forms.Button
            $button.Text = $text
            $button.Width = $width
            $button.Height = 30
            $button.Margin = New-Object System.Windows.Forms.Padding(4, 4, 4, 4)
            $button
        }

        $applyButton   = New-Button "套用並重啟 PIME" 150
        $refreshButton = New-Button "重新整理" 100
        $folderButton  = New-Button "開啟資料夾" 110
        [void]$buttons.Controls.Add($applyButton)
        [void]$buttons.Controls.Add($refreshButton)
        [void]$buttons.Controls.Add($folderButton)

        # 這兩個助手寫成**變數**而不是 function，$refresh 也一定要 GetNewClosure。
        #
        # 原本它們是 Build 裡的具名 function，$refresh 是普通 scriptblock。建構
        # 當下一切正常，但按鈕按下去時 Build 這層函式作用域早就結束了，於是
        # Add-Row、Get-CandidateUiEnabled 一個都找不到，連 $toggle 都是 null——
        # 「重新整理」的實際效果是把表格清空然後什麼都填不回去。
        # GetNewClosure 只複製**變數**，不複製 function，所以助手必須是變數。
        $getCandidateUiEnabled = {
            param([string]$path)
            # 預設開啟：只有明確的 enabled:false 會關閉，檔案不存在或損壞一律
            # 視為開啟。這條規則必須與 bopomofo_core\candidate_ui_client.py 一致。
            if (-not (Test-Path -LiteralPath $path)) { return $true }
            try {
                $value = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($null -ne $value.enabled) { return [bool]$value.enabled }
                return $true
            }
            catch { return $true }
        }

        $addRow = {
            param($state, $item, $detail)
            $index = $grid.Rows.Add($item, $state, $detail)
            $colour = switch ($state) {
                "執行中" { [System.Drawing.Color]::FromArgb(0, 120, 60) }
                "存在"   { [System.Drawing.Color]::FromArgb(0, 120, 60) }
                "啟用"   { [System.Drawing.Color]::FromArgb(0, 120, 60) }
                "關閉"   { [System.Drawing.Color]::FromArgb(150, 90, 0) }
                default  { [System.Drawing.Color]::FromArgb(180, 30, 30) }
            }
            $grid.Rows[$index].Cells["state"].Style.ForeColor = $colour
        }.GetNewClosure()

        $refresh = {
            $grid.Rows.Clear()

            # -ErrorAction Ignore 而不是 SilentlyContinue：兩者都不顯示，但
            # SilentlyContinue 仍然把錯誤堆進 $Error。「沒在跑」在這一頁是正常
            # 狀態，不該留下錯誤紀錄——按鈕測試正是以 $Error 的增量判斷成敗。
            $launcher = Get-Process -Name "PIMELauncher" -ErrorAction Ignore
            & $addRow $(if ($launcher) { "執行中" } else { "未執行" }) "PIMELauncher" `
                $(if ($launcher) { "PID $($launcher.Id -join ', ')" } else { "輸入法不會被載入，先重啟 PIME" })

            # PIME 的 python 伺服器要等第一次打字才會起來，所以「未執行」不代表壞掉。
            $server = Get-Process -Name "python" -ErrorAction Ignore
            & $addRow $(if ($server) { "執行中" } else { "未啟動" }) "PIME python 伺服器" `
                $(if ($server) { "PID $($server.Id -join ', ')" } else { "第一次打字才會啟動，尚未打字屬正常" })

            $helper = Get-Process -Name "SmartPriorityCandidateUI" -ErrorAction Ignore
            & $addRow $(if ($helper) { "執行中" } else { "未執行" }) "候選視窗輔助程式" `
                $(if ($helper) { "PID $($helper.Id -join ', ')" } else { "候選視窗關閉時本來就不會執行" })

            if ($Context.ModuleRoot) {
                $imeJson = Join-Path $Context.ModuleRoot "ime.json"
                $version = "讀不到版本"
                if (Test-Path -LiteralPath $imeJson) {
                    try {
                        $version = (Get-Content -LiteralPath $imeJson -Raw -Encoding UTF8 |
                            ConvertFrom-Json).version
                    }
                    catch { $version = "ime.json 無法解析" }
                }
                & $addRow "存在" "輸入法模組 $version" $Context.ModuleRoot
            }
            else {
                & $addRow "找不到" "輸入法模組" "PIME 底下沒有 pinned_bopomofo，輸入法不會出現在切換清單"
            }

            & $addRow $(if ($Context.PimeRoot) { "存在" } else { "找不到" }) "PIME 安裝位置" `
                $(if ($Context.PimeRoot) { $Context.PimeRoot } else { "登錄檔沒有有效的 Software\PIME" })

            $enabled = & $getCandidateUiEnabled $Context.CandidateUi
            $source = if (Test-Path -LiteralPath $Context.CandidateUi) { $Context.CandidateUi } else { "偏好檔不存在（預設開啟）" }
            & $addRow $(if ($enabled) { "啟用" } else { "關閉" }) "行程外候選視窗" $source
            $toggle.Checked = $enabled

            & $addRow $(if (Test-Path -LiteralPath $Context.StateRoot) { "存在" } else { "尚未建立" }) `
                "個人資料夾" $Context.StateRoot
        }.GetNewClosure()

        $applyButton.Add_Click({
            try {
                New-Item -ItemType Directory -Path $Context.StateRoot -Force | Out-Null
                # 明確寫入 true/false 兩種值。刪檔＝回到預設（開啟），
                # 但使用者按下的是一個明確的選擇，就明確記下來。
                $json = @{ enabled = [bool]$toggle.Checked; version = 1 } | ConvertTo-Json
                # UTF-8 **不含** BOM：Python 端以 utf-8 讀取，BOM 會讓 json 解析
                # 失敗並被靜默吞掉，開關就永遠是預設值。PowerShell 5.1 的
                # Set-Content -Encoding UTF8 會寫 BOM，所以這裡不能用它。
                [IO.File]::WriteAllText($Context.CandidateUi, $json,
                    (New-Object Text.UTF8Encoding($false)))

                $result = & $Context.RestartPime $Context.LauncherPath
                & $refresh
                [System.Windows.Forms.MessageBox]::Show(
                    "設定已寫入。$($result.Message)", "智慧優先注音",
                    [System.Windows.Forms.MessageBoxButtons]::OK,
                    $(if ($result.Success) { [System.Windows.Forms.MessageBoxIcon]::Information }
                      else { [System.Windows.Forms.MessageBoxIcon]::Warning })) | Out-Null
            }
            catch {
                [System.Windows.Forms.MessageBox]::Show(
                    ($_ | Out-String), "套用失敗",
                    [System.Windows.Forms.MessageBoxButtons]::OK,
                    [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
            }
        }.GetNewClosure())

        $refreshButton.Add_Click($refresh)

        $folderButton.Add_Click({
            New-Item -ItemType Directory -Path $Context.StateRoot -Force | Out-Null
            Start-Process -FilePath "explorer.exe" -ArgumentList "`"$($Context.StateRoot)`"" | Out-Null
        }.GetNewClosure())

        & $refresh

        $bottom = New-Object System.Windows.Forms.FlowLayoutPanel
        $bottom.Dock = "Fill"
        $bottom.AutoSize = $true
        $bottom.FlowDirection = "TopDown"
        $bottom.WrapContents = $false
        [void]$bottom.Controls.Add($toggle)
        [void]$bottom.Controls.Add($note)

        $panel.Controls.Add($grid, 0, 0)
        $panel.Controls.Add($bottom, 0, 1)
        $panel.Controls.Add($buttons, 0, 2)
        $panel
    }
}
