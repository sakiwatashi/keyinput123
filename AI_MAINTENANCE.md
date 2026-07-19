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
- `tools/build_frequency_lexicon.py`：從固定版本 Rime Essay 重建臺灣正體高頻詞索引。生成的 JSON 不應手工修改。
- `tests/`：核心與 PIME 整合測試。
- `installer/`：正式安裝與解除安裝流程。

## 修改後必須驗證

```powershell
python -m unittest discover -s tests -v
.\build_pime_overlay.ps1
& 'C:\Program Files (x86)\PIME\python\python3\python.exe' .\tests\pime_adapter_smoke.py
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
- 使用者明確選擇永遠最高；內建候選先比較詞彙涵蓋的音節數，較短後綴不可
  覆蓋較長完整轉換，涵蓋相同時再依台灣官方字詞頻、其他內建詞庫排序。
  一般送出文字不可自動強化個人權重。
- `bopomofo_core/feedback_store.py` 與 `feedback-report.ps1` 只保存明確改選
  差異並讓使用者審查。輸入法執行期間不得自動上傳，也不得蒐集前後句或
  應用程式身分。
