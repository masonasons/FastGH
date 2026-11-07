#pragma once

// HTTP(S) requests. libcurl on macOS and Linux (src/platform/http_curl.cpp),
// WinHTTP on Windows (src/platform/http_windows.cpp). Blocking: call from a worker
// thread. Safe to call from several threads at once; connections to a host are
// kept alive and reused between requests on the same thread.

#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <vector>

struct HttpRequest {
    std::string method = "GET";  // GET, POST, PUT, PATCH, DELETE
    std::string url;
    // Extra request headers, "Name: value".
    std::vector<std::string> headers;
    std::string body;  // sent for POST/PUT/PATCH (and DELETE when not empty)
    bool followRedirects = true;
    // Stream the body into this file instead of memory (UTF-8 path).
    std::string saveTo;
    // Called as data arrives: bytes received and the total (0 if unknown).
    // Returning false cancels the request.
    std::function<bool(uint64_t received, uint64_t total)> progress;
    unsigned timeoutMs = 30000;  // connect timeout, and the stall timeout
};

struct HttpResponse {
    bool completed = false;  // a final response arrived (any status)
    bool cancelled = false;  // the progress callback stopped it
    long status = 0;
    std::string body;
    // Response headers of the final response, names lowercased.
    std::map<std::string, std::string> headers;
    std::string error;  // why the request failed when !completed

    bool ok() const { return completed && status >= 200 && status < 300; }
    std::string header(const std::string& lowerName) const {
        auto it = headers.find(lowerName);
        return it == headers.end() ? std::string() : it->second;
    }
};

HttpResponse HttpSend(const HttpRequest& request);

// "FastGH/0.2.0"
const std::string& UserAgent();

// Percent-encode a query string value or path segment.
std::string UrlEncode(const std::string& value);
