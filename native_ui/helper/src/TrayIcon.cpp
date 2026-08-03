#include "TrayIcon.h"

#include <shlwapi.h>
#include <strsafe.h>

namespace {

const UINT kIconId = 1;
const UINT kMenuOpenPanel = 0x3001;

// The panel is PowerShell, and WinForms needs STA. -WindowStyle Hidden keeps
// the console from flashing up behind the window.
const wchar_t* kPowerShellArgs =
    L"-NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File";

}  // namespace

TrayIcon::TrayIcon(): data_{}, added_(false), owner_(nullptr), callbackMessage_(0) {
}

TrayIcon::~TrayIcon() {
    remove();
}

bool TrayIcon::add(HWND owner, UINT callbackMessage, const std::wstring& tooltip) {
    if (added_)
        return true;

    callbackMessage_ = callbackMessage;
    owner_ = owner;
    tooltip_ = tooltip;
    data_ = {};
    data_.cbSize = sizeof(data_);
    data_.hWnd = owner;
    data_.uID = kIconId;
    data_.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    data_.uCallbackMessage = callbackMessage;

    // The helper has no icon resource of its own, so borrow the executable's.
    // Falling back to a stock icon keeps a missing resource from costing the
    // user the only obvious way into the control panel.
    data_.hIcon = static_cast<HICON>(::LoadImageW(
        ::GetModuleHandleW(nullptr), MAKEINTRESOURCEW(1), IMAGE_ICON,
        ::GetSystemMetrics(SM_CXSMICON), ::GetSystemMetrics(SM_CYSMICON),
        LR_DEFAULTCOLOR));
    if (data_.hIcon == nullptr)
        data_.hIcon = ::LoadIconW(nullptr, IDI_APPLICATION);

    ::StringCchCopyW(data_.szTip, ARRAYSIZE(data_.szTip), tooltip.c_str());

    added_ = ::Shell_NotifyIconW(NIM_ADD, &data_) != FALSE;
    return added_;
}

void TrayIcon::remove() {
    if (!added_)
        return;
    ::Shell_NotifyIconW(NIM_DELETE, &data_);
    added_ = false;
}

UINT TrayIcon::taskbarCreatedMessage() {
    // Registered once per process; the value is stable for the session.
    static const UINT message = ::RegisterWindowMessageW(L"TaskbarCreated");
    return message;
}

void TrayIcon::reAdd() {
    // Explorer has thrown the old icon away, so forget it and register again.
    added_ = false;
    if (owner_ != nullptr)
        add(owner_, callbackMessage_, tooltip_);
}

bool TrayIcon::handleMessage(HWND owner, WPARAM wp, LPARAM lp) {
    if (wp != kIconId)
        return false;

    switch (LOWORD(lp)) {
    case WM_LBUTTONDBLCLK:
        openControlPanel();
        return true;
    case WM_RBUTTONUP:
    case WM_CONTEXTMENU:
        showMenu(owner);
        return true;
    default:
        return true;
    }
}

void TrayIcon::showMenu(HWND owner) {
    HMENU menu = ::CreatePopupMenu();
    if (menu == nullptr)
        return;
    ::AppendMenuW(menu, MF_STRING, kMenuOpenPanel, L"開啟控制台(&O)");

    POINT cursor = {};
    ::GetCursorPos(&cursor);
    // Required so the menu closes when the user clicks elsewhere; without it
    // a tray menu can be left stranded on screen.
    ::SetForegroundWindow(owner);
    UINT choice = static_cast<UINT>(::TrackPopupMenu(
        menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
        cursor.x, cursor.y, 0, owner, nullptr));
    ::DestroyMenu(menu);

    if (choice == kMenuOpenPanel)
        openControlPanel();
}

void TrayIcon::openControlPanel() {
    if (controlPanelPath_.empty())
        return;

    std::wstring parameters = kPowerShellArgs;
    parameters += L" \"";
    parameters += controlPanelPath_;
    parameters += L"\"";

    // ShellExecute rather than CreateProcess: the panel is a user-facing
    // application, and this keeps it running under the user's own shell
    // context rather than inheriting the helper's.
    ::ShellExecuteW(nullptr, L"open", L"powershell.exe", parameters.c_str(),
                    nullptr, SW_SHOWNORMAL);
}
