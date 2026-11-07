// HTTP through WinHTTP. One session for the whole program, so its connection
// pool is shared by every worker thread.

#include "core/http.h"
#include "version.h"

#include <windows.h>
#include <winhttp.h>

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <mutex>
#include <vector>

namespace {

std::wstring Wide(const std::string& s) {
    if (s.empty()) return std::wstring();
    int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), nullptr, 0);
    std::wstring out(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), out.data(), n);
    return out;
}

std::string Narrow(const std::wstring& s) {
    if (s.empty()) return std::string();
    int n = WideCharToMultiByte(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), nullptr, 0, nullptr, nullptr);
    std::string out(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), out.data(), n, nullptr, nullptr);
    return out;
}

HINTERNET Session() {
    static HINTERNET session = [] {
        HINTERNET h = WinHttpOpen(Wide(UserAgent()).c_str(), WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
                                  WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
        if (!h) {
            // Before Windows 8.1 there is no automatic proxy type.
            h = WinHttpOpen(Wide(UserAgent()).c_str(), WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                            WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
        }
        if (h) {
            DWORD protocols = WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2;
#ifdef WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_3
            protocols |= WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_3;
#endif
            if (!WinHttpSetOption(h, WINHTTP_OPTION_SECURE_PROTOCOLS, &protocols, sizeof(protocols))) {
                protocols = WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2;
                WinHttpSetOption(h, WINHTTP_OPTION_SECURE_PROTOCOLS, &protocols, sizeof(protocols));
            }
        }
        return h;
    }();
    return session;
}

std::string SystemMessage(DWORD error) {
    wchar_t* text = nullptr;
    HMODULE module = GetModuleHandleW(L"winhttp.dll");
    DWORD flags = FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_IGNORE_INSERTS | FORMAT_MESSAGE_FROM_SYSTEM |
                  (module ? FORMAT_MESSAGE_FROM_HMODULE : 0);
    FormatMessageW(flags, module, error, 0, reinterpret_cast<wchar_t*>(&text), 0, nullptr);
    std::string message = text ? Narrow(text) : "Network error " + std::to_string(error);
    if (text) LocalFree(text);
    while (!message.empty() && (message.back() == '\n' || message.back() == '\r' || message.back() == ' '))
        message.pop_back();
    return message;
}

struct Handle {
    HINTERNET h = nullptr;
    ~Handle() {
        if (h) WinHttpCloseHandle(h);
    }
};

void ParseHeaders(const std::wstring& raw, HttpResponse& response) {
    std::string text = Narrow(raw);
    size_t pos = 0;
    while (pos < text.size()) {
        size_t end = text.find("\r\n", pos);
        if (end == std::string::npos) end = text.size();
        std::string line = text.substr(pos, end - pos);
        pos = end + 2;
        size_t colon = line.find(':');
        if (colon == std::string::npos) continue;
        std::string name = line.substr(0, colon);
        std::transform(name.begin(), name.end(), name.begin(), [](unsigned char c) { return std::tolower(c); });
        size_t start = line.find_first_not_of(" \t", colon + 1);
        response.headers[name] = start == std::string::npos ? "" : line.substr(start);
    }
}

}  // namespace

const std::string& UserAgent() {
    static const std::string agent = std::string(APP_NAME "/") + APP_VERSION;
    return agent;
}

std::string UrlEncode(const std::string& value) {
    static const char* hex = "0123456789ABCDEF";
    std::string out;
    out.reserve(value.size() * 3);
    for (unsigned char c : value) {
        if (std::isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
            out += static_cast<char>(c);
        } else {
            out += '%';
            out += hex[c >> 4];
            out += hex[c & 15];
        }
    }
    return out;
}

HttpResponse HttpSend(const HttpRequest& request) {
    HttpResponse response;
    HINTERNET session = Session();
    if (!session) {
        response.error = SystemMessage(GetLastError());
        return response;
    }

    std::wstring url = Wide(request.url);
    URL_COMPONENTS parts = {sizeof(parts)};
    wchar_t host[256] = {0};
    std::vector<wchar_t> path(url.size() + 1);
    parts.lpszHostName = host;
    parts.dwHostNameLength = 256;
    parts.lpszUrlPath = path.data();
    parts.dwUrlPathLength = static_cast<DWORD>(path.size());
    if (!WinHttpCrackUrl(url.c_str(), 0, 0, &parts)) {
        response.error = "Invalid address: " + request.url;
        return response;
    }
    // The path component includes the query when no separate buffer is given for it.

    Handle connection{WinHttpConnect(session, host, parts.nPort, 0)};
    if (!connection.h) {
        response.error = SystemMessage(GetLastError());
        return response;
    }
    DWORD flags = parts.nScheme == INTERNET_SCHEME_HTTPS ? WINHTTP_FLAG_SECURE : 0;
    Handle req{WinHttpOpenRequest(connection.h, Wide(request.method).c_str(), path.data(), nullptr,
                                  WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, flags)};
    if (!req.h) {
        response.error = SystemMessage(GetLastError());
        return response;
    }

    int timeout = request.timeoutMs ? static_cast<int>(request.timeoutMs) : 30000;
    WinHttpSetTimeouts(req.h, timeout, timeout, timeout, timeout);
    if (!request.followRedirects) {
        DWORD policy = WINHTTP_OPTION_REDIRECT_POLICY_NEVER;
        WinHttpSetOption(req.h, WINHTTP_OPTION_REDIRECT_POLICY, &policy, sizeof(policy));
    }
#ifdef WINHTTP_OPTION_DECOMPRESSION
    DWORD decompression = WINHTTP_DECOMPRESSION_FLAG_ALL;  // Windows 8.1 and later; harmless before
    WinHttpSetOption(req.h, WINHTTP_OPTION_DECOMPRESSION, &decompression, sizeof(decompression));
#endif

    std::wstring headers;
    for (const auto& header : request.headers) headers += Wide(header) + L"\r\n";
    if (!headers.empty()) {
        WinHttpAddRequestHeaders(req.h, headers.c_str(), static_cast<DWORD>(-1L),
                                 WINHTTP_ADDREQ_FLAG_ADD | WINHTTP_ADDREQ_FLAG_REPLACE);
    }

    void* body = request.body.empty() ? WINHTTP_NO_REQUEST_DATA : const_cast<char*>(request.body.data());
    DWORD bodySize = static_cast<DWORD>(request.body.size());
    if (!WinHttpSendRequest(req.h, WINHTTP_NO_ADDITIONAL_HEADERS, 0, body, bodySize, bodySize, 0) ||
        !WinHttpReceiveResponse(req.h, nullptr)) {
        response.error = SystemMessage(GetLastError());
        return response;
    }

    DWORD status = 0, size = sizeof(status);
    WinHttpQueryHeaders(req.h, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX,
                        &status, &size, WINHTTP_NO_HEADER_INDEX);
    response.status = static_cast<long>(status);

    size = 0;
    WinHttpQueryHeaders(req.h, WINHTTP_QUERY_RAW_HEADERS_CRLF, WINHTTP_HEADER_NAME_BY_INDEX, nullptr, &size,
                        WINHTTP_NO_HEADER_INDEX);
    if (size) {
        std::wstring raw(size / sizeof(wchar_t), L'\0');
        if (WinHttpQueryHeaders(req.h, WINHTTP_QUERY_RAW_HEADERS_CRLF, WINHTTP_HEADER_NAME_BY_INDEX, raw.data(),
                                &size, WINHTTP_NO_HEADER_INDEX)) {
            raw.resize(size / sizeof(wchar_t));
            ParseHeaders(raw, response);
        }
    }
    uint64_t total = 0;
    try {
        total = std::stoull(response.header("content-length"));
    } catch (...) {
    }

    FILE* file = nullptr;
    if (!request.saveTo.empty()) {
        file = _wfopen(Wide(request.saveTo).c_str(), L"wb");
        if (!file) {
            response.error = "Could not create " + request.saveTo;
            return response;
        }
    }

    uint64_t received = 0;
    std::vector<char> buffer(64 * 1024);
    for (;;) {
        DWORD read = 0;
        if (!WinHttpReadData(req.h, buffer.data(), static_cast<DWORD>(buffer.size()), &read)) {
            response.error = SystemMessage(GetLastError());
            break;
        }
        if (read == 0) {
            response.completed = true;
            break;
        }
        if (file) {
            if (fwrite(buffer.data(), 1, read, file) != read) {
                response.error = "Could not write " + request.saveTo;
                break;
            }
        } else {
            response.body.append(buffer.data(), read);
        }
        received += read;
        if (request.progress && !request.progress(received, total)) {
            response.cancelled = true;
            break;
        }
    }

    if (file) {
        fclose(file);
        if (!response.ok()) _wremove(Wide(request.saveTo).c_str());
    }
    return response;
}
