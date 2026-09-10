# 同步分頁真的跑得起來，不只是「按了不會爆」。
#
# control_panel_buttons_smoke.ps1 在空狀態下按每一顆按鈕，確認沒有例外。那擋
# 不住這一類：參數名打錯、JSON 解析失敗、Python 回傳的中文變成亂碼——按鈕照樣
# 不丟例外，只是把錯誤訊息顯示在結果框裡，測試看不出差別。
#
# 所以這支給它一個真的 Python、真的共用資料夾、真的詞庫，按下去之後檢查結果
# 框裡是不是真的出現了合併報告。
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$failures = New-Object System.Collections.Generic.List[string]
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { $failures.Add($Message) }
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$modulePath = Join-Path $projectRoot "control_panel\modules\50-sync.ps1"
if (-not (Test-Path -LiteralPath $modulePath)) { throw "找不到同步分頁模組：$modulePath" }

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "找不到 python，無法驗證同步分頁的接線" }

$sandbox = Join-Path ([IO.Path]::GetTempPath()) ("sync-panel-" + [Guid]::NewGuid().ToString("N"))
$stateRoot = Join-Path $sandbox "state"
$sharedRoot = Join-Path $sandbox "shared"
New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
New-Item -ItemType Directory -Path $sharedRoot -Force | Out-Null

$utf8NoBom = New-Object Text.UTF8Encoding($false)
# 刻意讓 ㄍㄨㄥ ㄕˋ 在兩邊記法不同。報告只在衝突那幾行印出實際的注音與中文，
# 所以這是唯一能驗到「Python 的中文有沒有原封不動穿過 JSON 傳到 UI」的路徑；
# 沒有衝突的報告只有筆數，用它當編碼證據等於沒驗。
[IO.File]::WriteAllText((Join-Path $stateRoot "phrases.json"),
    '{"ㄕㄨˋ ㄧㄝˋ":"樹葉","ㄍㄨㄥ ㄕˋ":"公式"}', $utf8NoBom)
[IO.File]::WriteAllText((Join-Path $sharedRoot "phrases.json"),
    '{"ㄒㄧㄝˇ ㄔㄥˊ ㄕˋ":"寫程式","ㄍㄨㄥ ㄕˋ":"公事"}', $utf8NoBom)

# 重啟 PIME 換成假的。這支測試要驗的是同步接線，不是去動這台機器的輸入法。
$restartCalled = @{ Count = 0 }
$fakeRestart = { param([string]$LauncherPath)
    $restartCalled.Count++
    return @{ Success = $true; Message = "（測試）已重啟 PIME。" }
}.GetNewClosure()

$context = [pscustomobject]@{
    StateRoot    = $stateRoot
    PimeRoot     = $projectRoot
    ModuleRoot   = $projectRoot
    PythonPath   = $python
    LauncherPath = "C:\nonexistent\PIMELauncher.exe"
    RestartPime  = $fakeRestart
    UiFont       = (New-Object System.Drawing.Font("Microsoft JhengHei UI", 9))
    MonoFont     = (New-Object System.Drawing.Font("Consolas", 9))
}

function Get-Descendant {
    # $Text 不能宣告成 [string]：呼叫端傳 $null 會被轉成空字串，於是「不限
    # 文字」變成「只找文字是空的」，找不到目標時回傳 $null，接著每一條依賴
    # 它的斷言都拿空字串去比對——測試看起來在跑，其實什麼都沒檢查到。
    param($Control, [string]$Type, $Text)
    foreach ($child in $Control.Controls) {
        if ($child.GetType().Name -eq $Type -and
            ($null -eq $Text -or $child.Text -like $Text)) { return $child }
        $found = Get-Descendant -Control $child -Type $Type -Text $Text
        if ($found) { return $found }
    }
    return $null
}

try {
    $definition = & $modulePath
    if ($definition -is [array]) { $definition = $definition[-1] }
    $panel = & $definition.Build $context

    $folderBox = Get-Descendant -Control $panel -Type "TextBox" -Text $null
    Assert-True ($null -ne $folderBox) "找不到共用資料夾輸入欄"
    $output = Get-Descendant -Control $panel -Type "TextBox" -Text "*共用資料夾*"

    $preview = Get-Descendant -Control $panel -Type "Button" -Text "*試跑*"
    $merge = Get-Descendant -Control $panel -Type "Button" -Text "*合併*"
    Assert-True ($null -ne $preview) "找不到「試跑」按鈕"
    Assert-True ($null -ne $merge) "找不到「合併並重啟 PIME」按鈕"

    if ($folderBox -and $preview -and $merge) {
        $folderBox.Text = $sharedRoot

        # --- 試跑：要看到報告，而且不能寫入任何東西 ---------------------
        $preview.PerformClick()
        $text = $output.Text
        Assert-True ($text -match "試跑") "試跑後結果框沒有說明這是試跑：$text"
        Assert-True ($text -notmatch "找不到|失敗|Traceback") "試跑出錯：$text"
        # 注音與中文都要原封不動地穿過 JSON 抵達 UI。子行程的輸出用的是主控台
        # 字碼頁，中文直接印會在 cp950 以外變成亂碼——這幾行就是那條路徑的證據。
        Assert-True ($text -match "ㄍㄨㄥ ㄕˋ") "報告裡的注音沒有正確傳回：$text"
        Assert-True ($text -match "公式" -and $text -match "公事") `
            "報告裡的中文沒有正確傳回：$text"
        Assert-True ($text -match "保留") "試跑沒有列出兩邊記法不同的那一筆：$text"

        $localAfterPreview = [IO.File]::ReadAllText((Join-Path $stateRoot "phrases.json"))
        Assert-True ($localAfterPreview -notmatch "寫程式") "試跑竟然真的寫入了本機詞庫"
        Assert-True ($restartCalled.Count -eq 0) "試跑不該重啟 PIME"

        # --- 合併：兩邊都要有對方的詞，而且要重啟 PIME ------------------
        $merge.PerformClick()
        $text = $output.Text
        Assert-True ($text -notmatch "找不到|Traceback") "合併出錯：$text"
        Assert-True ($text -match "已重啟") "合併後沒有重啟 PIME，這次同步遲早被記憶體內容蓋掉：$text"
        Assert-True ($restartCalled.Count -eq 1) "預期重啟 PIME 一次，實際 $($restartCalled.Count) 次"

        $local = [IO.File]::ReadAllText((Join-Path $stateRoot "phrases.json"))
        $shared = [IO.File]::ReadAllText((Join-Path $sharedRoot "phrases.json"))
        Assert-True ($local -match "寫程式") "合併後本機沒有拿到共用資料夾的詞"
        Assert-True ($shared -match "樹葉") "合併後共用資料夾沒有拿到本機的詞"
        # 沒有使用紀錄時衝突保留本機，同步不該悄悄改掉眼前這台機器打得出來的字。
        Assert-True ($local -match "公式" -and $local -notmatch "公事") `
            "沒有使用紀錄的衝突竟然採用了遠端的記法"

        # JSON 帶 BOM 會讓 PIMELauncher 無聲地起不來。
        foreach ($path in @((Join-Path $stateRoot "phrases.json"), (Join-Path $sharedRoot "phrases.json"))) {
            $bytes = [IO.File]::ReadAllBytes($path)
            $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
            Assert-True (-not $hasBom) "同步寫出的 JSON 帶了 BOM：$path"
        }

        # 選過的資料夾要記住，下次開控制台不必重打。
        $settings = Join-Path $stateRoot "sync.json"
        Assert-True (Test-Path -LiteralPath $settings) "沒有記住這次用的共用資料夾"
    }
    $panel.Dispose()
}
finally {
    Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) { Write-Output "FAIL: $failure" }
    throw "sync_panel_smoke 有 $($failures.Count) 項失敗。"
}
Write-Output "PASS: 同步分頁試跑不寫入、合併寫回兩邊、重啟 PIME、JSON 不帶 BOM"
