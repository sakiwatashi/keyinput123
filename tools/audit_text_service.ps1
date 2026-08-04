# 盯著 PIMETextService.dll，下次被刪時記下是誰動的手。
#
# 2026-08-04 那次，PIME 的 x86 與 x64 兩個資料夾在一次關機／開機之間整個消失。
# 已經排除的：我們的安裝與解除安裝腳本（記錄檔與程式碼路徑雙重確認）、
# UTF-8 BOM、Windows Defender、PendingFileRenameOperations。剩下的嫌疑是關機或
# 開機時執行的常駐程式，但沒有任何證據能指名道姓——因為當時沒有人在記錄。
#
# 這支就是那個記錄器。它不預防，只作證。
#
#     .\tools\audit_text_service.ps1 -Report     看有沒有抓到（不需提權）
#     .\tools\audit_text_service.ps1 -Enable     開始盯（需要系統管理員）
#     .\tools\audit_text_service.ps1 -Disable    停止盯（需要系統管理員）
#
# -Enable 會做兩件事，兩件都是系統安全設定，所以一定要由使用者自己執行：
#   1. auditpol 開啟「檔案系統」物件存取稽核
#   2. 在那兩個資料夾上加一條 SACL，只稽核刪除與寫入
# 範圍刻意收得很窄——只有這兩個資料夾、只有刪除與寫入、不稽核讀取，
# 否則安全性記錄會被灌爆，真正的那一筆反而找不到。
[CmdletBinding()]
param(
    [switch]$Enable,
    [switch]$Disable,
    [switch]$Report,
    [string]$PimeRoot,
    [int]$Days = 7
)

$ErrorActionPreference = "Stop"

if (-not $PimeRoot) {
    foreach ($view in @("Registry64", "Registry32")) {
        try {
            $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
                [Microsoft.Win32.RegistryHive]::LocalMachine, $view)
            $key = $base.OpenSubKey("Software\PIME")
            if ($key) {
                $candidate = $key.GetValue("")
                if (-not $candidate) { $candidate = $key.GetValue("InstallDir") }
                if ($candidate -and (Test-Path -LiteralPath $candidate)) { $PimeRoot = $candidate; break }
            }
        }
        catch { }
    }
    if (-not $PimeRoot) { $PimeRoot = Join-Path ${env:ProgramFiles(x86)} "PIME" }
}

$targets = @("x86", "x64") | ForEach-Object { Join-Path $PimeRoot $_ }

function Test-Elevated {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}


# 「檔案系統」子分類的 GUID。用 GUID 而不是名稱：名稱會隨系統語系翻譯，在中文
# Windows 上傳 "File System" 會直接得到 0x00000057 參數錯誤。
$fileSystemSubcategory = "{0CCE921D-69AE-11D9-BED3-505054503030}"
if (-not ($Enable -or $Disable -or $Report)) { $Report = $true }

if ($Enable) {
    if (-not (Test-Elevated)) {
        Write-Output "需要系統管理員權限。請以管理員身分執行這支腳本的 -Enable。"
        return
    }
    # 系統層級：把「檔案系統」這個子分類的物件存取稽核打開。沒有它，SACL 寫了
    # 也不會產生任何事件。
    & auditpol.exe /set /subcategory:$fileSystemSubcategory /success:enable /failure:enable | Out-Null
    Write-Output "已開啟檔案系統物件存取稽核。"

    foreach ($target in $targets) {
        if (-not (Test-Path -LiteralPath $target)) {
            Write-Output "  略過（不存在）：$target"
            continue
        }
        $acl = Get-Acl -LiteralPath $target -Audit
        # 只稽核會造成檔案消失或被換掉的動作。讀取不管——那是常態，量太大。
        $rule = New-Object System.Security.AccessControl.FileSystemAuditRule(
            "Everyone",
            "Delete, DeleteSubdirectoriesAndFiles, WriteData, AppendData, ChangePermissions, TakeOwnership",
            "ContainerInherit, ObjectInherit",
            "None",
            "Success, Failure")
        $acl.AddAuditRule($rule)
        Set-Acl -LiteralPath $target -AclObject $acl
        Write-Output "  已加上稽核規則：$target"
    }
    Write-Output ""
    Write-Output "從現在起，刪除或改寫這兩個資料夾的行為會寫進「安全性」事件記錄。"
    Write-Output "下次出事就跑：.\tools\audit_text_service.ps1 -Report"
    return
}

if ($Disable) {
    if (-not (Test-Elevated)) {
        Write-Output "需要系統管理員權限。請以管理員身分執行這支腳本的 -Disable。"
        return
    }
    foreach ($target in $targets) {
        if (-not (Test-Path -LiteralPath $target)) { continue }
        $acl = Get-Acl -LiteralPath $target -Audit
        # 只移除我們加的那一條，不要整組清掉——別人可能也在稽核這裡。
        foreach ($rule in @($acl.GetAuditRules($true, $false, [Security.Principal.NTAccount]))) {
            if ($rule.IdentityReference.Value -match "Everyone|EVERYONE|所有人") {
                [void]$acl.RemoveAuditRule($rule)
            }
        }
        Set-Acl -LiteralPath $target -AclObject $acl
        Write-Output "  已移除稽核規則：$target"
    }
    # 刻意不關閉系統層級的稽核原則：那是全機器的設定，別的東西可能正在用它。
    Write-Output ""
    Write-Output "資料夾上的稽核規則已移除。"
    Write-Output "系統層級的稽核原則沒有動——那是全機器的設定，可能有別的用途在依賴它。"
    Write-Output "要一併關閉請自行執行："
    Write-Output ("  auditpol /set /subcategory:" + $fileSystemSubcategory + " /success:disable /failure:disable")
    return
}

# ---- 報告 -------------------------------------------------------------------
Write-Output "=== 目前狀態 ==="
# 三態，不是布林。查詢本身可能因為權限不足而失敗，那時候我們**不知道**原則
# 開沒開——把「查不到」寫成「未開啟」是在報告一個沒驗證過的結論，而這支工具
# 的全部價值就在於它說的話可信。
$policyState = "unknown"
try {
    $policy = (& auditpol.exe /get /subcategory:$fileSystemSubcategory | Out-String)
    # 用結束碼判斷，不要比對訊息文字：auditpol 把「權限不足」寫到 stderr，
    # 而這裡只捕捉 stdout，所以訊息比對永遠比不中，會把「查不到」誤報成
    # 「未開啟」。結束碼非 0 就是查詢本身失敗。
    if ($LASTEXITCODE -ne 0) {
        $policyState = "unknown"
    }
    elseif (($policy -match "成功|失敗|Success|Failure") -and ($policy -notmatch "沒有稽核|No Auditing")) {
        $policyState = "on"
    }
    else {
        $policyState = "off"
    }
}
catch { $policyState = "unknown" }
$policyOn = ($policyState -eq "on")
Write-Output ("  稽核原則  : " + $(switch ($policyState) {
    "on"  { "已開啟" }
    "off" { "未開啟（-Enable 才會開始記錄）" }
    default { "查不到（需要提權才讀得到，不代表沒開）" }
}))

foreach ($target in $targets) {
    if (-not (Test-Path -LiteralPath $target)) {
        Write-Output ("  {0} : 資料夾不存在" -f $target)
        continue
    }
    try {
        $rules = @((Get-Acl -LiteralPath $target -Audit).GetAuditRules($true, $false, [Security.Principal.NTAccount]))
        Write-Output ("  {0} : {1} 條稽核規則" -f $target, $rules.Count)
    }
    catch {
        Write-Output ("  {0} : 讀不到稽核設定（需要提權）" -f $target)
    }
}

Write-Output ""
Write-Output "=== 最近 $Days 天的相關事件 ==="
$since = (Get-Date).AddDays(-$Days)
try {
    # 4656 要求控制代碼、4660 物件被刪除、4663 實際存取。三個合起來才看得出
    # 「誰、在什麼時候、對哪個檔案做了什麼」。
    $events = Get-WinEvent -FilterHashtable @{
        LogName = "Security"; Id = 4656, 4660, 4663; StartTime = $since
    } -ErrorAction Stop | Where-Object { $_.Message -match "PIMETextService|\PIME\x86|\PIME\x64" }

    if (-not $events) {
        Write-Output "  沒有相關事件。"
        if ($policyState -ne "on") {
            Write-Output "  （稽核可能還沒開啟，那樣本來就不會有——先跑 -Enable）"
        }
    }
    else {
        foreach ($event in ($events | Select-Object -First 40)) {
            $process = ([regex]::Match($event.Message, "(?m)^\s*(?:處理程序名稱|Process Name):\s*(.+)$")).Groups[1].Value.Trim()
            $object = ([regex]::Match($event.Message, "(?m)^\s*(?:物件名稱|Object Name):\s*(.+)$")).Groups[1].Value.Trim()
            $accesses = ([regex]::Match($event.Message, "(?m)^\s*(?:存取|Accesses):\s*(.+)$")).Groups[1].Value.Trim()
            Write-Output ("  {0}  Id={1}" -f $event.TimeCreated, $event.Id)
            Write-Output ("      行程 : {0}" -f $(if ($process) { $process } else { "(未記錄)" }))
            Write-Output ("      物件 : {0}" -f $object)
            if ($accesses) { Write-Output ("      動作 : {0}" -f $accesses) }
        }
    }
}
catch [Exception] {
    # Get-WinEvent 在「一筆都沒符合」時就會丟例外。那是沒有事件，不是讀不到——
    # 把兩者混為一談會讓人以為權限有問題，然後往完全錯的方向查。
    if ($_.Exception.Message -match "找不到符合|No events were found") {
        Write-Output "  沒有相關事件。"
        if ($policyState -ne "on") {
            Write-Output "  （稽核可能還沒開啟，那樣本來就不會有——先跑 -Enable）"
        }
    }
    else {
        Write-Output "  讀取安全性記錄失敗：$($_.Exception.Message)"
        Write-Output "  （讀安全性記錄需要系統管理員權限）"
    }
}
