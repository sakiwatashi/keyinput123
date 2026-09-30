# 讓 Windows「應用程式」清單裡的版本號跟實際安裝的一致。
#
# 版本號只有 NSIS 安裝檔會寫。從原始碼用 install.ps1 更新之後，清單還停在上一次
# 跑 EXE 的版本——實測一台機器跑的是 0.8.1，清單寫 0.6.5。
#
# 只改版本號會讓清單說謊：那筆紀錄的「解除安裝」執行的是 InstallLocation 裡的
# uninstall.ps1，也就是當初 EXE 放進去的那一版。所以先把 NSIS 會放進那個資料夾的
# 檔案換成現在的版本，全部換好之後才改版本號；換到一半失敗，版本號就不動。
#
# 兩個登錄檢視都要找。NSIS 是 32 位元安裝程式，紀錄寫在 WOW6432Node；提權後的
# install.ps1 是 64 位元 PowerShell，直接寫 HKLM:\SOFTWARE\... 會落到另一個檢視，
# 清單照樣顯示舊版號。
#
# 找不到紀錄就什麼都不做：純原始碼安裝沒有 Uninstall.exe，不該憑空造一筆解除安裝
# 不了的紀錄。安裝目錄裡沒有 Uninstall.exe 的紀錄也不動。
function Sync-UninstallEntry {
    param(
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string[]]$RegistryPaths,
        [Parameter(Mandatory = $true)][string[]]$PayloadFiles
    )

    $result = [pscustomobject]@{ Updated = @(); Skipped = @() }
    foreach ($key in $RegistryPaths) {
        if (-not (Test-Path -LiteralPath $key)) {
            continue
        }
        $location = (Get-ItemProperty -LiteralPath $key).InstallLocation
        if ([string]::IsNullOrWhiteSpace($location) -or
            -not (Test-Path -LiteralPath (Join-Path $location "Uninstall.exe"))) {
            $result.Skipped += "$key (no Uninstall.exe in its install location)"
            continue
        }
        foreach ($file in $PayloadFiles) {
            Copy-Item -LiteralPath $file -Destination $location -Force -ErrorAction Stop
        }
        Set-ItemProperty -LiteralPath $key -Name "DisplayVersion" -Value $Version -ErrorAction Stop
        $result.Updated += $key
    }
    return $result
}
