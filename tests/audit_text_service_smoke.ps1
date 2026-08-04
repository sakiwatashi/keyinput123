# 稽核工具在沒有提權時也必須誠實。
#
# 這支測試盯的是「它會不會報告自己沒驗證過的結論」。第一版就犯了兩次：
# auditpol 因權限不足而查不到時被寫成「未開啟」，Get-WinEvent 在零筆符合時丟的
# 例外被寫成「讀取失敗，需要管理員權限」。兩者都會把人帶去查錯的方向，而這支
# 工具存在的唯一價值就是它說的話可信。
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $root "tools\audit_text_service.ps1"
$failures = New-Object System.Collections.Generic.List[string]
if (-not (Test-Path -LiteralPath $tool)) { throw "找不到 tools\audit_text_service.ps1" }

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$elevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

$output = ""
try {
    $output = (& $tool -Report -Days 1 2>&1 | Out-String)
}
catch {
    $failures.Add("未提權執行 -Report 竟然丟出例外：$($_.Exception.Message)")
}

if ($output) {
    if ($output -notmatch "目前狀態") {
        $failures.Add("報告沒有輸出狀態區塊")
    }
    if ($output -notmatch "讀取安全性記錄失敗" -and $output -notmatch "沒有相關事件") {
        $failures.Add("報告沒有交代事件查詢的結果")
    }
    # 零筆符合不是失敗。
    if ($output -match "讀取安全性記錄失敗[\s\S]*找不到符合") {
        $failures.Add("把「沒有符合的事件」報成了「讀取失敗」")
    }
    if (-not $elevated) {
        if ($output -match "稽核原則\s*:\s*未開啟") {
            $failures.Add("未提權時查不到稽核原則，卻斷言「未開啟」——那是沒驗證過的結論")
        }
        if ($output -notmatch "查不到") {
            $failures.Add("未提權時應該明說查不到")
        }
    }
}

$text = [IO.File]::ReadAllText($tool)
foreach ($name in @("Enable", "Disable", "Report", "PimeRoot", "Days")) {
    if ($text -notmatch ("\" + "$" + $name)) {
        $failures.Add("缺少參數 -$name")
    }
}
# 子分類必須用 GUID：名稱會隨系統語系翻譯，中文 Windows 上傳英文名會得到
# 0x00000057 參數錯誤，實測就是這樣壞的。
if ($text -match 'subcategory:"File System"') {
    $failures.Add("auditpol 用了英文子分類名稱，在非英文 Windows 上會失敗")
}
if ($text -notmatch "0CCE921D-69AE-11D9-BED3-505054503030") {
    $failures.Add("沒有使用檔案系統子分類的 GUID")
}
# auditpol 的權限不足是寫到 stderr 的，比對訊息文字永遠比不中，只能看結束碼。
if ($text -notmatch "LASTEXITCODE") {
    $failures.Add("沒有用結束碼判斷 auditpol 是否查詢成功")
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) { Write-Output "FAIL: $failure" }
    throw "audit_text_service_smoke 有 $($failures.Count) 項失敗。"
}
Write-Output "PASS: 稽核工具未提權時不丟例外，且不會報告沒驗證過的結論"
