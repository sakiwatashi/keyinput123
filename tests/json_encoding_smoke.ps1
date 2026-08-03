# JSON 檔一律不得有 UTF-8 BOM。
#
# 這支測試來自一次把使用者輸入法弄到完全無法使用數小時的事故。
#
# 這個專案有一條相反的規則：含中文的 PowerShell 腳本**必須**有 BOM，否則
# Windows PowerShell 5.1 解析失敗。批次改檔的腳本因此習慣性地補 BOM，而
# 升版時那個習慣套到了 `pime_module/ime.json` 上。
#
# 後果不是「顯示怪怪的」：PIMELauncher 用 jsoncpp 解析 ime.json，jsoncpp
# **不接受 BOM**，在第 1 行第 1 欄丟出 Json::RuntimeError，沒有人接住，
# 行程以 __fastfail 中止（結束碼 0xC0000409），連當機傾印都不產生。使用者
# 看到的只是「輸入法不見了、只能打英文」，而所有靜態檢查都顯示一切正常。
#
# 判準：專案裡每一個 .json 都不得以 EF BB BF 開頭。Python 讀檔多半用
# utf-8-sig 因此不受影響，但 C++ 那端不會原諒。
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$offenders = @()

$skip = @("dist", "release-staging", "release", ".git", "tmp", "__pycache__", "node_modules")
Get-ChildItem -LiteralPath $root -Recurse -Filter "*.json" -File -ErrorAction SilentlyContinue |
    Where-Object {
        $relative = $_.FullName.Substring($root.Length).TrimStart("\")
        $first = ($relative -split "\\")[0]
        $skip -notcontains $first
    } |
    ForEach-Object {
        $stream = [IO.File]::OpenRead($_.FullName)
        try {
            $head = New-Object byte[] 3
            $read = $stream.Read($head, 0, 3)
        }
        finally { $stream.Dispose() }
        if ($read -eq 3 -and $head[0] -eq 0xEF -and $head[1] -eq 0xBB -and $head[2] -eq 0xBF) {
            $offenders += $_.FullName.Substring($root.Length).TrimStart("\")
        }
    }

if ($offenders.Count -gt 0) {
    Write-Output "以下 JSON 檔有 UTF-8 BOM。jsoncpp 會拒絕解析，PIMELauncher 會直接中止："
    $offenders | ForEach-Object { Write-Output "  $_" }
    throw "json_encoding_smoke 找到 $($offenders.Count) 個含 BOM 的 JSON 檔。"
}

Write-Output "PASS: 沒有任何 JSON 檔含 UTF-8 BOM"
