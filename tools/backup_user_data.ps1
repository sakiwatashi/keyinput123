# 個人資料的輪替備份。
#
# phrases.json、pins.json 這些是使用者唯一不可取代的東西——輸入法本體、DLL、
# 詞庫索引通通可以重裝，這些不行。目前唯一的備份只在「清理重複片段」時產生，
# 而且不輪替：實測 %APPDATA% 底下躺了三份 .before-prune-*，只增不減。
#
# 備份刻意放在 %LOCALAPPDATA%，不是跟活資料同一個 %APPDATA% 資料夾。跟本體
# 放在一起的備份，在整個資料夾被刪掉時等於沒有備份。
#
#     .\tools\backup_user_data.ps1              備份一次並輪替
#     .\tools\backup_user_data.ps1 -List        只列出現有備份
[CmdletBinding()]
param(
    [string]$StateRoot,
    [string]$BackupRoot,
    [int]$Keep = 10,
    [switch]$List,
    # 內容跟最新一份備份一樣時仍然產生新檔。預設不會，免得每開一次控制台就
    # 多一份一模一樣的壓縮檔，把真正有差異的舊備份擠出保留範圍。
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not $StateRoot) { $StateRoot = Join-Path $env:APPDATA "PinnedBopomofo" }
if (-not $BackupRoot) { $BackupRoot = Join-Path $env:LOCALAPPDATA "PinnedBopomofo\backups" }

# 要備份哪些。副檔名寫死，避免把 keyevent-trace.log 這種可以再生的大檔案也
# 一起壓進去——它單獨就有 742 KB，備份十份就是 7 MB 的垃圾。
$patterns = @("*.json")

function Get-BackupSet {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    $found = @()
    foreach ($pattern in $patterns) {
        $found += Get-ChildItem -LiteralPath $Path -Filter $pattern -File -ErrorAction SilentlyContinue
    }
    # 暫存檔與既有備份不必收進去。
    return @($found | Where-Object { $_.Name -notlike ".*" } | Sort-Object Name)
}

function Get-SetFingerprint {
    param($Files)
    # 內容指紋：檔名加雜湊。時間戳不算——只是被讀過不代表內容變了。
    $parts = foreach ($file in $Files) {
        "$($file.Name):$((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash)"
    }
    $joined = ($parts -join "|")
    $stream = [IO.MemoryStream]::new([Text.Encoding]::UTF8.GetBytes($joined))
    return (Get-FileHash -InputStream $stream -Algorithm SHA256).Hash
}

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null

$existing = @(Get-ChildItem -LiteralPath $BackupRoot -Filter "PinnedBopomofo-*.zip" -File -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending)

if ($List) {
    if ($existing.Count -eq 0) { Write-Output "還沒有任何備份。" }
    foreach ($file in $existing) {
        Write-Output ("  {0}  {1,10:N0} bytes  {2}" -f $file.Name, $file.Length, $file.LastWriteTime)
    }
    Write-Output ""
    Write-Output "備份位置：$BackupRoot"
    return
}

$files = Get-BackupSet -Path $StateRoot
if ($files.Count -eq 0) {
    Write-Output "找不到可備份的資料（$StateRoot）。"
    return
}

$fingerprint = Get-SetFingerprint -Files $files
$fingerprintPath = Join-Path $BackupRoot "last-fingerprint.txt"
$previous = if (Test-Path -LiteralPath $fingerprintPath) {
    (Get-Content -LiteralPath $fingerprintPath -Raw -ErrorAction SilentlyContinue).Trim()
} else { "" }

if (-not $Force -and $existing.Count -gt 0 -and $previous -eq $fingerprint) {
    Write-Output "資料沒有變動，沿用最新的備份：$($existing[0].Name)"
    return
}

$stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
$target = Join-Path $BackupRoot "PinnedBopomofo-$stamp.zip"
Compress-Archive -LiteralPath @($files | ForEach-Object { $_.FullName }) -DestinationPath $target -Force
Set-Content -LiteralPath $fingerprintPath -Value $fingerprint -Encoding ASCII

Write-Output ("已備份 {0} 個檔案 -> {1}（{2:N0} bytes）" -f
    $files.Count, (Split-Path $target -Leaf), (Get-Item $target).Length)

# ---- 輪替 -------------------------------------------------------------------
$all = @(Get-ChildItem -LiteralPath $BackupRoot -Filter "PinnedBopomofo-*.zip" -File |
    Sort-Object Name -Descending)
if ($all.Count -gt $Keep) {
    foreach ($file in $all[$Keep..($all.Count - 1)]) {
        Remove-Item -LiteralPath $file.FullName -Force
        Write-Output "  已刪除舊備份：$($file.Name)"
    }
}

# 清理工具留下的 .before-prune-* 也要輪替。它們原本只增不減，實測三份就佔了
# 565 KB，而且沒有任何機制會回收。
$strays = @(Get-ChildItem -LiteralPath $StateRoot -Filter "*.before-prune-*" -File -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending)
if ($strays.Count -gt 3) {
    foreach ($file in $strays[3..($strays.Count - 1)]) {
        Remove-Item -LiteralPath $file.FullName -Force
        Write-Output "  已刪除舊的清理前備份：$($file.Name)"
    }
}

Write-Output "備份位置：$BackupRoot"
