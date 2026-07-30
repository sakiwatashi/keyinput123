# Watch PIME's candidate window while the user types.
#
# The out-of-process candidate UI design uses PIME's own candidate window as a
# position beacon. This records whether that window appears, where it is, and
# how big it gets, so the beacon assumption can be checked against reality
# before any of the design is implemented.
#
# Usage: run it, then type Bopomofo in any app until candidates appear.
param(
    [int]$Seconds = 60,
    [int]$PollMs = 80
)

if (-not ("CandWatch" -as [type])) {
Add-Type @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential)]
public struct WRECT { public int left, top, right, bottom; }

public static class CandWatch {
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll")] static extern int GetClassName(IntPtr h, StringBuilder s, int max);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out WRECT r);
    [DllImport("user32.dll")] static extern int GetWindowThreadProcessId(IntPtr h, out int procId);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();

    public class Found {
        public long Hwnd; public int Pid; public bool Visible;
        public int Left, Top, Width, Height;
    }

    public static List<Found> Scan() {
        var list = new List<Found>();
        EnumWindows((h, l) => {
            var sb = new StringBuilder(64);
            GetClassName(h, sb, 64);
            if (sb.ToString() == "LibImeWindow") {
                WRECT r; GetWindowRect(h, out r);
                int procId; GetWindowThreadProcessId(h, out procId);
                list.Add(new Found {
                    Hwnd = h.ToInt64(), Pid = procId, Visible = IsWindowVisible(h),
                    Left = r.left, Top = r.top,
                    Width = r.right - r.left, Height = r.bottom - r.top
                });
            }
            return true;
        }, IntPtr.Zero);
        return list;
    }
}
"@
}

Write-Host "監看 PIME 候選視窗 $Seconds 秒 —— 請在任何程式裡打注音直到候選框出現。" -ForegroundColor Cyan
Write-Host "(按 Ctrl+C 可提前結束)`n" -ForegroundColor DarkGray

$deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
$seen = @{}
$events = 0

while ([DateTime]::UtcNow -lt $deadline) {
    foreach ($w in [CandWatch]::Scan()) {
        # Fingerprint position+size so only real changes are reported.
        $key = "$($w.Hwnd)"
        $state = "$($w.Visible)|$($w.Left),$($w.Top)|$($w.Width)x$($w.Height)"
        if ($seen[$key] -ne $state) {
            $seen[$key] = $state
            $events++
            $procName = try { (Get-Process -Id $w.Pid -ErrorAction Stop).ProcessName } catch { '?' }
            $stamp = [DateTime]::Now.ToString('HH:mm:ss.fff')
            $vis = if ($w.Visible) { "顯示" } else { "隱藏" }
            Write-Host ("[{0}] {1,-6} 位置=({2},{3}) 尺寸={4}x{5} 行程={6} hwnd=0x{7:X}" -f `
                $stamp, $vis, $w.Left, $w.Top, $w.Width, $w.Height, $procName, $w.Hwnd)
        }
    }
    Start-Sleep -Milliseconds $PollMs
}

Write-Host "`n共記錄 $events 次狀態變化。" -ForegroundColor Cyan
if ($events -eq 0) {
    Write-Host "沒有觀察到任何 LibImeWindow —— 表示監看期間候選框未曾出現。" -ForegroundColor Yellow
}
