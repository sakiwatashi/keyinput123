# 控制台的守門測試。
#
# 三件事只會在成品上出錯，單元測試看不到：
#   1. 含中文的 .ps1 少了 UTF-8 BOM，Windows PowerShell 5.1 直接解析失敗
#   2. 按鍵對照表是 Python 字典的手抄副本，改了單邊就會與實際行為不符
#   3. 一個模組壞掉不該拖垮整個控制台 —— 那是模組化的全部意義
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$panelRoot = Join-Path $root "control_panel"
$shell = Join-Path $panelRoot "SmartPriorityControlPanel.ps1"
$moduleDirectory = Join-Path $panelRoot "modules"

$failures = New-Object System.Collections.Generic.List[string]
function Assert-True([bool]$condition, [string]$message) {
    if (-not $condition) { $failures.Add($message) }
}

# --- 1. 編碼 -------------------------------------------------------------
foreach ($file in @($shell) + @(Get-ChildItem -LiteralPath $moduleDirectory -Filter *.ps1 -File | ForEach-Object { $_.FullName })) {
    $bytes = [IO.File]::ReadAllBytes($file)
    $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
    Assert-True $hasBom "缺少 UTF-8 BOM，Windows PowerShell 5.1 會解析錯誤：$file"
}

# --- 2. 模組合約 ---------------------------------------------------------
$modules = @()
foreach ($file in Get-ChildItem -LiteralPath $moduleDirectory -Filter *.ps1 -File | Sort-Object Name) {
    $definition = & $file.FullName
    if ($definition -is [array]) { $definition = $definition[-1] }
    Assert-True ($null -ne $definition) "模組沒有輸出定義：$($file.Name)"
    Assert-True ([bool]$definition.Name) "模組缺少 Name：$($file.Name)"
    Assert-True ($definition.Build -is [scriptblock]) "模組的 Build 不是 scriptblock：$($file.Name)"
    Assert-True ($null -ne $definition.Order) "模組缺少 Order：$($file.Name)"
    $modules += [pscustomobject]@{ File = $file.Name; Definition = $definition }
}
Assert-True ($modules.Count -ge 4) "預期至少四個模組，實際 $($modules.Count) 個"

# --- 3. 按鍵表與 Python 原始碼一致 --------------------------------------
# 用 ast 解析而非 import：pime_module 需要 PIME 的執行環境才載入得起來。
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Output "略過按鍵表比對：找不到 python"
}
else {
    $extractor = Join-Path $env:TEMP "control_panel_keymap_dump.py"
    @'
import ast, json, sys
root = sys.argv[1]
sys.path.insert(0, root)
from bopomofo_core.keymap import KEY_TO_SYMBOL

source = open(root + r"\pime_module\pinned_bopomofo_ime.py", encoding="utf-8").read()
tree = ast.parse(source)
constants, ctrl = {}, {}
for node in tree.body:
    if not isinstance(node, ast.Assign):
        continue
    name = node.targets[0].id if isinstance(node.targets[0], ast.Name) else None
    if name and name.startswith("VK_") and isinstance(node.value, ast.Constant):
        constants[name] = node.value.value
    if name == "CTRL_PUNCTUATION":
        for key, value in zip(node.value.keys, node.value.values):
            code, shift = key.elts
            code = constants[code.id] if isinstance(code, ast.Name) else code.value
            ctrl["%d|%s" % (code, shift.value)] = value.value
# 寫檔而不是 print。注音符號經過 stdout 時要看主控台的字碼頁臉色：GitHub
# runner 上 Python 的 stdout 是 cp1252，遇到 ㄅ（U+3105）直接 UnicodeEncodeError，
# 輸出變成空的，比對就報「UI 41 筆、Python 0 筆」。本機主控台是中文環境所以
# 一路都過，只有 CI 會紅——這種只在別的機器上失敗的測試最難查。
# 指定 encoding 寫檔，結果就跟執行環境無關。
out = sys.argv[2]
with open(out, "w", encoding="utf-8") as handle:
    json.dump({"bopomofo": KEY_TO_SYMBOL, "ctrl": ctrl}, handle, ensure_ascii=False)
'@ | Set-Content -LiteralPath $extractor -Encoding UTF8

    $dumpPath = Join-Path $env:TEMP "control_panel_keymap_dump.json"
    & $python.Source $extractor $root $dumpPath | Out-Null
    if (-not (Test-Path -LiteralPath $dumpPath)) {
        throw "按鍵表匯出失敗：$extractor 沒有產生 $dumpPath"
    }
    $dump = [IO.File]::ReadAllText($dumpPath, [Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
    Remove-Item -LiteralPath $extractor -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $dumpPath -Force -ErrorAction SilentlyContinue

    # 虛擬鍵碼 → 鍵面字元，與對照表模組畫在鍵盤上的位置對應。
    $vkToKey = @{
        "0x31" = "1"; "0xBA" = ";"; "0xBC" = ","; "0xBE" = "."
        "0xBF" = "/"; "0xDB" = "["; "0xDD" = "]"; "0xDE" = "'"
    }

    $keymapModule = ($modules | Where-Object { $_.File -like "*guide*" }).Definition
    Assert-True ($null -ne $keymapModule.Tables) "按鍵對照模組沒有輸出 Tables，無法比對"

    if ($keymapModule.Tables) {
        # 3a. 注音表：Python 的空白鍵（一聲）在 UI 上單獨呈現，不在鍵位表內。
        $expected = @{}
        foreach ($property in $dump.bopomofo.PSObject.Properties) {
            if ($property.Name -eq " ") { continue }
            $expected[$property.Name] = $property.Value
        }
        $actual = $keymapModule.Tables.Bopomofo
        Assert-True ($actual.Count -eq $expected.Count) `
            "注音表筆數不符：UI $($actual.Count) 筆，Python $($expected.Count) 筆"
        foreach ($key in $expected.Keys) {
            Assert-True ($actual[$key] -eq $expected[$key]) `
                "注音表不符：'$key' UI 是 '$($actual[$key])'，Python 是 '$($expected[$key])'"
        }

        # 3b. Ctrl 標點表，含 Shift 變體。
        $expectedCtrl = @{}
        $expectedCtrlShift = @{}
        foreach ($property in $dump.ctrl.PSObject.Properties) {
            $parts = $property.Name -split "\|"
            $keyChar = $vkToKey[("0x{0:X2}" -f [int]$parts[0])]
            Assert-True ([bool]$keyChar) "測試沒有涵蓋虛擬鍵碼 $($parts[0])，請補進 vkToKey"
            if ($parts[1] -eq "True") { $expectedCtrlShift[$keyChar] = $property.Value }
            else { $expectedCtrl[$keyChar] = $property.Value }
        }
        foreach ($pair in @(
            @{ Label = "Ctrl";       Expected = $expectedCtrl;      Actual = $keymapModule.Tables.Ctrl },
            @{ Label = "Ctrl+Shift"; Expected = $expectedCtrlShift; Actual = $keymapModule.Tables.CtrlShift })) {
            Assert-True ($pair.Actual.Count -eq $pair.Expected.Count) `
                "$($pair.Label) 標點表筆數不符：UI $($pair.Actual.Count) 筆，Python $($pair.Expected.Count) 筆"
            foreach ($key in $pair.Expected.Keys) {
                Assert-True ($pair.Actual[$key] -eq $pair.Expected[$key]) `
                    "$($pair.Label) 標點不符：'$key' UI 是 '$($pair.Actual[$key])'，Python 是 '$($pair.Expected[$key])'"
            }
        }
    }
}

# --- 3c. 說明內容真的產生得出來 -------------------------------------------
# 只檢查「建構成功」不夠：整份說明是靠一連串閉包附加文字，閉包抓不到東西時
# 會安靜地產出一個空白頁，分頁看起來完全正常。所以直接讀回文字長度與關鍵字。
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$fixtureContext = [pscustomobject]@{
    UiFont   = New-Object System.Drawing.Font("Microsoft JhengHei UI", 9)
    MonoFont = New-Object System.Drawing.Font("Consolas", 9)
}
$guideDefinition = ($modules | Where-Object { $_.File -like "*guide*" }).Definition
$guide = & $guideDefinition.Build $fixtureContext
Assert-True ($guide -is [System.Windows.Forms.RichTextBox]) "使用說明沒有回傳文字控制項"
if ($guide -is [System.Windows.Forms.RichTextBox]) {
    Assert-True ($guide.TextLength -gt 600) "使用說明內容過短（$($guide.TextLength) 字），閉包可能沒抓到東西"
    foreach ($topic in @("空白鍵", "Shift", "Ctrl", "個人詞庫", "候選字過濾", "PinnedBopomofo")) {
        Assert-True ($guide.Text -match [regex]::Escape($topic)) "使用說明沒有提到「$topic」"
    }
    # 標點對照表必須是從 Tables 產生的，不是另外手寫一份。
    foreach ($key in $guideDefinition.Tables.Ctrl.Keys) {
        $mark = $guideDefinition.Tables.Ctrl[$key]
        Assert-True ($guide.Text -match [regex]::Escape($mark)) "說明裡找不到標點「$mark」"
    }
}
$guide.Dispose()

# --- 4. 壞掉的模組不會拖垮控制台 ----------------------------------------
# 真的放一個壞檔進去再跑整個殼，而不是只檢查程式碼裡有 try/catch。
$broken = Join-Path $moduleDirectory "99-broken-smoke-fixture.ps1"
try {
    Set-Content -LiteralPath $broken -Encoding UTF8 -Value 'throw "測試用的故意失敗"'
    $output = & $shell -NoShow 2>&1 | Out-String
    Assert-True ($output -match "modules=5") "壞掉的模組應仍被列出並以錯誤分頁呈現，實際輸出：$output"
    Assert-True ($output -match "buildFailures=0") "只有載入失敗的模組不該再產生建構失敗：$output"
    Assert-True ($output -match "載入失敗") "壞掉的模組沒有被標示為載入失敗：$output"
    foreach ($name in @("狀態", "個人詞庫", "使用說明", "候選字過濾")) {
        Assert-True ($output -match $name) "壞掉的模組拖垮了「$name」分頁：$output"
    }
}
finally {
    Remove-Item -LiteralPath $broken -Force -ErrorAction SilentlyContinue
}

# --- 5. 正常情況 ---------------------------------------------------------
$output = & $shell -NoShow 2>&1 | Out-String
Assert-True ($output -match "modules=4") "預期載入三個模組：$output"
Assert-True ($output -notmatch "載入失敗") "正常情況不該有模組載入失敗：$output"
# 建構失敗的分頁標題是正常的，只有內容變成錯誤訊息，所以必須另外檢查 ——
# 少了這一項，20-lexicon 在閉包裡呼叫不到輔助函式的 bug 就矇混過關了。
Assert-True ($output -match "buildFailures=0") "有模組建構失敗：$output"

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) { Write-Output "FAIL: $failure" }
    throw "control_panel_smoke 有 $($failures.Count) 項失敗。"
}
Write-Output "PASS: 控制台外殼、四個模組、按鍵表與 Python 原始碼一致、壞模組隔離"
