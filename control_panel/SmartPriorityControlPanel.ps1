# 智慧優先注音 控制台
#
# 一個殼，加上 modules\ 底下各自獨立的分頁模組。殼不知道任何一個模組在做什麼：
# 它只負責找出模組、依序載入、把每個模組回傳的控制項放進分頁。
#
# 模組合約：modules\*.ps1 執行後必須輸出一個雜湊表
#     @{ Name = "分頁標題"; Order = 10; Build = { param($Context) <控制項> } }
# Build 收到共用的 $Context（路徑、狀態），回傳一個 Windows.Forms.Control。
# 任何一個模組載入或建構失敗，只有那一個分頁變成錯誤訊息，其餘照常運作。
#
# WinForms 而非 tkinter：PIME 內建的 Python 沒有 tkinter，終端使用者機器上
# 不保證有 Python。.NET Framework 則是 Windows 一定有的。與 feedback-report.ps1
# 同一套做法。
[CmdletBinding()]
param(
    # 測試用：建好視窗與所有分頁就結束，不進入訊息迴圈。
    [switch]$NoShow
)

$ErrorActionPreference = "Stop"

# WinForms 需要 STA。powershell.exe 預設就是 STA，但從別的宿主叫起來不一定，
# 所以自己確認並重啟，而不是讓它在建立控制項時才丟出難懂的錯誤。
if ([Threading.Thread]::CurrentThread.GetApartmentState() -ne "STA") {
    $arguments = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-STA",
        "-File", "`"$PSCommandPath`""
    )
    if ($NoShow) { $arguments += "-NoShow" }
    $process = Start-Process -FilePath (Get-Process -Id $PID).Path `
        -ArgumentList $arguments -PassThru -Wait
    exit $process.ExitCode
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# 重啟 PIME 一律走這裡。它會確認行程真的活著，並在失敗時據實回報 ——
# 先前各模組自己 Stop+Start 又不檢查，害使用者的輸入法整個消失卻顯示成功。
. (Join-Path $PSScriptRoot "restart_pime.ps1")

$script:UiFont = New-Object System.Drawing.Font("Microsoft JhengHei UI", 9)
$script:MonoFont = New-Object System.Drawing.Font("Consolas", 9)

function New-SmartPriorityContext {
    <#
        每個模組共用的路徑與環境。集中在這裡解析，模組就不必各自重複，
        也不會出現寫死的使用者名稱或磁碟機代號。
    #>
    $stateRoot = Join-Path $env:APPDATA "PinnedBopomofo"

    $pimeRoot = $null
    foreach ($view in @("Registry64", "Registry32")) {
        try {
            $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
                [Microsoft.Win32.RegistryHive]::LocalMachine, $view)
            $key = $base.OpenSubKey("Software\PIME")
            if ($key) {
                $candidate = $key.GetValue("")
                if (-not $candidate) { $candidate = $key.GetValue("InstallDir") }
                # 殘留登錄鍵會指向已刪除的目錄；驗證目錄真的存在才採用。
                # （0.6.6 的安裝失敗就是只讀值不驗路徑造成的。）
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

    $moduleRoot = $null
    if ($pimeRoot) {
        $candidate = Join-Path $pimeRoot "python\input_methods\pinned_bopomofo"
        if (Test-Path -LiteralPath $candidate) { $moduleRoot = $candidate }
    }

    [pscustomobject]@{
        StateRoot     = $stateRoot
        PimeRoot      = $pimeRoot
        ModuleRoot    = $moduleRoot
        LauncherPath  = if ($pimeRoot) { Join-Path $pimeRoot "PIMELauncher.exe" } else { $null }
        CandidateUi   = Join-Path $stateRoot "candidate-ui.json"
        PhrasesPath   = Join-Path $stateRoot "phrases.json"
        PinsPath      = Join-Path $stateRoot "pins.json"
        RestartPime   = ${function:Restart-Pime}
        UiFont        = $script:UiFont
        MonoFont      = $script:MonoFont
    }
}

function Start-SmartPriorityBackup {
    <#
        .SYNOPSIS
        開啟控制台時順手備份一次個人資料。

        永遠不要讓備份擋住控制台開啟：這裡整段包在 try/catch 裡，失敗就安靜
        跳過。控制台是「輸入法壞掉時」的求救入口，它自己一定要開得起來。

        備份工具本身在內容沒變時不會產生新檔，所以開一百次控制台不會塞出
        一百份一樣的壓縮檔。
    #>
    param([string]$ModuleRoot)

    try {
        if (-not $ModuleRoot) { return }
        $tool = Join-Path $ModuleRoot (Join-Path "tools" "backup_user_data.ps1")
        if (-not (Test-Path -LiteralPath $tool)) { return }
        & $tool | Out-Null
    }
    catch { }
}

function New-SmartPriorityErrorPanel {
    param([string]$Title, [string]$Detail)

    $box = New-Object System.Windows.Forms.TextBox
    $box.Multiline = $true
    $box.ReadOnly = $true
    $box.ScrollBars = "Vertical"
    $box.Dock = "Fill"
    $box.Font = $script:MonoFont
    $box.Text = "這個模組無法載入。其餘分頁不受影響。`r`n`r`n$Title`r`n`r`n$Detail"
    $box
}

function Get-SmartPriorityModule {
    <#
        載入一個模組檔並驗證它符合合約。回傳 Name/Order/Build，
        或在任何一步失敗時回傳一個顯示錯誤的替代模組。
    #>
    param([string]$Path)

    $name = [IO.Path]::GetFileNameWithoutExtension($Path)
    try {
        $definition = & $Path
        if ($definition -is [array]) { $definition = $definition[-1] }
        if (-not $definition -or -not $definition.Name -or -not $definition.Build) {
            throw "模組必須輸出含有 Name 與 Build 的雜湊表。"
        }
        $order = if ($null -ne $definition.Order) { [int]$definition.Order } else { 999 }
        return [pscustomobject]@{
            Name  = [string]$definition.Name
            Order = $order
            Build = $definition.Build
        }
    }
    catch {
        # 控制項先做好再包進閉包。GetNewClosure 只帶走「當下這一層的變數」，
        # 帶不走 script 作用域的函式，所以閉包裡呼叫 New-SmartPriorityErrorPanel
        # 會在建構分頁時才失敗 —— 那正是這個 fallback 要避免的事。
        $panel = New-SmartPriorityErrorPanel -Title "檔案：$Path" -Detail ($_ | Out-String)
        return [pscustomobject]@{
            Name  = "$name（載入失敗）"
            Order = 999
            Build = { param($Context) $panel }.GetNewClosure()
        }
    }
}

$context = New-SmartPriorityContext

# 開啟控制台就順手備份一次。使用者會來開控制台，通常正是「要動設定」或
# 「出事了」的時候——兩者都是最值得先留一份的時機。
Start-SmartPriorityBackup -ModuleRoot $context.ModuleRoot

$form = New-Object System.Windows.Forms.Form
$form.Text = "智慧優先注音 控制台"
$form.Font = $script:UiFont
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(940, 660)
$form.MinimumSize = New-Object System.Drawing.Size(760, 520)

$tabs = New-Object System.Windows.Forms.TabControl
$tabs.Dock = "Fill"
$tabs.Padding = New-Object System.Drawing.Point(14, 6)
$form.Controls.Add($tabs)

$moduleDirectory = Join-Path $PSScriptRoot "modules"
$loaded = @()
if (Test-Path -LiteralPath $moduleDirectory) {
    $loaded = @(
        Get-ChildItem -LiteralPath $moduleDirectory -Filter "*.ps1" -File |
            Sort-Object Name |
            ForEach-Object { Get-SmartPriorityModule -Path $_.FullName } |
            Sort-Object Order, Name
    )
}

$buildFailures = @()
foreach ($module in $loaded) {
    $page = New-Object System.Windows.Forms.TabPage
    $page.Text = $module.Name
    $page.Padding = New-Object System.Windows.Forms.Padding(12)
    $page.BackColor = [System.Drawing.SystemColors]::Window
    try {
        $control = & $module.Build $context
        if ($control) { $page.Controls.Add($control) }
        else { throw "Build 沒有回傳控制項。" }
    }
    catch {
        # 建構期的錯誤和載入期一樣，只影響這一個分頁 —— 但必須留下痕跡，
        # 否則分頁標題正常、內容卻是空的，測試與使用者都看不出哪裡壞了。
        $buildFailures += "$($module.Name): $($_.Exception.Message)"
        $page.Controls.Add((New-SmartPriorityErrorPanel `
            -Title "分頁：$($module.Name)" -Detail ($_ | Out-String)))
    }
    $tabs.TabPages.Add($page)
}

if ($tabs.TabPages.Count -eq 0) {
    $tabs.TabPages.Add((New-Object System.Windows.Forms.TabPage))
    $tabs.TabPages[0].Text = "沒有模組"
    $tabs.TabPages[0].Controls.Add((New-SmartPriorityErrorPanel `
        -Title "找不到任何模組" -Detail "預期位置：$moduleDirectory"))
}

if ($NoShow) {
    Write-Output "modules=$($loaded.Count)"
    foreach ($module in $loaded) { Write-Output "  $($module.Order)`t$($module.Name)" }
    Write-Output "buildFailures=$($buildFailures.Count)"
    foreach ($failure in $buildFailures) { Write-Output "  建構失敗 $failure" }
    $form.Dispose()
    return
}

[void]$form.ShowDialog()
$form.Dispose()
