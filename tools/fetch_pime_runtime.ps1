# 取得 CI 跑按鍵行為測試所需的 PIME 檔案。
#
# tests\pime_adapter_smoke.py 和 tests\pime_all_readings_audit.py 是唯一真正
# 按下按鍵、看輸出什麼的測試——音節邊界、按住不放、上下文學習、詞頻表，全都
# 只有它們在守。但它們需要 PIME 的 textService.py 與 keycodes.py，而 GitHub
# runner 上沒有裝 PIME，於是這兩支一直只在本機跑。改完轉接層忘了本機跑，CI
# 會全綠而輸入法是壞的。
#
# 這兩個檔在 PIME 裡沒有任何 import，抓下來放進一個目錄、把 PIME_ROOT 指過去
# 就夠了。版本釘在 THIRD_PARTY_NOTICES.txt 記載的那個 commit，跟安裝包附帶的
# 是同一份（實測位元組相同）。
#
# 雜湊要對。抓取是把第三方的位元組拉進建置流程，不驗就等於信任那個 URL 當下
# 回傳的任何東西。對不上就停，不要繼續跑一個測不到東西的測試。
#
#     .\tools\fetch_pime_runtime.ps1 -Destination pime-ci
#     $env:PIME_ROOT = "$PWD\pime-ci"
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Destination
)

$ErrorActionPreference = "Stop"

# PIME v1.3.0-stable 隨附安裝程式來源版本，見 THIRD_PARTY_NOTICES.txt。
$commit = "571759f471c93e288682305148df751a12f5415e"
$expected = @{
    "textService.py" = "C84FC2E9E79824D0D7692C895BA385287F6E29A3E5BA8CC25945B913694026CE"
    "keycodes.py"    = "E8FAAFBE5B8B01180CC822302278C14A71D688536E9C2A908BF9867614DB7A3D"
}

$pythonDir = Join-Path $Destination "python"
New-Item -ItemType Directory -Path $pythonDir -Force | Out-Null

foreach ($name in $expected.Keys) {
    $target = Join-Path $pythonDir $name
    $url = "https://raw.githubusercontent.com/EasyIME/PIME/$commit/python/$name"
    Write-Host "抓取 $name"
    Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing

    $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($actual -ne $expected[$name]) {
        throw "$name 的 SHA256 對不上。預期 $($expected[$name])，實際 $actual。上游變了或抓到了別的東西，測試不要繼續。"
    }
}

Write-Host "PIME 執行期檔案就緒：$pythonDir"
