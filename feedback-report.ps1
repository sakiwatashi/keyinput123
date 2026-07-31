param(
    [string]$DataPath = (Join-Path $env:APPDATA "PinnedBopomofo\feedback.json"),
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName Microsoft.VisualBasic
[System.Windows.Forms.Application]::EnableVisualStyles()

$script:entries = @()

function Load-Feedback {
    if (-not (Test-Path -LiteralPath $DataPath)) {
        $script:entries = @()
        return
    }
    try {
        $raw = Get-Content -LiteralPath $DataPath -Raw -Encoding UTF8 |
            ConvertFrom-Json
        $script:entries = @($raw.entries)
    }
    catch {
        [System.Windows.Forms.MessageBox]::Show(
            "無法讀取錯誤資料。原始檔案不會被修改。`n$($_.Exception.Message)",
            "智慧優先注音",
            "OK",
            "Warning"
        ) | Out-Null
        $script:entries = @()
    }
}

function Save-Feedback {
    $parent = Split-Path -Parent $DataPath
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary = Join-Path $parent (".feedback.{0}.tmp" -f $PID)
    $payload = [ordered]@{ version = 1; entries = @($script:entries) }
    $json = $payload | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText(
        $temporary,
        $json + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporary -Destination $DataPath -Force
}

function Selected-Entries {
    $identifiers = @($grid.SelectedRows | ForEach-Object {
        [string]$_.Cells[0].Value
    })
    if ($identifiers.Count -eq 0) { return @() }
    return @($script:entries | Where-Object { $identifiers -contains $_.id })
}

function Refresh-Grid {
    $grid.Rows.Clear()
    foreach ($entry in ($script:entries | Sort-Object last_seen -Descending)) {
        $readings = @($entry.readings) -join " "
        $index = $grid.Rows.Add(
            [string]$entry.id,
            $readings,
            [string]$entry.converted,
            [string]$entry.expected,
            [int]$entry.count,
            [string]$entry.last_seen
        )
        $grid.Rows[$index].Cells[1].ToolTipText = $readings
    }
    $status.Text = "本機共有 $($script:entries.Count) 筆使用者明確改選紀錄"
}

if ($SelfTest) {
    Write-Output "feedback-report.ps1 syntax OK"
    exit 0
}

$form = [System.Windows.Forms.Form]::new()
$form.Text = "智慧優先注音－轉換錯誤回報工具"
$form.Size = [Drawing.Size]::new(900, 590)
$form.MinimumSize = [Drawing.Size]::new(760, 480)
$form.StartPosition = "CenterScreen"
$form.Font = [Drawing.Font]::new("Microsoft JhengHei UI", 10)

$intro = [System.Windows.Forms.Label]::new()
$intro.AutoSize = $false
$intro.Location = [Drawing.Point]::new(18, 16)
$intro.Size = [Drawing.Size]::new(845, 62)
$intro.Text = "以下只列出您曾經明確改選的轉換結果。資料目前只存在這台電腦，不包含前後句、應用程式名稱或身分資料，也不會自動上傳。請先檢查並移除不想分享的項目。"
$form.Controls.Add($intro)

$grid = [System.Windows.Forms.DataGridView]::new()
$grid.Location = [Drawing.Point]::new(18, 84)
$grid.Size = [Drawing.Size]::new(845, 365)
$grid.Anchor = "Top,Bottom,Left,Right"
$grid.AllowUserToAddRows = $false
$grid.AllowUserToDeleteRows = $false
$grid.ReadOnly = $true
$grid.MultiSelect = $true
$grid.SelectionMode = "FullRowSelect"
$grid.AutoSizeColumnsMode = "Fill"
$grid.RowHeadersVisible = $false
[void]$grid.Columns.Add("id", "識別碼")
$grid.Columns[0].Visible = $false
[void]$grid.Columns.Add("readings", "輸入注音")
[void]$grid.Columns.Add("converted", "原轉換結果")
[void]$grid.Columns.Add("expected", "使用者改選結果")
[void]$grid.Columns.Add("count", "次數")
[void]$grid.Columns.Add("lastSeen", "最近發生時間")
$grid.Columns[4].FillWeight = 35
$grid.Columns[5].FillWeight = 80
$form.Controls.Add($grid)

$status = [System.Windows.Forms.Label]::new()
$status.Location = [Drawing.Point]::new(18, 458)
$status.Size = [Drawing.Size]::new(845, 24)
$status.Anchor = "Bottom,Left,Right"
$form.Controls.Add($status)

$editButton = [System.Windows.Forms.Button]::new()
$editButton.Text = "編輯預期結果"
$editButton.Location = [Drawing.Point]::new(18, 495)
$editButton.Size = [Drawing.Size]::new(130, 34)
$editButton.Anchor = "Bottom,Left"
$editButton.Add_Click({
    $selected = @(Selected-Entries)
    if ($selected.Count -ne 1) {
        [System.Windows.Forms.MessageBox]::Show("請選取一筆資料再編輯。") | Out-Null
        return
    }
    $entry = $selected[0]
    $value = [Microsoft.VisualBasic.Interaction]::InputBox(
        "請輸入正確的轉換結果：",
        "編輯預期結果",
        [string]$entry.expected
    )
    if ($value -and $value.Length -eq @($entry.readings).Count) {
        $entry.expected = $value
        Save-Feedback
        Refresh-Grid
    }
    elseif ($value) {
        [System.Windows.Forms.MessageBox]::Show(
            "結果字數必須和注音音節數相同。"
        ) | Out-Null
    }
})
$form.Controls.Add($editButton)

$removeButton = [System.Windows.Forms.Button]::new()
$removeButton.Text = "移除選取項目"
$removeButton.Location = [Drawing.Point]::new(158, 495)
$removeButton.Size = [Drawing.Size]::new(130, 34)
$removeButton.Anchor = "Bottom,Left"
$removeButton.Add_Click({
    $selected = @(Selected-Entries)
    if ($selected.Count -eq 0) { return }
    $ids = @($selected | ForEach-Object { $_.id })
    $script:entries = @($script:entries | Where-Object { $ids -notcontains $_.id })
    Save-Feedback
    Refresh-Grid
})
$form.Controls.Add($removeButton)

$exportButton = [System.Windows.Forms.Button]::new()
$exportButton.Text = "匯出 JSON"
$exportButton.Location = [Drawing.Point]::new(298, 495)
$exportButton.Size = [Drawing.Size]::new(110, 34)
$exportButton.Anchor = "Bottom,Left"
$exportButton.Add_Click({
    $selected = @(Selected-Entries)
    if ($selected.Count -eq 0) { $selected = @($script:entries) }
    $dialog = [System.Windows.Forms.SaveFileDialog]::new()
    $dialog.Filter = "JSON 檔案 (*.json)|*.json"
    $dialog.FileName = "smart-bopomofo-feedback.json"
    if ($dialog.ShowDialog() -eq "OK") {
        $payload = [ordered]@{ version = 1; entries = $selected }
        [IO.File]::WriteAllText(
            $dialog.FileName,
            ($payload | ConvertTo-Json -Depth 8),
            [Text.UTF8Encoding]::new($false)
        )
    }
})
$form.Controls.Add($exportButton)

$reportButton = [System.Windows.Forms.Button]::new()
$reportButton.Text = "建立 GitHub 回報"
$reportButton.Location = [Drawing.Point]::new(548, 495)
$reportButton.Size = [Drawing.Size]::new(150, 34)
$reportButton.Anchor = "Bottom,Right"
$reportButton.Add_Click({
    $selected = @(Selected-Entries)
    if ($selected.Count -eq 0) {
        [System.Windows.Forms.MessageBox]::Show("請先選取要回報的項目。") | Out-Null
        return
    }
    if ($selected.Count -gt 40) {
        [System.Windows.Forms.MessageBox]::Show("一次最多回報 40 筆，請減少選取項目。") | Out-Null
        return
    }
    $answer = [System.Windows.Forms.MessageBox]::Show(
        "選取內容將放入公開 GitHub issue 的編輯頁。瀏覽器開啟後仍需由您確認並按下送出。是否繼續？",
        "確認回報範圍",
        "YesNo",
        "Warning"
    )
    if ($answer -ne "Yes") { return }
    $lines = @(
        "以下資料由智慧優先注音的本機錯誤回報工具產生。",
        "",
        "| 輸入注音 | 原轉換 | 使用者改選 | 次數 |",
        "|---|---|---|---:|"
    )
    foreach ($entry in $selected) {
        $reading = (@($entry.readings) -join " ").Replace("|", "\|")
        $converted = ([string]$entry.converted).Replace("|", "\|")
        $expected = ([string]$entry.expected).Replace("|", "\|")
        $lines += "| $reading | $converted | $expected | $($entry.count) |"
    }
    $body = $lines -join "`n"
    $title = "輸入法轉換錯誤回報（$($selected.Count) 筆）"
    $url = "https://github.com/sakiwatashi/keyinput123/issues/new?title=$([Uri]::EscapeDataString($title))&body=$([Uri]::EscapeDataString($body))"
    Start-Process $url
})
$form.Controls.Add($reportButton)

$closeButton = [System.Windows.Forms.Button]::new()
$closeButton.Text = "關閉"
$closeButton.Location = [Drawing.Point]::new(708, 495)
$closeButton.Size = [Drawing.Size]::new(155, 34)
$closeButton.Anchor = "Bottom,Right"
$closeButton.Add_Click({ $form.Close() })
$form.Controls.Add($closeButton)

Load-Feedback
Refresh-Grid
[void]$form.ShowDialog()
