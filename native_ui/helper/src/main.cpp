// Smart Priority Bopomofo out-of-process candidate window.
//
// This executable never loads into another application. It draws the
// Japanese-inspired vertical-first candidate grid in its own process and
// anchors itself to the position PIME's signed in-process DLL already computed
// from TSF, so no unsigned code has to enter a game or any other host process.
//
// Milestone 1 scope: locate the beacon window and render over it. Candidate
// content still comes from the command line; the named pipe fed by the Python
// layer arrives in the next milestone.

#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef UNICODE
#define UNICODE
#endif

#include "CandidateRenderer.h"
#include "PipeServer.h"

#include <windows.h>
#include <shellapi.h>

#include <string>
#include <vector>

namespace {

using SmartPriority::CandidateRenderer;

const wchar_t kWindowClass[] = L"SmartPriorityCandidateWindow";
const wchar_t kBeaconClass[] = L"LibImeWindow";
const wchar_t kSelectionKeys[] = L"1234567890";
const wchar_t kPipeName[] = L"\\\\.\\pipe\\SmartPriorityBopomofo.CandidateUI";

// Every application that accepts text gets its own text-service instance, so
// several of them may try to launch the helper at once. A session-local mutex
// makes the extra launches exit immediately instead of fighting over the pipe.
const wchar_t kInstanceMutex[] = L"Local\\SmartPriorityBopomofo.CandidateUI";
const UINT_PTR kPollTimerId = 1;
const UINT_PTR kTopmostTimerId = 2;

// Measured: a beacon that re-asserts HWND_TOPMOST on its own schedule can sit
// above us between our syncs, because a re-assert that changes neither position
// nor size raises no EVENT_OBJECT_LOCATIONCHANGE for the hook to catch. This
// cheap reassertion keeps the grid on top without polling for the beacon.
const UINT kTopmostIntervalMs = 60;

struct Beacon {
    HWND hwnd = nullptr;
    RECT rect = {0, 0, 0, 0};
};

struct AppState {
    HWND hwnd = nullptr;
    HFONT font = nullptr;
    CandidateRenderer renderer;
    bool demoMode = false;
    POINT demoOrigin = {0, 0};
    Beacon beacon;
    bool visible = false;
    // Once beacon mode is on, the real candidate list exists only here. If the
    // beacon momentarily cannot be found while candidates are still active,
    // holding the last known anchor is far better than showing nothing.
    POINT lastAnchor = {0, 0};
    bool hasLastAnchor = false;
    SmartPriority::PipeServer pipe;
    // Until the Python layer has sent something, the window stays hidden rather
    // than showing stale placeholder text over a real composition.
    bool hasCandidates = false;
};

AppState g_state;

// Selects the real candidate window among the several LibImeWindow instances
// PIME keeps alive. Measured behavior: the candidate window carries a genuine
// screen position, while message and freshly-created windows sit at (0,0).
// Filtering on position rather than size matters, because in beacon mode the
// candidate window is deliberately shrunk to a few pixels.
BOOL CALLBACK enumBeacon(HWND hwnd, LPARAM lparam) {
    wchar_t className[64] = {0};
    if (::GetClassNameW(hwnd, className, 64) == 0)
        return TRUE;
    if (::wcscmp(className, kBeaconClass) != 0)
        return TRUE;
    if (!::IsWindowVisible(hwnd))
        return TRUE;

    RECT rect = {0, 0, 0, 0};
    if (!::GetWindowRect(hwnd, &rect))
        return TRUE;
    if (rect.left == 0 && rect.top == 0)
        return TRUE;

    Beacon* found = reinterpret_cast<Beacon*>(lparam);
    found->hwnd = hwnd;
    found->rect = rect;
    return FALSE;
}

bool findBeacon(Beacon& beacon) {
    Beacon found;
    ::EnumWindows(enumBeacon, reinterpret_cast<LPARAM>(&found));
    beacon = found;
    return found.hwnd != nullptr;
}

int windowDpi(HWND hwnd) {
    // GetDpiForWindow keeps a secondary monitor with a different scale correct;
    // the original in-process code sampled the primary screen instead.
    typedef UINT(WINAPI * GetDpiForWindowFn)(HWND);
    static GetDpiForWindowFn getDpiForWindow = reinterpret_cast<GetDpiForWindowFn>(
        ::GetProcAddress(::GetModuleHandleW(L"user32.dll"), "GetDpiForWindow"));
    if (getDpiForWindow != nullptr) {
        UINT dpi = getDpiForWindow(hwnd);
        if (dpi > 0)
            return static_cast<int>(dpi);
    }
    HDC screen = ::GetDC(nullptr);
    int dpi = screen ? ::GetDeviceCaps(screen, LOGPIXELSX) : 96;
    if (screen)
        ::ReleaseDC(nullptr, screen);
    return dpi;
}

void rebuildFont(AppState& state) {
    if (state.font != nullptr) {
        ::DeleteObject(state.font);
        state.font = nullptr;
    }
    int dpi = windowDpi(state.hwnd);
    state.renderer.setDpi(dpi);

    LOGFONTW lf = {0};
    lf.lfHeight = -::MulDiv(16, dpi, 72);
    lf.lfWeight = FW_NORMAL;
    lf.lfCharSet = DEFAULT_CHARSET;
    lf.lfQuality = CLEARTYPE_QUALITY;
    ::wcsncpy_s(lf.lfFaceName, L"Microsoft JhengHei UI", _TRUNCATE);
    state.font = ::CreateFontIndirectW(&lf);
}

// Keeps the popup fully on the monitor that contains its anchor.
void clampToMonitor(POINT anchor, SIZE size, POINT& origin) {
    HMONITOR monitor = ::MonitorFromPoint(anchor, MONITOR_DEFAULTTONEAREST);
    MONITORINFO info = {0};
    info.cbSize = sizeof(info);
    if (!::GetMonitorInfoW(monitor, &info))
        return;
    if (origin.x + size.cx > info.rcWork.right)
        origin.x = info.rcWork.right - size.cx;
    if (origin.y + size.cy > info.rcWork.bottom)
        origin.y = info.rcWork.bottom - size.cy;
    if (origin.x < info.rcWork.left)
        origin.x = info.rcWork.left;
    if (origin.y < info.rcWork.top)
        origin.y = info.rcWork.top;
}

void layoutAndShow(AppState& state, POINT anchor, const RECT* coverRect) {
    HDC hdc = ::GetDC(state.hwnd);
    HGDIOBJ oldFont = ::SelectObject(hdc, state.font);
    SIZE size = state.renderer.measure(hdc);
    ::SelectObject(hdc, oldFont);
    ::ReleaseDC(state.hwnd, hdc);

    // Fully cover the beacon so no stock row-major content can peek out.
    if (coverRect != nullptr) {
        long coverWidth = coverRect->right - coverRect->left;
        long coverHeight = coverRect->bottom - coverRect->top;
        if (coverWidth > size.cx)
            size.cx = coverWidth;
        if (coverHeight > size.cy)
            size.cy = coverHeight;
    }

    POINT origin = anchor;
    clampToMonitor(anchor, size, origin);

    ::SetWindowPos(state.hwnd, HWND_TOPMOST, origin.x, origin.y, size.cx, size.cy,
                   SWP_NOACTIVATE | SWP_SHOWWINDOW);

    HRGN region = ::CreateRoundRectRgn(0, 0, size.cx + 1, size.cy + 1,
                                       ::MulDiv(12, windowDpi(state.hwnd), 96),
                                       ::MulDiv(12, windowDpi(state.hwnd), 96));
    if (!::SetWindowRgn(state.hwnd, region, TRUE))
        ::DeleteObject(region);

    ::InvalidateRect(state.hwnd, nullptr, TRUE);
    state.visible = true;
}

void hideWindow(AppState& state) {
    if (!state.visible)
        return;
    ::ShowWindow(state.hwnd, SW_HIDE);
    state.visible = false;
}

void syncToBeacon(AppState& state) {
    if (state.demoMode)
        return;
    if (!state.hasCandidates) {
        hideWindow(state);
        return;
    }

    Beacon beacon;
    if (!findBeacon(beacon)) {
        state.beacon = Beacon();
        if (state.hasLastAnchor) {
            // Candidates are still live, so keep them readable at the last
            // known position rather than blanking the only copy on screen.
            layoutAndShow(state, state.lastAnchor, nullptr);
        } else {
            hideWindow(state);
        }
        return;
    }

    // The beacon is recreated per composition, so its handle must never be
    // cached across appearances.
    state.beacon = beacon;
    POINT anchor = {beacon.rect.left, beacon.rect.top};
    state.lastAnchor = anchor;
    state.hasLastAnchor = true;
    layoutAndShow(state, anchor, &beacon.rect);
}

void onPaint(AppState& state) {
    PAINTSTRUCT ps;
    HDC hdc = ::BeginPaint(state.hwnd, &ps);

    RECT client;
    ::GetClientRect(state.hwnd, &client);

    // Double-buffer so rapid candidate changes stay flicker-free.
    HDC memoryDc = ::CreateCompatibleDC(hdc);
    HBITMAP bitmap = ::CreateCompatibleBitmap(hdc, client.right - client.left,
                                              client.bottom - client.top);
    HGDIOBJ oldBitmap = ::SelectObject(memoryDc, bitmap);
    HGDIOBJ oldFont = ::SelectObject(memoryDc, state.font);

    state.renderer.paint(memoryDc, client);

    ::BitBlt(hdc, 0, 0, client.right, client.bottom, memoryDc, 0, 0, SRCCOPY);

    ::SelectObject(memoryDc, oldFont);
    ::SelectObject(memoryDc, oldBitmap);
    ::DeleteObject(bitmap);
    ::DeleteDC(memoryDc);
    ::EndPaint(state.hwnd, &ps);
}

LRESULT CALLBACK wndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_PAINT:
        onPaint(g_state);
        return 0;
    case WM_ERASEBKGND:
        return TRUE;
    case WM_MOUSEACTIVATE:
        return MA_NOACTIVATE;
    case WM_TIMER:
        if (wp == kPollTimerId) {
            syncToBeacon(g_state);
        } else if (wp == kTopmostTimerId && g_state.visible) {
            ::SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                           SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        }
        return 0;
    case SmartPriority::WM_CANDIDATE_UPDATE: {
        SmartPriority::CandidateUpdate update;
        if (!g_state.pipe.takeLatest(update))
            return 0;
        if (!update.show || update.items.empty()) {
            g_state.hasCandidates = false;
            // The composition ended, so the remembered anchor is stale and
            // must not resurrect the window on the next beacon event.
            g_state.hasLastAnchor = false;
            hideWindow(g_state);
            return 0;
        }
        g_state.renderer.setCandidates(update.items, kSelectionKeys);
        g_state.renderer.setSelection(update.selection);
        g_state.hasCandidates = true;
        syncToBeacon(g_state);
        return 0;
    }
    case WM_DPICHANGED:
        rebuildFont(g_state);
        ::InvalidateRect(hwnd, nullptr, TRUE);
        return 0;
    case WM_DESTROY:
        ::PostQuitMessage(0);
        return 0;
    default:
        break;
    }
    return ::DefWindowProcW(hwnd, msg, wp, lp);
}

void CALLBACK winEventProc(HWINEVENTHOOK, DWORD, HWND hwnd, LONG idObject,
                           LONG, DWORD, DWORD) {
    if (idObject != OBJID_WINDOW || hwnd == nullptr)
        return;
    wchar_t className[64] = {0};
    if (::GetClassNameW(hwnd, className, 64) == 0)
        return;
    if (::wcscmp(className, kBeaconClass) != 0)
        return;
    syncToBeacon(g_state);
}

std::vector<std::wstring> parseCandidates(const std::wstring& joined) {
    std::vector<std::wstring> items;
    size_t start = 0;
    while (start <= joined.size()) {
        size_t separator = joined.find(L',', start);
        if (separator == std::wstring::npos) {
            if (start < joined.size())
                items.push_back(joined.substr(start));
            break;
        }
        items.push_back(joined.substr(start, separator - start));
        start = separator + 1;
    }
    return items;
}

} // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, LPWSTR, int) {
    typedef BOOL(WINAPI * SetContextFn)(HANDLE);
    SetContextFn setDpiContext = reinterpret_cast<SetContextFn>(::GetProcAddress(
        ::GetModuleHandleW(L"user32.dll"), "SetProcessDpiAwarenessContext"));
    if (setDpiContext != nullptr)
        setDpiContext(reinterpret_cast<HANDLE>(-4)); // PER_MONITOR_AWARE_V2

    std::vector<std::wstring> candidates;
    int argc = 0;
    LPWSTR* argv = ::CommandLineToArgvW(::GetCommandLineW(), &argc);
    for (int i = 1; i < argc; ++i) {
        std::wstring argument = argv[i];
        if (argument == L"--demo") {
            g_state.demoMode = true;
            g_state.demoOrigin.x = 400;
            g_state.demoOrigin.y = 400;
        } else if (argument.rfind(L"--candidates=", 0) == 0) {
            candidates = parseCandidates(argument.substr(13));
        }
    }
    if (argv != nullptr)
        ::LocalFree(argv);

    // Placeholder content exists only for --demo. In follow mode the window
    // stays empty until the Python layer sends the real candidates.
    if (g_state.demoMode && candidates.empty()) {
        candidates = {L"你好", L"妳好", L"擬好", L"你號", L"泥好",
                      L"你耗", L"匿好", L"你郝", L"倪好", L"你好嗎"};
    }

    // --demo stays freely runnable for visual checks even while the real
    // helper is live, so only follow mode takes the single-instance lock.
    HANDLE instanceLock = nullptr;
    if (!g_state.demoMode) {
        instanceLock = ::CreateMutexW(nullptr, TRUE, kInstanceMutex);
        if (instanceLock == nullptr || ::GetLastError() == ERROR_ALREADY_EXISTS)
            return 0;
    }

    WNDCLASSEXW wc = {0};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = wndProc;
    wc.hInstance = instance;
    wc.hCursor = ::LoadCursor(nullptr, IDC_ARROW);
    wc.lpszClassName = kWindowClass;
    if (::RegisterClassExW(&wc) == 0)
        return 1;

    g_state.hwnd = ::CreateWindowExW(
        WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE,
        kWindowClass, L"", WS_POPUP | WS_CLIPCHILDREN,
        0, 0, 10, 10, nullptr, nullptr, instance, nullptr);
    if (g_state.hwnd == nullptr)
        return 1;

    rebuildFont(g_state);
    g_state.renderer.setCandidates(candidates, kSelectionKeys);
    g_state.renderer.setCandPerRow(2);
    g_state.renderer.setSelection(0);

    if (g_state.demoMode) {
        g_state.hasCandidates = true;
        layoutAndShow(g_state, g_state.demoOrigin, nullptr);
    } else {
        g_state.pipe.start(kPipeName, g_state.hwnd);
        HWINEVENTHOOK hook = ::SetWinEventHook(
            EVENT_OBJECT_SHOW, EVENT_OBJECT_LOCATIONCHANGE, nullptr,
            winEventProc, 0, 0, WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS);
        // A slow timer is a safety net for events the hook may coalesce; the
        // hook remains the primary trigger.
        ::SetTimer(g_state.hwnd, kPollTimerId, 250, nullptr);
        ::SetTimer(g_state.hwnd, kTopmostTimerId, kTopmostIntervalMs, nullptr);
        syncToBeacon(g_state);
        (void)hook;
    }

    MSG msg;
    while (::GetMessageW(&msg, nullptr, 0, 0) > 0) {
        ::TranslateMessage(&msg);
        ::DispatchMessageW(&msg);
    }

    g_state.pipe.stop();
    if (g_state.font != nullptr)
        ::DeleteObject(g_state.font);
    if (instanceLock != nullptr) {
        ::ReleaseMutex(instanceLock);
        ::CloseHandle(instanceLock);
    }
    return 0;
}
