# Create a stand-in for PIME's candidate window so the helper's beacon-following
# and z-order behaviour can be tested without typing in a real application.
#
# The fixture mimics the parts that matter: the LibImeWindow class name, the
# topmost / no-activate styles, a real screen position, and -- critically -- it
# re-asserts HWND_TOPMOST on a timer the way PIME does when candidates change on
# every keystroke. It paints solid red so any pixel of it left uncovered by the
# helper is obvious in a screenshot.
param(
    [int]$X = 700,
    [int]$Y = 500,
    [int]$Width = 300,
    [int]$Height = 160,
    [int]$Seconds = 25,
    [int]$ReassertMs = 150
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Threading;

public class FakeBeacon {
    delegate IntPtr WndProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    struct WNDCLASS {
        public uint style;
        public IntPtr lpfnWndProc;
        public int cbClsExtra;
        public int cbWndExtra;
        public IntPtr hInstance;
        public IntPtr hIcon;
        public IntPtr hCursor;
        public IntPtr hbrBackground;
        [MarshalAs(UnmanagedType.LPWStr)] public string lpszMenuName;
        [MarshalAs(UnmanagedType.LPWStr)] public string lpszClassName;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct MSG { public IntPtr hwnd; public uint message; public IntPtr wParam, lParam; public uint time; public int x, y; }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern ushort RegisterClassW(ref WNDCLASS c);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr CreateWindowExW(
        int exStyle, string cls, string name, int style, int x, int y, int w, int h,
        IntPtr parent, IntPtr menu, IntPtr inst, IntPtr param);
    [DllImport("user32.dll")] static extern IntPtr DefWindowProcW(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int hh, uint flags);
    [DllImport("user32.dll")] static extern int GetMessageW(out MSG m, IntPtr h, uint min, uint max);
    [DllImport("user32.dll")] static extern bool TranslateMessage(ref MSG m);
    [DllImport("user32.dll")] static extern IntPtr DispatchMessageW(ref MSG m);
    [DllImport("user32.dll")] static extern bool DestroyWindow(IntPtr h);
    [DllImport("gdi32.dll")] static extern IntPtr CreateSolidBrush(int color);
    [DllImport("kernel32.dll")] static extern IntPtr GetModuleHandleW(string n);

    static WndProc _proc;
    public static IntPtr Hwnd = IntPtr.Zero;

    public static void Run(int x, int y, int w, int h, int seconds, int reassertMs) {
        _proc = new WndProc(DefWindowProcW);
        IntPtr inst = GetModuleHandleW(null);
        WNDCLASS wc = new WNDCLASS();
        wc.lpfnWndProc = Marshal.GetFunctionPointerForDelegate(_proc);
        wc.hInstance = inst;
        wc.hbrBackground = CreateSolidBrush(0x0000FF); // BGR: solid red
        wc.lpszClassName = "LibImeWindow";
        RegisterClassW(ref wc);

        // WS_POPUP | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE
        Hwnd = CreateWindowExW(0x00000080 | 0x00000008 | 0x08000000,
            "LibImeWindow", "", unchecked((int)0x80000000),
            x, y, w, h, IntPtr.Zero, IntPtr.Zero, inst, IntPtr.Zero);
        ShowWindow(Hwnd, 5);
        SetWindowPos(Hwnd, new IntPtr(-1), x, y, w, h, 0x0010); // HWND_TOPMOST, SWP_NOACTIVATE

        // Re-assert topmost the way PIME does when candidates change per keystroke.
        var stop = DateTime.UtcNow.AddSeconds(seconds);
        var pump = new Thread(delegate() {
            while (DateTime.UtcNow < stop) {
                SetWindowPos(Hwnd, new IntPtr(-1), x, y, w, h, 0x0010);
                Thread.Sleep(reassertMs);
            }
            DestroyWindow(Hwnd);
        });
        pump.IsBackground = true;
        pump.Start();

        MSG msg;
        while (DateTime.UtcNow < stop && GetMessageW(out msg, IntPtr.Zero, 0, 0) > 0) {
            TranslateMessage(ref msg);
            DispatchMessageW(ref msg);
        }
    }
}
"@

Write-Host "Fake LibImeWindow at ($X,$Y) ${Width}x${Height}, re-asserting topmost every ${ReassertMs}ms for ${Seconds}s."
[FakeBeacon]::Run($X, $Y, $Width, $Height, $Seconds, $ReassertMs)
