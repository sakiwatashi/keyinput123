# 交接文件（2026-07-31）

寫給下一個接手這個專案的人或 AI。長期規範在 `AGENTS.md` 與 `AI_MAINTENANCE.md`；
本文只記錄**這次工作階段的成果、尚未解決的問題,以及踩過的坑**。

## 1. 專案現況

- 正式位置：https://github.com/sakiwatashi/keyinput123
- 最新版本：**v0.6.6**，安裝檔由 CI 自動建置發布
- 舊 repo `sakiwatashi/inputmethod` 已封存唯讀，release 與 tag 皆已刪除，
  README 有搬遷公告。**不要再往那裡推東西。**
- 版控乾淨，本機與遠端同步。**注意本機 git 結構**：開發在外層 repo 的工作
  分支（本專案是 `pime-bopomofo-core/` 子目錄），GitHub 的 `main` 對應本機
  `ime-standalone` 分支（獨立歷史）；發布靠子樹重建同步，完整步驟見
  `AI_MAINTENANCE.md` 的「發布流程」。工作分支的 upstream 指向已封存的舊
  repo，不要直接 `git push`。

## 2. 這次做了什麼

### 行程外候選視窗（主線工作）

日式直向候選框原本畫在 `PIMETextService.dll` 裡。TSF 文字服務會被載入**每一個**
接收文字的行程，遊戲也不例外，VALORANT 的 Vanguard 因此把未簽章的 DLL 強制卸載，
遊戲以 BEX64 崩潰（2026-07-23 三筆系統事件為證）。

改為由 `native_ui/helper/` 這個獨立行程繪製。定位方式是沿用原廠簽章 DLL 已經算好
的候選視窗位置：Python 把送給 DLL 的清單改寫成單一空白項，使其縮成定位信標，再由
輔助程式覆蓋。完整設計、實測數據與被推翻的方案記錄在
`OUT_OF_PROCESS_UI_DESIGN.md`。

**預設開啟**（0.6.5 發布後應真實使用者回饋改為預設；只有明確的
`{"enabled": false}` 會關閉，檔案不存在或損壞一律視為開啟）。要關閉：
`%APPDATA%\PinnedBopomofo\candidate-ui.json` 設 `{"enabled": false}` 並重啟 PIME。

### 標點鍵位對齊微軟注音

中文標點由 Shift 移到 Ctrl，Shift 一律輸出標準 ASCII。原設計讓同一個實體按鍵在
中英模式下語意不同。對照表與刻意偏離微軟之處（`「」` 放在 `Ctrl+[ ]`）記於
`KEY_BINDING_ALIGNMENT.md`。

### 其他修正

- 個人詞彙不再拆解權重更高的相鄰詞（「電話一來」曾變成「店化一來」）
- `Shift+字母` 遵循大寫鎖定狀態
- 安裝程式：補上缺漏的腳本、授權頁亂碼、已安裝偵測、解除安裝捷徑
- 舊的行程內 DLL 移出版控，僅保留本機

## 3. 尚未解決 —— 最重要的一項

### 解除安裝後重新安裝，輸入法不會出現在切換清單

**這是本次留下最嚴重的問題，會重現，而且原因未查明。**

實際發生經過：使用者用 EXE 安裝 → 解除安裝 → 重新安裝（含靜默安裝與重開機），
輸入法就是不出現在 Win+Space 清單，也無法使用。最後由使用者自行再安裝一次才恢復。

已確認**全部正確**、因此不是原因的項目：

| 檢查 | 結果 |
|---|---|
| 模組檔案與 `ime.json` | 齊全，版本正確 |
| PIME 的 Python 載入模組 | 成功建立輸入法實例 |
| COM 註冊 `HKLM\...\CLSID\{35F67E9D...}\InprocServer32` | 指向存在且簽章有效的 DLL（32/64 兩個檢視） |
| TSF 類別註冊（含鍵盤類別 `{34745C63...}`） | 32/64 兩個檢視都齊全，與微軟注音結構一致 |
| `Get-WinUserLanguageList` | 我們的 TIP 在 zh-Hant-TW 第一順位 |
| `Get-WinDefaultInputMethodOverride` | 指向我們的 TIP |
| `HKCU\...\CTF\Assemblies\0x00000404\{34745C63...}` | `Default` 與 `Profile` 都是我們的 |
| `HKCU\...\CTF\SortOrder\AssemblyItem` | 我們排 `00000000` |
| PIMELauncher | 開機自動啟動且執行中 |

決定性的反證：在 Notepad 打 `su3` 再按 `↓`，**PIME 的 `LibImeWindow` 不出現，
PIME 的 python 伺服器也從未啟動** —— 表示沒有任何應用程式載入我們的文字服務。

已試過但無效：重新套用語言清單、移除再加回 TIP、設為預設、重開機。
無法終止 `ctfmon.exe`（系統保護）。

尚未試過的方向：
1. `regsvr32 /u` 反註冊後再重新註冊 PIME 的文字服務，強迫 Windows 重建整個
   TSF 登錄，而非覆蓋
2. 移除並重裝 PIME 本身
3. 比對「乾淨安裝」與「解除安裝後重裝」兩種狀態下的完整 CTF 登錄差異，找出
   uninstall 移除了什麼而 install 沒有重建

**給接手者的提醒**：診斷這個問題時，唯一可信的判準是「打字後 `LibImeWindow`
會不會出現、PIME 的 python 伺服器會不會啟動」。登錄檔全部正確**不代表**輸入法能用
—— 這次就是因為只看登錄檔而兩度誤判。

## 4. 其他已知但未處理

- **一聲音節不按空白鍵時連續輸入會出錯**：`ㄉㄨㄥ` 接 `ㄒㄧ` 變成 `ㄒㄧㄥ`，因為
  新的聲母取代了舊的。大千鍵盤本來就規定空白鍵是一聲，按規矩打沒問題；使用者
  已表示不處理。要修的話會動到「同類按鍵取代舊值」這條既有設計。
- **滑鼠點選候選字**：使用者實測可用，但無法自動化驗證 —— 以合成按鍵驅動真實
  注音輸入法不穩定，造不出候選頁。
- **`【】` 與 `｛｝` 沒有輸入法內的入口**：把 `Ctrl+[ ]` 讓給更常用的 `「」` 的代價。
- **一聲符號 `ˉ` 沒有任何按鍵**：使用者選擇移除。

## 5. 踩過的坑（會再咬人）

### 編碼：Windows 工具鏈預設不假設 UTF-8

同一類問題在這次踩了**四次**：

| 情境 | 症狀 | 解法 |
|---|---|---|
| NSIS 授權頁 | 整頁亂碼 | 授權檔要有 UTF-8 BOM |
| Windows PowerShell 5.1 腳本 | 中文字串解析錯誤、腳本無法執行 | 檔案要有 UTF-8 BOM |
| MSVC 編譯 C++ | 中文字面值變亂碼、編譯失敗 | 加 `/utf-8` 編譯選項 |
| Python 讀 PowerShell 寫的 JSON | `json.load` 失敗被靜默吞掉，開關永遠是關 | 用 `utf-8-sig` |

`tests/release_consistency_smoke.ps1` 現在會擋住第一項。其餘三項只能靠記得。

### 只在成品安裝程式才會顯現的缺陷

單元測試全綠、從原始碼安裝也正常，但下載 EXE 的使用者第一步就失敗。這次出過兩次：

1. `install.ps1` 與 `uninstall.ps1` 以 dot-source 載入的腳本沒被打包進 NSIS，
   腳本在 `Start-Transcript` 之前就中止，記錄檔完全空白，只有一個「結束碼 1」
2. 版本號散落六處，`.txt` 那一處連續三版沒更新

`tests/installer_payload_smoke.ps1` 與 `tests/release_consistency_smoke.ps1`
現在各自守住一項，兩者都已接入 CI。**不要因為它們看起來與程式邏輯無關而略過。**

### 輔助程式會鎖住自己的檔案

`SmartPriorityCandidateUI.exe` 安裝在模組目錄內。它執行中時會鎖住
`build_pime_overlay.ps1` 要清除的 `dist`、以及安裝程式要替換的模組目錄，造成
**安裝回報成功但檔案實際沒更新**。overlay 建置、安裝、解除安裝現在都會先停止它。

### EXE 與原始碼安裝到同一個位置

輸入法必須位於 PIME 底下才能被 Windows 載入，路徑由 PIME 的登錄項決定。所以電腦上
只會有一份輸入法。**解除安裝 EXE 會移除那唯一一份，包含從原始碼安裝的版本。**
個人學習資料（`%APPDATA%\PinnedBopomofo`）不受影響，已實測確認。

### 個人詞彙曾經絕對凌駕權重

詞網格的評分是元組，逐項比較。「個人詞彙字數」原本排第一，於是權重 0 的個人詞
直接擊敗權重 50001 的內建詞，且 15 倍的差距完全不被納入考量。現在個人詞的權重取
「同段最強內建候選 + 1」，字數移到最後一個決勝條件。**不要把它移回第一順位。**

## 6. 驗證清單

改完任何東西後跑這些（`AI_MAINTENANCE.md` 有完整版）：

```powershell
python -m unittest discover -s tests -v
.\tests\release_consistency_smoke.ps1
.\tests\installer_payload_smoke.ps1
.\tests\installer_resilience_smoke.ps1
.\tests\candidate_ui_policy_smoke.ps1
.\tests\restore_signed_text_service_smoke.ps1
.\tests\native_ui_preference_smoke.ps1
.\build_pime_overlay.ps1
& 'C:\Program Files (x86)\PIME\python\python3\python.exe' .\tests\pime_adapter_smoke.py
& 'C:\Program Files (x86)\PIME\python\python3\python.exe' .\tests\pime_all_readings_audit.py
```

發版另外要更新六處版本號（`release_consistency_smoke.ps1` 會核對），並確認
`native_ui/diagnostics/` 底下的工具仍可用。

## 7. 診斷工具

`native_ui/diagnostics/` 收錄了這次寫的工具，都可重複使用：

- `watch_candidate_window.ps1` —— 監看 PIME 候選視窗的出現、位置與尺寸
- `probe_caret.ps1` —— 比較 `GetGUIThreadInfo` 與 UI Automation 的游標定位可行性
- `fake_beacon.ps1` —— 建立假的 `LibImeWindow` 測試信標跟隨與 z-order
- `toggle_candidate_ui.ps1` —— 開關行程外候選視窗並重啟 PIME

## 8. 後續更新（2026-08-01，v0.6.6）

第一位外部使用者安裝 0.6.5 失敗，牽出兩個安裝程式缺陷，連同候選視窗預設值
一併修正發佈：

- **殘留 PIME 登錄鍵誤判**：使用者機器留有指向已刪除目錄的 `HKLM\Software\PIME`
  鍵，install.ps1 只讀值不驗路徑，誤判「已安裝」而跳過隨附 PIME，隨後以
  "A valid PIME installation directory was not found" 失敗。現在偵測一律經
  `Find-PimeInstallRoot` 驗證目錄存在，殘留鍵視同未安裝。
- **install.log 吞掉錯誤**：`try/finally` 沒有 `catch`，未攔截的 throw 要等
  transcript 關閉後才印出，log 只有頭尾、內容空白（診斷全靠 NSIS 視窗截圖）。
  install/uninstall 現在都會先把錯誤寫進 transcript 再重拋。
- **行程外候選視窗改為預設開啟**：同一位使用者把藏在 JSON 的 opt-in 理解成
  「功能沒實裝」。規則改為只有明確 `{"enabled": false}` 才關閉；
  `toggle_candidate_ui.ps1 -Off` 因此改寫入明確 false（刪檔＝回到預設＝開啟）。
- 新增 `tests/installer_resilience_smoke.ps1` 守住前兩項，已接入 CI。
- 診斷時間軸與判讀方法（同秒開始結束的空 log ＝ 沒跑隨附安裝就拋錯）值得
  記住：比登錄檔快照更能區分「走了哪條路」。
