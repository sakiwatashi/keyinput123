# 一次跑完所有測試。
#
# CI 分成兩個 job：test 跑 64 位元 Python 的單元測試和 PowerShell 煙霧測試，
# keys 跑真正按下按鍵的那兩支（tests\pime_adapter_smoke.py 與
# tests\pime_all_readings_audit.py）。後者需要 32 位元 Python 才載得動
# libchewing，CI 用 setup-python 的 x86 加上 tools\fetch_pime_runtime.ps1
# 抓下來的 PIME 檔案；本機則直接用 PIME 內建的那一份。
#
# 本機仍然要跑：CI 要推上去才會動，而音節邊界、按住不放、上下文學習、詞頻表
# 這些只有那兩支在守，改完 pinned_bopomofo_ime.py 當場就該知道有沒有壞。
#
#     .\tools\run_all_tests.ps1
#     .\tools\run_all_tests.ps1 -SkipSlow      跳過全讀音稽核
#
# -SkipSlow 是歷史包袱。稽核現在跑 0.8 秒，真正花時間的是按鍵測試（5.7 秒），
# 而那一支不能跳。旗標留著只是為了不讓既有的呼叫壞掉。
[CmdletBinding()]
param(
    [switch]$SkipSlow
)

$ErrorActionPreference = "Continue"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$failures = New-Object System.Collections.Generic.List[string]

function Invoke-Step {
    param([string]$Name, [scriptblock]$Body)
    Write-Host ("  {0,-46}" -f $Name) -NoNewline
    $output = & $Body 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0) {
        Write-Host "PASS"
    }
    else {
        Write-Host "FAIL"
        $failures.Add("$Name`n" + ($output.Trim() -split "`n" | Select-Object -Last 8 | Out-String))
    }
}

# 快取沒失效會讓結果騙人：還原原始碼之後測試仍然報失敗，清掉才對。方向是假陰性，
# 會讓人以為某個改動壞掉了。
Get-ChildItem -LiteralPath $projectRoot -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notlike "*\dist\*" } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "`n== 單元測試（64 位元 Python）=="
Invoke-Step "python -m unittest discover -s tests" { python -m unittest discover -s tests }

Write-Host "`n== PowerShell 煙霧測試 =="
foreach ($script in Get-ChildItem -LiteralPath (Join-Path $projectRoot "tests") -Filter "*_smoke.ps1" -File | Sort-Object Name) {
    Invoke-Step $script.BaseName {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File $script.FullName
    }.GetNewClosure()
}

Write-Host "`n== 需要 PIME 32 位元 Python 的（CI 跑不到）=="
$pythonPath = Join-Path ${env:ProgramFiles(x86)} "PIME\python\python3\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Host "  找不到 $pythonPath —— 這幾支跳過了，CI 也不會跑，等於沒有人在守。" -ForegroundColor Yellow
    $failures.Add("PIME 的 32 位元 Python 不存在，按鍵行為完全沒有被測到")
}
else {
    Invoke-Step "build_pime_overlay.ps1（前置）" {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot "build_pime_overlay.ps1")
    }
    Invoke-Step "pime_adapter_smoke.py" {
        & $pythonPath (Join-Path $projectRoot "tests\pime_adapter_smoke.py")
    }
    if ($SkipSlow) {
        Write-Host "  pime_all_readings_audit.py                     跳過（-SkipSlow，其實只要 0.8 秒）"
    }
    else {
        Invoke-Step "pime_all_readings_audit.py" {
            & $pythonPath (Join-Path $projectRoot "tests\pime_all_readings_audit.py")
        }
    }
}

Write-Host ""
if ($failures.Count -eq 0) {
    Write-Host "全部通過。" -ForegroundColor Green
    exit 0
}
Write-Host "$($failures.Count) 項失敗：" -ForegroundColor Red
foreach ($failure in $failures) {
    Write-Host ""
    Write-Host $failure
}
exit 1
