#include "core/github.h"

#include "core/http.h"
#include "core/util.h"

#include <algorithm>
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <thread>

const char* const kGitHubClientId = "Ov23liErbWGLzAKTlLFW";

namespace {

const char* const kApiUrl = "https://api.github.com";
const char* const kDefaultAccept = "application/vnd.github+json";
// Enough parallel page fetches to hide latency without tripping GitHub's secondary rate limits.
const size_t kMaxParallel = 6;
// Cached bodies are kept in memory; drop them all past this many URLs rather than track usage.
const size_t kMaxEtagEntries = 2000;

thread_local std::string t_lastError;

using Params = std::vector<std::pair<std::string, std::string>>;

// --- JSON access that never throws on missing keys or odd types ---

const json* Child(const json& j, const char* key) {
    if (!j.is_object()) return nullptr;
    auto it = j.find(key);
    if (it == j.end() || it->is_null()) return nullptr;
    return &*it;
}

std::string Str(const json& j, const char* key) {
    const json* c = Child(j, key);
    return c && c->is_string() ? c->get<std::string>() : std::string();
}

long long Int(const json& j, const char* key, long long fallback = 0) {
    const json* c = Child(j, key);
    if (!c || !c->is_number()) return fallback;
    return c->is_number_float() ? static_cast<long long>(c->get<double>()) : c->get<long long>();
}

bool Bool(const json& j, const char* key) {
    const json* c = Child(j, key);
    return c && c->is_boolean() && c->get<bool>();
}

// --- URLs and headers ---

std::string HostOf(const std::string& url) {
    size_t start = url.find("://");
    start = start == std::string::npos ? 0 : start + 3;
    size_t end = url.find_first_of("/:?#", start);
    return ToLower(url.substr(start, end == std::string::npos ? std::string::npos : end - start));
}

bool IsGitHubHost(const std::string& url) {
    std::string host = HostOf(url);
    return host == "github.com" || EndsWith(host, ".github.com");
}

std::string ApiUrl(const std::string& path) {
    if (StartsWith(path, "https://") || StartsWith(path, "http://")) return path;
    return kApiUrl + path;
}

std::string WithQuery(std::string path, const Params& params) {
    char sep = path.find('?') == std::string::npos ? '?' : '&';
    for (const auto& [key, value] : params) {
        path += sep;
        path += key + "=" + UrlEncode(value);
        sep = '&';
    }
    return path;
}

// A repository path ("docs/a b.md"): each segment encoded, slashes kept.
std::string EncodePath(const std::string& path) {
    std::string out;
    size_t start = 0;
    while (true) {
        size_t slash = path.find('/', start);
        out += UrlEncode(path.substr(start, slash == std::string::npos ? std::string::npos : slash - start));
        if (slash == std::string::npos) break;
        out += '/';
        start = slash + 1;
    }
    return out;
}

std::string RepoPath(const std::string& owner, const std::string& repo) {
    return "/repos/" + owner + "/" + repo;
}

bool IsHeader(const std::string& header, const char* lowerName) {
    size_t len = strlen(lowerName);
    return header.size() > len && header[len] == ':' && ToLower(header.substr(0, len)) == lowerName;
}

std::vector<std::string> ApiHeaders(const std::string& token, const std::string& url,
                                    const std::vector<std::string>& extra) {
    std::vector<std::string> headers;
    headers.reserve(extra.size() + 4);
    headers.push_back("User-Agent: " + UserAgent());
    headers.push_back("X-GitHub-Api-Version: 2022-11-28");
    bool hasAccept =
        std::any_of(extra.begin(), extra.end(), [](const std::string& h) { return IsHeader(h, "accept"); });
    if (!hasAccept) headers.push_back(std::string("Accept: ") + kDefaultAccept);
    // Only GitHub gets the token, whatever URL a caller passes.
    if (!token.empty() && IsGitHubHost(url)) headers.push_back("Authorization: Bearer " + token);
    headers.insert(headers.end(), extra.begin(), extra.end());
    return headers;
}

std::string AcceptOf(const std::vector<std::string>& headers) {
    for (const auto& h : headers)
        if (IsHeader(h, "accept")) return Trim(h.substr(7));
    return kDefaultAccept;
}

const char* StatusText(long status) {
    switch (status) {
        case 304: return "Not Modified";
        case 400: return "Bad Request";
        case 401: return "Unauthorized";
        case 403: return "Forbidden";
        case 404: return "Not Found";
        case 405: return "Method Not Allowed";
        case 409: return "Conflict";
        case 410: return "Gone";
        case 422: return "Unprocessable Entity";
        case 429: return "Too Many Requests";
        case 500: return "Internal Server Error";
        case 502: return "Bad Gateway";
        case 503: return "Service Unavailable";
        case 504: return "Gateway Timeout";
        default: return status >= 500 ? "Server Error" : "Error";
    }
}

// "HTTP 404: Not Found", preferring GitHub's own message ("API rate limit exceeded...").
std::string HttpError(long status, const json& data) {
    std::string message = Str(data, "message");
    return "HTTP " + std::to_string(status) + ": " + (message.empty() ? StatusText(status) : message);
}

std::string TransportError(const HttpResponse& r) {
    if (r.cancelled) return "Cancelled";
    return r.error.empty() ? "Network error" : r.error;
}

// Cut to at most `max` bytes without splitting a UTF-8 sequence.
std::string Utf8Prefix(const std::string& s, size_t max) {
    if (s.size() <= max) return s;
    size_t end = max;
    while (end > 0 && (static_cast<unsigned char>(s[end]) & 0xC0) == 0x80) --end;
    return s.substr(0, end);
}

bool IsValidUtf8(const std::string& s) {
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        size_t extra;
        unsigned min;
        unsigned cp;
        if (c < 0x80) { ++i; continue; }
        if ((c & 0xE0) == 0xC0) { extra = 1; min = 0x80; cp = c & 0x1F; }
        else if ((c & 0xF0) == 0xE0) { extra = 2; min = 0x800; cp = c & 0x0F; }
        else if ((c & 0xF8) == 0xF0) { extra = 3; min = 0x10000; cp = c & 0x07; }
        else return false;
        if (i + extra >= s.size()) return false;
        for (size_t k = 1; k <= extra; ++k) {
            unsigned char cc = static_cast<unsigned char>(s[i + k]);
            if ((cc & 0xC0) != 0x80) return false;
            cp = (cp << 6) | (cc & 0x3F);
        }
        if (cp < min || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) return false;
        i += extra + 1;
    }
    return true;
}

// rel -> URL from a Link header: <https://...&page=2>; rel="next", <...>; rel="last"
std::map<std::string, std::string> ParseLinks(const std::string& header) {
    std::map<std::string, std::string> links;
    size_t pos = 0;
    while (true) {
        size_t open = header.find('<', pos);
        if (open == std::string::npos) break;
        size_t close = header.find('>', open);
        if (close == std::string::npos) break;
        size_t next = header.find('<', close);
        size_t paramsEnd = next == std::string::npos ? header.size() : next;
        std::string params = header.substr(close + 1, paramsEnd - close - 1);
        size_t rel = params.find("rel=\"");
        if (rel != std::string::npos) {
            size_t endQuote = params.find('"', rel + 5);
            if (endQuote != std::string::npos)
                links[params.substr(rel + 5, endQuote - rel - 5)] = header.substr(open + 1, close - open - 1);
        }
        pos = close + 1;
    }
    return links;
}

int PageFromUrl(const std::string& url) {
    for (const char* key : {"?page=", "&page="}) {
        size_t at = url.find(key);
        if (at != std::string::npos) return std::atoi(url.c_str() + at + 6);
    }
    return 0;
}

// Runs fn(0..count-1) on up to kMaxParallel threads (this one included). fn must be thread-safe.
void ParallelFor(size_t count, const std::function<void(size_t)>& fn) {
    if (count == 0) return;
    std::atomic<size_t> next{0};
    auto worker = [&] {
        for (size_t i; (i = next.fetch_add(1)) < count;) {
            try {
                fn(i);
            } catch (...) {
                // An exception escaping a std::thread would terminate the app.
            }
        }
    };
    std::vector<std::thread> threads;
    size_t extra = std::min(count, kMaxParallel) - 1;
    for (size_t t = 0; t < extra; ++t) {
        try {
            threads.emplace_back(worker);
        } catch (...) {
            break;  // out of threads: the rest run here
        }
    }
    worker();
    for (auto& t : threads) t.join();
}

template <typename T>
void AppendAll(std::vector<T>& out, std::vector<T>& more) {
    out.insert(out.end(), std::make_move_iterator(more.begin()), std::make_move_iterator(more.end()));
}

// Every page of a list endpoint. Page 1's Link header names the last page, so the rest are
// fetched in parallel; without one we walk pages one by one, as the Python client did.
// `parse(item, out)` appends what an item yields (it may skip items). `itemsKey` names the
// array in wrapped responses ({"workflows": [...]}). Pages after a failed one are dropped.
template <typename T, typename Parse>
std::vector<T> FetchPages(GitHubAccount& gh, const std::string& path, const Params& params, int perPage,
                          Parse parse, const char* itemsKey = nullptr, int maxPages = 0,
                          const std::vector<std::string>& headers = {}) {
    struct Page {
        bool ok = false;
        size_t count = 0;  // items on the page before parse() filtered them
        std::vector<T> items;
        std::string error;
        std::string link;
    };
    auto fetch = [&](int page) {
        Page p;
        Params query = params;
        query.emplace_back("per_page", std::to_string(perPage));
        query.emplace_back("page", std::to_string(page));
        GitHubAccount::ApiResponse r = gh.Request("GET", WithQuery(path, query), json(), headers);
        if (!r.ok()) {
            p.error = GitHubAccount::LastError();
            return p;
        }
        p.ok = true;
        auto link = r.headers.find("link");
        if (link != r.headers.end()) p.link = link->second;
        const json* items = itemsKey ? Child(r.data, itemsKey) : &r.data;
        if (items && items->is_array()) {
            p.count = items->size();
            p.items.reserve(p.count);
            for (const auto& item : *items) parse(item, p.items);
        }
        return p;
    };
    auto more = [&](const Page& p, const std::map<std::string, std::string>& links) {
        if (p.count == 0) return false;
        return links.empty() ? p.count >= static_cast<size_t>(perPage) : links.count("next") > 0;
    };

    Page first = fetch(1);
    std::vector<T> out = std::move(first.items);
    if (!first.ok) {
        t_lastError = first.error;
        return out;
    }
    auto links = ParseLinks(first.link);
    int last = links.count("last") ? PageFromUrl(links["last"]) : 0;
    if (maxPages > 0) last = std::min(last, maxPages);

    if (last > 1) {
        std::vector<Page> pages(static_cast<size_t>(last - 1));
        ParallelFor(pages.size(), [&](size_t i) { pages[i] = fetch(static_cast<int>(i) + 2); });
        for (auto& p : pages) {
            if (!p.ok) {
                t_lastError = p.error;
                break;
            }
            AppendAll(out, p.items);
        }
        return out;
    }

    // No last page given: GitHub offers only cursor links for some sorts (issues by
    // "updated"), but numbered pages still work. Fetch them in parallel batches and
    // stop at the first short page; at most a batch of empty pages is wasted.
    bool keepGoing = more(first, links);
    for (int start = 2; keepGoing && (maxPages <= 0 || start <= maxPages);) {
        int end = start + static_cast<int>(kMaxParallel) - 1;
        if (maxPages > 0) end = std::min(end, maxPages);
        std::vector<Page> pages(static_cast<size_t>(end - start + 1));
        ParallelFor(pages.size(), [&](size_t i) { pages[i] = fetch(start + static_cast<int>(i)); });
        for (auto& p : pages) {
            if (!p.ok) {
                t_lastError = p.error;
                keepGoing = false;
                break;
            }
            AppendAll(out, p.items);
            if (p.count < static_cast<size_t>(perPage)) {
                keepGoing = false;
                break;
            }
        }
        start = end + 1;
    }
    return out;
}

// One page of a list endpoint. More follow when GitHub links a next page, or (with no
// Link header) when the page came back full.
template <typename T, typename Parse>
Page<T> FetchOnePage(GitHubAccount& gh, const std::string& path, const Params& params, int perPage, int page,
                     Parse parse, const char* itemsKey = nullptr, const std::vector<std::string>& headers = {}) {
    Page<T> out;
    Params query = params;
    query.emplace_back("per_page", std::to_string(perPage));
    query.emplace_back("page", std::to_string(page));
    GitHubAccount::ApiResponse r = gh.Request("GET", WithQuery(path, query), json(), headers);
    if (!r.ok()) return out;
    const json* items = itemsKey ? Child(r.data, itemsKey) : &r.data;
    size_t count = 0;
    if (items && items->is_array()) {
        count = items->size();
        out.items.reserve(count);
        for (const auto& item : *items) parse(item, out.items);
    }
    auto link = r.headers.find("link");
    if (link != r.headers.end() && !link->second.empty()) out.hasMore = ParseLinks(link->second).count("next") > 0;
    else out.hasMore = count >= static_cast<size_t>(perPage);
    return out;
}

template <typename T>
auto Append() {
    return [](const json& item, std::vector<T>& out) { out.push_back(T::FromJson(item)); };
}

// Search and following results carry only the basics of each user.
UserProfile BasicProfile(const json& item) {
    UserProfile p;
    p.id = Int(item, "id");
    p.login = Str(item, "login");
    p.avatarUrl = Str(item, "avatar_url");
    p.htmlUrl = Str(item, "html_url");
    std::string type = Str(item, "type");
    if (!type.empty()) p.type = type;
    return p;
}

void SortByPushedDesc(std::vector<Repository>& repos) {
    std::stable_sort(repos.begin(), repos.end(),
                     [](const Repository& a, const Repository& b) { return a.pushedAt > b.pushedAt; });
}

// Run f, turning any exception into an empty result and LastError().
template <typename F>
auto Guarded(F&& f) -> decltype(f()) {
    try {
        return f();
    } catch (const std::exception& e) {
        t_lastError = std::string("Unexpected error: ") + e.what();
    } catch (...) {
        t_lastError = "Unexpected error";
    }
    return decltype(f())();
}

// The exact status the Python code required; LastError() covers a 2xx we didn't expect.
bool Expect(const GitHubAccount::ApiResponse& r, std::initializer_list<long> codes) {
    if (std::find(codes.begin(), codes.end(), r.status) != codes.end()) return true;
    if (r.ok()) t_lastError = "Unexpected HTTP status " + std::to_string(r.status);
    return false;
}

// GETs `url`, following redirects by hand: GitHub sends downloads and logs to signed storage
// URLs on other hosts, which reject (and must never see) our Authorization header.
HttpResponse SendWithRedirects(HttpRequest req) {
    const std::string firstHost = HostOf(req.url);
    for (int hop = 0; hop < 8; ++hop) {
        req.followRedirects = false;
        HttpResponse r = HttpSend(req);
        if (!r.completed || r.status < 300 || r.status >= 400 || r.status == 304) return r;
        std::string location = r.header("location");
        if (location.empty()) return r;
        if (StartsWith(location, "/")) {
            size_t scheme = req.url.find("://");
            size_t pathStart = req.url.find('/', scheme == std::string::npos ? 0 : scheme + 3);
            location = req.url.substr(0, pathStart) + location;
        }
        req.url = location;
        req.method = "GET";
        req.body.clear();
        if (HostOf(location) != firstHost) req.headers = {"User-Agent: " + UserAgent()};
    }
    HttpResponse tooMany;
    tooMany.error = "Too many redirects";
    return tooMany;
}

bool Download(HttpRequest req, const std::string& destPath, const ProgressFn& progress) {
    req.saveTo = destPath;
    req.progress = progress;
    HttpResponse r = SendWithRedirects(std::move(req));
    if (r.ok()) return true;
    t_lastError = r.completed ? HttpError(r.status, json::parse(r.body, nullptr, false)) : TransportError(r);
    // Don't leave a truncated or error-page file behind.
    if (PathExists(destPath)) RemoveTree(destPath);
    return false;
}

const char* const kDiscussionCommentFields = R"(
                  id
                  databaseId
                  body
                  url
                  createdAt
                  updatedAt
                  author {
                    login
                    avatarUrl
                  }
)";

std::string CommentNodesQuery() {
    return std::string("nodes {") + kDiscussionCommentFields + "                  replies(first: 50) {\n"
           "                    nodes {" + kDiscussionCommentFields + "                    }\n"
           "                  }\n"
           "                }\n";
}

}  // namespace

// --- Device flow ---

namespace {
void SetOut(std::string* out, const std::string& value) {
    if (out) *out = value;
}

HttpResponse PostForm(const std::string& url, const std::string& body) {
    HttpRequest req;
    req.method = "POST";
    req.url = url;
    req.headers = {"Accept: application/json", "Content-Type: application/x-www-form-urlencoded",
                   "User-Agent: " + UserAgent()};
    req.body = body;
    return HttpSend(req);
}
}  // namespace

std::optional<DeviceCode> RequestDeviceCode(std::string* error) {
    try {
        HttpResponse r = PostForm("https://github.com/login/device/code",
                                  "client_id=" + UrlEncode(kGitHubClientId) +
                                      "&scope=" + UrlEncode("repo user notifications"));
        if (!r.completed) {
            SetOut(error, "Failed to get device code: " + TransportError(r));
            return std::nullopt;
        }
        if (r.status != 200) {
            SetOut(error, "Failed to get device code: " + Trim(r.body));
            return std::nullopt;
        }
        json data = json::parse(r.body, nullptr, false);
        DeviceCode code;
        code.deviceCode = Str(data, "device_code");
        code.userCode = Str(data, "user_code");
        code.verificationUri = Str(data, "verification_uri");
        code.expiresIn = static_cast<int>(Int(data, "expires_in", 900));
        code.interval = static_cast<int>(Int(data, "interval", 5));
        if (code.deviceCode.empty() || code.userCode.empty() || code.verificationUri.empty()) {
            // GitHub reports problems such as a disabled device flow as a 200 with an error.
            std::string why = Str(data, "error_description");
            if (why.empty()) why = Str(data, "error");
            SetOut(error, "Failed to get device code: " + (why.empty() ? Trim(r.body) : why));
            return std::nullopt;
        }
        return code;
    } catch (const std::exception& e) {
        SetOut(error, std::string("Failed to get device code: ") + e.what());
        return std::nullopt;
    }
}

DevicePollResult PollDeviceToken(const DeviceCode& code, std::string* token, std::string* error) {
    try {
        HttpResponse r = PostForm("https://github.com/login/oauth/access_token",
                                  "client_id=" + UrlEncode(kGitHubClientId) + "&device_code=" +
                                      UrlEncode(code.deviceCode) +
                                      "&grant_type=" + UrlEncode("urn:ietf:params:oauth:grant-type:device_code"));
        // Like the Python poller, a failed request is retried on the next poll.
        if (!r.completed || r.status != 200) {
            SetOut(error, r.completed ? HttpError(r.status, json()) : TransportError(r));
            return DevicePollResult::Pending;
        }
        json data = json::parse(r.body, nullptr, false);
        std::string accessToken = Str(data, "access_token");
        if (!accessToken.empty()) {
            SetOut(token, accessToken);
            return DevicePollResult::Success;
        }
        std::string err = Str(data, "error");
        if (err == "authorization_pending") return DevicePollResult::Pending;
        if (err == "slow_down") return DevicePollResult::SlowDown;
        if (err == "expired_token") {
            SetOut(error, "Authorization expired. Please try again.");
            return DevicePollResult::Expired;
        }
        if (err == "access_denied") {
            SetOut(error, "Authorization denied.");
            return DevicePollResult::Denied;
        }
        std::string why = Str(data, "error_description");
        SetOut(error, why.empty() ? (err.empty() ? "Unexpected response from GitHub." : err) : why);
        return DevicePollResult::Error;
    } catch (const std::exception& e) {
        SetOut(error, e.what());
        return DevicePollResult::Error;
    }
}

// --- Account ---

GitHubAccount::GitHubAccount(int index)
    : m_index(index), m_prefs(std::make_unique<Config>(AccountConfigDir(index))) {}

bool GitHubAccount::HasToken() const { return !m_prefs->GetString("access_token").empty(); }

void GitHubAccount::SetToken(const std::string& token) {
    m_prefs->Set("access_token", token);
    std::lock_guard<std::mutex> lock(m_etagMutex);
    m_etags.clear();  // cached bodies belong to the old token's user
}

GitHubAccount::VerifyResult GitHubAccount::Verify() {
    try {
        ApiResponse r = Request("GET", "/user");
        if (r.status == 401) return VerifyResult::Unauthorized;
        if (!r.ok()) return VerifyResult::Failed;
        if (!r.data.is_object()) {
            t_lastError = "Invalid response from GitHub.";
            return VerifyResult::Failed;
        }
        std::lock_guard<std::mutex> lock(m_meMutex);
        m_me = std::move(r.data);
        return VerifyResult::Ok;
    } catch (const std::exception& e) {
        t_lastError = e.what();
        return VerifyResult::Failed;
    }
}

json GitHubAccount::Me() const {
    std::lock_guard<std::mutex> lock(m_meMutex);
    return m_me;
}

std::string GitHubAccount::Username() const {
    std::lock_guard<std::mutex> lock(m_meMutex);
    return Str(m_me, "login");
}

std::string GitHubAccount::DisplayName() const {
    std::lock_guard<std::mutex> lock(m_meMutex);
    std::string name = Str(m_me, "name");
    return name.empty() ? Str(m_me, "login") : name;
}

std::string GitHubAccount::LastError() { return t_lastError; }

// --- Low level ---

GitHubAccount::ApiResponse GitHubAccount::Request(const std::string& method, const std::string& path,
                                                  const json& body, const std::vector<std::string>& extraHeaders) {
    ApiResponse out;
    t_lastError.clear();
    try {
        HttpRequest req;
        req.method = method;
        req.url = ApiUrl(path);
        req.headers = ApiHeaders(m_prefs->GetString("access_token"), req.url, extraHeaders);
        if (!body.is_null()) {
            req.body = body.dump(-1, ' ', false, json::error_handler_t::replace);
            req.headers.push_back("Content-Type: application/json");
        }

        // The cache key includes Accept: one URL gives different bodies per media type.
        const bool conditional = method == "GET";
        std::string key;
        if (conditional) {
            key = AcceptOf(req.headers) + ' ' + req.url;
            std::lock_guard<std::mutex> lock(m_etagMutex);
            auto it = m_etags.find(key);
            if (it != m_etags.end())
                req.headers.push_back("If-None-Match: " + it->second.first.substr(0, it->second.first.find('\n')));
        }

        HttpResponse r = HttpSend(req);
        bool fromCache = false;
        if (conditional && r.completed && r.status == 304) {
            std::lock_guard<std::mutex> lock(m_etagMutex);
            auto it = m_etags.find(key);
            if (it != m_etags.end()) {
                // The cached entry is "etag\nlink": a 304 may not repeat the Link header pagination needs.
                const std::string& meta = it->second.first;
                size_t nl = meta.find('\n');
                r.status = 200;
                r.body = it->second.second;
                fromCache = true;
                r.headers["etag"] = meta.substr(0, nl);
                if (nl != std::string::npos && nl + 1 < meta.size()) r.headers["link"] = meta.substr(nl + 1);
            }
        }
        if (conditional && r.completed && r.status == 304) {
            // Another thread cleared the cache between our lookup and the reply: ask again in full.
            req.headers.erase(std::remove_if(req.headers.begin(), req.headers.end(),
                                             [](const std::string& h) { return IsHeader(h, "if-none-match"); }),
                              req.headers.end());
            r = HttpSend(req);
        }
        if (!r.completed) {
            t_lastError = TransportError(r);
            return out;
        }
        if (conditional && r.status == 200 && !fromCache) {
            std::string etag = r.header("etag");
            if (!etag.empty()) {
                std::lock_guard<std::mutex> lock(m_etagMutex);
                if (m_etags.size() >= kMaxEtagEntries && !m_etags.count(key)) m_etags.clear();
                m_etags[key] = {etag + '\n' + r.header("link"), r.body};
            }
        }

        out.status = r.status;
        out.raw = std::move(r.body);
        out.headers = std::move(r.headers);
        if (!out.raw.empty()) {
            out.data = json::parse(out.raw, nullptr, false);
            if (out.data.is_discarded()) out.data = json();
        }
        if (!out.ok()) t_lastError = HttpError(out.status, out.data);
    } catch (const std::exception& e) {
        t_lastError = std::string("Request failed: ") + e.what();
    }
    return out;
}

std::optional<json> GitHubAccount::Graphql(const std::string& query, const json& variables) {
    try {
        json payload = {{"query", query}, {"variables", variables.is_null() ? json::object() : variables}};
        ApiResponse r = Request("POST", "/graphql", payload);
        if (r.status == 0) {
            t_lastError = "GraphQL request failed: " + t_lastError;
            return std::nullopt;
        }
        if (r.status != 200) {
            std::string text = Trim(r.raw);
            t_lastError = "GraphQL HTTP " + std::to_string(r.status);
            if (!text.empty()) t_lastError += ": " + Utf8Prefix(text, 200);
            return std::nullopt;
        }
        if (!r.data.is_object()) {
            t_lastError = "Invalid GraphQL response.";
            return std::nullopt;
        }
        const json* errors = Child(r.data, "errors");
        if (errors && errors->is_array() && !errors->empty()) {
            std::string messages;
            size_t n = 0;
            for (const auto& err : *errors) {
                if (n++ == 3) break;
                std::string msg = Str(err, "message");
                if (msg.empty()) continue;
                if (!messages.empty()) messages += " | ";
                messages += msg;
            }
            t_lastError = messages.empty() ? "GraphQL returned errors." : "GraphQL error: " + messages;
            return std::nullopt;
        }
        auto data = r.data.find("data");
        if (data == r.data.end() || data->is_null()) {
            t_lastError = "GraphQL returned no data.";
            return std::nullopt;
        }
        return std::move(*data);
    } catch (const std::exception& e) {
        t_lastError = std::string("GraphQL request failed: ") + e.what();
        return std::nullopt;
    }
}

// --- Repositories ---

std::vector<Repository> GitHubAccount::GetRepos(const std::string& sort) {
    return Guarded([&] {
        Params params = {{"sort", sort},
                         {"direction", "desc"},
                         {"affiliation", "owner,collaborator,organization_member"}};
        return FetchPages<Repository>(*this, "/user/repos", params, 100, Append<Repository>());
    });
}

std::vector<Repository> GitHubAccount::GetStarred() {
    return Guarded([&] {
        auto repos = FetchPages<Repository>(*this, "/user/starred", {}, 100, Append<Repository>());
        SortByPushedDesc(repos);
        return repos;
    });
}

std::vector<Repository> GitHubAccount::GetWatched() {
    return Guarded([&] {
        auto repos = FetchPages<Repository>(*this, "/user/subscriptions", {}, 100, Append<Repository>());
        SortByPushedDesc(repos);
        return repos;
    });
}

std::optional<Repository> GitHubAccount::GetRepo(const std::string& owner, const std::string& repo) {
    return Guarded([&]() -> std::optional<Repository> {
        ApiResponse r = Request("GET", RepoPath(owner, repo));
        if (r.status != 200) return std::nullopt;
        return Repository::FromJson(r.data);
    });
}

std::vector<Repository> GitHubAccount::GetForks(const std::string& owner, const std::string& repo,
                                                const std::string& sort) {
    return Guarded([&] {
        return FetchPages<Repository>(*this, RepoPath(owner, repo) + "/forks", {{"sort", sort}}, 100,
                                      Append<Repository>());
    });
}

std::pair<std::vector<Stargazer>, bool> GitHubAccount::GetStargazers(const std::string& owner,
                                                                     const std::string& repo, int page,
                                                                     int perPage) {
    return Guarded([&]() -> std::pair<std::vector<Stargazer>, bool> {
        // The star media type adds when each user starred the repo.
        ApiResponse r = Request(
            "GET",
            WithQuery(RepoPath(owner, repo) + "/stargazers",
                      {{"per_page", std::to_string(perPage)}, {"page", std::to_string(page)}}),
            json(), {"Accept: application/vnd.github.star+json"});
        if (r.status != 200) return {{}, false};
        std::vector<Stargazer> out;
        if (r.data.is_array()) {
            out.reserve(r.data.size());
            for (const auto& item : r.data) out.push_back(Stargazer::FromJson(item));
        }
        auto links = ParseLinks(r.headers.count("link") ? r.headers["link"] : std::string());
        bool more = links.empty() ? out.size() == static_cast<size_t>(perPage) : links.count("next") > 0;
        return {std::move(out), more};
    });
}

std::string GitHubAccount::GetRepoPermission(const std::string& owner, const std::string& repo) {
    return Guarded([&]() -> std::string {
        ApiResponse r = Request("GET", RepoPath(owner, repo));
        if (r.status != 200) return "";
        const json* perms = Child(r.data, "permissions");
        if (!perms) return "";
        if (Bool(*perms, "admin")) return "admin";
        if (Bool(*perms, "maintain")) return "maintain";
        if (Bool(*perms, "push")) return "write";
        if (Bool(*perms, "triage")) return "triage";
        if (Bool(*perms, "pull")) return "read";
        return "";
    });
}

bool GitHubAccount::CanMerge(const std::string& owner, const std::string& repo) {
    std::string permission = GetRepoPermission(owner, repo);
    return permission == "admin" || permission == "maintain" || permission == "write";
}

bool GitHubAccount::IsStarred(const std::string& owner, const std::string& repo) {
    return Guarded([&] {
        ApiResponse r = Request("GET", "/user/starred/" + owner + "/" + repo);
        if (r.status == 404) t_lastError.clear();  // 404 is the API's "no"
        return r.status == 204;
    });
}

bool GitHubAccount::StarRepo(const std::string& owner, const std::string& repo) {
    return Guarded([&] { return Expect(Request("PUT", "/user/starred/" + owner + "/" + repo), {204}); });
}

bool GitHubAccount::UnstarRepo(const std::string& owner, const std::string& repo) {
    return Guarded([&] { return Expect(Request("DELETE", "/user/starred/" + owner + "/" + repo), {204}); });
}

bool GitHubAccount::IsWatching(const std::string& owner, const std::string& repo) {
    return Guarded([&] {
        ApiResponse r = Request("GET", RepoPath(owner, repo) + "/subscription");
        if (r.status == 404) t_lastError.clear();
        return r.status == 200;
    });
}

bool GitHubAccount::WatchRepo(const std::string& owner, const std::string& repo) {
    return Guarded([&] {
        return Expect(Request("PUT", RepoPath(owner, repo) + "/subscription", {{"subscribed", true}}), {200});
    });
}

bool GitHubAccount::UnwatchRepo(const std::string& owner, const std::string& repo) {
    return Guarded([&] { return Expect(Request("DELETE", RepoPath(owner, repo) + "/subscription"), {204}); });
}

// --- Issues ---

std::vector<Issue> GitHubAccount::GetIssues(const std::string& owner, const std::string& repo,
                                            const std::string& state) {
    return Guarded([&] {
        return FetchPages<Issue>(*this, RepoPath(owner, repo) + "/issues",
                                 {{"state", state}, {"sort", "updated"}, {"direction", "desc"}}, 100,
                                 [](const json& item, std::vector<Issue>& out) {
                                     // The issues endpoint lists pull requests too.
                                     if (!item.contains("pull_request")) out.push_back(Issue::FromJson(item));
                                 });
    });
}

std::optional<Issue> GitHubAccount::GetIssue(const std::string& owner, const std::string& repo, int number) {
    return Guarded([&]() -> std::optional<Issue> {
        ApiResponse r = Request("GET", RepoPath(owner, repo) + "/issues/" + std::to_string(number));
        if (r.status != 200) return std::nullopt;
        return Issue::FromJson(r.data);
    });
}

std::optional<Issue> GitHubAccount::CreateIssue(const std::string& owner, const std::string& repo,
                                                const std::string& title, const std::string& body,
                                                const std::vector<std::string>& labels) {
    return Guarded([&]() -> std::optional<Issue> {
        json data = {{"title", title}, {"body", body}};
        if (!labels.empty()) data["labels"] = labels;
        ApiResponse r = Request("POST", RepoPath(owner, repo) + "/issues", data);
        if (!Expect(r, {201})) return std::nullopt;
        return Issue::FromJson(r.data);
    });
}

namespace {
json EditFields(const std::optional<std::string>& title, const std::optional<std::string>& body,
                const std::optional<std::string>& state) {
    json data = json::object();
    if (title) data["title"] = *title;
    if (body) data["body"] = *body;
    if (state) data["state"] = *state;
    return data;
}
}  // namespace

std::optional<Issue> GitHubAccount::UpdateIssue(const std::string& owner, const std::string& repo, int number,
                                                const std::optional<std::string>& title,
                                                const std::optional<std::string>& body,
                                                const std::optional<std::string>& state) {
    return Guarded([&]() -> std::optional<Issue> {
        ApiResponse r = Request("PATCH", RepoPath(owner, repo) + "/issues/" + std::to_string(number),
                                EditFields(title, body, state));
        if (!Expect(r, {200})) return std::nullopt;
        return Issue::FromJson(r.data);
    });
}

bool GitHubAccount::CloseIssue(const std::string& owner, const std::string& repo, int number) {
    return UpdateIssue(owner, repo, number, std::nullopt, std::nullopt, std::string("closed")).has_value();
}

bool GitHubAccount::ReopenIssue(const std::string& owner, const std::string& repo, int number) {
    return UpdateIssue(owner, repo, number, std::nullopt, std::nullopt, std::string("open")).has_value();
}

std::vector<Comment> GitHubAccount::GetIssueComments(const std::string& owner, const std::string& repo,
                                                     int number) {
    return Guarded([&] {
        std::string path = RepoPath(owner, repo) + "/issues/" + std::to_string(number) + "/comments";
        return FetchPages<Comment>(*this, path, {}, 100, [](const json& item, std::vector<Comment>& out) {
                                       out.push_back(Comment::FromJson(item));
                                   });
    });
}

std::optional<Comment> GitHubAccount::CreateIssueComment(const std::string& owner, const std::string& repo,
                                                         int number, const std::string& body) {
    return Guarded([&]() -> std::optional<Comment> {
        ApiResponse r = Request("POST", RepoPath(owner, repo) + "/issues/" + std::to_string(number) + "/comments",
                                {{"body", body}});
        if (!Expect(r, {201})) return std::nullopt;
        return Comment::FromJson(r.data);
    });
}

bool GitHubAccount::DeleteIssueComment(const std::string& owner, const std::string& repo, long long commentId) {
    return Guarded([&] {
        return Expect(Request("DELETE", RepoPath(owner, repo) + "/issues/comments/" + std::to_string(commentId)),
                      {204});
    });
}

// --- Pull requests ---

std::vector<PullRequest> GitHubAccount::GetPullRequests(const std::string& owner, const std::string& repo,
                                                        const std::string& state) {
    return Guarded([&] {
        return FetchPages<PullRequest>(*this, RepoPath(owner, repo) + "/pulls",
                                       {{"state", state}, {"sort", "updated"}, {"direction", "desc"}}, 100,
                                       Append<PullRequest>());
    });
}

std::optional<PullRequest> GitHubAccount::GetPullRequest(const std::string& owner, const std::string& repo,
                                                         int number) {
    return Guarded([&]() -> std::optional<PullRequest> {
        ApiResponse r = Request("GET", RepoPath(owner, repo) + "/pulls/" + std::to_string(number));
        if (r.status != 200) return std::nullopt;
        return PullRequest::FromJson(r.data);
    });
}

std::optional<PullRequest> GitHubAccount::CreatePullRequest(const std::string& owner, const std::string& repo,
                                                            const std::string& title, const std::string& head,
                                                            const std::string& base, const std::string& body,
                                                            bool draft) {
    return Guarded([&]() -> std::optional<PullRequest> {
        json data = {{"title", title}, {"head", head}, {"base", base}, {"body", body}, {"draft", draft}};
        ApiResponse r = Request("POST", RepoPath(owner, repo) + "/pulls", data);
        if (!Expect(r, {201})) return std::nullopt;
        return PullRequest::FromJson(r.data);
    });
}

std::optional<PullRequest> GitHubAccount::UpdatePullRequest(const std::string& owner, const std::string& repo,
                                                            int number, const std::optional<std::string>& title,
                                                            const std::optional<std::string>& body,
                                                            const std::optional<std::string>& state) {
    return Guarded([&]() -> std::optional<PullRequest> {
        ApiResponse r = Request("PATCH", RepoPath(owner, repo) + "/pulls/" + std::to_string(number),
                                EditFields(title, body, state));
        if (!Expect(r, {200})) return std::nullopt;
        return PullRequest::FromJson(r.data);
    });
}

bool GitHubAccount::MergePullRequest(const std::string& owner, const std::string& repo, int number,
                                     const std::string& commitTitle, const std::string& commitMessage,
                                     const std::string& mergeMethod) {
    return Guarded([&] {
        json data = {{"merge_method", mergeMethod}};
        if (!commitTitle.empty()) data["commit_title"] = commitTitle;
        if (!commitMessage.empty()) data["commit_message"] = commitMessage;
        return Expect(Request("PUT", RepoPath(owner, repo) + "/pulls/" + std::to_string(number) + "/merge", data),
                      {200});
    });
}

bool GitHubAccount::ClosePullRequest(const std::string& owner, const std::string& repo, int number) {
    return UpdatePullRequest(owner, repo, number, std::nullopt, std::nullopt, std::string("closed")).has_value();
}

std::vector<Comment> GitHubAccount::GetPrReviewComments(const std::string& owner, const std::string& repo,
                                                        int number) {
    return Guarded([&] {
        std::string path = RepoPath(owner, repo) + "/pulls/" + std::to_string(number) + "/comments";
        return FetchPages<Comment>(*this, path, {}, 100, [](const json& item, std::vector<Comment>& out) {
                                       out.push_back(Comment::FromJson(item, "review"));
                                   });
    });
}

std::vector<Comment> GitHubAccount::GetPrComments(const std::string& owner, const std::string& repo, int number) {
    return Guarded([&] {
        // The two lists are independent: fetch them side by side.
        std::vector<Comment> review;
        std::string reviewError;
        std::thread reviewThread([&] {
            review = Guarded([&] { return GetPrReviewComments(owner, repo, number); });
            reviewError = t_lastError;
        });
        std::vector<Comment> comments = GetIssueComments(owner, repo, number);
        reviewThread.join();
        if (t_lastError.empty()) t_lastError = reviewError;
        comments.insert(comments.end(), std::make_move_iterator(review.begin()),
                        std::make_move_iterator(review.end()));
        std::stable_sort(comments.begin(), comments.end(),
                         [](const Comment& a, const Comment& b) { return a.createdAt < b.createdAt; });
        return comments;
    });
}

std::optional<Comment> GitHubAccount::CreatePrComment(const std::string& owner, const std::string& repo,
                                                      int number, const std::string& body) {
    return CreateIssueComment(owner, repo, number, body);
}

// --- Discussions ---

std::optional<Discussion> GitHubAccount::GetDiscussion(const std::string& owner, const std::string& repo,
                                                       int number, int commentsFirst) {
    return Guarded([&]() -> std::optional<Discussion> {
        static const std::string query = R"(
        query GetDiscussion($owner: String!, $repo: String!, $number: Int!, $commentsFirst: Int!) {
          repository(owner: $owner, name: $repo) {
            discussion(number: $number) {
              id
              number
              title
              body
              url
              isAnswered
              createdAt
              updatedAt
              author {
                login
                avatarUrl
              }
              category {
                name
              }
              comments(first: $commentsFirst) {
                totalCount
                pageInfo {
                  hasNextPage
                  endCursor
                }
                )" + CommentNodesQuery() + R"(
              }
            }
          }
        }
        )";
        auto data = Graphql(query, {{"owner", owner}, {"repo", repo}, {"number", number},
                                    {"commentsFirst", commentsFirst}});
        if (!data) return std::nullopt;
        const json* repository = Child(*data, "repository");
        const json* discussion = repository ? Child(*repository, "discussion") : nullptr;
        if (!discussion) {
            t_lastError = "Discussion not found or access denied.";
            return std::nullopt;
        }
        return Discussion::FromGraphql(*discussion);
    });
}

std::optional<GitHubAccount::CommentPage> GitHubAccount::GetDiscussionComments(
    const std::string& owner, const std::string& repo, int number, int first, const std::string& after) {
    return Guarded([&]() -> std::optional<CommentPage> {
        static const std::string query = R"(
        query GetDiscussionComments($owner: String!, $repo: String!, $number: Int!, $first: Int!, $after: String) {
          repository(owner: $owner, name: $repo) {
            discussion(number: $number) {
              comments(first: $first, after: $after) {
                pageInfo {
                  hasNextPage
                  endCursor
                }
                )" + CommentNodesQuery() + R"(
              }
            }
          }
        }
        )";
        auto data = Graphql(query, {{"owner", owner}, {"repo", repo}, {"number", number}, {"first", first},
                                    {"after", after.empty() ? json() : json(after)}});
        if (!data) return std::nullopt;
        CommentPage page;
        const json* repository = Child(*data, "repository");
        const json* discussion = repository ? Child(*repository, "discussion") : nullptr;
        const json* comments = discussion ? Child(*discussion, "comments") : nullptr;
        if (comments) {
            if (const json* nodes = Child(*comments, "nodes"))
                page.comments = Discussion::FlattenCommentNodes(*nodes);
            if (const json* info = Child(*comments, "pageInfo")) {
                page.hasNextPage = Bool(*info, "hasNextPage");
                page.endCursor = Str(*info, "endCursor");
            }
        }
        return page;
    });
}

std::optional<DiscussionComment> GitHubAccount::CreateDiscussionComment(const std::string& discussionId,
                                                                        const std::string& body) {
    return Guarded([&]() -> std::optional<DiscussionComment> {
        static const std::string mutation = std::string(R"(
        mutation AddDiscussionComment($discussionId: ID!, $body: String!) {
          addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
            comment {)") + kDiscussionCommentFields + R"(
            }
          }
        }
        )";
        auto data = Graphql(mutation, {{"discussionId", discussionId}, {"body", body}});
        if (!data) return std::nullopt;
        const json* added = Child(*data, "addDiscussionComment");
        const json* comment = added ? Child(*added, "comment") : nullptr;
        if (!comment) {
            t_lastError = "Comment was not created.";
            return std::nullopt;
        }
        return DiscussionComment::FromGraphql(*comment);
    });
}

// --- Commits and branches ---

std::pair<std::vector<Commit>, bool> GitHubAccount::GetCommits(const std::string& owner, const std::string& repo,
                                                               const std::string& sha, int page, int perPage) {
    return Guarded([&]() -> std::pair<std::vector<Commit>, bool> {
        Params params = {{"per_page", std::to_string(perPage)}, {"page", std::to_string(page)}};
        if (!sha.empty()) params.emplace_back("sha", sha);
        ApiResponse r = Request("GET", WithQuery(RepoPath(owner, repo) + "/commits", params));
        if (r.status != 200) return {{}, false};
        std::vector<Commit> commits;
        if (r.data.is_array()) {
            commits.reserve(r.data.size());
            for (const auto& item : r.data) commits.push_back(Commit::FromJson(item));
        }
        // GitHub sends rel="next" while more pages remain; without a Link header, a full page
        // probably means more.
        auto links = ParseLinks(r.headers.count("link") ? r.headers["link"] : std::string());
        bool more = links.empty() ? commits.size() == static_cast<size_t>(perPage) : links.count("next") > 0;
        return {std::move(commits), more};
    });
}

std::optional<Commit> GitHubAccount::GetCommit(const std::string& owner, const std::string& repo,
                                               const std::string& sha) {
    return Guarded([&]() -> std::optional<Commit> {
        ApiResponse r = Request("GET", RepoPath(owner, repo) + "/commits/" + EncodePath(sha));
        if (r.status != 200) return std::nullopt;
        return Commit::FromJson(r.data);
    });
}

namespace {
void SortBranches(std::vector<Branch>& branches) {
    // Newest first; branches without a date (0) end up last.
    std::stable_sort(branches.begin(), branches.end(),
                     [](const Branch& a, const Branch& b) { return a.lastCommitDate > b.lastCommitDate; });
}

// GraphQL returns every branch's commit date in one request per 100 branches; it can't sort by
// them server side, so we sort here. nullopt means "use REST".
std::optional<std::vector<Branch>> BranchesGraphql(GitHubAccount& gh, const std::string& owner,
                                                   const std::string& repo) {
    static const char* const query = R"(
        query($owner: String!, $name: String!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            defaultBranchRef { name }
            refs(refPrefix: "refs/heads/", first: 100, after: $cursor) {
              pageInfo { hasNextPage endCursor }
              nodes {
                name
                target { ... on Commit { oid committedDate } }
              }
            }
          }
        }
        )";
    std::vector<Branch> branches;
    std::string defaultName;
    json cursor;
    while (true) {
        auto data = gh.Graphql(query, {{"owner", owner}, {"name", repo}, {"cursor", cursor}});
        if (!data) return std::nullopt;
        const json* repository = Child(*data, "repository");
        if (!repository) return std::nullopt;
        if (defaultName.empty())
            if (const json* ref = Child(*repository, "defaultBranchRef")) defaultName = Str(*ref, "name");
        const json* refs = Child(*repository, "refs");
        if (!refs) break;
        if (const json* nodes = Child(*refs, "nodes"); nodes && nodes->is_array()) {
            for (const auto& node : *nodes) {
                Branch b;
                b.name = Str(node, "name");
                if (const json* target = Child(node, "target")) {
                    b.sha = Str(*target, "oid");
                    b.lastCommitDate = ParseIsoTime(Str(*target, "committedDate"));
                }
                branches.push_back(std::move(b));
            }
        }
        const json* info = Child(*refs, "pageInfo");
        if (!info || !Bool(*info, "hasNextPage")) break;
        cursor = Str(*info, "endCursor");
    }
    for (auto& b : branches) b.isDefault = !defaultName.empty() && b.name == defaultName;
    SortBranches(branches);
    return branches;
}
}  // namespace

std::vector<Branch> GitHubAccount::GetBranches(const std::string& owner, const std::string& repo) {
    return Guarded([&] {
        if (auto branches = BranchesGraphql(*this, owner, repo)) return std::move(*branches);

        // REST: list the branches, then one commit request each (in parallel) for the dates.
        std::string base = RepoPath(owner, repo);
        auto branches = FetchPages<Branch>(*this, base + "/branches", {}, 100,
                                           [](const json& item, std::vector<Branch>& out) {
                                               Branch b;
                                               b.name = Str(item, "name");
                                               if (const json* commit = Child(item, "commit"))
                                                   b.sha = Str(*commit, "sha");
                                               out.push_back(std::move(b));
                                           });
        std::string listError = t_lastError;
        ParallelFor(branches.size(), [&](size_t i) {
            Branch& b = branches[i];
            if (b.sha.empty()) return;
            ApiResponse r = Request("GET", base + "/commits/" + b.sha);
            if (r.status != 200) return;
            const json* commit = Child(r.data, "commit");
            const json* committer = commit ? Child(*commit, "committer") : nullptr;
            if (committer) b.lastCommitDate = ParseIsoTime(Str(*committer, "date"));
        });
        // The REST list doesn't say which branch is the default; the repo does.
        if (auto repoInfo = GetRepo(owner, repo))
            for (auto& b : branches) b.isDefault = b.name == repoInfo->defaultBranch;
        t_lastError = listError;
        SortBranches(branches);
        return branches;
    });
}

// --- Search and users ---

std::vector<Repository> GitHubAccount::SearchRepos(const std::string& query, const std::string& sort,
                                                   int perPage) {
    return Guarded([&] {
        Params params = {{"q", query}, {"per_page", std::to_string(perPage)}};
        if (!sort.empty() && sort != "best-match") params.emplace_back("sort", sort);
        ApiResponse r = Request("GET", WithQuery("/search/repositories", params));
        std::vector<Repository> repos;
        if (r.status != 200) return repos;
        if (const json* items = Child(r.data, "items"); items && items->is_array())
            for (const auto& item : *items) repos.push_back(Repository::FromJson(item));
        return repos;
    });
}

std::vector<UserProfile> GitHubAccount::SearchUsers(const std::string& query, const std::string& sort,
                                                    int perPage) {
    return Guarded([&] {
        Params params = {{"q", query}, {"per_page", std::to_string(perPage)}};
        if (!sort.empty() && sort != "best-match") params.emplace_back("sort", sort);
        ApiResponse r = Request("GET", WithQuery("/search/users", params));
        std::vector<UserProfile> users;
        if (r.status != 200) return users;
        if (const json* items = Child(r.data, "items"); items && items->is_array())
            for (const auto& item : *items) users.push_back(BasicProfile(item));
        return users;
    });
}

std::optional<UserProfile> GitHubAccount::GetUser(const std::string& username) {
    return Guarded([&]() -> std::optional<UserProfile> {
        ApiResponse r = Request("GET", "/users/" + UrlEncode(username));
        if (r.status != 200) return std::nullopt;
        return UserProfile::FromJson(r.data);
    });
}

std::vector<Repository> GitHubAccount::GetUserRepos(const std::string& username, const std::string& sort) {
    return Guarded([&] {
        return FetchPages<Repository>(*this, "/users/" + UrlEncode(username) + "/repos",
                                      {{"sort", sort}, {"direction", "desc"}}, 100, Append<Repository>());
    });
}

std::vector<UserProfile> GitHubAccount::GetFollowing() {
    return Guarded([&] {
        return FetchPages<UserProfile>(*this, "/user/following", {}, 100,
                                       [](const json& item, std::vector<UserProfile>& out) {
                                           out.push_back(BasicProfile(item));
                                       });
    });
}

bool GitHubAccount::IsFollowing(const std::string& username) {
    return Guarded([&] {
        ApiResponse r = Request("GET", "/user/following/" + UrlEncode(username));
        if (r.status == 404) t_lastError.clear();
        return r.status == 204;
    });
}

bool GitHubAccount::FollowUser(const std::string& username) {
    return Guarded([&] { return Expect(Request("PUT", "/user/following/" + UrlEncode(username)), {204}); });
}

bool GitHubAccount::UnfollowUser(const std::string& username) {
    return Guarded([&] { return Expect(Request("DELETE", "/user/following/" + UrlEncode(username)), {204}); });
}

// --- Actions ---

std::vector<Workflow> GitHubAccount::GetWorkflows(const std::string& owner, const std::string& repo) {
    return Guarded([&] {
        return FetchPages<Workflow>(*this, RepoPath(owner, repo) + "/actions/workflows", {}, 100,
                                    Append<Workflow>(), "workflows");
    });
}

std::vector<WorkflowRun> GitHubAccount::GetWorkflowRuns(const std::string& owner, const std::string& repo,
                                                        long long workflowId, const std::string& branch,
                                                        const std::string& status, int perPage) {
    return Guarded([&] {
        Params params = {{"per_page", std::to_string(perPage)}};
        if (!branch.empty()) params.emplace_back("branch", branch);
        if (!status.empty()) params.emplace_back("status", status);
        std::string path = RepoPath(owner, repo) + "/actions/runs";
        if (workflowId)
            path = RepoPath(owner, repo) + "/actions/workflows/" + std::to_string(workflowId) + "/runs";
        ApiResponse r = Request("GET", WithQuery(path, params));
        std::vector<WorkflowRun> runs;
        if (r.status != 200) return runs;
        if (const json* items = Child(r.data, "workflow_runs"); items && items->is_array())
            for (const auto& item : *items) runs.push_back(WorkflowRun::FromJson(item));
        return runs;
    });
}

std::optional<WorkflowRun> GitHubAccount::GetWorkflowRun(const std::string& owner, const std::string& repo,
                                                         long long runId) {
    return Guarded([&]() -> std::optional<WorkflowRun> {
        ApiResponse r = Request("GET", RepoPath(owner, repo) + "/actions/runs/" + std::to_string(runId));
        if (r.status != 200) return std::nullopt;
        return WorkflowRun::FromJson(r.data);
    });
}

std::vector<WorkflowJob> GitHubAccount::GetWorkflowRunJobs(const std::string& owner, const std::string& repo,
                                                           long long runId) {
    return Guarded([&] {
        std::string path = RepoPath(owner, repo) + "/actions/runs/" + std::to_string(runId) + "/jobs";
        return FetchPages<WorkflowJob>(*this, path, {}, 100, Append<WorkflowJob>(), "jobs");
    });
}

bool GitHubAccount::RerunWorkflow(const std::string& owner, const std::string& repo, long long runId) {
    return Guarded([&] {
        return Expect(Request("POST", RepoPath(owner, repo) + "/actions/runs/" + std::to_string(runId) + "/rerun"),
                      {201});
    });
}

bool GitHubAccount::RerunFailedJobs(const std::string& owner, const std::string& repo, long long runId) {
    return Guarded([&] {
        return Expect(Request("POST", RepoPath(owner, repo) + "/actions/runs/" + std::to_string(runId) +
                                          "/rerun-failed-jobs"),
                      {201});
    });
}

bool GitHubAccount::CancelWorkflowRun(const std::string& owner, const std::string& repo, long long runId) {
    return Guarded([&] {
        std::string path = RepoPath(owner, repo) + "/actions/runs/" + std::to_string(runId) + "/cancel";
        return Expect(Request("POST", path), {202});
    });
}

std::string GitHubAccount::GetWorkflowRunLogsUrl(const std::string& owner, const std::string& repo,
                                                 long long runId) {
    return Guarded([&]() -> std::string {
        t_lastError.clear();
        HttpRequest req;
        req.url = ApiUrl(RepoPath(owner, repo) + "/actions/runs/" + std::to_string(runId) + "/logs");
        req.headers = ApiHeaders(m_prefs->GetString("access_token"), req.url, {});
        req.followRedirects = false;
        HttpResponse r = HttpSend(req);
        if (r.completed && r.status == 302) return r.header("location");
        t_lastError = r.completed ? HttpError(r.status, json::parse(r.body, nullptr, false)) : TransportError(r);
        return "";
    });
}

std::optional<std::string> GitHubAccount::GetJobLogs(const std::string& owner, const std::string& repo,
                                                     long long jobId) {
    return Guarded([&]() -> std::optional<std::string> {
        t_lastError.clear();
        HttpRequest req;
        req.url = ApiUrl(RepoPath(owner, repo) + "/actions/jobs/" + std::to_string(jobId) + "/logs");
        req.headers = ApiHeaders(m_prefs->GetString("access_token"), req.url,
                                 {"Accept: application/vnd.github.v3+json"});
        HttpResponse r = SendWithRedirects(std::move(req));
        if (r.completed && r.status == 200) return std::move(r.body);
        t_lastError = r.completed ? HttpError(r.status, json::parse(r.body, nullptr, false)) : TransportError(r);
        return std::nullopt;
    });
}

std::vector<Artifact> GitHubAccount::GetRunArtifacts(const std::string& owner, const std::string& repo,
                                                     long long runId) {
    return Guarded([&] {
        std::string path = RepoPath(owner, repo) + "/actions/runs/" + std::to_string(runId) + "/artifacts";
        return FetchPages<Artifact>(*this, path, {}, 100, Append<Artifact>(), "artifacts");
    });
}

bool GitHubAccount::DownloadArtifact(const std::string& owner, const std::string& repo, long long artifactId,
                                     const std::string& destPath, const ProgressFn& progress) {
    return Guarded([&] {
        t_lastError.clear();
        // Expired artifacts answer 410 Gone.
        HttpRequest req;
        req.url = ApiUrl(RepoPath(owner, repo) + "/actions/artifacts/" + std::to_string(artifactId) + "/zip");
        req.headers = ApiHeaders(m_prefs->GetString("access_token"), req.url, {});
        return Download(std::move(req), destPath, progress);
    });
}

// --- Releases ---

std::vector<Release> GitHubAccount::GetReleases(const std::string& owner, const std::string& repo, int perPage) {
    return Guarded([&] {
        return FetchPages<Release>(*this, RepoPath(owner, repo) + "/releases", {}, perPage, Append<Release>());
    });
}

std::optional<Release> GitHubAccount::GetRelease(const std::string& owner, const std::string& repo,
                                                 long long releaseId) {
    return Guarded([&]() -> std::optional<Release> {
        ApiResponse r = Request("GET", RepoPath(owner, repo) + "/releases/" + std::to_string(releaseId));
        if (r.status != 200) return std::nullopt;
        return Release::FromJson(r.data);
    });
}

std::optional<Release> GitHubAccount::GetLatestRelease(const std::string& owner, const std::string& repo) {
    return Guarded([&]() -> std::optional<Release> {
        ApiResponse r = Request("GET", RepoPath(owner, repo) + "/releases/latest");
        if (r.status != 200) return std::nullopt;
        return Release::FromJson(r.data);
    });
}

std::optional<Release> GitHubAccount::GetReleaseByTag(const std::string& owner, const std::string& repo,
                                                      const std::string& tag) {
    return Guarded([&]() -> std::optional<Release> {
        ApiResponse r = Request("GET", RepoPath(owner, repo) + "/releases/tags/" + EncodePath(tag));
        if (r.status != 200) return std::nullopt;
        return Release::FromJson(r.data);
    });
}

bool GitHubAccount::DownloadAsset(const std::string& owner, const std::string& repo, long long assetId,
                                  const std::string& destPath, const ProgressFn& progress) {
    return Guarded([&] {
        t_lastError.clear();
        HttpRequest req;
        req.url = ApiUrl(RepoPath(owner, repo) + "/releases/assets/" + std::to_string(assetId));
        req.headers =
            ApiHeaders(m_prefs->GetString("access_token"), req.url, {"Accept: application/octet-stream"});
        return Download(std::move(req), destPath, progress);
    });
}

bool GitHubAccount::DownloadUrl(const std::string& url, const std::string& destPath, const ProgressFn& progress) {
    return Guarded([&] {
        t_lastError.clear();
        HttpRequest req;
        req.url = ApiUrl(url);
        req.headers = ApiHeaders(m_prefs->GetString("access_token"), req.url, {});
        return Download(std::move(req), destPath, progress);
    });
}

// --- Notifications ---

namespace {
Params NotificationParams(bool all, bool participating) {
    Params params;
    if (all) params.emplace_back("all", "true");
    if (participating) params.emplace_back("participating", "true");
    return params;
}

json LastReadBody(const std::string& lastReadAt) {
    json data = json::object();  // an empty body means "now"
    if (!lastReadAt.empty()) data["last_read_at"] = lastReadAt;
    return data;
}
}  // namespace

std::vector<Notification> GitHubAccount::GetNotifications(bool all, bool participating) {
    return Guarded([&] {
        return FetchPages<Notification>(*this, "/notifications", NotificationParams(all, participating), 50,
                                        Append<Notification>());
    });
}

std::vector<Notification> GitHubAccount::GetRepoNotifications(const std::string& owner, const std::string& repo,
                                                              bool all, bool participating) {
    return Guarded([&] {
        return FetchPages<Notification>(*this, RepoPath(owner, repo) + "/notifications",
                                        NotificationParams(all, participating), 50, Append<Notification>());
    });
}

bool GitHubAccount::MarkNotificationsRead(const std::string& lastReadAt) {
    return Guarded([&] { return Expect(Request("PUT", "/notifications", LastReadBody(lastReadAt)), {202, 205}); });
}

bool GitHubAccount::MarkRepoNotificationsRead(const std::string& owner, const std::string& repo,
                                              const std::string& lastReadAt) {
    return Guarded([&] {
        ApiResponse r = Request("PUT", RepoPath(owner, repo) + "/notifications", LastReadBody(lastReadAt));
        return Expect(r, {202, 205});
    });
}

bool GitHubAccount::MarkThreadRead(const std::string& threadId) {
    return Guarded([&] { return Expect(Request("PATCH", "/notifications/threads/" + threadId), {200, 205}); });
}

bool GitHubAccount::MarkThreadDone(const std::string& threadId) {
    return Guarded([&] { return Expect(Request("DELETE", "/notifications/threads/" + threadId), {204}); });
}

std::optional<json> GitHubAccount::GetThreadSubscription(const std::string& threadId) {
    return Guarded([&]() -> std::optional<json> {
        ApiResponse r = Request("GET", "/notifications/threads/" + threadId + "/subscription");
        if (r.status != 200) return std::nullopt;
        return std::move(r.data);
    });
}

bool GitHubAccount::SubscribeToThread(const std::string& threadId) {
    return Guarded([&] {
        json body = {{"subscribed", true}};
        return Expect(Request("PUT", "/notifications/threads/" + threadId + "/subscription", body), {200});
    });
}

bool GitHubAccount::UnsubscribeFromThread(const std::string& threadId) {
    return Guarded([&] {
        return Expect(Request("DELETE", "/notifications/threads/" + threadId + "/subscription"), {204});
    });
}

bool GitHubAccount::MuteThread(const std::string& threadId) {
    return Guarded([&] {
        return Expect(Request("PUT", "/notifications/threads/" + threadId + "/subscription", {{"ignored", true}}),
                      {200});
    });
}

// --- Events ---

namespace {
std::vector<Event> EventsOnePage(GitHubAccount& gh, const std::string& path, int perPage) {
    GitHubAccount::ApiResponse r = gh.Request("GET", WithQuery(path, {{"per_page", std::to_string(perPage)}}));
    std::vector<Event> events;
    if (r.status != 200 || !r.data.is_array()) return events;
    events.reserve(r.data.size());
    for (const auto& item : r.data) events.push_back(Event::FromJson(item));
    return events;
}
}  // namespace

std::vector<Event> GitHubAccount::GetReceivedEvents(int perPage, int maxPages) {
    return Guarded([&] {
        // GitHub keeps at most 300 received events, hence the page cap.
        return FetchPages<Event>(*this, "/users/" + UrlEncode(Username()) + "/received_events", {}, perPage,
                                 Append<Event>(), nullptr, std::max(maxPages, 1));
    });
}

std::vector<Event> GitHubAccount::GetUserEvents(const std::string& username, int perPage) {
    return Guarded([&] { return EventsOnePage(*this, "/users/" + UrlEncode(username) + "/events", perPage); });
}

std::vector<Event> GitHubAccount::GetRepoEvents(const std::string& owner, const std::string& repo, int perPage) {
    return Guarded([&] { return EventsOnePage(*this, RepoPath(owner, repo) + "/events", perPage); });
}

std::vector<Event> GitHubAccount::GetOrgEvents(const std::string& org, int perPage) {
    return Guarded([&] { return EventsOnePage(*this, "/orgs/" + UrlEncode(org) + "/events", perPage); });
}

// --- Contents ---

namespace {
std::string ContentsPath(const std::string& owner, const std::string& repo, const std::string& path,
                         const std::string& ref) {
    Params params;
    if (!ref.empty()) params.emplace_back("ref", ref);
    return WithQuery(RepoPath(owner, repo) + "/contents/" + EncodePath(path), params);
}
}  // namespace

std::optional<std::vector<ContentItem>> GitHubAccount::GetContents(const std::string& owner,
                                                                   const std::string& repo,
                                                                   const std::string& path,
                                                                   const std::string& ref) {
    return Guarded([&]() -> std::optional<std::vector<ContentItem>> {
        ApiResponse r = Request("GET", ContentsPath(owner, repo, path, ref));
        if (r.status != 200) return std::nullopt;
        std::vector<ContentItem> items;
        if (!r.data.is_array()) {
            items.push_back(ContentItem::FromJson(r.data));
            return items;
        }
        items.reserve(r.data.size());
        for (const auto& item : r.data) items.push_back(ContentItem::FromJson(item));
        // Directories first, then files, each alphabetically.
        std::sort(items.begin(), items.end(), [](const ContentItem& a, const ContentItem& b) {
            bool aDir = a.type == "dir";
            bool bDir = b.type == "dir";
            if (aDir != bDir) return aDir;
            return ToLower(a.name) < ToLower(b.name);
        });
        return items;
    });
}

std::optional<std::string> GitHubAccount::GetFileContent(const std::string& owner, const std::string& repo,
                                                         const std::string& path, const std::string& ref) {
    return Guarded([&]() -> std::optional<std::string> {
        // Not via GetContents: a directory holding one entry would look like a file there.
        ApiResponse r = Request("GET", ContentsPath(owner, repo, path, ref));
        if (r.status != 200 || !r.data.is_object()) return std::nullopt;
        std::string content = Str(r.data, "content");
        if (content.empty() || Str(r.data, "encoding") != "base64") return std::nullopt;
        std::string text = Base64Decode(content);
        if (!IsValidUtf8(text)) {
            t_lastError = "Binary file";
            return std::nullopt;
        }
        return text;
    });
}

std::optional<std::string> GitHubAccount::GetReadme(const std::string& owner, const std::string& repo,
                                                    const std::string& ref) {
    return Guarded([&]() -> std::optional<std::string> {
        Params params;
        if (!ref.empty()) params.emplace_back("ref", ref);
        ApiResponse r = Request("GET", WithQuery(RepoPath(owner, repo) + "/readme", params), json(),
                                {"Accept: application/vnd.github.raw"});
        if (r.status != 200) return std::nullopt;
        return std::move(r.raw);
    });
}

// --- Single pages ---

Page<Repository> GitHubAccount::GetReposPage(int page, const std::string& sort) {
    return Guarded([&] {
        Params params = {{"sort", sort},
                         {"direction", "desc"},
                         {"affiliation", "owner,collaborator,organization_member"}};
        return FetchOnePage<Repository>(*this, "/user/repos", params, kPageSize, page, Append<Repository>());
    });
}

Page<Repository> GitHubAccount::GetStarredPage(int page) {
    // "updated" sorts starred repositories by their last push, as the full list was sorted.
    return Guarded([&] {
        return FetchOnePage<Repository>(*this, "/user/starred", {{"sort", "updated"}, {"direction", "desc"}},
                                        kPageSize, page, Append<Repository>());
    });
}

Page<Repository> GitHubAccount::GetWatchedPage(int page) {
    return Guarded([&] {
        return FetchOnePage<Repository>(*this, "/user/subscriptions", {}, kPageSize, page, Append<Repository>());
    });
}

Page<UserProfile> GitHubAccount::GetFollowingPage(int page) {
    return Guarded([&] {
        return FetchOnePage<UserProfile>(*this, "/user/following", {}, kPageSize, page,
                                         [](const json& item, std::vector<UserProfile>& out) {
                                             out.push_back(BasicProfile(item));
                                         });
    });
}

Page<Notification> GitHubAccount::GetNotificationsPage(int page, bool all, bool participating) {
    return Guarded([&] {
        return FetchOnePage<Notification>(*this, "/notifications", NotificationParams(all, participating),
                                          kPageSize, page, Append<Notification>());
    });
}

Page<Event> GitHubAccount::GetReceivedEventsPage(int page) {
    return Guarded([&] {
        std::string user = Username();
        if (user.empty()) {
            Verify();
            user = Username();
        }
        auto out = FetchOnePage<Event>(*this, "/users/" + UrlEncode(user) + "/received_events", {}, 100, page,
                                       Append<Event>());
        if (page >= 3) out.hasMore = false;  // GitHub refuses pages past 300 events
        return out;
    });
}

Page<Issue> GitHubAccount::GetIssuesPage(const std::string& owner, const std::string& repo,
                                         const std::string& state, int page) {
    return Guarded([&] {
        return FetchOnePage<Issue>(*this, RepoPath(owner, repo) + "/issues",
                                   {{"state", state}, {"sort", "updated"}, {"direction", "desc"}}, kPageSize, page,
                                   [](const json& item, std::vector<Issue>& out) {
                                       // The issues endpoint lists pull requests too.
                                       if (!item.contains("pull_request")) out.push_back(Issue::FromJson(item));
                                   });
    });
}

Page<PullRequest> GitHubAccount::GetPullRequestsPage(const std::string& owner, const std::string& repo,
                                                     const std::string& state, int page) {
    return Guarded([&] {
        return FetchOnePage<PullRequest>(*this, RepoPath(owner, repo) + "/pulls",
                                         {{"state", state}, {"sort", "updated"}, {"direction", "desc"}}, kPageSize,
                                         page, Append<PullRequest>());
    });
}

Page<Repository> GitHubAccount::GetForksPage(const std::string& owner, const std::string& repo,
                                             const std::string& sort, int page) {
    return Guarded([&] {
        return FetchOnePage<Repository>(*this, RepoPath(owner, repo) + "/forks", {{"sort", sort}}, kPageSize, page,
                                        Append<Repository>());
    });
}

Page<Repository> GitHubAccount::GetUserReposPage(const std::string& username, const std::string& sort, int page) {
    return Guarded([&] {
        return FetchOnePage<Repository>(*this, "/users/" + UrlEncode(username) + "/repos",
                                        {{"sort", sort}, {"direction", "desc"}}, kPageSize, page,
                                        Append<Repository>());
    });
}

Page<Release> GitHubAccount::GetReleasesPage(const std::string& owner, const std::string& repo, int page) {
    return Guarded([&] {
        return FetchOnePage<Release>(*this, RepoPath(owner, repo) + "/releases", {}, kPageSize, page,
                                     Append<Release>());
    });
}

Page<WorkflowRun> GitHubAccount::GetWorkflowRunsPage(const std::string& owner, const std::string& repo,
                                                     long long workflowId, const std::string& branch,
                                                     const std::string& status, int page) {
    return Guarded([&] {
        Params params;
        if (!branch.empty()) params.emplace_back("branch", branch);
        if (!status.empty()) params.emplace_back("status", status);
        std::string path = RepoPath(owner, repo) + "/actions/runs";
        if (workflowId)
            path = RepoPath(owner, repo) + "/actions/workflows/" + std::to_string(workflowId) + "/runs";
        return FetchOnePage<WorkflowRun>(*this, path, params, kPageSize, page, Append<WorkflowRun>(),
                                         "workflow_runs");
    });
}

Page<Repository> GitHubAccount::SearchReposPage(const std::string& query, const std::string& sort, int page) {
    return Guarded([&] {
        Params params = {{"q", query}};
        if (!sort.empty() && sort != "best-match") params.emplace_back("sort", sort);
        auto out = FetchOnePage<Repository>(*this, "/search/repositories", params, kPageSize, page,
                                            Append<Repository>(), "items");
        if (page * kPageSize >= 1000) out.hasMore = false;  // search stops at 1000 results
        return out;
    });
}

Page<UserProfile> GitHubAccount::SearchUsersPage(const std::string& query, const std::string& sort, int page) {
    return Guarded([&] {
        Params params = {{"q", query}};
        if (!sort.empty() && sort != "best-match") params.emplace_back("sort", sort);
        auto out = FetchOnePage<UserProfile>(*this, "/search/users", params, kPageSize, page,
                                             [](const json& item, std::vector<UserProfile>& out) {
                                                 out.push_back(BasicProfile(item));
                                             },
                                             "items");
        if (page * kPageSize >= 1000) out.hasMore = false;
        return out;
    });
}
