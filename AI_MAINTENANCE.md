# 使用 AI 維護智慧優先注音

安裝程式本身不是 AI，也不會從網路自動改寫程式；它只會從使用者實際選字中維護
個人優先字與詞語。若要使用自己的 AI 修改功能，必須提供這份原始碼專案，而不只是
安裝用的 EXE。

## 建議給 AI 的工作方式

可以先要求 AI：

> 請先閱讀 README.md 與 AI_MAINTENANCE.md，檢查目前測試，再修改指定功能。
> 不要直接改 Program Files 裡已安裝的檔案；修改專案來源、補測試，全部通過後再
> 執行 build_release.ps1 產生新版安裝程式。

主要檔案位置：

- `pime_module/pinned_bopomofo_ime.py`：按鍵、游標、候選視窗及 PIME 行為。
- `bopomofo_core/libchewing_provider.py`：libchewing 候選、詞語上下文與保守的常用詞規則。
- `bopomofo_core/pinned_store.py`：單一讀音的個人優先字。
- `bopomofo_core/phrase_store.py`：使用者確認過的 2–12 字詞語。
- `bopomofo_core/frequency_lexicon.py`：離線高頻詞索引查詢；資料位於 `bopomofo_core/data/`。
- `bopomofo_core/reading_phrase_lexicon.py`：查詢帶完整注音與權重的單字／詞語索引。
- `bopomofo_core/phrase_decoder.py`：以動態規劃把整句切成多個精確注音詞，不要求字典含有整句。
- `bopomofo_core/autocorrect.py`：產生可見完整句候選的離線高可信錯字修正；規則位於 `bopomofo_core/data/common_typos.json`。
- `bopomofo_core/phonetic_corrector.py`：以每個字保留的注音、候選欄與常用詞庫重新解碼；同一讀音或保守的注音槽位混淆不應展開成大量表面錯字規則。
- `tools/build_frequency_lexicon.py`：從固定版本 Rime Essay 重建臺灣正體高頻詞索引。生成的 JSON 不應手工修改。
- `tools/build_reading_phrase_lexicon.py`：合併固定版本 McBopomofo、libchewing-data 與 Rime Essay 權重，重建 `reading_phrases.json.gz`；生成檔不應手工修改。
- `tests/`：核心與 PIME 整合測試。
- `installer/`：正式安裝與解除安裝流程。
- `native_ui/`：候選框的完整 LGPL 原始碼、可重現建置腳本及 x86/x64 產物。

候選視窗的字型、每列數量、選擇標籤與方向鍵行為由 Python 模組控制；圓角、顏色、
邊框、選取樣式，以及**兩個直欄（左 1–5、右 6–0、先直後橫）**都位於
`native_ui/src/CandidateWindow.cpp`。原廠簽章 `PIMETextService.dll` 會把
`candPerRow=2` 畫成橫向成對（`1 2 / 3 4 / …`），看起來像「候選單不是縱向」——
那不是 Python 壞了，是原生 UI 被還原。原生元件固定從隨附的 PIME `v1.3.0-stable`
重建，但它沒有正式程式碼簽章，可能與遊戲反作弊衝突。
全新安裝與尚未選擇介面的使用者保留 PIME 原廠簽章 DLL；只有使用者明確傳入
`-EnableUnsignedNativeUi` 且沒有其他 PIME 模組時才首次套用自訂 DLL。這項選擇必須
跨一般更新、EXE 與 AI 維護持久保存，除非明確傳入 `-DisableUnsignedNativeUi`，不得在
更新 Python 層時恢復舊簽章介面。**修 IME／緊急腳本／「讓中文能打」都不得**
以簽章 `Valid` 為目標去蓋回原廠 DLL，也不得把
`%ProgramData%\SmartPriorityBopomofo\native-ui-preference.json` 設成
`enabled: false`，也不得清掉 `native-state\pending` 的待套用 DLL。安裝器須備份與
還原原始 DLL；被 TSF 鎖定時以 `MoveFileEx` 排程至重開機，不能把這些限制拿掉。

候選窗每頁固定 10 個、分成兩個直欄：左欄由上而下 `1–5`，右欄由上而下 `6–0`；`→` 直接翻到下一頁，`↓` 依數字順序逐項移動並在
本頁末端翻頁。完整讀音的原始注音須留在前四個候選。單獨注音按空白時一律先向
字典查詢補上一聲後的候選，不可單靠 initial／medial／rime 分類判定，因為 `ㄙ`、
`ㄓ` 等聲母本身也是完整音節。字典候選零是中文字時直接採用；候選零仍是原注音
時必須開啟原符號第一的選單，不可讓尾端生僻字自動勝出。原注音仍須保留在前四項。
沒有作用中的音節時，大千聲調鍵直接輸出符號（3=ˇ、6=ˊ、4=ˋ、7=˙）；已有未提交
文字時，聲調與候選中的原始注音須以受保護片段插入同一組字區，不得提交其他片段。
右側數字鍵盤的數字、小數點與 `/ * - +` 必須直接輸出原字元，不可進入注音映射。

精確注音、保守模糊讀音與補充錯字規則都必須先產生可見的完整句候選，並即時更新
未鎖定的組字內容；Enter 不得在送出瞬間暗中改字。原始精確讀音句要保留為後續候選。
規則必須等長、精確、高可信且附來源。當次親自選字與個人詞彙所涵蓋的字元須設為保護範圍；
已儲存的單字優先只控制單一讀音排序，不得鎖死整句脈絡。`的／得／地`、`在／再`、合法異形詞等需要語境的
項目不可加入無條件規則。執行期間不得傳送文字到網路，也不得把自動修正當成個人學習。

完整句預設與候選視窗必須共用 `_ranked_phrase_options()`；開啟候選及任何送出動作前
都要先執行 `_apply_phrase_ranking()`。禁止新增只在候選視窗可見、但不會同步到組字區
的另一套第一候選邏輯，也禁止在 Enter 路徑另外做不可見修正。方向鍵是改選功能，
不是取得系統已知正解的必要步驟。

Rime Essay 與台灣字頻本身只有文字／權重，沒有完整詞語讀音；權重只能套用到
`reading_phrases.json.gz` 已由 McBopomofo 或 libchewing-data 證明完整讀音的拼法。
整句預設必須由 `phrase_decoder.py` 的全域詞網格決定，不能再用逐字貪婪修正覆蓋結果。
任何高頻詞或模糊音修正也必須再經精確讀音索引驗證。游標在句中時，候選零必須是游標右側的單字候選，選擇後只鎖定涵蓋的
音節並前進；詞語與完整句候選保留在同一頁。游標在句尾時才可把完整句／詞語排在前面。

## 修改後必須驗證

```powershell
python -m unittest discover -s tests -v
.\build_pime_overlay.ps1
& 'C:\Program Files (x86)\PIME\python\python3\python.exe' .\tests\pime_adapter_smoke.py
& 'C:\Program Files (x86)\PIME\python\python3\python.exe' .\tests\pime_all_readings_audit.py
.\native_ui\build_native_ui.ps1
.\build_release.ps1
```

修改正式版本時，也要同步更新 `pime_module/ime.json`、NSIS 安裝檔中的版本號及
README。不要沿用舊安裝包的 SHA-256；每次建置都會產生新的雜湊。

## 個人資料與隱私

`%APPDATA%\PinnedBopomofo` 可能包含使用者實際輸入或選過的字詞。除非使用者明確
同意，請勿把 `pins.json`、`phrases.json`、`feedback.json` 上傳給外部 AI、
公開儲存庫或其他人。
一般功能開發不需要這兩個檔案，測試應使用暫存資料。

## Clone 後直接安裝

AI 不需要猜測專案的絕對路徑。Windows PowerShell 使用：

```powershell
.\install.ps1
```

Git Bash 使用：

```bash
./install.sh
```

腳本會以自己的所在目錄為根目錄建立 overlay、要求 UAC、驗證包內 PIME 簽章並
完成註冊。不要把路徑寫死成開發者的使用者名稱或 Documents 資料夾。

## 台灣排序與錯誤回報

- `tools/build_taiwan_frequency.py` 從教育部字頻／詞頻 CSV 重建台灣預設排序；
  `bopomofo_core/data/taiwan_frequency.json` 是產物，不可手改。
- 單字候選必須保留 libchewing 讀音字典的第一項，再用全域台灣字頻整理其餘候選；
  全域字頻不含讀音資訊，不得讓多音字（例如 `員`）覆蓋 `ㄩㄣˋ→運` 等讀音首選。
- 當次使用者明確選擇永遠最高；儲存的單字優先在孤立讀音中列為候選零，但可靠的
  整詞／整句脈絡可覆蓋它。內建候選先比較詞彙涵蓋的音節數，較短後綴不可
  覆蓋較長完整轉換，涵蓋相同時再依台灣官方字詞頻、其他內建詞庫排序。
  一般送出文字不可自動強化個人權重。
- `bopomofo_core/feedback_store.py` 與 `feedback-report.ps1` 只保存明確改選
  差異並讓使用者審查。輸入法執行期間不得自動上傳，也不得蒐集前後句或
  應用程式身分。
