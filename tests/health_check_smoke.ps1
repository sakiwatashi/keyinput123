# 健康檢查本身要能驗出壞掉的安裝，也要在健康時不亂叫。
#
# 這支測試最重要的一項是「它有能力變紅」：先餵一個刻意壞掉的 PIME 目錄，確認
# 它真的報 FAIL。這個專案已經出現過兩支永遠通過卻什麼都沒驗的測試，所以新的
# 檢查工具一定要先證明自己會失敗。
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$checker = Join-Path $root "tools\health_check.ps1"
$failures = New-Object System.Collections.Generic.List[string]

if (-not (Test-Path -LiteralPath $checker)) { throw "找不到 tools\health_check.ps1" }

$sandbox = Join-Path ([IO.Path]::GetTempPath()) ("health-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $sandbox -Force | Out-Null
try {
    $fakePime = Join-Path $sandbox "PIME"
    $fakeState = Join-Path $sandbox "state"
    New-Item -ItemType Directory -Path $fakeState -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $fakePime "python\input_methods\pinned_bopomofo") -Force | Out-Null

    # --- 情境一：DLL 缺失 + JSON 帶 BOM，必須報 FAIL --------------------------
    $bomFile = Join-Path $fakeState "candidate-ui.json"
    [IO.File]::WriteAllText($bomFile, '{"enabled":true}', (New-Object Text.UTF8Encoding($true)))

    $broken = & $checker -PimeRoot $fakePime -StateRoot $fakeState 2>&1 | Out-String

    if ($broken -notmatch "文字服務 DLL") {
        $failures.Add("壞掉的安裝沒有檢查文字服務 DLL")
    }
    if ($broken -notmatch "\[失敗\]") {
        $failures.Add("刻意弄壞的安裝竟然沒有任何失敗項目——這支檢查沒有能力變紅")
    }
    if ($broken -notmatch [regex]::Escape("BOM")) {
        $failures.Add("帶 BOM 的 JSON 沒有被抓到")
    }

    # --- 情境二：-Repair 要真的把 BOM 拿掉（不需要提權）---------------------
    & $checker -PimeRoot $fakePime -StateRoot $fakeState -Repair 2>&1 | Out-Null
    $bytes = [IO.File]::ReadAllBytes($bomFile)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $failures.Add("-Repair 沒有移除 JSON 的 BOM")
    }
    # 內容不能被改壞
    try {
        $value = [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json
        if (-not $value.enabled) { $failures.Add("-Repair 移除 BOM 時改動了內容") }
    }
    catch { $failures.Add("-Repair 之後 JSON 反而解析不了：$($_.Exception.Message)") }

    # --- 情境三：真實安裝不該冒出假警報 -------------------------------------
    # 只有在本機真的裝了 PIME 時才跑；CI 上沒有。
    $installed = "C:\Program Files (x86)\PIME"
    if (Test-Path -LiteralPath (Join-Path $installed "PIMELauncher.exe")) {
        $live = & $checker 2>&1 | Out-String
        if ($live -notmatch "結果：") {
            $failures.Add("對真實安裝執行時沒有輸出結果摘要")
        }
        # 後端沒在跑時報 WARN 是對的（要打字才會啟動），但不該報 FAIL。
        if ($live -match "\[失敗\] 輸入法後端" -and $live -notmatch "\[失敗\] 文字服務 DLL") {
            $failures.Add("後端未執行卻報成失敗，而 DLL 是好的——判準搞反了")
        }
    }
}
finally {
    Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) { Write-Output "FAIL: $failure" }
    throw "health_check_smoke 有 $($failures.Count) 項失敗。"
}
Write-Output "PASS: 健康檢查抓得到壞掉的安裝，-Repair 能移除 BOM 且不改動內容"
