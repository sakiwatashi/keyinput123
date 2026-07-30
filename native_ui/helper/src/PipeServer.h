// Receives candidate updates from the Python input-method layer.
//
// This is a channel of our own, deliberately separate from PIME's transport.
// PIME's DLL-to-Python pipe is a strict request/response exchange with sequence
// validation that tears the connection down on any unexpected message, so the
// candidate mirror must never share it.

#ifndef SMARTPRIORITY_PIPE_SERVER_H
#define SMARTPRIORITY_PIPE_SERVER_H

#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <windows.h>

#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace SmartPriority {

// Posted to the UI thread whenever a newer update is available.
const UINT WM_CANDIDATE_UPDATE = WM_APP + 1;

struct CandidateUpdate {
    bool show = false;
    int selection = 0;
    std::vector<std::wstring> items;
};

class PipeServer {
public:
    PipeServer();
    ~PipeServer();

    bool start(const std::wstring& pipeName, HWND target);
    void stop();

    // Takes the most recent update. Bursts coalesce: only the newest state is
    // kept, because intermediate keystrokes have no value once superseded.
    bool takeLatest(CandidateUpdate& update);

private:
    void run(std::wstring pipeName, HWND target);
    void handleLine(const std::string& line, HWND target);

    std::thread worker_;
    std::mutex mutex_;
    CandidateUpdate latest_;
    bool hasUpdate_;
    volatile bool stopping_;
    HANDLE pipe_;
};

} // namespace SmartPriority

#endif
