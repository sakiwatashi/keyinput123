# Probe how a separate process can locate the text caret of another app.
# Compares the two strategies available to an out-of-process candidate window:
#   1. GetGUIThreadInfo       - cheap, classic Win32 caret
#   2. UI Automation TextPattern - broad app support, higher cost
#
# Both APIs work against a target thread/window without stealing focus, so this
# probes real apps without fighting the window manager.
param([string[]]$Process = @())

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

if (-not ("CaretProbe" -as [type])) {
Add-Type @"
using System;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential)]
public struct RECT { public int left, top, right, bottom; }

[StructLayout(LayoutKind.Sequential)]
public struct GUITHREADINFO {
    public int cbSize;
    public int flags;
    public IntPtr hwndActive, hwndFocus, hwndCapture, hwndMenuOwner, hwndMoveSize, hwndCaret;
    public RECT rcCaret;
}

public static class CaretProbe {
    [DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(IntPtr hWnd, out int procId);
    [DllImport("user32.dll")] public static extern bool GetGUIThreadInfo(int idThread, ref GUITHREADINFO lpgui);
}
"@
}

function Probe-Target {
    param([string]$Name, [IntPtr]$Hwnd)

    $procId = 0
    $tid = [CaretProbe]::GetWindowThreadProcessId($Hwnd, [ref]$procId)
    $result = [ordered]@{ App = $Name; Hwnd = ("0x{0:X}" -f $Hwnd.ToInt64()) }

    # --- Strategy 1: GetGUIThreadInfo against the target's UI thread ---
    $gti = New-Object GUITHREADINFO
    $gti.cbSize = [Runtime.InteropServices.Marshal]::SizeOf([type]'GUITHREADINFO')
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $ok = [CaretProbe]::GetGUIThreadInfo($tid, [ref]$gti)
    $sw.Stop()
    $result.GTI_ms = [math]::Round($sw.Elapsed.TotalMilliseconds, 1)
    if (-not $ok) {
        $result.GUIThreadInfo = "CALL FAILED"
    } elseif ($gti.hwndCaret -eq [IntPtr]::Zero) {
        $result.GUIThreadInfo = "NO CARET (app has no classic caret)"
    } else {
        $h = $gti.rcCaret.bottom - $gti.rcCaret.top
        $result.GUIThreadInfo = "OK caret client-rect=($($gti.rcCaret.left),$($gti.rcCaret.top)) h=$h"
    }

    # --- Strategy 2: UI Automation TextPattern on the target window tree ---
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $root = [System.Windows.Automation.AutomationElement]::FromHandle($Hwnd)
        if ($null -eq $root) {
            $result.UIA = "FromHandle returned null"
        } else {
            # Find the first descendant exposing TextPattern.
            $cond = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::IsTextPatternAvailableProperty, $true)
            $el = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
            if ($null -eq $el) {
                $result.UIA = "no element exposes TextPattern"
            } else {
                $pattern = $null
                $tp = [System.Windows.Automation.TextPattern]::Pattern
                if ($el.TryGetCurrentPattern($tp, [ref]$pattern)) {
                    $sel = $pattern.GetSelection()
                    $bb = $el.Current.BoundingRectangle
                    if ($sel -and $sel.Count -gt 0) {
                        $rects = $sel[0].GetBoundingRectangles()
                        if ($rects -and $rects.Count -gt 0) {
                            $r = $rects[0]
                            $result.UIA = "OK selection-rect=($([int]$r.X),$([int]$r.Y)) $([int]$r.Width)x$([int]$r.Height)"
                        } else {
                            # A collapsed caret reports no rectangles. The element
                            # box is still a usable anchor for the popup.
                            $result.UIA = "OK(collapsed caret) element=($([int]$bb.X),$([int]$bb.Y)) $([int]$bb.Width)x$([int]$bb.Height)"
                        }
                    } else {
                        $result.UIA = "TextPattern present, no selection; element=($([int]$bb.X),$([int]$bb.Y))"
                    }
                } else { $result.UIA = "TryGetCurrentPattern failed" }
            }
        }
    } catch { $result.UIA = "ERROR: $($_.Exception.Message)" }
    $sw.Stop()
    $result.UIA_ms = [math]::Round($sw.Elapsed.TotalMilliseconds, 1)

    [pscustomobject]$result
}

$targets = if ($Process.Count -gt 0) {
    Get-Process -Name $Process -ErrorAction SilentlyContinue
} else {
    Get-Process | Where-Object { $_.MainWindowHandle -ne 0 }
}

$targets | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
    Probe-Target -Name $_.ProcessName -Hwnd $_.MainWindowHandle
}
