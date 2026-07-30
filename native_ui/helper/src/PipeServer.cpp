#include "PipeServer.h"

namespace SmartPriority {

namespace {

const char kFieldSeparator = '\x1f';

// Length-prefix-free framing: candidates are natural-language text and never
// contain control characters, so a unit separator needs no escaping.
std::vector<std::string> splitFields(const std::string& line) {
    std::vector<std::string> fields;
    size_t start = 0;
    while (true) {
        size_t separator = line.find(kFieldSeparator, start);
        if (separator == std::string::npos) {
            fields.push_back(line.substr(start));
            break;
        }
        fields.push_back(line.substr(start, separator - start));
        start = separator + 1;
    }
    return fields;
}

std::wstring fromUtf8(const std::string& text) {
    if (text.empty())
        return std::wstring();
    int needed = ::MultiByteToWideChar(CP_UTF8, 0, text.data(),
                                       static_cast<int>(text.size()), nullptr, 0);
    if (needed <= 0)
        return std::wstring();
    std::wstring wide(static_cast<size_t>(needed), L'\0');
    ::MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()),
                          &wide[0], needed);
    return wide;
}

} // namespace

PipeServer::PipeServer():
    hasUpdate_(false),
    stopping_(false),
    pipe_(INVALID_HANDLE_VALUE) {
}

PipeServer::~PipeServer() {
    stop();
}

bool PipeServer::start(const std::wstring& pipeName, HWND target) {
    stopping_ = false;
    worker_ = std::thread(&PipeServer::run, this, pipeName, target);
    return true;
}

void PipeServer::stop() {
    stopping_ = true;
    HANDLE pipe = pipe_;
    if (pipe != INVALID_HANDLE_VALUE) {
        // Unblocks a worker parked in ConnectNamedPipe or ReadFile.
        ::CancelIoEx(pipe, nullptr);
        ::CloseHandle(pipe);
        pipe_ = INVALID_HANDLE_VALUE;
    }
    if (worker_.joinable())
        worker_.join();
}

bool PipeServer::takeLatest(CandidateUpdate& update) {
    std::lock_guard<std::mutex> guard(mutex_);
    if (!hasUpdate_)
        return false;
    update = latest_;
    hasUpdate_ = false;
    return true;
}

void PipeServer::handleLine(const std::string& line, HWND target) {
    if (line.empty())
        return;

    std::vector<std::string> fields = splitFields(line);
    CandidateUpdate update;
    if (fields[0] == "HIDE") {
        update.show = false;
    } else if (fields[0] == "SHOW" && fields.size() >= 2) {
        update.show = true;
        update.selection = std::atoi(fields[1].c_str());
        for (size_t i = 2; i < fields.size(); ++i)
            update.items.push_back(fromUtf8(fields[i]));
    } else {
        return;
    }

    {
        std::lock_guard<std::mutex> guard(mutex_);
        latest_ = update;
        hasUpdate_ = true;
    }
    ::PostMessageW(target, WM_CANDIDATE_UPDATE, 0, 0);
}

void PipeServer::run(std::wstring pipeName, HWND target) {
    std::string pending;

    while (!stopping_) {
        HANDLE pipe = ::CreateNamedPipeW(
            pipeName.c_str(),
            PIPE_ACCESS_INBOUND,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
            1,          // one writer: the Python input-method layer
            0, 4096,
            0,
            nullptr);   // default DACL restricts the pipe to this user
        if (pipe == INVALID_HANDLE_VALUE) {
            ::Sleep(200);
            continue;
        }
        pipe_ = pipe;

        BOOL connected = ::ConnectNamedPipe(pipe, nullptr)
            ? TRUE
            : (::GetLastError() == ERROR_PIPE_CONNECTED);
        if (connected) {
            pending.clear();
            char buffer[1024];
            DWORD read = 0;
            while (!stopping_ && ::ReadFile(pipe, buffer, sizeof(buffer), &read, nullptr) && read > 0) {
                pending.append(buffer, read);
                size_t newline = pending.find('\n');
                while (newline != std::string::npos) {
                    std::string line = pending.substr(0, newline);
                    if (!line.empty() && line.back() == '\r')
                        line.pop_back();
                    handleLine(line, target);
                    pending.erase(0, newline + 1);
                    newline = pending.find('\n');
                }
            }
        }

        if (pipe_ != INVALID_HANDLE_VALUE) {
            ::DisconnectNamedPipe(pipe);
            ::CloseHandle(pipe);
            pipe_ = INVALID_HANDLE_VALUE;
        }
    }
}

} // namespace SmartPriority
