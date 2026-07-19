# 微軟注音式核心行為測試器

這是 PIME/libchewing 整合前的隔離原型，不會註冊成 Windows 輸入法，也不會修改目前的小狼毫設定。

目前驗證的行為：

- 聲母、介音、韻母、聲調各自只有一個槽位；同類符號會覆寫舊值。
- 輸入順序自由，例如 `ㄧㄒㄣˋ` 會整理成 `ㄒㄧㄣˋ`。
- 聲調輸入後音節仍可編輯，例如 `ㄒㄩㄝˋ` 再按 `ㄑ` 會成為 `ㄑㄩㄝˋ`。
- 不建立一般的連續語句；必須按 Enter 才確認目前音節。
- 無效按鍵或候選檢查失敗時回報 `BELL`，Windows 測試器會播放系統提示音。

## 執行

在 PowerShell 中：

```powershell
.\run.ps1
```

使用標準大千注音鍵盤直接輸入。Escape 清除，Backspace 刪除最近一次編輯的槽位，Enter 確認。例如 `v m , 4` 是 `ㄒㄩㄝˋ`。

## 測試

```powershell
python -m unittest discover -s tests -v
```

## PIME/libchewing 整合狀態

目前已接上自行編譯的 32 位元 libchewing Simple Engine 與完整詞典，並可產生 PIME overlay：

```powershell
.\build_pime_overlay.ps1
```

輸入法內可用方向鍵選候選、Enter 或 Space 確認；`Ctrl+PageUp` 會把目前候選永久固定為該讀音的第一名。一般輸入仍限制為單一音節，不會累積成連續語句。

多字固定詞（例如「寫程式」）需要下一階段的「只針對已固定詞保留短 composition」機制；不會重新開啟一般智慧組句。

`install_pime_prototype.ps1` 會驗證官方 PIME 安裝程式簽章、安裝標準版 PIME、複製自訂模組並重新註冊輸入法 profile。它需要 Windows 系統管理員權限，會顯示 UAC 提示。
