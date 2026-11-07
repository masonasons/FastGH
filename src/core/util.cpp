#include "core/util.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <system_error>

#ifndef _WIN32
#include <pwd.h>
#include <unistd.h>
#endif

namespace fs = std::filesystem;

// --- Time ---

namespace {

bool ReadDigits(const std::string& s, size_t& pos, size_t count, int& out) {
    if (pos + count > s.size()) return false;
    int v = 0;
    for (size_t i = 0; i < count; ++i) {
        char c = s[pos + i];
        if (c < '0' || c > '9') return false;
        v = v * 10 + (c - '0');
    }
    pos += count;
    out = v;
    return true;
}

std::time_t UtcFromTm(std::tm& tm) {
#ifdef _WIN32
    return _mkgmtime(&tm);
#else
    return timegm(&tm);
#endif
}

bool UtcTm(std::time_t t, std::tm& out) {
#ifdef _WIN32
    return gmtime_s(&out, &t) == 0;
#else
    return gmtime_r(&t, &out) != nullptr;
#endif
}

bool LocalTm(std::time_t t, std::tm& out) {
#ifdef _WIN32
    return localtime_s(&out, &t) == 0;
#else
    return localtime_r(&t, &out) != nullptr;
#endif
}

}  // namespace

std::time_t ParseIsoTime(const std::string& text) {
    const std::string s = Trim(text);
    size_t pos = 0;
    int year, month, day, hour = 0, minute = 0, second = 0;
    if (!ReadDigits(s, pos, 4, year) || pos >= s.size() || s[pos++] != '-' ||
        !ReadDigits(s, pos, 2, month) || pos >= s.size() || s[pos++] != '-' ||
        !ReadDigits(s, pos, 2, day))
        return 0;
    if (month < 1 || month > 12 || day < 1 || day > 31) return 0;

    long offset = 0;  // seconds east of UTC
    if (pos < s.size() && (s[pos] == 'T' || s[pos] == 't' || s[pos] == ' ')) {
        ++pos;
        if (!ReadDigits(s, pos, 2, hour) || pos >= s.size() || s[pos++] != ':' ||
            !ReadDigits(s, pos, 2, minute))
            return 0;
        if (pos < s.size() && s[pos] == ':') {
            ++pos;
            if (!ReadDigits(s, pos, 2, second)) return 0;
            if (pos < s.size() && (s[pos] == '.' || s[pos] == ',')) {
                ++pos;
                size_t start = pos;
                while (pos < s.size() && std::isdigit(static_cast<unsigned char>(s[pos]))) ++pos;
                if (pos == start) return 0;
            }
        }
        if (hour > 23 || minute > 59 || second > 60) return 0;
        if (pos < s.size()) {
            char c = s[pos];
            if (c == 'Z' || c == 'z') {
                ++pos;
            } else if (c == '+' || c == '-') {
                ++pos;
                int oh, om = 0;
                if (!ReadDigits(s, pos, 2, oh)) return 0;
                if (pos < s.size() && s[pos] == ':') ++pos;
                if (pos < s.size() && !ReadDigits(s, pos, 2, om)) return 0;
                offset = (oh * 3600L + om * 60L) * (c == '-' ? -1 : 1);
            }
        }
    }
    if (pos != s.size()) return 0;

    std::tm tm{};
    tm.tm_year = year - 1900;
    tm.tm_mon = month - 1;
    tm.tm_mday = day;
    tm.tm_hour = hour;
    tm.tm_min = minute;
    tm.tm_sec = second;
    std::time_t t = UtcFromTm(tm);
    if (t == static_cast<std::time_t>(-1)) return 0;
    return t - offset;
}

std::string FormatIsoTime(std::time_t t) {
    if (t == 0) return "";
    std::tm tm{};
    if (!UtcTm(t, tm)) return "";
    char buf[32];
    std::strftime(buf, sizeof buf, "%Y-%m-%dT%H:%M:%SZ", &tm);
    return buf;
}

std::string FormatRelativeTime(std::time_t t) {
    if (t == 0) return "Unknown";
    // Python's timedelta keeps seconds in [0, 86400) and floors the days, so a
    // time slightly in the future reads as "23 hours ago" there too.
    long long diff = static_cast<long long>(std::time(nullptr)) - static_cast<long long>(t);
    long long days = diff >= 0 ? diff / 86400 : -((-diff + 86399) / 86400);
    long long secs = diff - days * 86400;
    auto unit = [](long long n, const char* word) {
        return std::to_string(n) + " " + word + (n > 1 ? "s" : "") + " ago";
    };
    if (days > 365) return unit(days / 365, "year");
    if (days > 30) return unit(days / 30, "month");
    if (days > 0) return unit(days, "day");
    if (secs > 3600) return unit(secs / 3600, "hour");
    if (secs > 60) return unit(secs / 60, "minute");
    return "just now";
}

std::string FormatLocalTime(std::time_t t, const char* format) {
    if (t == 0) return "";
    std::tm tm{};
    if (!LocalTm(t, tm)) return "";
    char buf[256];
    size_t n = std::strftime(buf, sizeof buf, format, &tm);
    return std::string(buf, n);
}

// --- Text ---

std::string Trim(const std::string& s) {
    size_t b = 0, e = s.size();
    while (b < e && std::isspace(static_cast<unsigned char>(s[b]))) ++b;
    while (e > b && std::isspace(static_cast<unsigned char>(s[e - 1]))) --e;
    return s.substr(b, e - b);
}

std::string ToLower(std::string s) {
    for (char& c : s)
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    return s;
}

std::vector<std::string> Split(const std::string& s, char sep) {
    std::vector<std::string> out;
    size_t start = 0;
    for (;;) {
        size_t p = s.find(sep, start);
        if (p == std::string::npos) {
            out.push_back(s.substr(start));
            return out;
        }
        out.push_back(s.substr(start, p - start));
        start = p + 1;
    }
}

bool StartsWith(const std::string& s, const std::string& prefix) {
    return s.size() >= prefix.size() && s.compare(0, prefix.size(), prefix) == 0;
}

bool EndsWith(const std::string& s, const std::string& suffix) {
    return s.size() >= suffix.size() && s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

std::string ReplaceAll(std::string s, const std::string& from, const std::string& to) {
    if (from.empty()) return s;
    size_t pos = 0;
    while ((pos = s.find(from, pos)) != std::string::npos) {
        s.replace(pos, from.size(), to);
        pos += to.size();
    }
    return s;
}

namespace {

// Byte offset just past the first `count` code points.
size_t Utf8Offset(const std::string& s, size_t count) {
    size_t i = 0;
    while (i < s.size() && count > 0) {
        ++i;
        while (i < s.size() && (static_cast<unsigned char>(s[i]) & 0xC0) == 0x80) ++i;
        --count;
    }
    return i;
}

}  // namespace

size_t Utf8Length(const std::string& s) {
    size_t n = 0;
    for (unsigned char c : s)
        if ((c & 0xC0) != 0x80) ++n;
    return n;
}

std::string Truncate(const std::string& s, size_t max) {
    if (Utf8Length(s) <= max) return s;
    if (max <= 3) return s.substr(0, Utf8Offset(s, max));
    return s.substr(0, Utf8Offset(s, max - 3)) + "...";
}

std::string FirstLine(const std::string& s) {
    return s.substr(0, s.find('\n'));
}

std::string FormatSize(uint64_t bytes) {
    char buf[64];
    if (bytes < 1024)
        std::snprintf(buf, sizeof buf, "%llu B", static_cast<unsigned long long>(bytes));
    else if (bytes < 1024ull * 1024)
        std::snprintf(buf, sizeof buf, "%.1f KB", bytes / 1024.0);
    else
        std::snprintf(buf, sizeof buf, "%.1f MB", bytes / (1024.0 * 1024.0));
    return buf;
}

std::string FormatThousands(long long n) {
    std::string digits = std::to_string(n);
    size_t start = digits[0] == '-' ? 1 : 0;
    std::string out;
    out.reserve(digits.size() + digits.size() / 3);
    out.append(digits, 0, start);
    size_t len = digits.size() - start;
    for (size_t i = 0; i < len; ++i) {
        if (i > 0 && (len - i) % 3 == 0) out.push_back(',');
        out.push_back(digits[start + i]);
    }
    return out;
}

namespace {
const char kB64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
}

std::string Base64Decode(const std::string& in) {
    static const auto table = [] {
        std::vector<int> t(256, -1);
        for (int i = 0; i < 64; ++i) t[static_cast<unsigned char>(kB64[i])] = i;
        t['-'] = 62;  // URL-safe alphabet too
        t['_'] = 63;
        return t;
    }();
    std::string out;
    out.reserve(in.size() * 3 / 4);
    unsigned int acc = 0;
    int bits = 0;
    for (unsigned char c : in) {
        if (c == '=') break;
        int v = table[c];
        if (v < 0) continue;  // whitespace, newlines
        acc = (acc << 6) | static_cast<unsigned int>(v);
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            out.push_back(static_cast<char>((acc >> bits) & 0xFF));
        }
    }
    return out;
}

std::string Base64Encode(const std::string& in) {
    std::string out;
    out.reserve((in.size() + 2) / 3 * 4);
    size_t i = 0;
    for (; i + 2 < in.size(); i += 3) {
        unsigned int v = (static_cast<unsigned char>(in[i]) << 16) |
                         (static_cast<unsigned char>(in[i + 1]) << 8) | static_cast<unsigned char>(in[i + 2]);
        out.push_back(kB64[(v >> 18) & 63]);
        out.push_back(kB64[(v >> 12) & 63]);
        out.push_back(kB64[(v >> 6) & 63]);
        out.push_back(kB64[v & 63]);
    }
    if (i < in.size()) {
        unsigned int v = static_cast<unsigned char>(in[i]) << 16;
        if (i + 1 < in.size()) v |= static_cast<unsigned char>(in[i + 1]) << 8;
        out.push_back(kB64[(v >> 18) & 63]);
        out.push_back(kB64[(v >> 12) & 63]);
        out.push_back(i + 1 < in.size() ? kB64[(v >> 6) & 63] : '=');
        out.push_back('=');
    }
    return out;
}

// --- Paths ---
// u8path keeps UTF-8 intact on Windows, where narrow strings would otherwise be
// read in the ANSI code page.

namespace {
fs::path P(const std::string& s) { return fs::u8path(s); }
}  // namespace

std::string HomeDir() {
#ifdef _WIN32
    if (const wchar_t* h = _wgetenv(L"USERPROFILE"); h && *h) return fs::path(h).u8string();
    const wchar_t* drive = _wgetenv(L"HOMEDRIVE");
    const wchar_t* path = _wgetenv(L"HOMEPATH");
    if (drive && path) return fs::path(std::wstring(drive) + path).u8string();
    return "";
#else
    if (const char* h = std::getenv("HOME"); h && *h) return h;
    if (const passwd* pw = getpwuid(getuid()); pw && pw->pw_dir) return pw->pw_dir;
    return "";
#endif
}

std::string JoinPath(const std::string& a, const std::string& b) {
    if (a.empty()) return b;
    if (b.empty()) return a;
    return (P(a) / P(b)).u8string();
}

bool PathExists(const std::string& path) {
    std::error_code ec;
    return !path.empty() && fs::exists(P(path), ec);
}

bool IsDirectory(const std::string& path) {
    std::error_code ec;
    return !path.empty() && fs::is_directory(P(path), ec);
}

bool MakeDirs(const std::string& path) {
    std::error_code ec;
    fs::create_directories(P(path), ec);
    return !ec || fs::is_directory(P(path), ec);
}

bool RemoveTree(const std::string& path) {
    std::error_code ec;
    fs::path p = P(path);
    fs::remove_all(p, ec);
    if (!ec) return true;
#ifdef _WIN32
    // Git marks its object files read-only, which Windows refuses to delete.
    for (auto it = fs::recursive_directory_iterator(p, ec); !ec && it != fs::recursive_directory_iterator();
         it.increment(ec))
        fs::permissions(it->path(), fs::perms::owner_write, fs::perm_options::add, ec);
    ec.clear();
    fs::remove_all(p, ec);
    return !ec;
#else
    return false;
#endif
}

bool RenamePath(const std::string& from, const std::string& to) {
    std::error_code ec;
    fs::rename(P(from), P(to), ec);
    return !ec;
}

bool ReadFile(const std::string& path, std::string& out) {
    std::ifstream in(P(path), std::ios::binary);
    if (!in) return false;
    in.seekg(0, std::ios::end);
    std::streamoff size = in.tellg();
    if (size < 0) return false;
    in.seekg(0, std::ios::beg);
    out.resize(static_cast<size_t>(size));
    if (size > 0) in.read(&out[0], size);
    return static_cast<bool>(in) || in.eof();
}

bool WriteFileAtomic(const std::string& path, const std::string& data) {
    fs::path target = P(path);
    fs::path tmp = target;
    tmp += ".tmp";
    {
        std::ofstream outFile(tmp, std::ios::binary | std::ios::trunc);
        if (!outFile) return false;
        outFile.write(data.data(), static_cast<std::streamsize>(data.size()));
        outFile.flush();
        if (!outFile) {
            outFile.close();
            std::error_code ec;
            fs::remove(tmp, ec);
            return false;
        }
    }
    std::error_code ec;
    fs::rename(tmp, target, ec);  // replaces an existing file on Windows too
    if (ec) {
        fs::remove(tmp, ec);
        return false;
    }
    return true;
}
