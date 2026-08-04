# 一次驗完「輸入法到底有沒有真的在跑」，並在能修的時候直接修。
#
# 這支的存在來自一次真實事故：PIMETextService.dll 從 PIME 底下消失，語言列
# 照樣選得到我們的輸入法，中文也照樣打得出來——因為 TSF 建立不了 COM 物件，
# 就默默退回系統內建的注音。使用者看到的是「好像好了」，實際上我們的輸入法
# 一次都沒被叫用過。診斷那一次花掉四十分鐘，查的每一項都寫在這裡了。
#
# 判準的優先序很重要：先驗「載得起來嗎」，再驗「跑起來了嗎」。順序反過來就會
# 被上面那個假象騙過去。
[CmdletBinding()]
param(
    [switch]$Repair,
    [string]$PimeRoot,
    [string]$StateRoot
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$findings = New-Object System.Collections.Generic.List[object]
function Add-Finding {
    param(
        [ValidateSet("OK", "WARN", "FAIL")][string]$Level,
        [string]$Item,
        [string]$Detail,
        [string]$Fix = ""
    )
    $findings.Add([pscustomobject]@{ Level = $Level; Item = $Item; Detail = $Detail; Fix = $Fix })
}

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
    if (-not $PimeRoot) {
        $fallback = Join-Path ${env:ProgramFiles(x86)} "PIME"
        if (Test-Path -LiteralPath $fallback) { $PimeRoot = $fallback }
    }
}
if (-not $StateRoot) { $StateRoot = Join-Path $env:APPDATA "PinnedBopomofo" }

if (-not $PimeRoot) {
    Add-Finding FAIL "PIME 安裝位置" "登錄檔 Software\PIME 沒有有效路徑，預設位置也不存在" "重新安裝"
}
else {
    Add-Finding OK "PIME 安裝位置" $PimeRoot
}

$moduleRoot = if ($PimeRoot) { Join-Path $PimeRoot "python\input_methods\pinned_bopomofo" } else { $null }

# 1. 文字服務的 DLL：最先驗，因為它壞掉的樣子最像沒壞。
$missingDll = @()
if ($PimeRoot) {
    foreach ($architecture in @("x86", "x64")) {
        $dll = Join-Path $PimeRoot (Join-Path $architecture "PIMETextService.dll")
        if (-not (Test-Path -LiteralPath $dll)) {
            $missingDll += $architecture
            Add-Finding FAIL "文字服務 DLL ($architecture)" "不存在：$dll" "-Repair 可從 vendor 安裝檔還原"
        }
        else {
            $signature = (Get-AuthenticodeSignature -LiteralPath $dll).Status
            if ($signature -eq "Valid") {
                Add-Finding OK "文字服務 DLL ($architecture)" "存在，簽章有效"
            }
            else {
                Add-Finding WARN "文字服務 DLL ($architecture)" "存在，簽章狀態 $signature（自製候選視窗版本會是這樣）"
            }
        }
    }
}

# 2. COM 註冊指向的檔案要真的在。
$clsid = "{35F67E9D-A54D-4177-9697-8B0AB71A9E04}"
foreach ($view in @("CLSID", "WOW6432Node\CLSID")) {
    $key = "HKLM:\SOFTWARE\Classes\$view\$clsid\InprocServer32"
    if (-not (Test-Path $key)) {
        Add-Finding FAIL "COM 註冊 ($view)" "找不到 $key" "重新安裝"
        continue
    }
    $target = (Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue).'(default)'
    if (-not $target) {
        Add-Finding FAIL "COM 註冊 ($view)" "註冊鍵沒有值" "重新安裝"
    }
    elseif (-not (Test-Path -LiteralPath $target)) {
        Add-Finding FAIL "COM 註冊 ($view)" "指向不存在的檔案：$target" "-Repair"
    }
    else {
        Add-Finding OK "COM 註冊 ($view)" $target
    }
}

# 3. 有沒有登記在語言清單裡。
$tip = "0404:$clsid{26EA5CF3-D515-40BE-9535-E7E98D5EE554}"
try {
    $registered = $false
    foreach ($language in (Get-WinUserLanguageList)) {
        if ($language.InputMethodTips -contains $tip) { $registered = $true }
    }
    if ($registered) { Add-Finding OK "語言清單" "智慧優先注音已登記" }
    else { Add-Finding FAIL "語言清單" "沒有登記，切換清單裡不會出現" "重新安裝" }
}
catch {
    Add-Finding WARN "語言清單" "讀取失敗：$($_.Exception.Message)"
}

# 4. 模組本身。
if ($moduleRoot -and (Test-Path -LiteralPath $moduleRoot)) {
    $imeJson = Join-Path $moduleRoot "ime.json"
    if (Test-Path -LiteralPath $imeJson) {
        try {
            $version = (Get-Content -LiteralPath $imeJson -Raw -Encoding UTF8 | ConvertFrom-Json).version
            Add-Finding OK "輸入法模組" "版本 $version"
        }
        catch {
            Add-Finding FAIL "輸入法模組" "ime.json 無法解析：$($_.Exception.Message)" "重新安裝"
        }
    }
    else { Add-Finding FAIL "輸入法模組" "缺少 ime.json" "重新安裝" }

    foreach ($script in @("list_hidden.py", "prune_phrases.py")) {
        $path = Join-Path $moduleRoot $script
        if (Test-Path -LiteralPath $path) { Add-Finding OK "控制台輔助腳本" $script }
        else { Add-Finding WARN "控制台輔助腳本" "缺少 $script，對應的頁面會列不出東西" "重新安裝" }
    }
}
else {
    Add-Finding FAIL "輸入法模組" "PIME 底下沒有 pinned_bopomofo" "重新安裝"
}

# 5. JSON 的 BOM：這一條的代價最貴。jsoncpp 拒收帶 BOM 的 JSON，而
#    PIMELauncher 是以 __fastfail 收場——沒有堆疊、沒有傾印、事件記錄空白。
$bomFiles = @()
$scanRoots = @()
if ($PimeRoot) { $scanRoots += $PimeRoot }
if (Test-Path -LiteralPath $StateRoot) { $scanRoots += $StateRoot }
foreach ($scanRoot in $scanRoots) {
    foreach ($file in (Get-ChildItem -LiteralPath $scanRoot -Filter *.json -Recurse -ErrorAction SilentlyContinue)) {
        $bytes = [IO.File]::ReadAllBytes($file.FullName)
        if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
            $bomFiles += $file.FullName
        }
    }
}
if ($bomFiles.Count -gt 0) {
    foreach ($file in $bomFiles) { Add-Finding FAIL "JSON 帶 UTF-8 BOM" $file "-Repair 會就地移除" }
}
else {
    Add-Finding OK "JSON 編碼" "檢查過的 JSON 都沒有 BOM"
}

# 6. 個人資料。
$phrases = Join-Path $StateRoot "phrases.json"
if (Test-Path -LiteralPath $phrases) {
    try {
        $parsed = Get-Content -LiteralPath $phrases -Raw -Encoding UTF8 | ConvertFrom-Json
        Add-Finding OK "個人詞庫" "$(@($parsed.PSObject.Properties).Count) 筆，可正常解析"
    }
    catch {
        Add-Finding FAIL "個人詞庫" "phrases.json 無法解析：$($_.Exception.Message)" "從備份還原"
    }
}
else {
    Add-Finding WARN "個人詞庫" "還沒有 phrases.json（沒學過任何詞就是這樣）"
}

# 7. 按鍵追蹤有沒有被留著開。它每次按鍵都寫檔，忘了關就會一直拖慢打字。
$traceSwitch = Join-Path $StateRoot "keyevent-trace.json"
if (Test-Path -LiteralPath $traceSwitch) {
    try {
        $enabled = [bool](Get-Content -LiteralPath $traceSwitch -Raw -Encoding UTF8 | ConvertFrom-Json).enabled
        if ($enabled) {
            $log = Join-Path $StateRoot "keyevent-trace.log"
            $size = if (Test-Path -LiteralPath $log) { "{0:N0} bytes" -f (Get-Item $log).Length } else { "尚未產生" }
            Add-Finding WARN "按鍵追蹤" "還開著，每次按鍵都寫檔（記錄檔 $size）" "把 enabled 改成 false 並重啟 PIME"
        }
        else { Add-Finding OK "按鍵追蹤" "已關閉" }
    }
    catch { Add-Finding WARN "按鍵追蹤" "keyevent-trace.json 無法解析" }
}

# 8. 行程放最後，因為它最會騙人。
$launcher = Get-Process -Name "PIMELauncher" -ErrorAction Ignore
if ($launcher) { Add-Finding OK "PIMELauncher" "執行中（PID $($launcher.Id -join '、')）" }
else { Add-Finding WARN "PIMELauncher" "未執行" "點桌面的「智慧優先注音」捷徑" }

# 這一條才是「我們的輸入法有沒有真的接管」的判準。
$server = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "server\.py" }
if ($server) {
    Add-Finding OK "輸入法後端" "執行中（PID $(($server | ForEach-Object { $_.ProcessId }) -join '、')）——確實在處理按鍵"
}
elseif ($missingDll.Count -gt 0) {
    Add-Finding FAIL "輸入法後端" "未執行，且 DLL 缺失——你打的字會被系統內建注音接手，看起來像正常" "-Repair"
}
else {
    Add-Finding WARN "輸入法後端" "未執行。它要等第一次打字才啟動；打幾個字後再檢查一次"
}

if ($Repair) {
    Write-Output ""
    Write-Output "=== 修復 ==="
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $elevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    foreach ($file in $bomFiles) {
        try {
            $text = [IO.File]::ReadAllText($file, [Text.UTF8Encoding]::new($false))
            $text = $text.TrimStart([char]0xFEFF)
            [IO.File]::WriteAllText($file, $text, (New-Object Text.UTF8Encoding($false)))
            Write-Output "  已移除 BOM：$file"
        }
        catch { Write-Output "  移除 BOM 失敗：$file -> $($_.Exception.Message)" }
    }

    if ($missingDll.Count -gt 0) {
        $setup = Join-Path $repoRoot "vendor\PIME-1.3.0-stable-setup.exe"
        $sevenZip = @("C:\Program Files\7-Zip\7z.exe", "C:\Program Files (x86)\7-Zip\7z.exe") |
            Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not (Test-Path -LiteralPath $setup)) { Write-Output "  找不到 $setup，無法還原 DLL。" }
        elseif (-not $sevenZip) { Write-Output "  找不到 7-Zip，無法從安裝檔取出 DLL。" }
        elseif (-not $elevated) { Write-Output "  還原 DLL 需要系統管理員權限，請以管理員身分再跑一次。" }
        else {
            $staging = Join-Path ([IO.Path]::GetTempPath()) ("pime-restore-" + [Guid]::NewGuid().ToString("N"))
            & $sevenZip x $setup ("-o" + $staging) "x86\PIMETextService.dll" "x64\PIMETextService.dll" -y | Out-Null
            foreach ($architecture in $missingDll) {
                $from = Join-Path $staging (Join-Path $architecture "PIMETextService.dll")
                $to = Join-Path $PimeRoot (Join-Path $architecture "PIMETextService.dll")
                if (-not (Test-Path -LiteralPath $from)) { Write-Output "  取不出 $architecture 的 DLL。"; continue }
                # 抽出來的東西沒驗過就往 Program Files 塞是不行的。
                $signature = Get-AuthenticodeSignature -LiteralPath $from
                if ($signature.Status -ne "Valid") {
                    Write-Output "  $architecture 簽章無效（$($signature.Status)），不予安裝。"
                    continue
                }
                New-Item -ItemType Directory -Path (Join-Path $PimeRoot $architecture) -Force | Out-Null
                Copy-Item -LiteralPath $from -Destination $to -Force
                $regsvr = if ($architecture -eq "x86") {
                    Join-Path $env:WINDIR (Join-Path "SysWOW64" "regsvr32.exe")
                } else {
                    Join-Path $env:WINDIR (Join-Path "System32" "regsvr32.exe")
                }
                & $regsvr /s $to
                Write-Output "  已還原並註冊 $architecture：$to"
            }
            Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
            Write-Output "  DLL 已還原。請重新登入或重啟應用程式，TSF 才會重新載入。"
        }
    }

    if ($bomFiles.Count -eq 0 -and $missingDll.Count -eq 0) {
        Write-Output "  沒有可自動修復的項目。"
    }
}

Write-Output ""
foreach ($finding in $findings) {
    $tag = switch ($finding.Level) { "OK" { "[ OK ]" } "WARN" { "[警告]" } "FAIL" { "[失敗]" } }
    Write-Output ("{0} {1,-22} {2}" -f $tag, $finding.Item, $finding.Detail)
    if ($finding.Fix -and $finding.Level -ne "OK") { Write-Output ("       -> " + $finding.Fix) }
}
$failed = @($findings | Where-Object { $_.Level -eq "FAIL" }).Count
$warned = @($findings | Where-Object { $_.Level -eq "WARN" }).Count
$passed = @($findings | Where-Object { $_.Level -eq "OK" }).Count
Write-Output ""
Write-Output ("結果：失敗 {0} 項，警告 {1} 項，通過 {2} 項" -f $failed, $warned, $passed)
if ($failed -gt 0 -and -not $Repair) {
    Write-Output "有失敗項目。加上 -Repair 可自動修復 DLL 缺失與 JSON 的 BOM。"
}
