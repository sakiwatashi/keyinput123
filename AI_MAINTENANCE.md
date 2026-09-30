# 使用 AI 維護智慧優先注音

安裝程式本身不是 AI，也不會從網路自動改寫程式；它只會從使用者實際選字中維護
個人優先字與詞語。若要使用自己的 AI 修改功能，必須提供這份原始碼專案，而不只是
安裝用的 EXE。

> 本文是唯一的維護規範。過去的交接紀錄與設計提案已併入此處，其餘保留在 git
> 歷史；每一版改了什麼看 `git log` 與 GitHub Releases。

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
- `bopomofo_core/candidate_ui_client.py`：把候選清單鏡像給行程外候選視窗。射後
  不理，絕不可阻塞 —— 出貨版 DLL 呼叫 `TransactNamedPipe` 沒有客戶端逾時，且
  PIME 的 `server.py` 是單執行緒服務所有應用程式，一次阻塞會凍結全系統打字。
- `tests/`：核心與 PIME 整合測試。
- `installer/`：正式安裝與解除安裝流程。
- `native_ui/`：候選框的 LGPL 授權與說明。**舊的行程內 DLL(`src/`、`bin/`、
  `build_native_ui.ps1`)已不再納入版控**,發布的安裝程式一律不含它;開發者若要
  使用 `-EnableUnsignedNativeUi` 可自行在本機重建,`build_pime_overlay.ps1` 有就
  收、沒有就略過。二進位與原始碼必須同進退(LGPL),建置會拒絕只有其中一邊的組合。
- `native_ui/helper/`：**行程外**候選視窗（C++／Win32／GDI，不含 TSF 或 COM）。
  日式直向候選框改由這個獨立行程繪製，讓所有應用程式（含遊戲）行程內只留 PIME
  原廠簽章 DLL。
- `native_ui/diagnostics/`：定位策略探測、候選視窗監看、假信標與開關工具。

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

一行跑完全部（含 CI 以外的按鍵行為測試與全讀音稽核）：`tools/run_all_tests.ps1`。
下面是個別指令：

```powershell
python -m unittest discover -s tests -v
.\tests\release_consistency_smoke.ps1
.\tests\control_panel_smoke.ps1
.\tests\installer_payload_smoke.ps1
.\tests\installer_resilience_smoke.ps1
.\tests\candidate_ui_policy_smoke.ps1
.\tests\restore_signed_text_service_smoke.ps1
.\tests\native_ui_preference_smoke.ps1
.\build_pime_overlay.ps1
& 'C:\Program Files (x86)\PIME\python\python3\python.exe' .\tests\pime_adapter_smoke.py
& 'C:\Program Files (x86)\PIME\python\python3\python.exe' .\tests\pime_all_readings_audit.py
.\native_ui\helper\build_helper.ps1
.\native_ui\build_native_ui.ps1
.\build_release.ps1
```

那五個 PowerShell 測試守的是**只在成品安裝程式才會顯現**的缺陷：單元測試全綠、
從原始碼安裝也正常，但下載 EXE 的使用者第一步就失敗。它們都是實際出包之後補上
的，不要因為「看起來與程式邏輯無關」而略過。

### 版本號位置

修改正式版本時，下列**六處**必須同時更新，`release_consistency_smoke.ps1` 會
逐一核對：

- `pime_module/ime.json`
- `installer/SmartPriorityBopomofo.nsi`（`PRODUCT_VERSION` 與 `VIProductVersion`）
- `build_release.ps1`（產物檔名）
- `.github/workflows/windows.yml`（發布清單的檔名）
- `README.md`（安裝說明）
- `THIRD_PARTY_NOTICES.txt`（授權頁標題）

最後一項曾被連續三個版本遺漏，因為當時的搜尋只涵蓋 `.ps1/.nsi/.json/.md/.yml`
而沒有 `.txt`，使用者在授權頁看到的版本與實際安裝的不符。

不要沿用舊安裝包的 SHA-256；每次建置都會產生新的雜湊。

### 發布流程（git 結構與步驟）

本機的 git 結構不寫下來就是地雷，因為它和直覺相反：

- 開發在**外層 repo**（`New project 2`）的工作分支進行，本專案位於
  `pime-bopomofo-core/` 子目錄。工作分支的 upstream 指向已封存的舊 repo
  `inputmethod`，該遠端分支已不存在（`[gone]`）——**絕對不要在工作分支直接
  `git push`**。
- GitHub 正式 repo `keyinput123` 的 `main` 對應本機的 **`ime-standalone`
  分支**：一條以子目錄內容為根的**獨立歷史**，與工作分支沒有共同祖先，
  commit 訊息相同但 hash 不同。內容靠子樹重建保持一致。

發布新版（v0.6.6 實測）：

1. 在工作分支完成修改、跑完驗證清單、更新六處版本號、提交
   `release: 發布智慧優先注音 X.Y.Z`。
2. 把每個尚未同步的 commit 重建到 `ime-standalone`（Git Bash，訊息沿用）：

   ```bash
   PREV=$(git rev-parse ime-standalone)
   for C in <依序列出未同步的 commit>; do
     TREE=$(git rev-parse "$C:pime-bopomofo-core")
     NEW=$(git log --format=%B -n 1 "$C" | git commit-tree "$TREE" -p "$PREV")
     PREV=$NEW
   done
   git update-ref refs/heads/ime-standalone "$PREV"
   ```

   **列 commit 的範圍要以工作分支上的提交當起點，不是 `ime-standalone` 上的。**
   兩條歷史沒有共同祖先，所以 `git log <standalone 的 commit>..HEAD` 不會報錯，
   而是退化成「HEAD 能到、那個 commit 到不了的全部」——實測寫成
   `755d21c..HEAD` 列出 104 個提交而不是 3 個，照著跑會把整部歷史重新接一次。
   正確的起點是**上一版的 release commit 在工作分支上的那一個**（訊息相同、
   hash 不同），例如發 0.8.1 時用 `e1865dc..HEAD`。

   步驟 3 的 `git diff` 為空**不代表做對了**：重建 104 個提交之後內容一樣是
   對的，錯的是歷史。推之前再看一次
   `git log --oneline keyinput/main..ime-standalone | wc -l`，數字要跟你打算
   同步的提交數一致。

3. 驗證同步：`git diff ime-standalone "HEAD:pime-bopomofo-core"` 必須為空。
4. 在 `ime-standalone` 上打附註 tag：
   `git tag -a vX.Y.Z ime-standalone -m "release: 智慧優先注音 X.Y.Z ..."`
5. 推送：`git push keyinput ime-standalone:main`、`git push keyinput vX.Y.Z`。
6. CI（`windows.yml`）在 tag 上跑完全部測試後自動建置安裝檔並發佈 Release，
   幾分鐘後到 GitHub Releases 確認 exe 與 `SHA256SUMS.txt` 都在。

文件類的後續修訂可以照步驟 2–3、5 再同步一次、直接推 `main`，不打新 tag。

### UTF-8 BOM：兩條方向相反的規則

**這是本專案最容易造成災難的一件事。** 有些檔案沒有 BOM 就壞，有些檔案有了
BOM 就壞，而兩者都不會給出有用的錯誤訊息。批次改檔的腳本尤其危險：一個
「全部補上 BOM」的迴圈會同時修好一半、毀掉另一半。

**必須有 BOM：**

| 檔案 | 沒有 BOM 的後果 |
|---|---|
| 含中文的 `.ps1` | Windows PowerShell 5.1 解析錯誤，腳本無法執行 |
| NSIS 授權檔（`THIRD_PARTY_NOTICES.txt` 等） | `Unicode True` 下以系統 ANSI 讀取，整頁亂碼 |

**絕對不能有 BOM：**

| 檔案 | 有 BOM 的後果 |
|---|---|
| **所有 `.json`**，尤其 `pime_module/ime.json` | PIMELauncher 以 jsoncpp 解析，**jsoncpp 不接受 BOM**：第 1 行第 1 欄丟出 `Json::RuntimeError`，沒有人接住，行程以 `__fastfail` 中止（`0xC0000409`）。**不產生當機傾印、不寫事件記錄。** 使用者只看到「輸入法不見了、只能打英文」，而登錄檔、檔案、版本全部顯示正常 |

2026-08-04 就是這樣把使用者的輸入法弄到數小時完全不能用：升版腳本替每個
目標檔補 BOM，`ime.json` 也被補了。當時往七個方向猜過原因（按鍵事件、TSF
保留鍵、殘留狀態、防作弊、安裝損壞、AppInit 注入、`__pycache__`）全都是錯的；
真正定案是用 Sysinternals `procdump` 抓下例外型別
`E06D7363.?AVRuntimeError@Json@@`，一次就到位。

**教訓：症狀是「行程立刻消失且系統毫無記錄」時，不要靠讀程式碼推論，直接抓
例外。** `procdump -ma -t -x <資料夾> <執行檔>` 會在行程終止時傾印並印出例外
型別。

`tests/json_encoding_smoke.ps1` 現在會擋住 JSON 帶 BOM，
`tests/release_consistency_smoke.ps1` 擋住授權檔缺 BOM，
`tests/control_panel_smoke.ps1` 擋住控制台的 `.ps1` 缺 BOM。三者都已接入 CI。

C++ 原始碼另外需要 `/utf-8` 編譯選項。

## 尚未解決：解除安裝後重新安裝，輸入法不出現

發生過一次，原因未查明：EXE 安裝 → 解除安裝 → 重新安裝（含重開機）之後，輸入法不在
Win+Space 清單裡、也無法使用；最後由使用者再安裝一次才恢復。

當時逐項確認都**正確**、因此不是原因的：模組檔與 `ime.json`、PIME 的 Python 能建立
輸入法實例、COM 與 TSF 類別註冊（32/64 兩個檢視）、語言清單第一順位、預設輸入法
覆寫、CTF Assemblies 與 SortOrder、PIMELauncher 開機啟動。決定性的反證是在記事本打
`su3` 再按 `↓`：PIME 的 `LibImeWindow` 不出現、PIME 的 python 伺服器也從未啟動——
沒有任何應用程式載入這個文字服務。

試過無效：重新套用語言清單、移除再加回 TIP、設為預設、重開機。尚未試過：以
`regsvr32 /u` 反註冊再重新註冊 PIME 文字服務，強迫重建 TSF 登錄；移除並重裝 PIME
本身；比對乾淨安裝與「解除後重裝」兩種狀態的完整 CTF 登錄差異。

**診斷時唯一可信的判準**是打字後 `LibImeWindow` 會不會出現、PIME 的 python 伺服器
會不會啟動。登錄檔全部正確不代表輸入法能用——當時就是只看登錄檔而兩度誤判。
控制台「狀態」分頁因此只顯示行程與檔案這類事實。

## 踩過的坑（會再咬人）

- **量使用者實際在跑的那一份。** 反覆出現的錯誤都是拿代理指標當結果：登錄檔齊全
  不等於輸入法被載入；`dist/` 測過不等於已安裝的版本修好了；讀程式碼推斷的分支
  不等於實際走的分支。改任何東西之前，先確認量的是已安裝的檔案、真的出現的視窗、
  真的被呼叫的回呼。
- **輔助程式會鎖住自己的檔案。** `SmartPriorityCandidateUI.exe` 安裝在模組目錄內，
  執行中會鎖住 `dist` 與安裝時要替換的模組目錄，造成安裝回報成功但檔案沒更新。
  overlay 建置、安裝、解除安裝都會先停止它，不要拿掉。
- **EXE 與原始碼安裝在同一個位置。** 輸入法必須位於 PIME 底下才會被載入，所以電腦上
  只有一份；解除安裝 EXE 會移除那唯一一份，包含從原始碼安裝的版本，個人資料不受
  影響。`install.ps1` 不會更新 Windows「應用程式」清單裡的版本號（只有 NSIS 安裝檔
  會寫），所以清單可能顯示舊版號。
- **Python 讀 PowerShell 寫的 JSON 要用 `utf-8-sig`。** Windows PowerShell 寫檔會帶
  BOM，用純 `utf-8` 讀會失敗並被靜默吞掉，偏好開關就永遠停在預設值。
- **Bash heredoc 會吃掉反斜線。** 用 heredoc 餵腳本寫檔時，Windows 路徑裡的 `\t`、`\f`、
  `\b` 會變成控制字元，檔案看起來完全正常——控制台的備份資料夾路徑就這樣壞過。
  `tests/installer_payload_smoke.ps1` 會掃控制字元。

## WinForms 控制台陷阱（每一條都曾經出貨過缺陷）

**`GetNewClosure()` copies variables, not functions, and only the immediate
scope.** A named `function` declared inside `Build` is gone by the time a button
is clicked -- `Build`'s scope has returned. The status page's Refresh button
silently cleared its own table this way for several releases. Helpers that a
handler needs must be scriptblock *variables*, and the handler must be
`.GetNewClosure()`d. The same applies to a handler created inside a nested `function`
such as `New-LexiconPage`: `Build`'s `$Context` parameter is not a local there,
so the closure sees `$null`. Copy it to a local (`$ctx = $Context`) next to the
other localised helpers -- the lexicon tab's Save button shipped broken this way.

**A closure captures a snapshot, so a scalar cannot be written back.** Assigning
`$floor = 7` inside one handler does not change what another closure sees; each
holds its own copy. Share mutable state through a hashtable or a real object --
`$saved = @{ Floor = 0 }` -- because the reference is what gets copied.

**`Button.PerformClick()` does nothing unless every parent in the chain is
visible.** It checks `CanSelect`, which walks the parent chain and fails on any
container that was never shown -- not only a hidden `Form`. Buttons inside a
`TabControl` page stayed unselectable with no Form parent at all: 26 of 41
buttons, the whole personal-lexicon tab, were never clicked while the smoke test
reported PASS. `control_panel_buttons_smoke.ps1` now raises `Click` by invoking
the protected `OnClick` through reflection, and its probe button sits inside a
`Panel`, because an orphan button happens to be selectable and proves nothing.
`TabControl.Controls` *is* its `TabPages`; walking both counts every button twice.

**A modal `MessageBox` will hang a test forever.** Nobody is there to press OK.
`control_panel_buttons_smoke.ps1` arms a watchdog that closes the dialog and
records its caption; a caption containing failure wording counts as a failure,
which is exactly the defect a user once reported by hand.

**Errors inside a click handler never reach `$Error`.** Measured: a
non-terminating error, an explicit `throw`, and an invalid path all leave
`$Error.Count` unchanged; the handler simply stops at the failing line. Do not
use `$Error` as a test signal. The button test checks observable results
instead: a folder button must launch `explorer` or leave a message on screen.

**Never name a local `$input`** (or `$args`, `$error`, `$host`...). Inside a
handler dispatched from a message loop, PowerShell's automatic variable shadows
it and the local reads as `$null`. Static check lives in
`control_panel_buttons_smoke.ps1`.

## 受保護的互動契約（Protected interaction contracts）

以下保留自已移除的 `AGENTS.md` 原文。沒有使用者明確要求，不得更動這些行為。

- Tapping Shift toggles persistent Chinese/English mode.
- Holding Shift and pressing A-Z emits one temporary uppercase English letter
  without changing modes. Pending Chinese must be committed before the letter.
- Chinese punctuation lives on **Ctrl**, following Microsoft Bopomofo, and
  **Shift is reserved for plain ASCII**. Binding punctuation to Shift made one
  physical key mean two things depending on mode, which is why it was changed;
  do not move it back. `Ctrl+,` `Ctrl+.` `Ctrl+'` `Ctrl+;` and their
  `Ctrl+Shift` variants must keep working in **both** Chinese and English mode,
  so the check has to precede the English-mode passthrough in both
  `filterKeyDown` and `onKeyDown`. `「」` sits on `Ctrl+[` / `Ctrl+]` and `『』`
  on `Ctrl+Shift+[` / `Ctrl+Shift+]`; this deliberately differs from Microsoft,
  which puts the rarer `【】` there.
- A shifted non-letter key must never reach the Bopomofo table. These keys
  carry Bopomofo unshifted (`,`=ㄝ `.`=ㄡ `/`=ㄥ `;`=ㄤ), so a gap inserts a
  Bopomofo symbol where a symbol belongs. Prefer the host's `charCode` so the
  active keyboard layout wins, and keep the fallback table for hosts that send
  none.
- Ten-item two-column candidate pages, Right/Down pagination,
  and right-side character editing are core behaviors. The left column must
  contain 1-5 from top to bottom and the right column 6-0; never bind A-J as
  candidate labels. Do not replace or
  remove these behaviors without an explicit user request.
- The two-column **vertical-first** grid and Japanese-inspired candidate chrome
  live only in `native_ui/` (`CandidateWindow.cpp` + built `PIMETextService.dll`).
  Stock signed PIME treats `candPerRow=2` as row-major horizontal pairs
  (`1 2 / 3 4 / …`), which is a regression. Once the user has opted in
  (`native-ui-preference.json` `enabled: true`), **never** restore signed
  DLLs, never run `-DisableUnsignedNativeUi`, and never “fix Chinese input”
  by forcing `Valid` Authenticode on `PIMETextService.dll`. Emergency recovery
  may only fix language list / tip Enable / launcher — not candidate UI.
- Candidate editing must offer and atomically apply common/personal phrases
  spanning 2-12 syllables while keeping high-frequency single-character and
  literal-Zhuyin choices available on the first ten-item page. At the end of
  the composition, phrase/sentence choices lead. After the caret moves inside
  the composition, the single character to its right must lead, so candidate
  1 locks only that syllable and advances instead of confirming the sentence.
- Automatic composition and the candidate editor share
  `_ranked_phrase_options()`. Conservative fuzzy-reading and exact typo
  corrections must enter that function as visible whole-sentence candidates;
  Enter must never perform a hidden final rewrite. Before opening Down or
  committing through any path, `_apply_phrase_ranking()` must synchronize the
  editable buffer. A better whole-buffer candidate must never be hidden behind
  Down; arrows are for overriding the default, not obtaining a default the
  engine already knew.
  Fuzzy-reading correction is **off by default** (`phonetic-correction.json`
  must say `enabled: true`); exact typo rules from `common_typos.json` always
  apply.
- Ranking order is a core contract: an explicit user candidate selection is
  first. Bundled candidates compare exact reading-span coverage before source
  weight through the global phrase lattice, so a shorter suffix cannot
  overwrite a longer complete conversion; equal spans prefer the pinned
  Rime/McBopomofo occurrence weights before the legacy engine.
  A stored single-character pin stays candidate zero for isolated input but
  is not a context lock; a reliable word or whole-buffer conversion may
  override it. Only a choice made explicitly in the current composition
  locks its covered segments.
- A learned personal phrase wins its own span and nothing wider. In the
  lattice it is scored just above the strongest bundled option for the same
  readings, and personal origin is the last tiebreaker rather than the first.
  Ranking personal origin first made any learned pair unbeatable, so a phrase
  learned in one sentence dismantled a far stronger word in another: 電話
  (weight 50001) lost to a learned 化一 (weight 0) and 電話一 came out as
  店化一. Never give a personal phrase an unbounded weight or restore it to
  the front of the score tuple.
  Automatic commits must not silently teach the personal stores.
- Single-character ranking preserves libchewing's reading-aware dictionary
  default, then uses global Taiwan frequency for the remaining tail. Global
  frequency has no pronunciation information and must never promote a common
  alternate-reading character such as 員 over 運 for ㄩㄣˋ.
- Text/weight-only frequency indexes are search aids, not pronunciation
  evidence. Before a corpus phrase or fuzzy-reading correction changes live
  text, validate the complete span through `phrase_candidates(readings)`.
  Character-column membership alone must never let an alternate reading
  borrow an unrelated word (for example 貝殼 for ㄅㄟˋ ㄑㄩㄝˋ).
- Autocorrection is conservative, offline, and visible before commit. Apply
  only exact, same-length high-confidence rules from `data/common_typos.json`
  as whole-sentence candidates. A currently selected candidate or a learned
  personal phrase is protected and must outrank every autocorrection rule; a
  stored single-character pin alone is not a context lock. Do not add
  context-dependent pairs such as 的/得/地 or
  在/再 as unconditional replacements, and never upload text for correction.
- Unlocked spans are re-ranked live from their retained Bopomofo readings by
  `phrase_decoder.py` and the exact-reading index. Do not run a second greedy
  exact-phrase pass after the lattice; it can destroy a globally coherent
  result. `phonetic_corrector.py`, reviewed fuzzy phonetic-slot confusions,
  and fallback typo rules must become visible
  whole-sentence candidates before Enter. Surface variants such as 音該/英該
  must not be enumerated as separate rules, and a valid exact-reading phrase
  must be preserved as an alternate candidate.
- Activation and forced focus termination reset only the profile's internal
  Shift toggle. Respect the TSF keyboard-open state supplied by the host;
  never reopen a compartment after an app closes it. This prevents games and
  secure/custom controls from entering an open/close feedback loop.
- Numpad 0-9, decimal, divide, multiply, subtract, and add always emit their
  literal ASCII characters and never Bopomofo or candidate numbers.
  Shift+A-Z, shifted ASCII symbols, and Ctrl punctuation replace only an
  unfinished active syllable, preserve completed Chinese, and emit at the
  active caret. They are emitted by the service rather than passed through to
  the application, because a pending composition has to commit first.
- Literal Bopomofo is a core behavior. For any lone initial, medial, or rime,
  Space first asks the dictionary for the corresponding first-tone Chinese
  syllable; do not classify every initial as invalid because ㄙ and ㄓ,
  and similar syllabic initials are real readings. When candidate zero is
  Chinese, it is auto-selected and raw Zhuyin stays within the first four
  candidates. When candidate zero is literal Zhuyin, open the literal-first
  menu even if libchewing appended obscure Han characters to the tail.
  Completed readings also offer their literal spelling within the
  first four candidates, including sentence editing. With no active syllable,
  bare DaQian tone keys emit their
  tone marks (3=ˇ, 6=ˊ, 4=ˋ, 7=˙). Shift+Space no longer emits ˉ: Shift is
  reserved for plain ASCII, so it emits a space like any shifted non-letter
  key. The first-tone mark has no standalone binding. Numpad digits
  and operators remain literal text. When completed segments already exist,
  raw Zhuyin and bare tone marks stay as protected segments in the editable
  composition; they must not commit the surrounding text like Enter.
- Feedback collection records only explicit conversion corrections. Never add
  surrounding text, application identity, automatic upload, or a network call
  to the IME runtime. The user must review records before opening a report.
- `bopomofo_core/data/high_frequency_phrases.json` is a generated LGPL-3.0
  derivative of pinned Rime Essay data. Never hand-edit it; preserve its
  attribution, generator, source hashes, and bundled license.
- `bopomofo_core/data/reading_phrases.json.gz` is a generated exact-reading
  index from pinned McBopomofo and libchewing-data rows, ranked with pinned
  Rime Essay occurrences. Never hand-edit it; preserve the generator, source
  hashes, MIT/LGPL notices, and the alternate-reading regression.
- `bopomofo_core/data/taiwan_frequency.json` is generated from the Ministry of
  Education's official open-data character and word tables. Never hand-edit
  it; preserve attribution, source hashes, generator, and data notice.
- `bopomofo_core/data/common_typos.json` is a reviewed source-attributed rule
  list. Keep source identifiers and URLs, require equal-length replacements,
  and add regression tests for every policy change.
- Add a regression assertion to `tests/pime_adapter_smoke.py` whenever a core
  interaction is fixed.
- Single-character ranking changes must also pass
  `tests/pime_all_readings_audit.py`, which enumerates every Bopomofo slot and
  tone combination accepted by libchewing. Never replace this with a handful
  of reported syllable examples.
- Candidate font, grid width, labels, and navigation can be changed through
  PIME's Python protocol. The authorized native style lives under `native_ui/`
  and is built from the exact bundled PIME `v1.3.0-stable` source. Install it
  only through the explicit `-EnableUnsignedNativeUi` opt-in, only when PIME
  has no unrelated modules, preserve the original DLLs, and restore them only
  when the installed hashes still match our build. Fresh installs keep the
  signed DLLs for game compatibility. Once opted in, persist that preference
  across normal and EXE updates; never silently restore the signed UI during
  a Python-layer update. `-DisableUnsignedNativeUi` is the explicit rollback.

Run `./build_release.ps1` for a distributable installer. Update all version
locations together when cutting a new version.

## 個人資料與隱私

`%APPDATA%\PinnedBopomofo` 可能包含使用者實際輸入或選過的字詞。除非使用者明確
同意，請勿把 `pins.json`、`phrases.json`、`feedback.json` 上傳給外部 AI、
公開儲存庫或其他人。
一般功能開發不需要這兩個檔案，測試應使用暫存資料。

只提交這個 repo 裡的檔案：外層工作區還有其他不相干的專案與未提交的變更。

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
