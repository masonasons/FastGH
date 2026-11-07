#pragma once

// Small helpers shared by the core and the windows: time, text, paths.
// All text in the core is UTF-8 std::string.

#include <cstdint>
#include <ctime>
#include <string>
#include <vector>

// --- Time ---
// Timestamps are UTC seconds since the epoch; 0 means "none".

// GitHub's ISO 8601 ("2024-01-02T03:04:05Z", also with +hh:mm offsets or
// fractional seconds). 0 for empty or unparseable text.
std::time_t ParseIsoTime(const std::string& text);
// Back to ISO 8601 UTC ("2024-01-02T03:04:05Z"); empty for 0.
std::string FormatIsoTime(std::time_t t);
// "3 days ago", "1 hour ago", "just now"; "Unknown" for 0. The same wording and
// thresholds as the Python app (years > 365 days, months > 30 days...).
std::string FormatRelativeTime(std::time_t t);
// Local time with strftime formatting, e.g. "%Y-%m-%d %H:%M". Empty for 0.
std::string FormatLocalTime(std::time_t t, const char* format = "%Y-%m-%d %H:%M");

// --- Text ---
std::string Trim(const std::string& s);
std::string ToLower(std::string s);
std::vector<std::string> Split(const std::string& s, char sep);
bool StartsWith(const std::string& s, const std::string& prefix);
bool EndsWith(const std::string& s, const std::string& suffix);
std::string ReplaceAll(std::string s, const std::string& from, const std::string& to);
// Shorten to at most `max` UTF-8 code points, ending in "..." when cut.
std::string Truncate(const std::string& s, size_t max);
// The first line of a block of text.
std::string FirstLine(const std::string& s);
// Number of UTF-8 code points.
size_t Utf8Length(const std::string& s);
// "1.5 KB", "3.2 MB", "12 B" (as the Python models formatted sizes).
std::string FormatSize(uint64_t bytes);
// "1,234"
std::string FormatThousands(long long n);
// "s" when n != 1, for "1 star" / "2 stars".
inline const char* Plural(long long n) { return n == 1 ? "" : "s"; }

std::string Base64Decode(const std::string& in);  // ignores whitespace/newlines
std::string Base64Encode(const std::string& in);

// --- Paths (UTF-8) ---
std::string HomeDir();
std::string JoinPath(const std::string& a, const std::string& b);
bool PathExists(const std::string& path);
bool IsDirectory(const std::string& path);
bool MakeDirs(const std::string& path);
bool RemoveTree(const std::string& path);
bool RenamePath(const std::string& from, const std::string& to);
bool ReadFile(const std::string& path, std::string& out);
// Written to a temporary file first, then renamed over the old one.
bool WriteFileAtomic(const std::string& path, const std::string& data);
