# Restart-Pime 必須據實回報。
#
# 這支測試來自一次真實事故：控制台與診斷腳本以 Stop-Process + Start-Process
# 重啟 PIME，然後不檢查就回報「已重啟」。PIMELauncher 啟動失敗時使用者的
# 輸入法就此消失，畫面上卻顯示成功，診斷因此往完全錯誤的方向走了很久 ——
# 使用者以為自己「卡在英文」，實際上輸入法根本沒有在跑。
#
# 唯一重要的性質：**行程沒活著就不准回報成功。**
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
. (Join-Path (Join-Path $root "control_panel") "restart_pime.ps1")

$failures = New-Object System.Collections.Generic.List[string]
function Assert-True([bool]$condition, [string]$message) {
    if (-not $condition) { $failures.Add($message) }
}

# 1. 啟動器路徑不存在。
$missing = Restart-Pime -LauncherPath (Join-Path $env:TEMP "no-such-launcher.exe")
Assert-True (-not $missing.Success) "找不到啟動器時不該回報成功"
Assert-True ([bool]$missing.Message) "失敗時必須有訊息"

# 2. 啟動器存在，但一啟動就結束 —— 正是實際發生的情況。
$compiler = Join-Path $env:WINDIR (Join-Path "Microsoft.NET" (Join-Path "Framework" (Join-Path "v4.0.30319" "csc.exe")))
if (Test-Path -LiteralPath $compiler) {
    $fake = Join-Path $env:TEMP "PIMELauncher.exe"
    $stub = Join-Path $env:TEMP "restart_pime_stub.cs"
    'public class Stub { public static int Main(string[] a) { return 0; } }' |
        Set-Content -LiteralPath $stub -Encoding UTF8
    try {
        & $compiler /nologo /target:exe /out:"$fake" "$stub" | Out-Null
        $result = Restart-Pime -LauncherPath $fake
        Assert-True (-not $result.Success) `
            "啟動後立刻結束的啟動器被回報成功了：$($result.Message)"
        Assert-True ($result.Message -match "重新開機") `
            "失敗訊息應告訴使用者怎麼復原，實際是：$($result.Message)"
    }
    finally {
        Remove-Item -LiteralPath $fake -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stub -Force -ErrorAction SilentlyContinue
    }
}
else {
    Write-Output "略過假啟動器測試：找不到 csc.exe"
}

# 3. 控制台模組一律經由 Context.RestartPime，不得自己 Stop/Start。
$moduleDirectory = Join-Path (Join-Path $root "control_panel") "modules"
foreach ($module in Get-ChildItem -LiteralPath $moduleDirectory -Filter *.ps1 -File) {
    $text = [IO.File]::ReadAllText($module.FullName)
    Assert-True ($text -notmatch "Stop-Process[^\r\n]*PIMELauncher") `
        "$($module.Name) 直接砍 PIMELauncher，應改用 Context.RestartPime"
    Assert-True ($text -notmatch "Start-Process[^\r\n]*LauncherPath") `
        "$($module.Name) 自己啟動 PIMELauncher 而不驗證，應改用 Context.RestartPime"
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) { Write-Output "FAIL: $failure" }
    throw "restart_pime_smoke 有 $($failures.Count) 項失敗。"
}
Write-Output "PASS: 重啟失敗會據實回報，控制台模組不自行重啟 PIME"
