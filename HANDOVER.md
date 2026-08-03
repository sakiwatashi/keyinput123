# 交接文件（2026-07-31）

寫給下一個接手這個專案的人或 AI。長期規範在 `AGENTS.md` 與 `AI_MAINTENANCE.md`；
本文只記錄**這次工作階段的成果、尚未解決的問題,以及踩過的坑**。

## 1. 專案現況

- 正式位置：https://github.com/sakiwatashi/keyinput123
- 最新版本：**v0.6.8**，安裝檔由 CI 自動建置發布
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
- `trace_key_events.ps1` —— 記錄哪些 PIME 回呼真的被呼叫。**遇到「某個環境按鍵沒反應」時先跑這個再改程式**（見第 11 節）

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

## 9. 後續更新（2026-08-01，v0.6.7）

實際使用回饋的兩個修正：

- **候選視窗方向鍵對齊直向優先網格**：`←→` 在同列兩欄之間跳（1→6），
  只有在外側欄才翻頁且保留列位；`PageUp/PageDown` 接上為專用翻頁鍵。
- **手動修正過的組句在送出時學進個人詞庫**：先前送出完全不學習、pins 又
  進不了詞網格，逐字修好的「魔物獵人」重打仍是「麼惡獵人」。現在只要
  組句含使用者親手選過的字，送出即整句學習（引擎自己的預設輸出刻意
  不學，避免錯誤轉換自我強化）。`BufferedSyllable.user_corrected` 是
  「使用者動過」的判準，與 `locked`（排名鎖定）刻意分開。

## 10. 後續更新（2026-08-01，v0.6.8）

- **解除安裝「檔案使用中」失敗**（真實回報，0.6.6 機器）：停止候選窗輔助
  程式後沒等它真正退出就刪模組目錄。候選窗預設開啟後這個競態變成常態。
  修正：`Stop-SmartPriorityCandidateUiAndWait`（停止後 WaitForExit）＋
  `Remove-DirectoryWithRetry`（0.5 秒×10 次），安裝升級路徑與解除安裝
  皆套用，`installer_resilience_smoke` 守門。
- 升級一律**不需要**先解除安裝：直接執行新版 exe 選「是」。已存在的舊版
  解除安裝腳本仍是壞的，升級後才會被換成修好的版本。

## 11. 已解決（2026-08-03）：主控台與遠端桌面裡短按 Shift 無法切換中英

使用者回報兩次：本機命令列視窗，以及用 AnyDesk 遠端連到 Linux 的 CLI 視窗，
短按 Shift 都切不了中英，但**微軟注音在同樣的地方可以**。

### 原因（實測，不是推論）

我為此連續猜錯兩輪，兩次都建立在「TSF 在那些環境裡會送出什麼」的假設上：

1. 賭「放開事件沒送達」→ 錯
2. 賭「要改用 TSF 保留鍵」→ 錯（保留鍵在那裡也沒被送出）

第三次改成量測。`bopomofo_core/request_trace.py` 記下每次短按 Shift 的實際樣態：

```
filterKeyDown   Shift   passed
filterKeyUp     Shift   handled     <- 我們的判斷正確，回報要處理
filterKeyUp     Shift   passed
```

**`onKeyUp` 一次都沒出現。** 放開事件其實有送達、判斷邏輯也是對的；問題在於
我們回傳 True 去**要求** PIME 給一個 `onKeyUp`，而這個環境不會呼叫它 ——
而真正執行切換的程式碼就寫在 `onKeyUp` 裡。

（當初那樣寫是有理由的：`filterKeyUp` 沒有 TSF 編輯工作階段，在那裡送出組字
會跟下一個按鍵競爭。理由沒錯，錯在沒有備援。）

### 修法

在**下一個按鍵**補做。`filterKeyDown` 一發現切換仍待處理就立刻補上：沒有組字
時直接翻轉旗標（不需要編輯工作階段）；有組字時先接手該按鍵，交由 `onKeyDown`
完成送出。代價是模式不在放開當下改變，但那個按鍵本身就會用新模式。

### 大寫鍵為什麼一直都能用

它不經過我們的程式。中文輸入法的大寫鍵切換由 Windows 自己翻轉 TSF 的開關
狀態，再以 `onKeyboardStatusChanged` 通知我們，全程沒有按鍵事件送到文字服務。
**這是遇到「某某環境切不了」時最可靠的對照組。**

### 留下來的東西

- `addPreservedKey(VK_SHIFT, TF_MOD_ON_KEYUP, ...)` 保留著。它在 AnyDesk 沒
  作用，但那是微軟自家模式切換鍵走的通道，別的環境可能有用。`filterKeyUp`
  會在保留鍵首次送達後自動退場，避免同一次放開被切換兩次。
- `native_ui/diagnostics/trace_key_events.ps1` —— 下次再遇到「某環境按鍵沒
  反應」，**先跑這個再改程式**。三輪裡只有量測那一輪是對的。
- 追蹤只記錄回呼名稱與是否為修飾鍵，不記錄輸入內容（虛擬鍵碼等同字元，所以
  非修飾鍵一律寫成 other）。`tests/test_request_trace.py` 守住這條界線。

## 12. 新增（2026-08-03）：控制台 `control_panel/`

設定原本散落在手改 JSON、PowerShell 腳本與寫死的 Python 表格裡，使用者看不到
也改不動。新增一個模組化的小 GUI，隨模組一起安裝，開始選單有捷徑。

- 外殼 `SmartPriorityControlPanel.ps1` 只負責找出 `modules\*.ps1`、依 `Order`
  排序、把每個模組回傳的控制項放進分頁。**模組合約**：檔案執行後輸出
  `@{ Name; Order; Build = { param($Context) <控制項> } }`。載入或建構失敗
  只會讓那一個分頁變成錯誤訊息，其餘照常運作。
- 目前三個模組：`10-status`（行程／版本／路徑＋候選視窗開關）、
  `20-lexicon`（phrases.json 與 pins.json 的檢視、搜尋、修改、刪除）、
  `30-keymap`（把鍵盤畫出來，唯讀）。
- PowerShell + WinForms 而不是 tkinter：**PIME 內建的 Python 沒有 tkinter**，
  終端使用者機器上也不保證有 Python。與 `feedback-report.ps1` 同一套做法。
- 個人詞庫存檔後**一定要重啟 PIME**：執行中的輸入法把整份詞庫放在記憶體，
  任何一次學習都會用記憶體內容覆蓋整個檔案。儲存鍵已經一併重啟。

### 這次踩到的新坑：`GetNewClosure()` 只捕捉「當下這一層」

同一個根因在三個地方各咬了一次，而且**全都不會報錯**，只是安靜地失效：

| 位置 | 症狀 |
|---|---|
| `20-lexicon` 的 `$load` | 上層定義的讀檔工具在閉包裡是 `$null` |
| 外殼載入失敗時的 fallback | 閉包裡呼叫不到 script 作用域的函式 |
| `30-keymap` 的 Paint | 表格是 `$null`，迴圈空轉，**鍵盤整片畫不出來** |

規則：**閉包要用到的東西，先在建立閉包的那一層存成本地變數**；
函式（`function`）不會被捕捉，要用就存成 scriptblock 變數。

### 測試

`tests/control_panel_smoke.ps1`（已接入 CI）守四件事，每一項都實測過
「把修正拿掉會失敗」：

1. 所有 `.ps1` 有 UTF-8 BOM
2. 模組合約完整、壞模組不會拖垮其他分頁
3. **按鍵表與 Python 原始碼一致** —— 表格是手抄副本，用 `ast` 解析
   `pinned_bopomofo_ime.py`（不 import，因為它需要 PIME 執行環境）比對
4. **真的把鍵盤渲染出來再數像素** —— 只檢查「建構成功」抓不到 Paint 空轉
   那個 bug。判準是找鍵面色，**不是數「非白像素」**：沒畫到的區域是黑的，
   一樣算非白，第一版就是這樣誤判成通過。

## 13. 新增（2026-08-03）：單一注音直接送出

回報：微軟注音打 `ㄏ`＋空白可以連續快速輸出好幾個 `ㄏ`，我們做不到。

實測 `ㄏ空ㄏ空ㄏ空` 六個按鍵只送出**一個** `ㄏ`。空白鍵補上一聲後，讀音若沒有
任何漢字，候選就只剩注音本身，而程式為它開了一個「只有一個選項」的候選窗：
不但多花一次按鍵，還會**吃掉輸入** —— 選窗開著時再打 `ㄏ` 只是用同類聲母取代
自己，組字區毫無變化。

改為候選只剩注音一項時直接送出。判斷放在**空白鍵那條路徑**，不放在共用的
`_handle_session_event`：使用者用聲調鍵明確打出的 `ㄢ˙` 同樣只有注音一個候選，
但那時的選單是微軟讓人刻意選擇注音拼法的方式。第一版改在共用處，既有測試
立刻抓到。

分界（37 個注音實測）是乾淨的二分，**沒有任何單一注音會開選單**：注音排第一
就直接送出（18 個），漢字排第一就轉漢字進組字區（19 個），四個聲調符號單獨
按不成立。

第一版還為 `ㄑ→['ㄑ','胠']`、`ㄟ→['ㄟ','欸']`、`ㄦ→['ㄦ','児']` 這類「注音排第一
但後面掛著冷僻字」的保留了選單，使用者要求全部比照 `ㄏ`。這與原註解的用意
其實一致：那段程式碼是為了**不讓冷僻字意外勝出**，直接送出注音比把冷僻字端到
使用者面前更符合這個目的。代價是那幾個冷僻字失去經由此鍵的入口。

`pime_adapter_smoke` 有兩處把舊行為當正解鎖住（「`ㄉ`＋空白要開選單」），已
連同原因一併更新 —— 遇到測試擋路時先判斷它鎖的是意圖還是實作。

## 14. 這幾輪反覆出現的教訓

同一個錯誤在這個工作階段出現了四次，都是**拿代理指標當結果**：

| 當時的代理指標 | 實際情況 |
|---|---|
| 登錄檔與檔案齊全 → 宣稱輸入法可用 | 沒有任何應用程式載入文字服務 |
| `dist/` 建置版測過 → 宣稱使用者端已修好 | 使用者跑的是舊的**已安裝**版本 |
| 讀程式碼推斷走 BELL 分支 | 實際是 UPDATED，改到死程式碼 |
| 數「非白像素」判定畫面有內容 | 沒畫到的區域是黑的，一樣算非白 |

可信的判準都是**在真正的執行環境裡量到的東西**：`LibImeWindow` 有沒有出現、
`onKeyUp` 有沒有被呼叫、已安裝的那份檔案裡有沒有那行程式碼。
**改任何東西之前，先確認你量的是不是使用者實際在跑的那一份。**
