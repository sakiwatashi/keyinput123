# 行程外候選視窗設計（提案，待審核）

把日式候選視窗從行程內 TSF DLL 移到獨立輔助行程，讓遊戲行程內永遠只有
PIME 原廠簽章 DLL。本文是設計提案，**尚未實作**；其中「契約變更」一節需要
明確核可才能動工。

## 0. 實作進度

| 項目 | 狀態 |
|---|---|
| 輔助程式建置（`native_ui/helper/`，C++／CMake） | 完成 |
| 直向優先格線繪製（左欄 1-5、右欄 6-0） | 完成，已截圖驗證 |
| 逐螢幕 DPI（修正原程式只讀主螢幕的缺陷） | 完成 |
| 信標搜尋與跟隨定位 | 完成，以 `fake_beacon.ps1` 驗證 |
| 置頂重申（降低 z-order 競態） | 完成，已量測 |
| 具名管道（Python → 輔助程式） | 完成，端到端驗證 |
| Python 端非阻塞鏡像 + 單一收斂點 | 完成 |
| 隨輸入法自動啟動、單一實例互斥鎖 | 完成，已驗證重複啟動不會產生第二個行程 |
| 打包進 overlay 與安裝流程 | 完成 |
| 使用者開關（預設關閉） | 完成 |
| **信標模式**（改寫送給原廠 DLL 的清單） | 完成，含存活門檻與整合測試 |
| 找不到信標時沿用上次錨點 | 完成 |
| 滑鼠選字回送 | 未做 |
| 遊戲政策（前景為防作弊遊戲時不作為） | 未做 |
| 尚未在真實輸入情境驗證 | **待使用者實測** |

共 24 個新單元測試，另在 `tests/pime_adapter_smoke.py` 加入信標模式三段斷言。

### 信標模式的安全設計

信標模式把真實候選清單從 PIME 自己的視窗移除，因此那份清單只存在於輔助程式。
若輔助程式不在，使用者會看到空白方塊且無法選字。三道防線：

1. **存活門檻**：只有在「最近一次寫入管道確實成功」時才啟用改寫
   （`beacon_ready`）。寫入失敗會立即撤銷，下一次按鍵就恢復完整清單。
2. **只改線上值**：改寫發生在 `handleRequest` 回傳的 reply，
   `self.candidateList` 保留真實清單，排序、翻頁、選字邏輯完全不受影響。
3. **錨點記憶**：輔助程式在候選仍有效但暫時找不到信標時，沿用上次已知位置
   繼續顯示，而不是讓畫面空白。

### 安裝流程的一個實際缺陷（已修）

輔助程式安裝在模組目錄內並持有自己的執行檔，會鎖住 `build_pime_overlay.ps1`
要清除的 `dist` 目錄與安裝程式要替換的模組目錄，造成安裝看似成功、實際檔案未
更新。overlay 建置、安裝與解除安裝現在都會先停止該行程；它是可拋棄的 UI 行程，
輸入法需要時會自行重啟。

### 開關

`%APPDATA%\PinnedBopomofo\candidate-ui.json`，內容 `{"enabled": true}` 才啟用。
檔案不存在、讀取失敗或值為 false 一律視為關閉，此時鏡像完全惰性：不建立執行緒、
不啟動行程、不開管道。偏好只在建立 client 時讀取一次 —— 打字途中讀檔會拖住宿主
應用程式的輸入執行緒 —— 因此變更需重啟 PIME 才生效。

## 1. 問題

`PIMETextService.dll` 是 TSF 文字服務，Windows 會把它載入每一個接收文字的
行程，遊戲也不例外。我們的自訂日式 UI 畫在這顆 DLL 裡，因此必然進入遊戲
記憶體。

實測證據（2026-07-23 00:03，三筆系統事件）：VALORANT 的 Vanguard 把該 DLL
**強制卸載**，TSF 隨後呼叫已解除映射的位址，遊戲以 BEX64 崩潰。崩潰事件回
報的 PE 編譯時間戳 `0x6a5ff231` = 2026-07-21 22:26 UTC，與我們保留的自訂建
置完全吻合，且不可能是原廠簽章版（2023-01-20）。7/24 還原簽章 DLL 之後未再
出現任何一筆同類事件。

### 已排除的方向

- **自簽憑證加入本機信任根**：修改系統信任存放區；且核心層防作弊不採信本機
  信任存放區，無效。
- **購買 OV/EV 憑證**：可讓 Authenticode 為 `Valid`，但 Vanguard 連大量合法
  簽章的疊加層工具都照擋，且須先付費才能驗證。不建議。
- **改用 C++ 重寫**：該 DLL 本來就是純 C++（`native_ui/src/*.cpp`，CMake 建置）。
  防作弊判斷的是模組的簽章信任與行為特徵，與原始語言無關。
- **讓 DLL 避開遊戲行程載入**：DLL 被映射時即已被掃描；且刻意規避防作弊偵測
  不在本專案範圍內，亦有帳號風險。

## 2. 定位策略的實測比較

行程外繪製的核心難題是「輔助行程如何知道要畫在哪裡」。行程內版本可直接向
TSF 取得組字矩形（`service->compositionWindow(session)`）；行程外沒有這個管道。

以 `GetGUIThreadInfo` 與 UI Automation `TextPattern` 對本機實際執行中的程式
探測（腳本見第 8 節）：

| 目標程式 | GetGUIThreadInfo | UIA TextPattern |
|---|---|---|
| Notepad（傳統 Win32） | OK caret=(16,16) h=15 | OK rect=(126,179) |
| chrome | 無 caret | OK rect=(194,51) |
| Discord（Electron） | 無 caret | 無 TextPattern |
| ChatGPT（Electron） | 無 caret | 無 TextPattern |
| claude（Electron） | 無 caret | 無 TextPattern |
| steamwebhelper | 無 caret | 無 TextPattern |
| explorer / AnyDesk / TextInputHost | 無 caret | 無 TextPattern |

耗時：`GetGUIThreadInfo` 約 0–14 ms；UIA 約 3–83 ms（首次呼叫最慢）。

**誠實的但書**：探測時這些程式並非前景、也沒有作用中的輸入欄位，因此「無
caret」有一部分是合理的。但 Electron 程式連 `TextPattern` 節點都完全不存在，
符合 Chromium 無障礙樹惰性啟用的已知行為 —— 而那正是使用者最常打字的地方。

**結論**：這兩條路都不足以支撐，且要下定論還得逐一手動聚焦重測。下一節的方案
讓這個問題整個消失，因此不再投入驗證。

## 3. 採用方案：位置預言機（position oracle）

關鍵觀察：**原廠簽章 DLL 本來就會把候選視窗正確定位在游標旁**。我們不需要
自己算位置，只要讀它算好的位置。

已驗證：候選視窗的視窗類別名稱是 `LibImeWindow`，**簽章原廠版與自訂版皆有**
（由兩顆 DLL 的 UTF-16 字串表確認）。因此可用 `EnumWindows` 從行程外找到它。

幾何也恰好相容：

- 自訂 `candidateGrid(10, candPerRow=2)`：`rows=min(5,10)=5`、`cols=2`（直向填）
- 原廠 `candPerRow=2` 語意為「每列 2 個」：`cols=2`、`rows=ceil(10/2)=5`（橫向填）

外框同為 2 欄 × 5 列，只有候選字填入順序不同 —— 也就是我們一直想修正的那一點。
兩者尺寸相近，可直接覆蓋。

### 資料流

1. 使用者按鍵。原廠 DLL 依現行協定送到 Python。
2. Python 照現行邏輯算出候選，回覆 `showCandidates=True` 與 `candidateList`。
   **此處完全不變。**
3. **新增**：Python 另外把候選狀態非阻塞推送給輔助行程。
4. 原廠 DLL 依 TSF 正確定位並顯示 `LibImeWindow`。
5. 輔助行程收到推送後，找出前景行程所擁有、可見的 `LibImeWindow`，讀出其螢幕
   矩形，把日式視窗畫在同一位置覆蓋其上。

定位正確性因此**繼承自 TSF 本身**：凡是原廠 PIME 候選框位置正確的程式，我們
就正確，沒有例外。

### 預言機視窗的處置（**本設計最高風險，須最先做原型驗證**）

單純「畫在上面蓋住」有一個嚴重問題：候選內容每次按鍵都會變，原廠 DLL 會隨之
重新定位與重繪它的視窗。兩個視窗同為 TOPMOST 時，z-order 由最後一次
`SetWindowPos` 決定，因此原廠視窗很可能在**每一次按鍵**都短暫蓋過我們的視窗，
造成使用者看到錯誤排列（橫向填）的閃爍。這比首次顯示閃一下嚴重得多。

依偏好排序的三個候選處置方式：

1. **信標模式（首選）**：Python 仍送 `showCandidates=True`，但把送給原廠 DLL 的
   `candidateList` 縮成單一空白項。原廠視窗因此縮成僅有邊距的一小塊，**位置
   依然由 TSF 正確計算**，我們純粹拿它當位置信標，再用自己的完整視窗完全覆蓋。
   因為原廠視窗根本沒有內容，就不存在「錯誤排列閃爍」。

   上游原始碼證實這個模式比原先設想的更穩固 —— 定位邏輯只用到游標矩形，與候選
   內容無關：

   ```cpp
   // PIMETextService.cpp:295-300
   RECT textRect;
   if (selectionRect(session, &textRect)) {
       candidateWindow_->move(textRect.left, textRect.bottom);
   }
   ```

   也就是說**信標視窗的左上角就是游標的左下角**。我們只需要它的「位置」，
   完全不依賴它的尺寸，即使它縮到只剩 1 像素也照樣是精確的錨點。
   *仍待驗證*：PIME 是否願意為空候選建立並顯示視窗。**必須先原型驗證。**
2. **一次性取樣**：組字開始時取一次預言機矩形，之後改送
   `showCandidates=False`，我們記住位置自行繪製。每次組字開始仍會閃一下。
3. **跨行程隱藏／移出螢幕**：讀出位置後把信標移到螢幕外，或設 layered alpha 0。
   有效但會去修改別的行程的視窗，且原廠 DLL 會在下次更新時移回來。另有一個
   失效模式需注意：若輔助行程崩潰時信標正停在螢幕外，使用者會短暫完全看不到
   候選框（下一次按鍵才會復原）。列為備案。

任一方式的尺寸都取 `max(自身自然尺寸, 預言機矩形)` 以確保完全覆蓋。實測資料
（見下）顯示方式 1 是唯一可靠的選擇。

### 實地量測（2026-07-31，原廠簽章 DLL 作用中）

以 `watch_candidate_window.ps1` 在 Electron 應用程式（claude）內打注音,60 秒內
觀察到 5 個 `LibImeWindow`：

| 位置 | 尺寸 | hwnd |
|---|---|---|
| (0,0) | 2x10 | 0x40E98 |
| (0,0) | 10x10 | 0x150E98 |
| **(748,876)** | **314x156** | **0x170E98** ← 真正的候選框 |
| (0,0) | 2x10 | 0x200E98 |
| (0,0) | 10x10 | 0xF0E8C |

結論：

1. **信標可從行程外定位** —— 候選框確實帶有真實的螢幕座標與尺寸。第 2 節那些
   在 Electron 應用程式上失效的定位 API，在這裡完全不需要。
2. **消歧義比預期容易**：真正的候選框位置不在 `(0,0)` 且尺寸顯著；其餘 4 個干擾
   視窗全部停在 `(0,0)` 且僅 2x10 或 10x10。篩選條件即為「位置非 (0,0) 且尺寸
   超過門檻」。
3. **不得快取 hwnd**：每次組字似乎都產生新的視窗代號，輔助行程必須每次重新
   搜尋，不能記住上一次的 hwnd。
4. 那 4 個小視窗始終停在 `(0,0)`，初判疑似對信標假設不利，但查證上游原始碼後
   **確認為虛驚**（見下）。

### 信標假設：已由原始碼證實

`tmp/PIME-upstream/PIMETextService/PIMETextService.cpp` 的 `updateCandidates()`：

```cpp
for (int i = 0; i < candidates_.size(); ++i) {
    candidateWindow_->add(candidates_[i], selKeys_[i]);
}
candidateWindow_->recalculateSize();
candidateWindow_->refresh();

RECT textRect;
// get the position of composition area from TSF
if (selectionRect(session, &textRect)) {
    candidateWindow_->move(textRect.left, textRect.bottom);
}
```

**`move()` 與候選數量完全無關**：候選為空時迴圈只是不執行，
`recalculateSize()` 退化成 `margin_ * 2` 的小方塊，而 `move()` 照樣被呼叫。
唯一的前提是 `selectionRect()` 成功 —— 那取決於 TSF 能否提供組字矩形，與候選
內容無關；而實測中同一個 Electron 應用程式已成功回傳 (748,876)，證明該路徑可用。

**因此信標模式在原始碼層面成立**：送出空候選清單仍會得到一個被正確定位到游標
旁的視窗。

至於那些停在 `(0,0)` 的小視窗，`showMessage()` 的路徑可以解釋：

```cpp
int x = 0, y = 0;
if (isComposing()) { RECT rc; if (selectionRect(session, &rc)) { x = rc.left; y = rc.bottom; } }
messageWindow_->move(x, y);
```

非組字狀態下 `x, y` 保持 0 並被 `move(0, 0)`。且 `MessageWindow` 每次
`showMessage()` 都重新建立（上游原始碼留有 `FIXME: reuse the window whenever
possible`），可解釋為何出現多個不同 hwnd。本模組確實會呼叫 `showMessage()`。
無論成因為何，第 2 點的篩選條件都能正確排除它們。

### z-order 實測：信標模式從「首選」升級為「必要」

以 `fake_beacon.ps1` 建立一個假的 `LibImeWindow`（TOPMOST、NOACTIVATE、每 150 ms
重新宣告 `HWND_TOPMOST`），再以輔助程式覆蓋，連續截圖統計信標外露的取樣點數：

| 情境 | 六次取樣 | 最壞值 | 全露基準 |
|---|---|---|---|
| 全尺寸信標 300x160，輔助程式無置頂重申 | 12000, 12000, 12000, 8, 12000, 12000 | 12000 | 12000 |
| 全尺寸信標 300x160，加入 60 ms 置頂重申 | 8, 8, 8, 8, **12000**, 8 | 12000 | 12000 |
| **信標模式 10x10**，加入 60 ms 置頂重申 | 25, 5, 5, 5, 5, 5 | **25** | 25 |

三個結論：

1. **單純覆蓋全尺寸信標不可行。** 未加置頂重申時，信標六次有五次完全壓在上面。
2. **靠 z-order 競賽取勝並不可靠。** 加入 60 ms 重申後大幅改善，但六次仍有一次
   整片外露。這是競態，不是可以調參數解決的問題。
3. **正解是讓「輸掉競賽」變得無害。** 信標模式把最壞情況從 48000 px² 的錯誤排列
   視窗，縮到 100 px² 的角落小方塊 —— 約 480 倍的改善。因此信標模式不是偏好，
   而是本設計的必要條件。

補充兩點實測細節：

- 殘餘的 8 點來自**我們自己的圓角**：輔助視窗有圓角裁切，方角的信標會從四個角
  露出來。信標模式下信標只在左上角，此問題自然消失。
- 信標模式下，信標正好落在輔助視窗左上角的**邊距區**（該處本來就沒有文字），
  且真實信標會是接近我們紙色背景的淺色，而非測試用的紅色。若實測仍可見，備案
  是讀出位置後把信標移到螢幕外。

置頂重申已實作於 `main.cpp`（`kTopmostIntervalMs`），因為它讓最壞情況的發生頻率
從 5/6 降到 1/6，成本僅為一個極輕量的計時器。

### 更新觸發，以及一個必須處理的競態

`SetWinEventHook(EVENT_OBJECT_SHOW | EVENT_OBJECT_LOCATIONCHANGE,
WINEVENT_OUTOFCONTEXT)`。**out-of-context 表示回呼在我們自己的行程執行，不會把
任何 DLL 注入目標行程** —— 這對防作弊敘事很重要。

競態來自事件順序：Python 是在**處理按鍵的當下**推送候選內容的，但原廠 DLL 要等
收到 Python 的回覆之後才會移動並顯示信標視窗。因此輔助行程若在收到推送的瞬間
就去讀信標位置，讀到的會是**上一次**的位置。

解法是把「內容」與「位置」視為兩個獨立的輸入源：推送只更新內容，WinEvent 只
更新位置，任一方變動都以雙方各自的最新值重繪。兩者以 epoch 標記，位置事件早於
對應內容抵達時先不繪製，避免顯示錯位的一幀。

## 4. 元件

| 元件 | 語言／位置 | 是否進入遊戲行程 |
|---|---|---|
| `PIMETextService.dll`（原廠簽章，不動） | C++，每個行程 | 是（但受信任） |
| `pinned_bopomofo_ime.py`（既有，小幅擴充） | Python，PIME 伺服器行程 | 否 |
| `SmartPriorityCandidateUI.exe`（新增） | C++，自有行程 | 否 |

輔助行程是我們自己的 EXE，**不需要簽章**，因為它從不進入別人的行程。

### 程式碼移植評估

以現有 `native_ui/src/CandidateWindow.cpp`（440 行）為基礎：

- **幾乎原封不動可移植（約 250 行）**：配色常數、`scaledPixel`、
  `candidateGrid`（直向優先格線，本專案的核心資產）、`fillRoundRect`、
  `onPaint`（雙緩衝）、`recalculateSize`、`paintItem`、`itemRect`、滑鼠處理。
- **直接刪除（約 150 行）**：`ITfUIElement` / `ITfCandidateListUIElement` 的全部
  COM 樣板（`GetDescription`、`GetGUID`、`Show`、`IsShown`、`GetUpdatedFlags`、
  分頁索引方法）、`filterKeyEvent`（按鍵邏輯本來就在 Python）。
- **新增（約 200 行）**：純 Win32 視窗類別與訊息迴圈、具名管道伺服器、預言機
  視窗搜尋、WinEvent hook、前景／遊戲政策。

相依性同時大幅縮減：**不再需要 libIME2**，也不需要 jsoncpp（可用極簡行協定）。

## 5. 行程間通訊

### 絕對禁止：不得借用 PIME 既有的通道

PIME 的 DLL↔Python 通道是**嚴格的請求／回應**，且對非預期訊息毫無容錯。上游
原始碼顯示，出貨版 DLL 用單一阻塞式 `TransactNamedPipe`，沒有讀取執行緒、沒有
非請求訊息路徑，並且對 `seqNum` 嚴格驗證：

```cpp
if (response["seqNum"].asUInt() != seqNum)  // sequence number mismatch
    success = false;
...
if (!success) {
    closeRpcConnection();   // close the pipe connection since it's broken
    resetTextServiceState();
}
```

而 launcher 端會無條件轉發任何 `PIME_MSG|` 開頭的 stdout 行。因此若 Python 模組
主動往 stdout 印出一行推送訊息，它會被當成**下一次按鍵的回覆**送給 DLL，
`seqNum` 比對失敗，管道被關閉、輸入法狀態被重置。**非同步推送不只是不支援，
而是會直接弄壞通道。**

結論：與輔助行程的通訊必須走**我們自己另開的具名管道**，與 PIME 的傳輸完全隔離。

### 我們自己的通道

- 具名管道 `\\.\pipe\SmartPriorityBopomofo.CandidateUI`，採預設 DACL（限本使用者），
  **純本機、絕不涉及網路**，符合既有的「執行期不得連網」契約。
- JSON 行格式。訊息內容：候選清單、游標索引、選擇標籤、一個單調遞增的 epoch
  用於丟棄過期訊息。
- **硬性要求：輔助行程掛掉或卡住，絕不能拖慢或中斷打字。** 這一點的嚴重性比原先
  評估的更高：出貨版 DLL 呼叫 `TransactNamedPipe(..., NULL)` **沒有客戶端逾時**，
  所以 Python 處理慢就會直接卡住宿主應用程式的輸入執行緒；而 `server.py` 是
  單執行緒阻塞迴圈服務**所有**連線，一個慢的處理常式會拖垮每一個程式的打字。
  因此 Python 端必須是純粹的射後不理：背景執行緒加有界佇列，輸入法執行緒永不
  阻塞，寫入失敗即靜默丟棄、下次按鍵重試。
- Launcher 另有 30 秒看門狗（`BACKEND_REQUEST_TIMEOUT_MS`），逾時會重啟整個
  Python 後端並清空狀態。任何新增的處理都必須遠低於這個量級。
- **隱私**：候選內容屬使用者私密輸入，只存在於記憶體與該管道，**不得寫入任何
  日誌檔**。

### 執行環境限制

- PIME 內嵌的直譯器是 **CPython 3.8.10（32 位元）**，與本專案單元測試所用的
  64 位元 Python 3.14 不同。新增的 Python 程式碼必須相容 3.8：現代型別註記需
  搭配 `from __future__ import annotations`（現有檔案已如此）。
- `subprocess`、`socket`、`threading`、`ctypes` 在該直譯器均可用。
- 啟動輔助行程有既有先例：上游輸入法以 `ShellExecuteW`／`subprocess` 啟動獨立的
  設定工具行程，且執行環境已內附 Tornado。
- `PIMELauncher.exe` 經由 libuv 建立了 job object，預設帶 `KILL_ON_JOB_CLOSE`。
  這表示我們啟動的輔助行程會隨 launcher 一起結束 —— 對本設計而言**這是想要的
  行為**（PIME 不在了就不需要候選視窗），不需要 breakaway。

### 生命週期

Python 於 `onActivate` 時若偵測輔助行程未執行則啟動它（單一實例 mutex）。輔助
行程閒置數分鐘後自行結束。

### 協定限制（實作時必須遵守）

- 客戶端只解析 19 個回覆鍵，額外鍵一律靜默丟棄 —— **協定沒有擴充欄位可用**，
  這也是必須自建通道的另一個理由。
- `candidateList`、`showCandidates`、`candidateCursor`、`commitString`、
  `compositionString`、`compositionCursor` **只有從 `onKeyDown`／`onKeyUp` 回覆時
  才生效**（其他回呼沒有 edit session，會被靜默忽略）。信標模式的欄位改寫必須
  發生在這兩個回呼裡。`setSelKeys`、`customizeUI` 則各處皆可。
- `customizeUI` 只接受四個鍵：`candFontName`、`candFontSize`、`candPerRow`、
  `candUseCursor`。
- 候選數量受 `assert(candidates_.size() <= selKeys_.size())` 約束；信標模式送出
  單一項目不受影響。
- 上游完整原始碼已存在於工作區 `tmp/PIME-upstream/`（出貨版標籤 `26fcf6ac`
  = `v1.3.0-stable`），實作時應以它為準查證行為。

### Python 端的落點

`pinned_bopomofo_ime.py` 目前有 11 處 `setCandidateList(...)` 呼叫點
（第 246、303、847、852、860、868、970、1112、1120、1137、1148 行）。實作時
不逐一修改，而是新增一個單一收斂點包住它：對輔助行程推送真實候選，對原廠 DLL
送出信標所需的內容。這樣既不動現有的排序與選字邏輯，回歸測試也只需驗證這個
收斂點。程式碼中已存在 `setCandidateList([])` 的用法，代表空候選本身是既有的
正常狀態。

## 6. 遊戲政策

輔助行程比對前景行程是否屬於已知防作弊遊戲；命中時**完全不作為**：不 hook、
不繪製、不碰該視窗，由原廠候選框正常顯示。這是刻意保守 —— 本設計的目的是讓
自訂 UI 遠離遊戲，不是讓它想辦法出現在遊戲裡。

## 7. 契約變更（需要核可才動工）

`AGENTS.md` 目前明訂：一旦使用者選用自訂 UI，**永不**還原簽章 DLL，且
`-DisableUnsignedNativeUi` 是唯一的回滾方式。本設計的終局狀態恰恰是「所有行程
都用簽章 DLL」，與該條契約直接衝突，因此必須由使用者明確決定。建議分三階段：

1. **階段一**：實作輔助行程，自訂 DLL 路徑完全不動，輔助行程以新旗標選用。
   兩者不得同時啟用（避免雙重視窗）。
2. **階段二**：在各類程式驗證通過後翻轉預設值 —— 全面簽章 DLL + 輔助行程開啟，
   `-EnableUnsignedNativeUi` 標記為淘汰。
3. **階段三**：移除 DLL 抽換機制。安裝器的備份、pending、`MoveFileEx` 排程、
   zombie 清理等複雜度**全部消失**，是一次大幅簡化。

## 8. 風險與未決事項

1. **預言機視窗處置**（見第 3 節）：原為最高風險項。其中「PIME 是否為空候選
   定位視窗」已由上游原始碼證實成立（`move()` 與候選數量無關），並經實地量測
   確認候選框帶有真實螢幕座標。**剩餘待驗證的只有兩個 TOPMOST 視窗的實際
   z-order 行為**，而信標模式本身就大幅降低了該風險（信標沒有內容可閃）。
2. **`LibImeWindow` 消歧義**：PIME 的訊息／提示視窗可能共用同一類別名稱。緩解
   方式為只在 Python 告知候選作用中時搜尋，並比對擁有者行程與預期尺寸。
3. **每螢幕 DPI**：現有 `scaledPixel()` 只讀主螢幕 DPI（`GetDC(NULL)`），移到
   多螢幕環境會失準。移植時必須改為每螢幕 DPI 感知 —— 這是既有程式碼的缺陷。
4. **螢幕邊緣裁切**：自身尺寸與原廠不完全相同時可能超出螢幕，需邊緣夾制。
5. **滑鼠選字**：我們的視窗在上層會接到點擊，需把選取結果回送 Python。由於
   PIME 不接受非同步推送（見第 5 節），回送只能等到下一次按鍵事件才能生效，
   或改由輔助行程直接以 `SendInput` 送出對應的選字鍵。後者較簡單，但須確認不會
   與遊戲政策衝突。
6. **沒有應用程式焦點回呼**：協定完全沒有 `onSetFocus`／`onKillFocus`；DLL 內的
   `onFocus()` 是空的且從不轉發。最接近的訊號是
   `onCompositionTerminated(forced=True)`，其語意為「其他應用程式搶走焦點」，
   但不帶任何目標資訊。輔助行程因此必須自行以 `GetForegroundWindow` 追蹤前景，
   不能依賴 PIME 通知。
7. 診斷腳本已收進 `native_ui/diagnostics/`：`probe_caret.ps1` 重測第 2 節的定位
   策略；`watch_candidate_window.ps1` 監看 `LibImeWindow` 的出現、位置與尺寸，
   用於驗證第 3 節的信標假設。

## 9. 測試計畫

- **單元**：格線版面數學、管道訊息框架、遊戲政策判斷式。
- **整合**：輔助行程搭配假造的 Python 產生端，驗證視窗出現在預言機矩形。
- **手動矩陣**：Notepad、Chrome、Electron（Discord／VS Code）、Office、終端機，
  以及一款防作弊遊戲（驗證輔助行程保持沉默且遊戲不崩潰）。
- **回歸**：`tests/pime_adapter_smoke.py` 斷言 Python 仍照舊送出
  `showCandidates`／`candidateList`（輔助行程屬純增量）。
- **崩潰安全**：打字途中強制結束輔助行程，打字必須無縫延續並回到原廠候選框。
