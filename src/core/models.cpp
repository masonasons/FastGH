#include "core/models.h"

#include <cstdio>
#include <map>

// GitHub sends nulls (and the odd wrong type) anywhere, so every read goes
// through these helpers, which fall back instead of throwing.
namespace {

const json& NullJson() {
    static const json n;
    return n;
}
const json& EmptyObject() {
    static const json o = json::object();
    return o;
}

// j[key], or null when j is not an object or lacks the key.
const json& At(const json& j, const char* key) {
    if (!j.is_object()) return NullJson();
    auto it = j.find(key);
    return it == j.end() ? NullJson() : *it;
}
bool Has(const json& j, const char* key) { return j.is_object() && j.contains(key); }

// A nested object; {} when missing, null or not an object.
const json& Obj(const json& j, const char* key) {
    const json& v = At(j, key);
    return v.is_object() ? v : EmptyObject();
}

std::string Str(const json& j, const char* key, const std::string& fallback = "") {
    const json& v = At(j, key);
    return v.is_string() ? v.get<std::string>() : fallback;
}
long long Int(const json& j, const char* key, long long fallback = 0) {
    const json& v = At(j, key);
    if (v.is_number_integer()) return v.get<long long>();
    if (v.is_number_float()) return static_cast<long long>(v.get<double>());
    return fallback;
}
int Int32(const json& j, const char* key, int fallback = 0) {
    return static_cast<int>(Int(j, key, fallback));
}
bool Bool(const json& j, const char* key, bool fallback = false) {
    const json& v = At(j, key);
    return v.is_boolean() ? v.get<bool>() : fallback;
}
std::time_t Time(const json& j, const char* key) {
    const json& v = At(j, key);
    return v.is_string() ? ParseIsoTime(v.get_ref<const std::string&>()) : 0;
}

// Python's truth value of a JSON value.
bool Truthy(const json& v) {
    switch (v.type()) {
        case json::value_t::null: return false;
        case json::value_t::boolean: return v.get<bool>();
        case json::value_t::number_integer: return v.get<long long>() != 0;
        case json::value_t::number_unsigned: return v.get<unsigned long long>() != 0;
        case json::value_t::number_float: return v.get<double>() != 0.0;
        case json::value_t::string: return !v.get_ref<const std::string&>().empty();
        case json::value_t::array:
        case json::value_t::object: return !v.empty();
        default: return false;
    }
}

// Python's str() of a JSON value, as an f-string would show it.
std::string PyStr(const json& v) {
    switch (v.type()) {
        case json::value_t::string: return v.get<std::string>();
        case json::value_t::null: return "None";
        case json::value_t::boolean: return v.get<bool>() ? "True" : "False";
        default: return v.dump();
    }
}
// dict.get(key, fallback) shown with str(): fallback only when the key is missing.
std::string PyGet(const json& j, const char* key, const std::string& fallback = "") {
    return Has(j, key) ? PyStr(At(j, key)) : fallback;
}

// str(obj[key]) when the value is truthy, else "" (for Python's `if value:` checks).
std::string TruthyStr(const json& j, const char* key) {
    const json& v = At(j, key);
    return Truthy(v) ? PyStr(v) : std::string();
}

// First `n` code points (Python's s[:n]).
std::string Prefix(const std::string& s, size_t n) {
    size_t i = 0;
    while (i < s.size() && n > 0) {
        ++i;
        while (i < s.size() && (static_cast<unsigned char>(s[i]) & 0xC0) == 0x80) ++i;
        --n;
    }
    return s.substr(0, i);
}

std::string UtcDate(std::time_t t) {
    std::tm tm{};
#ifdef _WIN32
    gmtime_s(&tm, &t);
#else
    gmtime_r(&t, &tm);
#endif
    char buf[16];
    std::strftime(buf, sizeof buf, "%Y-%m-%d", &tm);
    return buf;
}

std::string LocalOrUnknown(std::time_t t) {
    return t ? FormatLocalTime(t, "%Y-%m-%d %H:%M") : "Unknown";
}

std::string Fixed(double v, int decimals, const char* unit) {
    char buf[64];
    std::snprintf(buf, sizeof buf, "%.*f %s", decimals, v, unit);
    return buf;
}

// ReleaseAsset / Artifact sizes, which go on to GB unlike content.py's.
std::string FormatSizeWithGb(long long size) {
    if (size < 1024) return std::to_string(size) + " B";
    if (size < 1024LL * 1024) return Fixed(size / 1024.0, 1, "KB");
    if (size < 1024LL * 1024 * 1024) return Fixed(size / (1024.0 * 1024), 1, "MB");
    return Fixed(size / (1024.0 * 1024 * 1024), 2, "GB");
}

long long Elapsed(std::time_t t) {
    return static_cast<long long>(std::time(nullptr)) - static_cast<long long>(t);
}

std::vector<Label> ParseLabels(const json& arr) {
    std::vector<Label> out;
    if (!arr.is_array()) return out;
    out.reserve(arr.size());
    for (const json& l : arr) out.push_back(Label::FromJson(l));
    return out;
}

std::vector<User> ParseUsers(const json& arr) {
    std::vector<User> out;
    if (!arr.is_array()) return out;
    out.reserve(arr.size());
    for (const json& u : arr) out.push_back(User::FromJson(u));
    return out;
}

// Comment previews: newlines flattened, cut at `max` code points with "...".
std::string Preview(const std::string& body, size_t max) {
    std::string flat = ReplaceAll(body, "\n", " ");
    if (Utf8Length(flat) > max) return Prefix(flat, max) + "...";
    return flat;
}

}  // namespace

// --- Repository ---

Repository Repository::FromJson(const json& data) {
    Repository r;
    r.id = Int(data, "id");
    r.name = Str(data, "name");
    r.fullName = Str(data, "full_name");
    r.description = Str(data, "description");
    r.owner = Str(Obj(data, "owner"), "login");
    r.stars = Int(data, "stargazers_count");
    r.forks = Int(data, "forks_count");
    r.openIssues = Int(data, "open_issues_count");
    r.language = Str(data, "language");
    r.updatedAt = Time(data, "updated_at");
    r.pushedAt = Time(data, "pushed_at");
    r.url = Str(data, "url");
    r.htmlUrl = Str(data, "html_url");
    r.isPrivate = Bool(data, "private");
    r.isFork = Bool(data, "fork");
    r.parentFullName = Str(Obj(data, "parent"), "full_name");
    r.defaultBranch = Str(data, "default_branch");
    return r;
}

std::string Repository::FormatDisplay() const {
    std::string desc = description.empty() ? "No description" : description;
    if (Utf8Length(desc) > 80) desc = Prefix(desc, 77) + "...";
    const std::string lang = language.empty() ? "Unknown" : language;
    const std::string pushed = pushedAt ? FormatRelativeTime(pushedAt) : "Unknown";
    return fullName + " - " + desc + "\n" + "Stars: " + std::to_string(stars) +
           " | Forks: " + std::to_string(forks) + " | Issues: " + std::to_string(openIssues) + " | " +
           lang + " | Pushed " + pushed;
}

std::string Repository::FormatSingleLine() const {
    const std::string lang = language.empty() ? "Unknown" : language;
    return fullName + " | " + std::to_string(stars) + " stars | " + lang + " | Pushed " +
           LocalOrUnknown(pushedAt);
}

// --- Users ---

User User::FromJson(const json& data) {
    User u;
    if (!Truthy(data)) {
        u.login = "unknown";
        return u;
    }
    u.login = Str(data, "login", "unknown");
    u.id = Int(data, "id");
    u.avatarUrl = Str(data, "avatar_url");
    return u;
}

UserProfile UserProfile::FromJson(const json& data) {
    UserProfile p;
    p.id = Int(data, "id");
    p.login = Str(data, "login");
    p.name = Str(data, "name");
    p.avatarUrl = Str(data, "avatar_url");
    p.htmlUrl = Str(data, "html_url");
    p.bio = Str(data, "bio");
    p.company = Str(data, "company");
    p.location = Str(data, "location");
    p.email = Str(data, "email");
    p.blog = Str(data, "blog");
    p.twitterUsername = Str(data, "twitter_username");
    p.publicRepos = Int(data, "public_repos");
    p.publicGists = Int(data, "public_gists");
    p.followers = Int(data, "followers");
    p.following = Int(data, "following");
    p.createdAt = Time(data, "created_at");
    p.updatedAt = Time(data, "updated_at");
    p.type = Str(data, "type", "User");
    return p;
}

std::string UserProfile::FormatDisplay() const {
    std::string out = login;
    if (!name.empty()) out += " (" + name + ")";
    if (!bio.empty()) {
        std::string preview = ReplaceAll(Prefix(bio, 50), "\n", " ");
        if (Utf8Length(bio) > 50) preview += "...";
        out += " - " + preview;
    }
    return out;
}

Stargazer Stargazer::FromJson(const json& data) {
    // The star media type wraps the user beside starred_at; the default one is the bare user.
    const json& user = Has(data, "user") ? Obj(data, "user") : (data.is_object() ? data : EmptyObject());
    Stargazer s;
    s.login = Str(user, "login");
    s.htmlUrl = Str(user, "html_url");
    s.type = Str(user, "type", "User");
    s.starredAt = Time(data, "starred_at");
    return s;
}

std::string Stargazer::FormatDisplay() const {
    if (starredAt) return login + " - starred " + FormatRelativeTime(starredAt);
    return login;
}

// --- Issues and pull requests ---

Label Label::FromJson(const json& data) {
    Label l;
    l.name = Str(data, "name");
    l.color = Str(data, "color");
    l.description = Str(data, "description");
    return l;
}

Comment Comment::FromJson(const json& data, const std::string& kind) {
    Comment c;
    c.id = Int(data, "id");
    c.body = Str(data, "body");
    c.user = User::FromJson(At(data, "user"));
    c.createdAt = Time(data, "created_at");
    c.updatedAt = Time(data, "updated_at");
    c.htmlUrl = Str(data, "html_url");
    c.kind = kind;
    return c;
}

// The comment list rows built in GUI/issues.py and GUI/pullrequests.py.
std::string Comment::FormatDisplay() const {
    const char* source = kind == "review" ? "[Review] " : "";
    return user.login + " (" + LocalOrUnknown(createdAt) + "): " + source + Preview(body, 50);
}

Issue Issue::FromJson(const json& data) {
    Issue i;
    i.id = Int(data, "id");
    i.number = Int32(data, "number");
    i.title = Str(data, "title");
    i.body = Str(data, "body");
    i.state = Str(data, "state", "open");
    i.user = User::FromJson(At(data, "user"));
    i.labels = ParseLabels(At(data, "labels"));
    i.assignees = ParseUsers(At(data, "assignees"));
    i.commentsCount = Int32(data, "comments");
    i.createdAt = Time(data, "created_at");
    i.updatedAt = Time(data, "updated_at");
    i.closedAt = Time(data, "closed_at");
    i.htmlUrl = Str(data, "html_url");
    i.isPullRequest = Has(data, "pull_request");
    return i;
}

std::string Issue::FormatDisplay() const {
    std::string out = "#" + std::to_string(number) + (state == "open" ? " [Open] " : " [Closed] ") + title;
    if (!labels.empty()) {
        std::string joined;
        for (size_t k = 0; k < labels.size(); ++k) {
            if (k) joined += ", ";
            joined += labels[k].name;
        }
        if (!joined.empty()) out += " [" + joined + "]";
    }
    return out + " - by " + user.login;
}

PullRequest PullRequest::FromJson(const json& data) {
    PullRequest p;
    p.id = Int(data, "id");
    p.number = Int32(data, "number");
    p.title = Str(data, "title");
    p.body = Str(data, "body");
    p.state = Str(data, "state", "open");
    p.user = User::FromJson(At(data, "user"));
    p.labels = ParseLabels(At(data, "labels"));
    p.assignees = ParseUsers(At(data, "assignees"));
    p.headRef = Str(Obj(data, "head"), "ref");
    p.baseRef = Str(Obj(data, "base"), "ref");
    p.merged = Bool(data, "merged");
    if (const json& m = At(data, "mergeable"); m.is_boolean()) p.mergeable = m.get<bool>();
    p.mergeableState = Str(data, "mergeable_state");
    if (const json& mb = At(data, "merged_by"); Truthy(mb)) p.mergedBy = User::FromJson(mb);
    p.mergedAt = Time(data, "merged_at");
    p.commentsCount = Int32(data, "comments");
    p.commitsCount = Int32(data, "commits");
    p.additions = Int32(data, "additions");
    p.deletions = Int32(data, "deletions");
    p.changedFiles = Int32(data, "changed_files");
    p.createdAt = Time(data, "created_at");
    p.updatedAt = Time(data, "updated_at");
    p.closedAt = Time(data, "closed_at");
    p.htmlUrl = Str(data, "html_url");
    p.draft = Bool(data, "draft");
    return p;
}

std::string PullRequest::FormatDisplay() const {
    const char* stateIcon = merged ? "[Merged]" : state == "open" ? (draft ? "[Draft]" : "[Open]") : "[Closed]";
    return "#" + std::to_string(number) + " " + stateIcon + " " + title + " (" + headRef + " -> " + baseRef +
           ") - by " + user.login;
}

// --- Discussions ---

namespace {

User ParseGraphqlAuthor(const json& data) {
    User u;
    if (!Truthy(data)) {
        u.login = "unknown";
        return u;
    }
    const json& raw = At(data, "databaseId");
    if (raw.is_number()) {
        u.id = raw.get<long long>();
    } else if (raw.is_string()) {
        try {
            u.id = std::stoll(raw.get_ref<const std::string&>());
        } catch (...) {
            u.id = 0;
        }
    }
    u.login = Str(data, "login", "unknown");
    u.avatarUrl = Str(data, "avatarUrl");
    return u;
}

}  // namespace

DiscussionComment DiscussionComment::FromGraphql(const json& data, bool isReply,
                                                 const std::string& parentAuthorLogin) {
    DiscussionComment c;
    c.id = Str(data, "id");
    if (const json& db = At(data, "databaseId"); db.is_number()) c.databaseId = db.get<long long>();
    c.body = Str(data, "body");
    c.author = ParseGraphqlAuthor(At(data, "author"));
    c.createdAt = Time(data, "createdAt");
    c.updatedAt = Time(data, "updatedAt");
    c.url = Str(data, "url");
    c.isReply = isReply;
    c.parentAuthorLogin = parentAuthorLogin;
    return c;
}

// The comment list rows built in GUI/discussions.py.
std::string DiscussionComment::FormatDisplay() const {
    std::string row = author.login + " (" + LocalOrUnknown(createdAt) + "): " + Preview(body, 60);
    if (!isReply) return row;
    return "[Reply" + (parentAuthorLogin.empty() ? std::string() : " to " + parentAuthorLogin) + "] " + row;
}

std::vector<DiscussionComment> Discussion::FlattenCommentNodes(const json& nodes) {
    std::vector<DiscussionComment> out;
    if (!nodes.is_array()) return out;
    out.reserve(nodes.size());
    for (const json& item : nodes) {
        out.push_back(DiscussionComment::FromGraphql(item));
        const std::string parent = out.back().author.login;
        const json& replies = At(Obj(item, "replies"), "nodes");
        if (!replies.is_array()) continue;
        for (const json& reply : replies) out.push_back(DiscussionComment::FromGraphql(reply, true, parent));
    }
    return out;
}

Discussion Discussion::FromGraphql(const json& data) {
    const json& conn = Obj(data, "comments");
    const json& pageInfo = Obj(conn, "pageInfo");
    Discussion d;
    d.id = Str(data, "id");
    d.number = Int32(data, "number");
    d.title = Str(data, "title");
    d.body = Str(data, "body");
    d.author = ParseGraphqlAuthor(At(data, "author"));
    d.categoryName = Str(Obj(data, "category"), "name");
    d.isAnswered = Bool(data, "isAnswered");
    d.commentsCount = Int32(conn, "totalCount");
    d.createdAt = Time(data, "createdAt");
    d.updatedAt = Time(data, "updatedAt");
    d.url = Str(data, "url");
    d.comments = FlattenCommentNodes(At(conn, "nodes"));
    d.commentsHasNextPage = Bool(pageInfo, "hasNextPage");
    d.commentsEndCursor = Str(pageInfo, "endCursor");
    return d;
}

// --- Commits ---

CommitAuthor CommitAuthor::FromJson(const json& data) {
    CommitAuthor a;
    if (!Truthy(data)) {
        a.name = "unknown";
        return a;
    }
    a.name = Str(data, "name", "unknown");
    a.email = Str(data, "email");
    a.date = Time(data, "date");
    return a;
}

CommitFile CommitFile::FromJson(const json& data) {
    CommitFile f;
    f.filename = Str(data, "filename");
    f.status = Str(data, "status", "modified");
    f.additions = Int32(data, "additions");
    f.deletions = Int32(data, "deletions");
    f.changes = Int32(data, "changes");
    f.previousFilename = Str(data, "previous_filename");
    f.patch = Str(data, "patch");
    return f;
}

std::string CommitFile::FormatDisplay() const {
    static const std::map<std::string, const char*> icons = {
        {"added", "[A]"},   {"removed", "[D]"}, {"modified", "[M]"},  {"renamed", "[R]"},
        {"copied", "[C]"},  {"changed", "[M]"}, {"unchanged", "[ ]"},
    };
    auto it = icons.find(status);
    const std::string icon = it == icons.end() ? "[?]" : it->second;
    const std::string stats = "+" + std::to_string(additions) + " -" + std::to_string(deletions);
    if (status == "renamed" && !previousFilename.empty())
        return icon + " " + previousFilename + " -> " + filename + " (" + stats + ")";
    return icon + " " + filename + " (" + stats + ")";
}

Commit Commit::FromJson(const json& data) {
    const json& commitData = Obj(data, "commit");
    Commit c;
    c.sha = Str(data, "sha");
    c.message = Str(commitData, "message");
    c.author = CommitAuthor::FromJson(At(commitData, "author"));
    c.committer = CommitAuthor::FromJson(At(commitData, "committer"));
    if (const json& a = At(data, "author"); Truthy(a)) c.githubAuthor = User::FromJson(a);
    if (const json& a = At(data, "committer"); Truthy(a)) c.githubCommitter = User::FromJson(a);
    c.htmlUrl = Str(data, "html_url");
    if (const json& parents = At(data, "parents"); parents.is_array()) {
        c.parents.reserve(parents.size());
        for (const json& p : parents) c.parents.push_back(Str(p, "sha"));
    }
    const json& stats = Obj(data, "stats");
    c.statsAdditions = Int32(stats, "additions");
    c.statsDeletions = Int32(stats, "deletions");
    c.statsTotal = Int32(stats, "total");
    if (const json& files = At(data, "files"); files.is_array()) {
        c.files.reserve(files.size());
        for (const json& f : files) c.files.push_back(CommitFile::FromJson(f));
    }
    return c;
}

std::string Commit::ShortSha() const { return sha.substr(0, 7); }

std::string Commit::FirstLineOfMessage() const { return FirstLine(message); }

std::string Commit::FormatDisplay() const {
    const std::string& authorName = githubAuthor ? githubAuthor->login : author.name;
    return FirstLineOfMessage() + " - " + authorName + ", " + LocalOrUnknown(author.date) + " [" + ShortSha() +
           "]";
}

// --- Releases ---

ReleaseAsset ReleaseAsset::FromJson(const json& data) {
    ReleaseAsset a;
    a.id = Int(data, "id");
    a.name = Str(data, "name");
    a.label = Str(data, "label");
    a.contentType = Str(data, "content_type");
    a.size = Int(data, "size");
    a.downloadCount = Int(data, "download_count");
    a.browserDownloadUrl = Str(data, "browser_download_url");
    a.createdAt = Time(data, "created_at");
    a.updatedAt = Time(data, "updated_at");
    return a;
}

std::string ReleaseAsset::FormatSize() const { return FormatSizeWithGb(size); }

std::string ReleaseAsset::FormatDisplay() const {
    const std::string downloads =
        downloadCount != 1 ? std::to_string(downloadCount) + " downloads" : "1 download";
    return name + " (" + FormatSize() + ", " + downloads + ")";
}

Release Release::FromJson(const json& data) {
    Release r;
    r.id = Int(data, "id");
    r.tagName = Str(data, "tag_name");
    r.name = Str(data, "name");
    if (r.name.empty()) r.name = r.tagName;
    r.body = Str(data, "body");
    r.draft = Bool(data, "draft");
    r.prerelease = Bool(data, "prerelease");
    r.createdAt = Time(data, "created_at");
    r.publishedAt = Time(data, "published_at");
    r.htmlUrl = Str(data, "html_url");
    r.tarballUrl = Str(data, "tarball_url");
    r.zipballUrl = Str(data, "zipball_url");
    r.authorLogin = Str(Obj(data, "author"), "login");
    if (const json& assets = At(data, "assets"); assets.is_array()) {
        r.assets.reserve(assets.size());
        for (const json& a : assets) r.assets.push_back(ReleaseAsset::FromJson(a));
    }
    return r;
}

std::string Release::GetStatusLabel() const {
    if (draft && prerelease) return "Draft, Pre-release";
    if (draft) return "Draft";
    if (prerelease) return "Pre-release";
    return "Release";
}

long long Release::TotalDownloads() const {
    long long total = 0;
    for (const auto& a : assets) total += a.downloadCount;
    return total;
}

std::string Release::FormatDownloads() const {
    long long total = TotalDownloads();
    return total != 1 ? std::to_string(total) + " downloads" : "1 download";
}

std::string Release::FormatDisplay() const {
    std::string timeStr;
    if (std::time_t dt = publishedAt ? publishedAt : createdAt) {
        long long s = Elapsed(dt);
        if (s < 60) timeStr = "just now";
        else if (s < 3600) timeStr = std::to_string(s / 60) + "m ago";
        else if (s < 86400) timeStr = std::to_string(s / 3600) + "h ago";
        else if (s < 604800) timeStr = std::to_string(s / 86400) + "d ago";
        else if (s < 2592000) timeStr = std::to_string(s / 604800) + "w ago";
        else timeStr = UtcDate(dt);  // Python formatted the UTC datetime as is
    }
    std::string assetsStr = assets.size() != 1 ? std::to_string(assets.size()) + " assets" : "1 asset";
    // Downloads only when there is something to download; releases with just the
    // auto-generated source archives would otherwise all read "0 downloads".
    if (!assets.empty()) assetsStr += ", " + FormatDownloads();
    const std::string head = name != tagName ? tagName + ": " + name : tagName;
    return head + " - " + GetStatusLabel() + " (" + assetsStr + ") - " + timeStr;
}

// --- Notifications ---

NotificationSubject NotificationSubject::FromJson(const json& data) {
    NotificationSubject s;
    s.title = Str(data, "title");
    s.url = Str(data, "url");
    s.type = Str(data, "type");
    s.latestCommentUrl = Str(data, "latest_comment_url");
    return s;
}

Notification Notification::FromJson(const json& data) {
    const json& repo = Obj(data, "repository");
    Notification n;
    const json& id = At(data, "id");
    n.id = id.is_string() ? id.get<std::string>() : id.is_number() ? id.dump() : "";
    n.unread = Bool(data, "unread");
    n.reason = Str(data, "reason");
    n.subject = NotificationSubject::FromJson(Obj(data, "subject"));
    n.repositoryFullName = Str(repo, "full_name");
    n.repositoryOwner = Str(Obj(repo, "owner"), "login");
    n.repositoryName = Str(repo, "name");
    n.updatedAt = Time(data, "updated_at");
    n.lastReadAt = Time(data, "last_read_at");
    n.url = Str(data, "url");
    return n;
}

std::string Notification::GetReasonDisplay() const {
    static const std::map<std::string, std::string> reasons = {
        {"assign", "You were assigned"},
        {"author", "You created the thread"},
        {"comment", "You commented"},
        {"ci_activity", "CI activity"},
        {"invitation", "You were invited"},
        {"manual", "You subscribed manually"},
        {"mention", "You were @mentioned"},
        {"review_requested", "Review requested"},
        {"security_alert", "Security alert"},
        {"state_change", "State changed"},
        {"subscribed", "You're watching the repo"},
        {"team_mention", "Your team was @mentioned"},
    };
    auto it = reasons.find(reason);
    return it == reasons.end() ? reason : it->second;
}

std::string Notification::FormatDisplay() const {
    static const std::map<std::string, std::string> icons = {
        {"Issue", "Issue"},     {"PullRequest", "PR"},   {"Commit", "Commit"},
        {"Release", "Release"}, {"Discussion", "Disc"}, {"RepositoryVulnerabilityAlert", "Security"},
    };
    auto it = icons.find(subject.type);
    const std::string& typeIcon = it == icons.end() ? subject.type : it->second;
    return std::string(unread ? "● " : "○ ") + "[" + typeIcon + "] " + subject.title + " - " +
           repositoryFullName + " (" + GetReasonDisplay() + ") - " + LocalOrUnknown(updatedAt);
}

std::string Notification::GetWebUrl() const {
    if (!subject.url.empty())
        return ReplaceAll(ReplaceAll(subject.url, "api.github.com/repos", "github.com"), "/pulls/", "/pull/");
    return "https://github.com/" + repositoryFullName;
}

// --- Actions ---

namespace {

std::string StatusIcon(const std::string& status, const std::string& conclusion) {
    if (status == "completed") {
        if (conclusion == "success") return "✓";
        if (conclusion == "failure") return "✗";
        if (conclusion == "cancelled" || conclusion == "skipped") return "⊘";
        return "?";
    }
    if (status == "in_progress") return "●";
    if (status == "queued") return "○";
    return "?";
}

}  // namespace

Workflow Workflow::FromJson(const json& data) {
    Workflow w;
    w.id = Int(data, "id");
    w.name = Str(data, "name");
    w.path = Str(data, "path");
    w.state = Str(data, "state");
    w.htmlUrl = Str(data, "html_url");
    w.badgeUrl = Str(data, "badge_url");
    w.createdAt = Time(data, "created_at");
    w.updatedAt = Time(data, "updated_at");
    return w;
}

std::string Workflow::FormatDisplay() const { return std::string(state == "active" ? "✓" : "○") + " " + name; }

WorkflowRun WorkflowRun::FromJson(const json& data) {
    WorkflowRun r;
    r.id = Int(data, "id");
    r.name = Str(data, "name");
    r.workflowId = Int(data, "workflow_id");
    r.headBranch = Str(data, "head_branch");
    r.headSha = Str(data, "head_sha").substr(0, 7);
    r.status = Str(data, "status");
    r.conclusion = Str(data, "conclusion");
    r.event = Str(data, "event");
    r.runNumber = Int32(data, "run_number");
    r.runAttempt = Int32(data, "run_attempt", 1);
    r.htmlUrl = Str(data, "html_url");
    r.createdAt = Time(data, "created_at");
    r.updatedAt = Time(data, "updated_at");
    r.runStartedAt = Time(data, "run_started_at");
    const json& actor = Obj(data, "actor");
    r.actorLogin = Str(actor, "login");
    r.actorAvatarUrl = Str(actor, "avatar_url");
    r.triggeringActorLogin = Str(Obj(data, "triggering_actor"), "login");
    r.displayTitle = Str(data, "display_title");
    return r;
}

std::string WorkflowRun::GetStatusIcon() const { return StatusIcon(status, conclusion); }

std::string WorkflowRun::GetStatusText() const {
    if (status == "completed") return conclusion.empty() ? "completed" : conclusion;
    return ReplaceAll(status, "_", " ");
}

std::string WorkflowRun::FormatDisplay() const {
    std::string timeStr;
    if (createdAt) {
        long long s = Elapsed(createdAt);
        if (s < 60) timeStr = "just now";
        else if (s < 3600) timeStr = std::to_string(s / 60) + "m ago";
        else if (s < 86400) timeStr = std::to_string(s / 3600) + "h ago";
        else if (s < 604800) timeStr = std::to_string(s / 86400) + "d ago";
        else timeStr = UtcDate(createdAt);
    }
    return GetStatusIcon() + " " + name + " #" + std::to_string(runNumber) + " - " + headBranch + " (" + event +
           ") - " + timeStr;
}

WorkflowJob WorkflowJob::FromJson(const json& data) {
    WorkflowJob j;
    j.id = Int(data, "id");
    j.runId = Int(data, "run_id");
    j.name = Str(data, "name");
    j.status = Str(data, "status");
    j.conclusion = Str(data, "conclusion");
    j.startedAt = Time(data, "started_at");
    j.completedAt = Time(data, "completed_at");
    j.htmlUrl = Str(data, "html_url");
    j.runnerName = Str(data, "runner_name");
    if (const json& steps = At(data, "steps"); steps.is_array()) {
        j.steps.reserve(steps.size());
        for (const json& s : steps) {
            WorkflowStep step;
            step.name = Str(s, "name");
            step.status = Str(s, "status");
            step.conclusion = Str(s, "conclusion");
            step.number = Int32(s, "number");
            step.startedAt = Time(s, "started_at");
            step.completedAt = Time(s, "completed_at");
            j.steps.push_back(std::move(step));
        }
    }
    return j;
}

std::string WorkflowJob::GetStatusIcon() const { return StatusIcon(status, conclusion); }

std::string WorkflowJob::GetDuration() const {
    if (!startedAt) return "";
    std::time_t end = completedAt ? completedAt : std::time(nullptr);
    long long seconds = static_cast<long long>(end) - static_cast<long long>(startedAt);
    if (seconds < 60) return std::to_string(seconds) + "s";
    if (seconds < 3600) return std::to_string(seconds / 60) + "m " + std::to_string(seconds % 60) + "s";
    return std::to_string(seconds / 3600) + "h " + std::to_string((seconds % 3600) / 60) + "m";
}

std::string WorkflowJob::FormatDisplay() const {
    const std::string duration = GetDuration();
    if (!duration.empty()) return GetStatusIcon() + " " + name + " (" + duration + ")";
    return GetStatusIcon() + " " + name;
}

Artifact Artifact::FromJson(const json& data) {
    Artifact a;
    a.id = Int(data, "id");
    a.name = Str(data, "name");
    a.sizeInBytes = Int(data, "size_in_bytes");
    a.archiveDownloadUrl = Str(data, "archive_download_url");
    a.expired = Bool(data, "expired");
    a.createdAt = Time(data, "created_at");
    a.expiresAt = Time(data, "expires_at");
    return a;
}

std::string Artifact::FormatSize() const { return FormatSizeWithGb(sizeInBytes); }

std::string Artifact::FormatDisplay() const {
    std::string parts = FormatSize();
    if (expired) parts += ", expired";
    else if (createdAt) parts += ", " + UtcDate(createdAt);
    return name + " (" + parts + ")";
}

// --- Activity feed ---

Event Event::FromJson(const json& data) {
    Event e;
    const json& id = At(data, "id");
    e.id = id.is_string() ? id.get<std::string>() : id.is_number() ? id.dump() : "";
    e.type = Str(data, "type");
    const json& actor = Obj(data, "actor");
    e.actor.id = Int(actor, "id");
    e.actor.login = Str(actor, "login");
    e.actor.avatarUrl = Str(actor, "avatar_url");
    const json& repo = Obj(data, "repo");
    e.repo.id = Int(repo, "id");
    e.repo.name = Str(repo, "name");
    e.repo.url = Str(repo, "url");
    e.payload = Obj(data, "payload");
    e.isPublic = Bool(data, "public", true);
    e.createdAt = Time(data, "created_at");
    return e;
}

namespace {

// The 50-code-point title the feed shows for issues, PRs and discussions.
std::string ShortTitle(const json& item) { return Prefix(Str(item, "title"), 50); }

// "<head> #<number>[ [<tag>]]: <title>" or without the title when it is empty.
std::string WithTitle(const std::string& head, const std::string& title) {
    return title.empty() ? head : head + ": " + title;
}

std::string IssueLikeDescription(const json& payload, const char* itemKey, const char* noun) {
    const std::string action = PyGet(payload, "action");
    const json& item = Obj(payload, itemKey);
    const std::string number = PyGet(item, "number");
    const std::string title = ShortTitle(item);
    const std::string labelName = TruthyStr(Obj(payload, "label"), "name");
    const std::string assignee = TruthyStr(Obj(payload, "assignee"), "login");
    const std::string milestone = TruthyStr(Obj(payload, "milestone"), "title");
    const std::string ref = std::string(noun) + " #" + number;

    if ((action == "labeled" || action == "unlabeled") && !labelName.empty())
        return WithTitle(action + " " + ref + " [" + labelName + "]", title);
    if (action == "assigned" && !assignee.empty()) return WithTitle("assigned " + assignee + " to " + ref, title);
    if (action == "unassigned" && !assignee.empty())
        return WithTitle("unassigned " + assignee + " from " + ref, title);
    if ((action == "milestoned" || action == "demilestoned") && !milestone.empty())
        return WithTitle(action + " " + ref + " [" + milestone + "]", title);
    return std::string();  // not one of the shared actions
}

}  // namespace

std::string Event::GetActionDescription() const {
    const json& p = payload;

    if (type == "WatchEvent") return "starred";

    if (type == "ForkEvent") {
        const std::string forkName = TruthyStr(Obj(p, "forkee"), "full_name");
        return forkName.empty() ? "forked" : "forked to " + forkName;
    }

    if (type == "CreateEvent") {
        const std::string refType = PyGet(p, "ref_type");
        const std::string ref = PyGet(p, "ref");
        if (refType == "repository") return "created repository";
        if (refType == "branch") return "created branch " + ref;
        if (refType == "tag") return "created tag " + ref;
        return "created " + refType;
    }

    if (type == "DeleteEvent") return "deleted " + PyGet(p, "ref_type") + " " + PyGet(p, "ref");

    if (type == "DiscussionEvent") {
        const json& d = Obj(p, "discussion");
        return WithTitle(PyGet(p, "action") + " discussion #" + PyGet(d, "number"), ShortTitle(d));
    }

    if (type == "DiscussionCommentEvent") {
        const std::string action = PyGet(p, "action", "created");
        const json& d = Obj(p, "discussion");
        const std::string number = PyGet(d, "number");
        const std::string title = ShortTitle(d);
        const json& comment = Obj(p, "comment");
        const bool isReply = Truthy(At(comment, "in_reply_to_id")) || Truthy(At(comment, "reply_to_id"));
        if (action == "created" || action == "edited") {
            if (isReply) return WithTitle("replied in discussion #" + number, title);
            return WithTitle("commented on discussion #" + number, title);
        }
        return WithTitle(action + " comment on discussion #" + number, title);
    }

    if (type == "PushEvent") {
        // size is 0 for force pushes; distinct_size or the commits list may still count them.
        auto isZero = [](const json& v) { return v.is_number() && v.get<double>() == 0.0; };
        json size = Has(p, "size") ? At(p, "size") : json(0);
        if (isZero(size)) size = Has(p, "distinct_size") ? At(p, "distinct_size") : json(0);
        if (isZero(size)) {
            const json& commits = At(p, "commits");
            size = commits.is_array() || commits.is_object() ? commits.size() : 0;
        }
        const std::string ref = ReplaceAll(PyGet(p, "ref"), "refs/heads/", "");
        if (isZero(size)) return "force pushed to " + ref;
        if (size.is_number() && size.get<double>() == 1.0) return "pushed 1 commit to " + ref;
        return "pushed " + PyStr(size) + " commits to " + ref;
    }

    if (type == "IssuesEvent") {
        std::string shared = IssueLikeDescription(p, "issue", "issue");
        if (!shared.empty()) return shared;
        const std::string action = PyGet(p, "action");
        const json& issue = Obj(p, "issue");
        // pinned, unpinned, locked, unlocked, transferred and anything else read the same way.
        return WithTitle(action + " issue #" + PyGet(issue, "number"), ShortTitle(issue));
    }

    if (type == "IssueCommentEvent") {
        const std::string action = PyGet(p, "action", "created");
        const json& issue = Obj(p, "issue");
        const std::string number = PyGet(issue, "number");
        if (action == "created" || action == "edited")
            return WithTitle("commented on issue #" + number, ShortTitle(issue));
        return WithTitle(action + " comment on issue #" + number, ShortTitle(issue));
    }

    if (type == "PullRequestEvent") {
        const std::string action = PyGet(p, "action");
        const json& pr = Obj(p, "pull_request");
        const std::string number = PyGet(pr, "number");
        const std::string title = ShortTitle(pr);
        const std::string ref = "PR #" + number;
        if (action == "opened" || action == "reopened") return WithTitle(action + " " + ref, title);
        if (action == "closed") return WithTitle((Truthy(At(pr, "merged")) ? "merged " : "closed ") + ref, title);
        std::string shared = IssueLikeDescription(p, "pull_request", "PR");
        if (!shared.empty()) return shared;
        if (action == "locked" || action == "unlocked") return WithTitle(action + " " + ref, title);
        if (action == "review_requested" || action == "review_request_removed") {
            const bool requested = action == "review_requested";
            const std::string verb = requested ? "requested review" : "removed review request";
            const std::string forWord = requested ? " from " : " for ";
            const json& reviewer = At(Obj(p, "requested_reviewer"), "login");
            const json& team = At(Obj(p, "requested_team"), "name");
            if (Truthy(reviewer)) return WithTitle(verb + forWord + PyStr(reviewer) + " on " + ref, title);
            if (Truthy(team)) return WithTitle(verb + forWord + "team " + PyStr(team) + " on " + ref, title);
            return WithTitle(verb + " on " + ref, title);
        }
        if (action == "ready_for_review") return WithTitle("marked " + ref + " ready for review", title);
        if (action == "converted_to_draft") return WithTitle("converted " + ref + " to draft", title);
        if (action == "synchronize") return WithTitle("updated " + ref + " with new commits", title);
        return WithTitle(action + " " + ref, title);
    }

    if (type == "PullRequestReviewEvent") {
        const json& pr = Obj(p, "pull_request");
        const std::string ref = "PR #" + PyGet(pr, "number");
        const std::string title = ShortTitle(pr);
        const std::string state = PyGet(Obj(p, "review"), "state");
        if (state == "approved") return WithTitle("approved " + ref, title);
        if (state == "changes_requested") return WithTitle("requested changes on " + ref, title);
        return WithTitle("reviewed " + ref, title);
    }

    if (type == "PullRequestReviewCommentEvent") {
        const json& pr = Obj(p, "pull_request");
        return WithTitle("commented on PR #" + PyGet(pr, "number"), ShortTitle(pr));
    }

    if (type == "PullRequestReviewThreadEvent") {
        const json& pr = Obj(p, "pull_request");
        // resolved / unresolved / anything else all read "<action> review thread".
        return WithTitle(PyGet(p, "action") + " review thread on PR #" + PyGet(pr, "number"), ShortTitle(pr));
    }

    if (type == "ReleaseEvent") {
        const std::string action = PyGet(p, "action");
        const std::string tag = PyGet(Obj(p, "release"), "tag_name");
        if (action == "published") return "released " + tag;
        return action + " release " + tag;
    }

    if (type == "CommitCommentEvent") return "commented on a commit";

    if (type == "GollumEvent") {
        const json& pages = At(p, "pages");
        if (pages.is_array() && !pages.empty()) {
            const json& first = pages[0];
            return PyGet(first, "action", "updated") + " wiki page: " + PyGet(first, "title");
        }
        return "updated wiki";
    }

    if (type == "MemberEvent")
        return PyGet(p, "action") + " " + PyGet(Obj(p, "member"), "login") + " as collaborator";

    if (type == "PublicEvent") return "made repository public";

    static const std::map<std::string, std::string> kEventTypes = {
        {"CommitCommentEvent", "commented on a commit"},
        {"CreateEvent", "created"},
        {"DeleteEvent", "deleted"},
        {"DiscussionCommentEvent", "commented on discussion"},
        {"DiscussionEvent", "discussion"},
        {"ForkEvent", "forked"},
        {"GollumEvent", "updated wiki"},
        {"IssueCommentEvent", "commented on issue"},
        {"IssuesEvent", "issue"},
        {"MemberEvent", "added member"},
        {"PublicEvent", "made public"},
        {"PullRequestEvent", "pull request"},
        {"PullRequestReviewEvent", "reviewed PR"},
        {"PullRequestReviewThreadEvent", "updated PR review thread"},
        {"PullRequestReviewCommentEvent", "commented on PR review"},
        {"PushEvent", "pushed"},
        {"ReleaseEvent", "released"},
        {"SponsorshipEvent", "sponsorship"},
        {"WatchEvent", "starred"},
    };
    auto it = kEventTypes.find(type);
    return it == kEventTypes.end() ? type : it->second;
}

std::string Event::FormatDisplay() const {
    return actor.login + " " + GetActionDescription() + " in " + repo.name + " - " + LocalOrUnknown(createdAt);
}

std::string Event::GetWebUrl() const {
    const std::string base = "https://github.com/" + repo.name;
    const json& p = payload;
    // The first of these that is set (Python truthiness) wins.
    auto url = [](const json& obj) -> std::string {
        const json& u = At(obj, "html_url");
        return Truthy(u) ? PyStr(u) : std::string();
    };
    auto numbered = [&](const json& obj, const char* path) -> std::string {
        const json& n = At(obj, "number");
        return Truthy(n) ? base + path + PyStr(n) : std::string();
    };
    std::string out;

    if (type == "IssuesEvent") {
        out = numbered(Obj(p, "issue"), "/issues/");
    } else if (type == "IssueCommentEvent") {
        out = url(Obj(p, "comment"));
        if (out.empty()) out = numbered(Obj(p, "issue"), "/issues/");
    } else if (type == "DiscussionEvent") {
        const json& d = Obj(p, "discussion");
        out = url(d);
        if (out.empty()) out = numbered(d, "/discussions/");
    } else if (type == "DiscussionCommentEvent") {
        const json& d = Obj(p, "discussion");
        out = url(Obj(p, "comment"));
        if (out.empty()) out = url(d);
        if (out.empty()) out = numbered(d, "/discussions/");
    } else if (type == "PullRequestEvent" || type == "PullRequestReviewEvent") {
        out = numbered(Obj(p, "pull_request"), "/pull/");
    } else if (type == "PullRequestReviewCommentEvent") {
        out = url(Obj(p, "comment"));
        if (out.empty()) out = numbered(Obj(p, "pull_request"), "/pull/");
    } else if (type == "PullRequestReviewThreadEvent") {
        out = url(Obj(p, "thread"));
        if (out.empty()) out = numbered(Obj(p, "pull_request"), "/pull/");
    } else if (type == "PushEvent") {
        const std::string before = Prefix(Str(p, "before"), 7);
        const std::string head = Prefix(Str(p, "head"), 7);
        if (!before.empty() && !head.empty()) out = base + "/compare/" + before + "..." + head;
    } else if (type == "ReleaseEvent") {
        out = url(Obj(p, "release"));
    } else if (type == "ForkEvent") {
        out = url(Obj(p, "forkee"));
    } else if (type == "CommitCommentEvent") {
        out = url(Obj(p, "comment"));
    } else if (type == "CreateEvent") {
        const std::string refType = PyGet(p, "ref_type");
        const json& ref = At(p, "ref");
        if (refType == "branch" && Truthy(ref)) out = base + "/tree/" + PyStr(ref);
        else if (refType == "tag" && Truthy(ref)) out = base + "/releases/tag/" + PyStr(ref);
    }
    return out.empty() ? base : out;
}

std::string Event::GetActorUrl() const { return "https://github.com/" + actor.login; }

// --- Repository contents ---

ContentItem ContentItem::FromJson(const json& data) {
    ContentItem c;
    c.name = Str(data, "name");
    c.path = Str(data, "path");
    c.sha = Str(data, "sha");
    c.size = Int(data, "size");
    c.type = Str(data, "type", "file");
    c.downloadUrl = Str(data, "download_url");
    c.htmlUrl = Str(data, "html_url");
    c.content = Str(data, "content");
    c.encoding = Str(data, "encoding");
    return c;
}

std::string ContentItem::GetDisplayName() const { return type == "dir" ? "[" + name + "]" : name; }

std::string ContentItem::GetSizeStr() const {
    if (type == "dir") return "";
    return ::FormatSize(size < 0 ? 0 : static_cast<uint64_t>(size));
}
