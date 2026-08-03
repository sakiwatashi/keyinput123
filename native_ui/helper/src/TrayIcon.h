// A notification-area icon whose only job is to make the control panel
// reachable.
//
// The control panel shipped with a Start-menu shortcut and nothing else, and
// the user could not find it -- reasonably, since it sits inside a folder among
// other entries. An icon that appears while the input method is in use gives it
// somewhere obvious to live.
//
// This lives in the helper because the helper is the process that is already
// running whenever the input method is being used, and it already owns a window
// and a message loop. Adding a second background process for one icon would be
// worse.
#pragma once

#include <windows.h>
#include <shellapi.h>

#include <string>

class TrayIcon {
public:
    TrayIcon();
    ~TrayIcon();

    TrayIcon(const TrayIcon&) = delete;
    TrayIcon& operator=(const TrayIcon&) = delete;

    // Registers the icon. Failure is not fatal: the input method must keep
    // working on a desktop that refuses the notification area.
    bool add(HWND owner, UINT callbackMessage, const std::wstring& tooltip);
    void remove();

    // Handles the callback message. Returns true when the message was ours.
    bool handleMessage(HWND owner, WPARAM wp, LPARAM lp);

    // What a double-click or the menu's first item runs.
    void setControlPanelPath(const std::wstring& path) { controlPanelPath_ = path; }

private:
    void showMenu(HWND owner);
    void openControlPanel();

    NOTIFYICONDATAW data_;
    bool added_;
    UINT callbackMessage_;
    std::wstring controlPanelPath_;
};
