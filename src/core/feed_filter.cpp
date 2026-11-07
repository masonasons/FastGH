#include "core/feed_filter.h"

namespace feedfilter {

const std::vector<std::string> kAllEventTypes = {
    "CommitCommentEvent",
    "CreateEvent",
    "DeleteEvent",
    "DiscussionCommentEvent",
    "DiscussionEvent",
    "ForkEvent",
    "GollumEvent",
    "IssueCommentEvent",
    "IssuesEvent",
    "MemberEvent",
    "PublicEvent",
    "PullRequestEvent",
    "PullRequestReviewCommentEvent",
    "PullRequestReviewEvent",
    "PullRequestReviewThreadEvent",
    "PushEvent",
    "ReleaseEvent",
    "SponsorshipEvent",
    "WatchEvent",
};

// "merged" for PullRequestEvent is synthetic (closed + merged); Create/Delete use
// ref_type and PullRequestReviewEvent the review state (see GetEventAction).
const std::map<std::string, std::vector<std::string>> kEventTypeActions = {
    {"PullRequestEvent",
     {"opened", "closed", "merged", "reopened", "labeled", "unlabeled", "assigned", "unassigned", "locked",
      "unlocked"}},
    {"IssuesEvent",
     {"opened", "closed", "reopened", "labeled", "unlabeled", "assigned", "unassigned", "locked", "unlocked"}},
    {"IssueCommentEvent", {"created", "edited", "deleted"}},
    {"PullRequestReviewEvent", {"approved", "changes_requested", "commented"}},
    {"PullRequestReviewCommentEvent", {"created", "edited", "deleted"}},
    {"PullRequestReviewThreadEvent", {"resolved", "unresolved"}},
    {"CreateEvent", {"branch", "tag", "repository"}},
    {"DeleteEvent", {"branch", "tag"}},
    {"ReleaseEvent", {"published", "created", "edited", "deleted", "prereleased"}},
    {"DiscussionEvent", {"created", "answered", "category_changed", "labeled", "unlabeled"}},
    {"DiscussionCommentEvent", {"created", "edited", "deleted"}},
    {"MemberEvent", {"added", "removed"}},
    {"SponsorshipEvent", {"created", "cancelled"}},
};

const std::vector<std::pair<std::string, std::vector<std::string>>> kFilterGroups = {
    {"Pull Requests && Reviews",
     {"PullRequestEvent", "PullRequestReviewEvent", "PullRequestReviewCommentEvent",
      "PullRequestReviewThreadEvent"}},
    {"Issues", {"IssuesEvent", "IssueCommentEvent"}},
    {"Code", {"PushEvent", "CommitCommentEvent", "CreateEvent", "DeleteEvent"}},
    {"Collaboration", {"ForkEvent", "WatchEvent", "MemberEvent", "GollumEvent"}},
    {"Releases && Discussions",
     {"ReleaseEvent", "DiscussionEvent", "DiscussionCommentEvent", "SponsorshipEvent", "PublicEvent"}},
};

namespace {

const char* const kVisibleKey = "feed_visible_event_types";
const char* const kMutedReposKey = "feed_muted_repos";
const char* const kUserFiltersKey = "feed_user_filters";

// A stored list of strings; anything that is not a list reads as "never
// configured" so a damaged config shows everything rather than hiding events.
std::optional<std::set<std::string>> StringSet(const json& raw) {
    if (!raw.is_array()) return std::nullopt;
    std::set<std::string> out;
    for (const json& item : raw)
        if (item.is_string()) out.insert(item.get<std::string>());
    return out;
}

// std::set iterates in byte order, which for UTF-8 matches Python's sorted().
json SortedList(const std::set<std::string>& items) {
    json arr = json::array();
    for (const auto& s : items) arr.push_back(s);
    return arr;
}

// Python's truth value, for payload fields the filter keys are built from.
bool Truthy(const json& v) {
    if (v.is_null()) return false;
    if (v.is_boolean()) return v.get<bool>();
    if (v.is_number()) return v.get<double>() != 0.0;
    if (v.is_string() || v.is_array() || v.is_object()) return !v.empty();
    return false;
}

std::string PyStr(const json& v) {
    if (v.is_string()) return v.get<std::string>();
    if (v.is_boolean()) return v.get<bool>() ? "True" : "False";
    return v.dump();
}

// payload[key] as a filter action: "" when missing or falsy.
std::string ActionField(const json& obj, const char* key) {
    if (!obj.is_object()) return "";
    auto it = obj.find(key);
    return it != obj.end() && Truthy(*it) ? PyStr(*it) : "";
}

bool InVisible(const Event& event, const std::set<std::string>& visible) {
    if (kEventTypeActions.count(event.type)) {
        std::string action = GetEventAction(event);
        if (!action.empty()) return visible.count(event.type + ":" + action) > 0;
    }
    return visible.count(event.type) > 0;
}

}  // namespace

std::optional<std::set<std::string>> LoadVisibleTypes(const Config& accountPrefs) {
    return StringSet(accountPrefs.GetJson(kVisibleKey));
}

void SaveVisibleTypes(Config& accountPrefs, const std::set<std::string>& visible) {
    accountPrefs.SetJson(kVisibleKey, SortedList(visible));
}

std::optional<std::set<std::string>> LoadMutedRepos(const Config& accountPrefs) {
    return StringSet(accountPrefs.GetJson(kMutedReposKey));
}

void SaveMutedRepos(Config& accountPrefs, const std::set<std::string>& muted) {
    accountPrefs.SetJson(kMutedReposKey, SortedList(muted));
}

std::optional<std::map<std::string, std::set<std::string>>> LoadUserFilters(const Config& accountPrefs) {
    const json raw = accountPrefs.GetJson(kUserFiltersKey);
    if (!raw.is_object()) return std::nullopt;
    std::map<std::string, std::set<std::string>> out;
    // One bad entry is skipped rather than wiping every user's rule.
    for (auto it = raw.begin(); it != raw.end(); ++it)
        if (auto types = StringSet(it.value())) out.emplace(it.key(), std::move(*types));
    return out;
}

void SaveUserFilters(Config& accountPrefs, const std::map<std::string, std::set<std::string>>& filters) {
    json obj = json::object();
    for (const auto& [user, types] : filters) obj[user] = SortedList(types);
    accountPrefs.SetJson(kUserFiltersKey, obj);
}

std::string GetEventAction(const Event& event) {
    const std::string& t = event.type;
    if (!kEventTypeActions.count(t)) return "";
    const json& payload = event.payload;

    if (t == "PullRequestEvent") {
        std::string action = ActionField(payload, "action");
        if (action == "closed" && payload.is_object()) {
            auto pr = payload.find("pull_request");
            if (pr != payload.end() && pr->is_object() && Truthy(pr->value("merged", json()))) return "merged";
        }
        return action;
    }
    if (t == "CreateEvent" || t == "DeleteEvent") return ActionField(payload, "ref_type");
    if (t == "PullRequestReviewEvent") {
        if (!payload.is_object()) return "";
        auto review = payload.find("review");
        return review != payload.end() ? ActionField(*review, "state") : "";
    }
    return ActionField(payload, "action");
}

bool IsEventVisible(const Event& event, const std::optional<std::set<std::string>>& visible) {
    return !visible || InVisible(event, *visible);
}

std::vector<Event> FilterFeed(const std::vector<Event>& events,
                              const std::optional<std::set<std::string>>& visible,
                              const std::optional<std::set<std::string>>& mutedRepos,
                              const std::optional<std::map<std::string, std::set<std::string>>>& userFilters) {
    std::vector<Event> result;
    result.reserve(events.size());
    const bool anyMuted = mutedRepos && !mutedRepos->empty();
    const bool anyUserRules = userFilters && !userFilters->empty();
    for (const Event& e : events) {
        if (anyMuted && mutedRepos->count(ToLower(e.repo.name))) continue;

        // A user's own rule replaces the global set; an empty rule mutes them.
        const std::set<std::string>* vis = visible ? &*visible : nullptr;
        if (anyUserRules) {
            auto it = userFilters->find(ToLower(e.actor.login));
            if (it != userFilters->end()) vis = &it->second;
        }
        if (vis && !InVisible(e, *vis)) continue;

        result.push_back(e);
    }
    return result;
}

}  // namespace feedfilter
