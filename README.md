# 智慧優先注音

[![Windows checks](https://github.com/sakiwatashi/inputmethod/actions/workflows/windows.yml/badge.svg)](https://github.com/sakiwatashi/inputmethod/actions/workflows/windows.yml)

以 PIME 與 libchewing 為基礎、操作方式接近微軟注音的 Windows 繁體中文輸入法。
它保留逐字編輯的手感，同時使用常用詞庫與個人學習資料改善選字。

## Clone 與一鍵安裝

```powershell
git clone https://github.com/sakiwatashi/inputmethod.git
cd inputmethod
.\install.ps1
```

Git Bash 使用者可把最後一行改為 `./install.sh`。

## 主要功能

- 注音聲母、介音、韻母與聲調可用任意順序輸入；同類按鍵會取代舊值，不會誤接成下一句。
- 完成一個注音後自動採用第一候選，不必每字按空白鍵。
- `↓` 開啟前 5 個候選；繼續向下超過第 5 個時，展開最多 20 個實用候選，不列出整條生僻字尾。
- 選過的單字會記成該讀音的第一優先，之後先出現。
- 會參考 libchewing 常用詞庫與使用者確認過的 2–12 字詞，改善「樹葉」一類上下文選字。
- 「不」在 `ㄅㄨˋ` 中優先，並內建「不要、不是」及「再見、現在、跟在」等保守的繁體中文常用規則；有歧義的「在做／再做」仍由上下文判斷。
- 整段尚未送出的文字均可編輯；候選目標位於游標右邊，選完會前往下一字。
- 在段落中間按 Backspace 刪除後，下一個注音會補進原位置，不會跳到最右邊。
- 短按 `Shift` 切換中英文；按住 `Shift` 再按字母則暫時輸入大寫英文且不切換模式。兩種操作都會正確處理尚未完成或尚未送出的注音，不會讓英文跳到中文字前方。
- 常用 `Shift` 標點包括 `？`、`：`、`＋`、`——`、`，`、`。`、`『』` 與 `＂`。
- 快速重疊按鍵有實體鍵碼備援，降低漏掉前一個注音符號的機率。

## 安裝與移除

一般使用者只需要執行發佈資料夾中的：

```text
Smart-Priority-Bopomofo-Setup-0.2.0.exe
```

從 GitHub clone 原始碼後，可在 PowerShell 執行一鍵安裝：

```powershell
.\install.ps1
```

若使用 Git Bash，也可以執行：

```bash
./install.sh
```

兩個腳本都從自身位置尋找檔案，不依賴目前工作目錄，因此專案路徑含空白、中文或
放在其他磁碟時仍可使用。

安裝程式會要求系統管理員權限。若電腦沒有 PIME，會安裝包內已驗證數位簽章的
PIME 1.3.0；若已經有 PIME，則保留現有版本，不做降版。完成後可用 Windows 的
輸入法切換快捷鍵選擇「智慧優先注音」。
安裝程式會把智慧優先注音排在繁體中文鍵盤清單第一順位，並設成預設輸入法，讓
Alt+Shift 切回繁體中文時優先選到它。

若安裝程式在新電腦上首次安裝 PIME，會隱藏隨附的「新酷音」，只留下智慧優先
注音；若電腦原本已有 PIME，則不會擅自刪除使用者既有的新酷音。

解除安裝請到 Windows「設定 → 應用程式 → 已安裝的應用程式」。它只會移除
「智慧優先注音」，不移除共用的 PIME，也不刪除個人學習資料。

## 使用者資料與維護

個人資料存放在：

```text
%APPDATA%\PinnedBopomofo\pins.json
%APPDATA%\PinnedBopomofo\phrases.json
```

`pins.json` 是單一讀音的優先字；`phrases.json` 是從使用者確認文字學到的詞語。
兩者都可以直接備份。寫入採原子替換；若檔案意外損壞，輸入法會把原檔改名為
`*.corrupt-日期時間.json` 後以空資料啟動，不會因此整個失效。

## 開發與驗證

執行核心測試：

```powershell
python -m unittest discover -s tests -v
```

建立 PIME 模組覆蓋層：

```powershell
.\build_pime_overlay.ps1
```

建立正式安裝包（需要 NSIS 3.12）：

```powershell
.\build_release.ps1
```

正式安裝包會包含解除安裝程式、SHA-256 雜湊及 PIME/libchewing 的第三方授權
聲明。安裝腳本記錄位於 `%ProgramData%\SmartPriorityBopomofo`。

若要交給其他 AI 修改而不是只讓別人安裝使用，請連同整份原始碼與
`AI_MAINTENANCE.md` 一起提供；個人學習檔可能含有私人輸入內容，不應一併分享。
