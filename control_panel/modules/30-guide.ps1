# 分頁：使用說明
#
# 前身是一張畫出來的鍵盤。使用者的評語是「沒啥用」——它只回答了「這個鍵打
# 出什麼」，而那件事打一次就知道了。真正記不住的是規則：什麼時候按空白、
# 游標怎麼移、標點在哪、學過的詞怎麼刪。
#
# 標點對照表保留下來，因為那是唯一查得到價值的部分，而且 Tables 仍然輸出，
# 讓 tests\control_panel_smoke.ps1 能繼續跟 Python 原始碼比對，防止兩邊分岔。

# pime_module\pinned_bopomofo_ime.py 的 CTRL_PUNCTUATION，
# 虛擬鍵碼已換算成鍵面字元。
$ctrl = [ordered]@{
    "," = "，"; "." = "。"; "'" = "、"; ";" = "；"; "[" = "「"; "]" = "」"
}
$ctrlShift = [ordered]@{
    ";" = "："; "/" = "？"; "1" = "！"; "[" = "『"; "]" = "』"
}

# bopomofo_core\keymap.py 的 KEY_TO_SYMBOL。說明頁不畫鍵盤，但保留這份資料
# 供一致性測試比對；鍵位本身與微軟注音相同，使用者不需要重學。
$bopomofo = [ordered]@{
    "1" = "ㄅ"; "q" = "ㄆ"; "a" = "ㄇ"; "z" = "ㄈ"
    "2" = "ㄉ"; "w" = "ㄊ"; "s" = "ㄋ"; "x" = "ㄌ"
    "e" = "ㄍ"; "d" = "ㄎ"; "c" = "ㄏ"
    "r" = "ㄐ"; "f" = "ㄑ"; "v" = "ㄒ"
    "5" = "ㄓ"; "t" = "ㄔ"; "g" = "ㄕ"; "b" = "ㄖ"
    "y" = "ㄗ"; "h" = "ㄘ"; "n" = "ㄙ"
    "u" = "ㄧ"; "j" = "ㄨ"; "m" = "ㄩ"
    "8" = "ㄚ"; "i" = "ㄛ"; "k" = "ㄜ"; "," = "ㄝ"
    "9" = "ㄞ"; "o" = "ㄟ"; "l" = "ㄠ"; "." = "ㄡ"
    "0" = "ㄢ"; "p" = "ㄣ"; ";" = "ㄤ"; "/" = "ㄥ"; "-" = "ㄦ"
    "6" = "ˊ"; "3" = "ˇ"; "4" = "ˋ"; "7" = "˙"
}

@{
    Name   = "使用說明"
    Order  = 30
    Tables = @{
        Bopomofo  = $bopomofo
        Ctrl      = $ctrl
        CtrlShift = $ctrlShift
    }
    Build = {
        param($Context)

        $marks = $ctrl
        $shiftMarks = $ctrlShift

        $view = New-Object System.Windows.Forms.RichTextBox
        $view.Dock = "Fill"
        $view.ReadOnly = $true
        $view.BorderStyle = "None"
        $view.BackColor = [System.Drawing.SystemColors]::Window
        $view.ScrollBars = "Vertical"
        $view.Font = New-Object System.Drawing.Font("Microsoft JhengHei UI", 10)

        $heading = New-Object System.Drawing.Font("Microsoft JhengHei UI", 12, [System.Drawing.FontStyle]::Bold)
        $body = $view.Font
        $mono = New-Object System.Drawing.Font("Consolas", 10)

        $addText = {
            param([string]$text, $font, $colour)
            $view.SelectionStart = $view.TextLength
            $view.SelectionLength = 0
            $view.SelectionFont = $font
            $view.SelectionColor = $colour
            $view.AppendText($text)
        }.GetNewClosure()

        $ink = [System.Drawing.Color]::FromArgb(20, 20, 24)
        $quiet = [System.Drawing.Color]::FromArgb(105, 108, 115)
        $accent = [System.Drawing.Color]::FromArgb(18, 84, 216)

        $section = {
            param([string]$title)
            & $addText "`r`n$title`r`n" $heading $ink
        }.GetNewClosure()

        $line = {
            param([string]$text)
            & $addText "$text`r`n" $body $ink
        }.GetNewClosure()

        $note = {
            param([string]$text)
            & $addText "$text`r`n" $body $quiet
        }.GetNewClosure()

        $keys = {
            param([string]$text)
            & $addText "$text`r`n" $mono $accent
        }.GetNewClosure()

        & $addText "智慧優先注音 使用說明`r`n" $heading $ink
        & $note "鍵位與微軟注音相同，不必重學。以下只列與微軟不同、或容易忘記的部分。"

        & $section "打字"
        & $line "直接打注音。一個字打完會自動採用第一候選，不必每個字按空白鍵。"
        & $line "聲母、介音、韻母、聲調可以任意順序輸入。"
        & $keys "空白鍵 = 一聲"
        & $note "沒有對應漢字的單一注音（ㄏ、ㄑ、ㄦ…）按空白會直接送出注音本身，可以連打。"

        & $section "選字"
        & $keys "↓        開啟候選"
        & $keys "1-5      左欄由上而下      6-0      右欄由上而下"
        & $keys "← →      同一列的兩欄之間跳，到外側欄才翻頁"
        & $keys "↑ ↓      依序移動，到底自動翻頁"
        & $keys "PageUp / PageDown   專用翻頁"
        & $line "也可以直接用滑鼠點選。滑鼠移過去會用淡色預示，真正的游標仍是深色那格。"

        & $section "修改還沒送出的句子"
        & $line "整段未送出的文字都可以編輯。"
        & $keys "← →        移動游標"
        & $keys "Backspace  刪除游標左邊的字"
        & $line "移動游標後打字，新字會插在游標處，不會跳到最後面。"
        & $note "選字時游標右邊的那個字排在最前面，所以按 1 只鎖定那一個字並前進，不會誤確認整句。"

        & $section "中英文切換"
        & $keys "短按 Shift        切換中／英文（持續）"
        & $keys "按住 Shift + 字母  暫時打一個英文字母，不改變模式"
        & $keys "大寫鎖定鍵        也可以切換（由 Windows 處理）"
        & $note "大寫鎖定那條路不經過輸入法，所以在遠端桌面或命令列等特殊環境裡最可靠。"
        & $note "按住 Shift 打字母時會遵循大寫鎖定狀態：大寫鎖定開著時 Shift+A 輸出小寫 a，和 Windows 各處一致。"

        & $section "中文標點（走 Ctrl，不是 Shift）"
        & $note "Shift 一律輸出標準 ASCII，這樣同一個實體按鍵在中英模式下才不會有兩種意思。"
        $rows = @()
        foreach ($key in $marks.Keys) { $rows += ("  Ctrl + {0,-3} {1}" -f $key, $marks[$key]) }
        foreach ($key in $shiftMarks.Keys) { $rows += ("  Ctrl + Shift + {0,-3} {1}" -f $key, $shiftMarks[$key]) }
        & $keys ($rows -join "`r`n")
        & $note "「」放在 Ctrl+[ ]（微軟放的是【】）。代價是【】與｛｝沒有輸入法內的入口。"
        & $line "這些在中文與英文模式下都能用。"

        & $section "它會記住什麼"
        & $line "在組字區親手選過字再送出，整句會學進個人詞庫，下次同樣的讀音就會直接出現。"
        & $note "輸入法自己猜對的不會學——那是為了避免錯誤的轉換自我增強。"
        & $line "單字選過會記成該讀音的第一優先。"
        & $line "學過的東西都可以在「個人詞庫」分頁檢視、修改、刪除。"

        & $section "覺得候選字太多"
        & $line "到「候選字過濾」分頁，可以隱藏用不到的冷僻字。"
        & $note "那裡只是隱藏，內建字典沒有被改，設定清掉就全部回來。"

        & $section "資料放在哪"
        & $keys "%APPDATA%\PinnedBopomofo"
        & $line "個人詞庫、排名鎖定、各項設定都在這裡，只存在本機，不會外傳。"
        & $note "解除安裝不會刪除這個資料夾。"

        $view.SelectionStart = 0
        $view.SelectionLength = 0
        $view.ScrollToCaret()
        $view
    }.GetNewClosure()
}
