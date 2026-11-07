// HTTP through libcurl (macOS ships it with the system).
//
// Requests run on short-lived worker threads, so connections, DNS answers and
// TLS sessions live in one share handle: a request on a new thread reuses the
// connection to api.github.com left open by an earlier one.

#include "core/http.h"
#include "version.h"

#include <curl/curl.h>

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <mutex>

namespace {

std::once_flag g_init;
CURLSH* g_share = nullptr;
std::mutex g_shareLocks[CURL_LOCK_DATA_LAST];

void LockShare(CURL*, curl_lock_data data, curl_lock_access, void*) { g_shareLocks[data].lock(); }
void UnlockShare(CURL*, curl_lock_data data, void*) { g_shareLocks[data].unlock(); }

void Init() {
    curl_global_init(CURL_GLOBAL_DEFAULT);
    g_share = curl_share_init();
    curl_share_setopt(g_share, CURLSHOPT_LOCKFUNC, LockShare);
    curl_share_setopt(g_share, CURLSHOPT_UNLOCKFUNC, UnlockShare);
    curl_share_setopt(g_share, CURLSHOPT_SHARE, CURL_LOCK_DATA_CONNECT);
    curl_share_setopt(g_share, CURLSHOPT_SHARE, CURL_LOCK_DATA_DNS);
    curl_share_setopt(g_share, CURLSHOPT_SHARE, CURL_LOCK_DATA_SSL_SESSION);
}

struct Transfer {
    const HttpRequest* request;
    HttpResponse* response;
    FILE* file = nullptr;
};

size_t OnData(char* data, size_t size, size_t count, void* user) {
    auto* t = static_cast<Transfer*>(user);
    size_t bytes = size * count;
    if (t->file) {
        if (fwrite(data, 1, bytes, t->file) != bytes) return 0;
    } else {
        t->response->body.append(data, bytes);
    }
    return bytes;
}

size_t OnHeader(char* data, size_t size, size_t count, void* user) {
    auto* t = static_cast<Transfer*>(user);
    size_t bytes = size * count;
    std::string line(data, bytes);
    // Each response in a redirect chain starts with its status line; keep only the last's headers.
    if (line.compare(0, 5, "HTTP/") == 0) {
        t->response->headers.clear();
        return bytes;
    }
    size_t colon = line.find(':');
    if (colon == std::string::npos) return bytes;
    std::string name = line.substr(0, colon);
    std::transform(name.begin(), name.end(), name.begin(), [](unsigned char c) { return std::tolower(c); });
    size_t start = line.find_first_not_of(" \t", colon + 1);
    size_t end = line.find_last_not_of(" \t\r\n");
    std::string value = start == std::string::npos || end < start ? "" : line.substr(start, end - start + 1);
    t->response->headers[name] = value;
    return bytes;
}

int OnProgress(void* user, curl_off_t total, curl_off_t received, curl_off_t, curl_off_t) {
    auto* t = static_cast<Transfer*>(user);
    if (t->request->progress && received > 0 &&
        !t->request->progress(static_cast<uint64_t>(received), static_cast<uint64_t>(total))) {
        t->response->cancelled = true;
        return 1;
    }
    return 0;
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
    std::call_once(g_init, Init);

    HttpResponse response;
    CURL* curl = curl_easy_init();
    if (!curl) {
        response.error = "Could not start a network request";
        return response;
    }

    Transfer transfer{&request, &response};
    if (!request.saveTo.empty()) {
        transfer.file = fopen(request.saveTo.c_str(), "wb");
        if (!transfer.file) {
            response.error = "Could not create " + request.saveTo;
            curl_easy_cleanup(curl);
            return response;
        }
    }

    curl_easy_setopt(curl, CURLOPT_SHARE, g_share);
    curl_easy_setopt(curl, CURLOPT_URL, request.url.c_str());
    curl_easy_setopt(curl, CURLOPT_USERAGENT, UserAgent().c_str());
    curl_easy_setopt(curl, CURLOPT_ACCEPT_ENCODING, "");  // gzip and the rest, as curl supports
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, request.followRedirects ? 1L : 0L);
    curl_easy_setopt(curl, CURLOPT_MAXREDIRS, 10L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, OnData);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &transfer);
    curl_easy_setopt(curl, CURLOPT_HEADERFUNCTION, OnHeader);
    curl_easy_setopt(curl, CURLOPT_HEADERDATA, &transfer);
    curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION, OnProgress);
    curl_easy_setopt(curl, CURLOPT_XFERINFODATA, &transfer);
    curl_easy_setopt(curl, CURLOPT_NOPROGRESS, request.progress ? 0L : 1L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_TCP_KEEPALIVE, 1L);
    if (request.timeoutMs) {
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS, static_cast<long>(request.timeoutMs));
        // A stalled transfer (under 1 byte/s for the timeout) is abandoned; a slow
        // big download is not.
        curl_easy_setopt(curl, CURLOPT_LOW_SPEED_LIMIT, 1L);
        curl_easy_setopt(curl, CURLOPT_LOW_SPEED_TIME, static_cast<long>((request.timeoutMs + 999) / 1000));
    }

    if (request.method == "GET") {
        curl_easy_setopt(curl, CURLOPT_HTTPGET, 1L);
    } else {
        curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, request.method.c_str());
        if (request.method != "DELETE" || !request.body.empty()) {
            // PUT /user/starred/... has no body but needs Content-Length: 0.
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, request.body.c_str());
            curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE_LARGE, static_cast<curl_off_t>(request.body.size()));
        }
    }

    struct curl_slist* headers = nullptr;
    for (const auto& header : request.headers) headers = curl_slist_append(headers, header.c_str());
    // curl would otherwise send "Expect: 100-continue" for larger bodies and wait for it.
    headers = curl_slist_append(headers, "Expect:");
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

    CURLcode code = curl_easy_perform(curl);
    long status = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);

    if (code == CURLE_OK && status > 0) {
        response.completed = true;
        response.status = status;
    } else if (!response.cancelled) {
        response.error = curl_easy_strerror(code);
    }

    if (transfer.file) {
        fclose(transfer.file);
        if (!response.ok()) remove(request.saveTo.c_str());
    }
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    return response;
}
