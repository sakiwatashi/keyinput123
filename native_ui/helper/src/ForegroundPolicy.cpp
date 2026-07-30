#include "ForegroundPolicy.h"

#include <string>

namespace SmartPriority {

namespace {

// Games whose anti-cheat is known to police what surrounds their process.
// The list is a convenience, not the main defence: the query rule below covers
// protected processes this list has never heard of.
const wchar_t* const kBlockedImages[] = {
    L"valorant.exe",
    L"valorant-win64-shipping.exe",
    L"riotclientservices.exe",
    L"fortniteclient-win64-shipping.exe",
    L"r5apex.exe",
    L"csgo.exe",
    L"cs2.exe",
    L"rainbowsix.exe",
    L"destiny2.exe",
    L"pubg.exe",
    L"tslgame.exe",
    L"deltaforceclient-win64-shipping.exe",
    L"naraka.exe",
};

std::wstring toLower(const std::wstring& text) {
    std::wstring lowered = text;
    for (size_t i = 0; i < lowered.size(); ++i)
        lowered[i] = static_cast<wchar_t>(::towlower(lowered[i]));
    return lowered;
}

std::wstring fileNameOf(const std::wstring& path) {
    size_t slash = path.find_last_of(L"\\/");
    return slash == std::wstring::npos ? path : path.substr(slash + 1);
}

} // namespace

bool processNameIsBlocked(const wchar_t* imageName) {
    if (imageName == nullptr)
        return true;
    std::wstring name = toLower(fileNameOf(imageName));
    if (name.empty())
        return true;
    for (size_t i = 0; i < sizeof(kBlockedImages) / sizeof(kBlockedImages[0]); ++i) {
        if (name == kBlockedImages[i])
            return true;
    }
    return false;
}

bool foregroundAllowsCandidateWindow() {
    HWND foreground = ::GetForegroundWindow();
    if (foreground == nullptr)
        return true; // No focused window at all; nothing to intrude upon.

    DWORD processId = 0;
    ::GetWindowThreadProcessId(foreground, &processId);
    if (processId == 0)
        return false;

    HANDLE process = ::OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, processId);
    if (process == nullptr) {
        // A foreground process we are not even allowed to name is the signature
        // of a protected or anti-cheat-guarded application. Staying out is the
        // conservative reading, and PIME's own window still serves the user.
        return false;
    }

    wchar_t imageName[MAX_PATH] = {0};
    DWORD size = MAX_PATH;
    BOOL queried = ::QueryFullProcessImageNameW(process, 0, imageName, &size);
    ::CloseHandle(process);
    if (!queried)
        return false;

    return !processNameIsBlocked(imageName);
}

} // namespace SmartPriority
