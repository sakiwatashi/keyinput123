# 同步分頁：把個人詞庫與一個共用資料夾合併。
#
# 合併規則全部在 bopomofo_core/sync.py，這裡只負責挑資料夾、呼叫它、顯示結果。
# PowerShell 不重寫一份規則——兩邊各說各話正是這個控制台一再踩到的坑。連報告
# 的排版都由 Python 回傳，這裡顯示就好。
#
# 這個分頁的存在理由不只是「有個 GUI」。命令列工具在 PIME 執行中時會拒絕合併，
# 因為執行中的輸入法把整份詞庫放在記憶體裡，下一次學習就會用記憶體內容覆蓋整個
# phrases.json，合併結果就此消失而且毫無錯誤訊息。控制台能在合併後重啟 PIME，
# 讓輸入法從磁碟重新載入，所以它是唯一能在輸入法開著時安全合併的入口。

@{
    Name  = "同步"
    Order = 50
    Build = {
        param($Context)

        $settingsPath = Join-Path $Context.StateRoot "sync.json"

        # 由外殼解析好交進來，測試才能指定一個真的跑得動的直譯器，驗到接線本身。
        $python = $Context.PythonPath

        $syncTool = if ($Context.ModuleRoot) {
            $candidate = Join-Path $Context.ModuleRoot (Join-Path "tools" "sync_user_data.py")
            if (Test-Path -LiteralPath $candidate) { $candidate } else { $null }
        } else { $null }

        # ---- 版面 ----------------------------------------------------------
        $layout = New-Object System.Windows.Forms.TableLayoutPanel
        $layout.Dock = "Fill"
        $layout.ColumnCount = 1
        $layout.RowCount = 4
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("AutoSize")))
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("Percent", 100)))

        $intro = New-Object System.Windows.Forms.Label
        $intro.AutoSize = $true
        $intro.MaximumSize = New-Object System.Drawing.Size(860, 0)
        $intro.Font = $Context.UiFont
        $intro.Text = @"
把這台機器學到的詞跟一個共用資料夾合併，另一台機器指向同一個資料夾再跑一次就會
一致。資料夾放哪裡由你決定（OneDrive、Dropbox、git repo、隨身碟都行）——控制台
不上傳任何東西，只讀寫你指定的那個資料夾。

合併只增不減：任何一邊有的詞都會保留，不會因為另一邊沒有就被當成刪除。唯一會改
動既有值的情況，是同一個讀音在兩台機器上被記成不同的字，那會依實際使用次數決定
並逐條列出。同一份來源合併兩次的結果跟一次相同。
"@

        # ---- 資料夾 --------------------------------------------------------
        $folderRow = New-Object System.Windows.Forms.TableLayoutPanel
        $folderRow.Dock = "Fill"
        $folderRow.AutoSize = $true
        $folderRow.ColumnCount = 3
        $folderRow.RowCount = 1
        [void]$folderRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle("Percent", 100)))
        [void]$folderRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle("AutoSize")))
        [void]$folderRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle("AutoSize")))

        $folderBox = New-Object System.Windows.Forms.TextBox
        $folderBox.Dock = "Fill"
        $folderBox.Font = $Context.UiFont

        # 上次用過的資料夾。不記住的話每次開控制台都要重打一次路徑，而使用者
        # 手打路徑打錯時，合併會安靜地在一個新的空資料夾裡完成，看起來像成功。
        if (Test-Path -LiteralPath $settingsPath) {
            try {
                $saved = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($saved.folder) { $folderBox.Text = [string]$saved.folder }
            }
            catch { }
        }

        $browseButton = New-Object System.Windows.Forms.Button
        $browseButton.Text = "瀏覽…"
        $browseButton.AutoSize = $true
        $browseButton.Font = $Context.UiFont

        $openButton = New-Object System.Windows.Forms.Button
        $openButton.Text = "開啟共用資料夾"
        $openButton.AutoSize = $true
        $openButton.Font = $Context.UiFont

        $folderRow.Controls.Add($folderBox, 0, 0)
        $folderRow.Controls.Add($browseButton, 1, 0)
        $folderRow.Controls.Add($openButton, 2, 0)

        # ---- 按鈕 ----------------------------------------------------------
        $buttonRow = New-Object System.Windows.Forms.FlowLayoutPanel
        $buttonRow.Dock = "Fill"
        $buttonRow.AutoSize = $true
        $buttonRow.WrapContents = $false

        $previewButton = New-Object System.Windows.Forms.Button
        $previewButton.Text = "試跑（不寫入）"
        $previewButton.AutoSize = $true
        $previewButton.Font = $Context.UiFont

        $mergeButton = New-Object System.Windows.Forms.Button
        $mergeButton.Text = "合併並重啟 PIME"
        $mergeButton.AutoSize = $true
        $mergeButton.Font = $Context.UiFont

        $buttonRow.Controls.Add($previewButton)
        $buttonRow.Controls.Add($mergeButton)

        $output = New-Object System.Windows.Forms.TextBox
        $output.Multiline = $true
        $output.ReadOnly = $true
        $output.ScrollBars = "Vertical"
        $output.Dock = "Fill"
        $output.Font = $Context.MonoFont
        $output.Text = "選一個共用資料夾，先按「試跑」看看會變什麼。"

        # ---- 執行 ----------------------------------------------------------
        #
        # 一般區域變數而非 $script:。GetNewClosure 捕捉的是呼叫它的那一層，
        # $script: 指向模組檔的腳本作用域，閉包裡拿到的會是 $null——這個陷阱
        # 在這個控制台已經咬過好幾次。
        $runSync = {
            param([bool]$DryRun)

            if (-not $folderBox.Text.Trim()) {
                $output.Text = "還沒選共用資料夾。按「瀏覽…」挑一個，或直接把路徑貼進上面的欄位。"
                return
            }
            # 失敗原因要分得出來。共用一句「找不到 python 或工具」會讓「明明都
            # 在卻仍然沒反應」完全無從查起。
            if (-not $python) {
                $output.Text = if ($Context.PimeRoot) {
                    "找不到 PIME 的 Python：" + (Join-Path $Context.PimeRoot "python\python3\python.exe")
                } else {
                    "找不到 PIME 安裝位置（登錄檔 Software\PIME 沒有有效路徑）"
                }
                return
            }
            if (-not $syncTool) {
                $output.Text = if ($Context.ModuleRoot) {
                    "找不到 sync_user_data.py：" + (Join-Path $Context.ModuleRoot "tools\sync_user_data.py")
                } else {
                    "找不到輸入法模組（PIME 底下沒有 pinned_bopomofo）"
                }
                return
            }

            $folder = $folderBox.Text.Trim()
            # --state 一定要明講。少了它，工具會用自己的預設值（%APPDATA%\
            # PinnedBopomofo），於是同步的是那個資料夾而不是外殼交進來的
            # StateRoot。正式環境下兩者剛好相同，所以這個 bug 在使用者機器上
            # 不會被發現——但任何測試或非預設路徑都會安靜地同步到錯的地方。
            $arguments = @($syncTool, "--state", $Context.StateRoot, "--folder", $folder, "--json")
            if ($DryRun) { $arguments += "--dry-run" }
            # 控制台自己會重啟 PIME，所以不必被那道「PIME 執行中就拒絕」的閘門
            # 擋住——那道閘門是為了保護沒有能力重啟的命令列使用者。
            else { $arguments += "--force" }

            try {
                # stderr 併進來：出事時那才是有用的那一半。--json 模式下正常輸出
                # 只有一行 JSON，所以取最後一行能容忍前面的警告雜訊。
                $raw = (& $python $arguments 2>&1 | Out-String)
                $line = @($raw -split "`r?`n" | Where-Object { $_.Trim().StartsWith("{") })
                if ($line.Count -eq 0) {
                    $output.Text = "同步工具沒有回傳結果（結束碼 $LASTEXITCODE）：`r`n`r`n$($raw.Trim())"
                    return
                }
                $result = $line[-1] | ConvertFrom-Json
            }
            catch {
                $output.Text = "執行同步工具失敗：$($_.Exception.Message)"
                return
            }

            if (-not $result.ok) {
                $output.Text = [string]$result.error
                return
            }

            $header = if ($DryRun) { "試跑，沒有寫入任何東西。" } else { "已合併並寫回兩邊。" }
            $body = "$header`r`n`r`n本機：$($Context.StateRoot)`r`n共用：$folder`r`n`r`n$($result.text)"

            if (-not $DryRun) {
                # 記住這次用的資料夾。Set-Content -Encoding UTF8 會寫 BOM，
                # 而帶 BOM 的 JSON 會讓 PIMELauncher 無聲地起不來。
                try {
                    $json = ([pscustomobject]@{ folder = $folder } | ConvertTo-Json)
                    [IO.File]::WriteAllText($settingsPath, $json,
                        (New-Object Text.UTF8Encoding($false)))
                }
                catch { }

                # 執行中的輸入法把整份詞庫放在記憶體裡，下一次學習就會用記憶體
                # 內容蓋掉剛剛合併的檔案。不重啟，這次同步遲早白做。
                $restart = & $Context.RestartPime $Context.LauncherPath
                $body += "`r`n`r`n$($restart.Message)"
            }
            $output.Text = $body
        }.GetNewClosure()

        $browseButton.Add_Click({
            $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
            $dialog.Description = "選一個共用資料夾（OneDrive、Dropbox、git repo…）"
            if ($folderBox.Text.Trim() -and (Test-Path -LiteralPath $folderBox.Text.Trim())) {
                $dialog.SelectedPath = $folderBox.Text.Trim()
            }
            if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                $folderBox.Text = $dialog.SelectedPath
            }
            $dialog.Dispose()
        }.GetNewClosure())

        $openButton.Add_Click({
            $folder = $folderBox.Text.Trim()
            if (-not $folder) {
                $output.Text = "還沒選共用資料夾，沒有東西可以開。"
                return
            }
            if (-not (Test-Path -LiteralPath $folder)) {
                $output.Text = "這個資料夾還不存在：$folder`r`n`r`n合併時會自動建立。"
                return
            }
            Start-Process -FilePath "explorer.exe" -ArgumentList "`"$folder`""
        }.GetNewClosure())

        $previewButton.Add_Click({ & $runSync $true }.GetNewClosure())
        $mergeButton.Add_Click({ & $runSync $false }.GetNewClosure())

        $layout.Controls.Add($intro, 0, 0)
        $layout.Controls.Add($folderRow, 0, 1)
        $layout.Controls.Add($buttonRow, 0, 2)
        $layout.Controls.Add($output, 0, 3)
        $layout
    }
}
