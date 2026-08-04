# 桌面捷徑的進入點：把輸入法叫起來，然後打開控制台。
#
# 存在的理由是一次真實的困境：控制台被安裝程式關掉之後，使用者沒有地方可以
# 再打開它。托盤圖示由 SmartPriorityCandidateUI.exe 提供，而那支程式要等第一次
# 打字才會啟動——於是「輸入法不能用」的時候恰好也沒有圖示可以點，最需要入口
# 的時刻入口正好不在。
#
# 所以這支腳本不假設任何東西正在跑，缺什麼補什麼，並且照實回報。
[CmdletBinding()]
param(
    # 已經在跑也強制重啟。桌面捷徑預設不帶這個參數：沒壞就不要動它。
    [switch]$Restart,
    # 只做啟動、不開控制台。給測試用。
    [switch]$NoPanel
)

$ErrorActionPreference = "Stop"

$moduleRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "restart_pime.ps1")

# PIME 位置：先問登錄檔，再退回預設路徑。跟控制台同一套規則——殘留的登錄鍵會
# 指向已刪除的目錄，所以一律驗證路徑真的存在才採用。
$pimeRoot = $null
foreach ($view in @("Registry64", "Registry32")) {
    try {
        $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
            [Microsoft.Win32.RegistryHive]::LocalMachine, $view)
        $key = $base.OpenSubKey("Software\PIME")
        if ($key) {
            $candidate = $key.GetValue("")
            if (-not $candidate) { $candidate = $key.GetValue("InstallDir") }
            if ($candidate -and (Test-Path -LiteralPath $candidate)) {
                $pimeRoot = $candidate
                break
            }
        }
    }
    catch { }
}
if (-not $pimeRoot) {
    $fallback = Join-Path ${env:ProgramFiles(x86)} "PIME"
    if (Test-Path -LiteralPath $fallback) { $pimeRoot = $fallback }
}

$report = New-Object System.Collections.Generic.List[string]

if (-not $pimeRoot) {
    $report.Add("找不到 PIME 安裝位置，無法啟動輸入法。請重新安裝。")
}
else {
    # 1. 文字服務的 DLL。它不見過一次，而症狀極具誤導性：語言列照樣選得到
    #    我們的輸入法，按鍵卻全部退回微軟注音，因為 TSF 建立不了 COM 物件。
    #    先驗它，不然後面全部都是白忙。
    $missing = @()
    foreach ($architecture in @("x86", "x64")) {
        $dll = Join-Path $pimeRoot (Join-Path $architecture "PIMETextService.dll")
        if (-not (Test-Path -LiteralPath $dll)) { $missing += $architecture }
    }
    if ($missing.Count -gt 0) {
        $report.Add("PIMETextService.dll 不見了（$($missing -join '、')）。" +
                    "輸入法會退回系統內建的注音，看起來像我們的在跑其實不是。請重新安裝。")
    }

    # 2. PIMELauncher。
    $launcher = Join-Path $pimeRoot "PIMELauncher.exe"
    $running = Get-Process -Name "PIMELauncher" -ErrorAction Ignore
    if ($Restart -or -not $running) {
        if (Test-Path -LiteralPath $launcher) {
            # Restart-Pime 會確認行程真的活著才回報成功。不要自己編一句「已啟動」。
            $result = Restart-Pime $launcher
            $report.Add($result.Message)
        }
        else {
            $report.Add("找不到 PIMELauncher.exe。")
        }
    }
    else {
        $report.Add("PIMELauncher 已在執行（PID $($running.Id -join '、')）。")
    }

    # 3. 托盤圖示與候選視窗的輔助程式。這才是平常的入口，所以一定要補起來。
    $helper = Join-Path $moduleRoot (Join-Path "helper" "SmartPriorityCandidateUI.exe")
    if (Test-Path -LiteralPath $helper) {
        $helperRunning = Get-Process -Name "SmartPriorityCandidateUI" -ErrorAction Ignore
        if ($Restart -and $helperRunning) {
            $helperRunning | Stop-Process -Force -ErrorAction Ignore
            $helperRunning = $null
        }
        if (-not $helperRunning) {
            Start-Process -FilePath $helper | Out-Null
            $report.Add("已啟動候選視窗輔助程式（托盤圖示）。")
        }
        else {
            $report.Add("托盤圖示已在執行。")
        }
    }
    else {
        $report.Add("找不到候選視窗輔助程式，托盤圖示不會出現。")
    }
}

foreach ($line in $report) { Write-Output $line }

if ($NoPanel) { return }

$panel = Join-Path $PSScriptRoot "SmartPriorityControlPanel.ps1"
if (-not (Test-Path -LiteralPath $panel)) {
    Write-Output "找不到控制台腳本。"
    return
}

# 控制台需要 STA 才能跑 WinForms。這支腳本本身不需要，所以另外開一個行程，
# 而不是在這裡硬轉——也讓捷徑點下去之後這支可以直接結束。
$powershell = Join-Path $env:WINDIR (Join-Path "System32" (Join-Path "WindowsPowerShell" (Join-Path "v1.0" "powershell.exe")))
Start-Process -FilePath $powershell -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-STA", "-WindowStyle", "Hidden",
    "-File", ('"' + $panel + '"')
) | Out-Null
