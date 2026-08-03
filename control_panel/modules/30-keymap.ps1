# 分頁：按鍵對照表（唯讀）
#
# 把 KEY_BINDING_ALIGNMENT.md 的表格畫成看得到的鍵盤。每個鍵上同時顯示
# 三層意義：中文模式打出的注音、英文模式打出的 ASCII、按著 Ctrl 打出的標點。
#
# 表格是從 Python 抄過來的副本（PowerShell 讀不到 Python 的字典），因此
# 連同資料一起從 Tables 輸出，讓 tests\control_panel_smoke.ps1 能直接跟
# 原始碼比對。抄錯、或日後只改了單邊，測試都會擋下來。

# bopomofo_core\keymap.py 的 KEY_TO_SYMBOL（空白鍵另外處理，見下方說明）
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

# pime_module\pinned_bopomofo_ime.py 的 CTRL_PUNCTUATION，
# 虛擬鍵碼已換算成鍵面字元。
$ctrl = [ordered]@{
    "," = "，"; "." = "。"; "'" = "、"; ";" = "；"; "[" = "「"; "]" = "」"
}
$ctrlShift = [ordered]@{
    ";" = "："; "/" = "？"; "1" = "！"; "[" = "『"; "]" = "』"
}

$rows = @(
    @{ Offset = 0.00; Keys = @("1","2","3","4","5","6","7","8","9","0","-","=") },
    @{ Offset = 0.55; Keys = @("q","w","e","r","t","y","u","i","o","p","[","]") },
    @{ Offset = 0.80; Keys = @("a","s","d","f","g","h","j","k","l",";","'") },
    @{ Offset = 1.30; Keys = @("z","x","c","v","b","n","m",",",".","/") }
)

@{
    Name   = "按鍵對照"
    Order  = 30
    Tables = @{
        Bopomofo  = $bopomofo
        Ctrl      = $ctrl
        CtrlShift = $ctrlShift
    }
    Build = {
        param($Context)

        # GetNewClosure 只捕捉「呼叫它時的那一層」的變數。下面的 Paint 處理程序
        # 是在這個 Build 裡建立閉包，所以四張表必須先落到本地變數，否則畫圖時
        # 全是 $null，迴圈空轉，鍵盤整片畫不出來（而且不會有任何錯誤訊息）。
        $keyRows = $rows
        $symbols = $bopomofo
        $ctrlMarks = $ctrl
        $ctrlShiftMarks = $ctrlShift

        $keySize = 62
        $gap = 6
        $step = $keySize + $gap

        $canvas = New-Object System.Windows.Forms.Panel
        $canvas.Dock = "Fill"
        $canvas.BackColor = [System.Drawing.SystemColors]::Window

        $fontSymbol = New-Object System.Drawing.Font("Microsoft JhengHei UI", 15)
        $fontAscii  = New-Object System.Drawing.Font("Consolas", 8)
        $fontPunct  = New-Object System.Drawing.Font("Microsoft JhengHei UI", 9)

        $penEdge = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(198, 200, 205))
        $brushFace = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
        $brushCtrlFace = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(240, 246, 255))
        $brushSymbol = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(20, 20, 24))
        $brushAscii = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(130, 134, 140))
        $brushPunct = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(18, 84, 216))

        $canvas.Add_Paint({
            param($sender, $eventArgs)
            $graphics = $eventArgs.Graphics
            $graphics.SmoothingMode = "AntiAlias"
            $graphics.TextRenderingHint = "ClearTypeGridFit"

            $y = 10
            foreach ($row in $keyRows) {
                $x = 10 + [int]($row.Offset * $step)
                foreach ($key in $row.Keys) {
                    $symbol = $symbols[$key]
                    $punct = $ctrlMarks[$key]
                    $punctShift = $ctrlShiftMarks[$key]

                    $face = if ($punct -or $punctShift) { $brushCtrlFace } else { $brushFace }
                    $rect = New-Object System.Drawing.Rectangle($x, $y, $keySize, $keySize)
                    $graphics.FillRectangle($face, $rect)
                    $graphics.DrawRectangle($penEdge, $rect)

                    # 左上角小字：英文模式下這個鍵打出的字元。
                    $graphics.DrawString($key.ToUpper(), $fontAscii, $brushAscii,
                        [single]($x + 4), [single]($y + 3))

                    # 中央大字：中文模式下的注音符號。
                    if ($symbol) {
                        $size = $graphics.MeasureString($symbol, $fontSymbol)
                        $graphics.DrawString($symbol, $fontSymbol, $brushSymbol,
                            [single]($x + ($keySize - $size.Width) / 2),
                            [single]($y + ($keySize - $size.Height) / 2 + 3))
                    }

                    # 右下角：Ctrl（與 Ctrl+Shift）打出的中文標點。
                    $marks = @($punct, $punctShift) | Where-Object { $_ }
                    if ($marks) {
                        $text = $marks -join ""
                        $size = $graphics.MeasureString($text, $fontPunct)
                        $graphics.DrawString($text, $fontPunct, $brushPunct,
                            [single]($x + $keySize - $size.Width - 3),
                            [single]($y + $keySize - $size.Height - 1))
                    }
                    $x += $step
                }
                $y += $step
            }

            # 空白鍵不打出符號，而是補上隱含的一聲，所以單獨畫並註明。
            $spaceRect = New-Object System.Drawing.Rectangle(
                (10 + [int](3.3 * $step)), $y, (5 * $step - $gap), 34)
            $graphics.FillRectangle($brushFace, $spaceRect)
            $graphics.DrawRectangle($penEdge, $spaceRect)
            $text = "空白：補一聲／選第一個候選／無組字時送出空格"
            $size = $graphics.MeasureString($text, $fontPunct)
            $graphics.DrawString($text, $fontPunct, $brushAscii,
                [single]($spaceRect.X + ($spaceRect.Width - $size.Width) / 2),
                [single]($spaceRect.Y + ($spaceRect.Height - $size.Height) / 2))
        }.GetNewClosure())

        $legend = New-Object System.Windows.Forms.Label
        $legend.AutoSize = $true
        $legend.MaximumSize = New-Object System.Drawing.Size(880, 0)
        $legend.Margin = New-Object System.Windows.Forms.Padding(4, 6, 4, 4)
        $legend.Text = @"
每個鍵上：左上灰字＝英文模式輸出的字元、中央大字＝中文模式的注音、右下藍字＝Ctrl（以及 Ctrl+Shift）的中文標點；有標點的鍵底色偏藍。

Shift 一律輸出標準 ASCII，中文標點統一放在 Ctrl —— 這是為了不讓同一個實體按鍵在中英模式下語意不同。刻意偏離微軟的一處：「」放在 Ctrl+[ ]（微軟是 Ctrl+Shift+[ ]），代價是【】與｛｝沒有輸入法內的入口。

短按 Shift 切換中英；按住 Shift 打字母為暫時英文，並遵循大寫鎖定狀態。已知問題：命令列視窗裡短按 Shift 不會切換（見 HANDOVER.md 第 11 節）。

本頁唯讀。改鍵尚未實作。
"@

        $layout = New-Object System.Windows.Forms.TableLayoutPanel
        $layout.Dock = "Fill"
        $layout.ColumnCount = 1
        $layout.RowCount = 2
        $layout.AutoScroll = $true
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("Absolute", 340)))
        [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle("Percent", 100)))
        $layout.Controls.Add($canvas, 0, 0)
        $layout.Controls.Add($legend, 0, 1)
        $layout
    }.GetNewClosure()
}
