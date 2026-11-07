#pragma once

// GitHub data, as the windows show it. A port of the Python models/ package:
// each struct has FromJson() (the Python from_github_api / from_api /
// from_graphql) and the same display formatting, word for word.
//
// Text is UTF-8. Python's Optional[str] is an empty string here; Optional[datetime]
// is a time_t of 0 (see util.h).

#include "core/util.h"

#include <nlohmann/json.hpp>

#include <ctime>
#include <optional>
#include <string>
#include <vector>

using json = nlohmann::json;

// --- Repository (models/repository.py) ---
struct Repository {
    long long id = 0;
    std::string name;
    std::string fullName;
    std::string description;
    std::string owner;
    long long stars = 0;
    long long forks = 0;
    long long openIssues = 0;
    std::string language;
    std::time_t updatedAt = 0;
    std::time_t pushedAt = 0;
    std::string url;
    std::string htmlUrl;
    bool isPrivate = false;
    bool isFork = false;
    std::string parentFullName;  // only in single-repo responses
    std::string defaultBranch;   // "default_branch"

    static Repository FromJson(const json& data);
    std::string FormatDisplay() const;     // two lines
    std::string FormatSingleLine() const;  // the list row
};

// --- Users (models/user.py, models/issue.py User) ---
struct User {
    std::string login;
    long long id = 0;
    std::string avatarUrl;
    static User FromJson(const json& data);  // tolerates null
};

struct UserProfile {
    long long id = 0;
    std::string login;
    std::string name;
    std::string avatarUrl;
    std::string htmlUrl;
    std::string bio;
    std::string company;
    std::string location;
    std::string email;
    std::string blog;
    std::string twitterUsername;
    long long publicRepos = 0;
    long long publicGists = 0;
    long long followers = 0;
    long long following = 0;
    std::time_t createdAt = 0;
    std::time_t updatedAt = 0;
    std::string type = "User";  // "User" or "Organization"

    static UserProfile FromJson(const json& data);
    std::string DisplayName() const { return name.empty() ? login : name; }
    std::string FormatDisplay() const;
};

struct Stargazer {
    std::string login;
    std::string htmlUrl;
    std::string type = "User";
    std::time_t starredAt = 0;
    static Stargazer FromJson(const json& data);
    std::string FormatDisplay() const;
};

// --- Issues and pull requests (models/issue.py) ---
struct Label {
    std::string name;
    std::string color;
    std::string description;
    static Label FromJson(const json& data);
};

struct Comment {
    long long id = 0;
    std::string body;
    User user;
    std::time_t createdAt = 0;
    std::time_t updatedAt = 0;
    std::string htmlUrl;
    std::string kind = "issue";  // "issue" or "review"
    static Comment FromJson(const json& data, const std::string& kind = "issue");
    std::string FormatDisplay() const;
};

struct Issue {
    long long id = 0;
    int number = 0;
    std::string title;
    std::string body;
    std::string state;  // "open" or "closed"
    User user;
    std::vector<Label> labels;
    std::vector<User> assignees;
    int commentsCount = 0;
    std::time_t createdAt = 0;
    std::time_t updatedAt = 0;
    std::time_t closedAt = 0;
    std::string htmlUrl;
    bool isPullRequest = false;

    static Issue FromJson(const json& data);
    std::string FormatDisplay() const;
};

struct PullRequest {
    long long id = 0;
    int number = 0;
    std::string title;
    std::string body;
    std::string state;
    User user;
    std::vector<Label> labels;
    std::vector<User> assignees;
    std::string headRef;
    std::string baseRef;
    bool merged = false;
    std::optional<bool> mergeable;
    std::string mergeableState;
    std::optional<User> mergedBy;
    std::time_t mergedAt = 0;
    int commentsCount = 0;
    int commitsCount = 0;
    int additions = 0;
    int deletions = 0;
    int changedFiles = 0;
    std::time_t createdAt = 0;
    std::time_t updatedAt = 0;
    std::time_t closedAt = 0;
    std::string htmlUrl;
    bool draft = false;

    static PullRequest FromJson(const json& data);
    std::string FormatDisplay() const;
};

// --- Discussions (models/discussion.py; GraphQL) ---
struct DiscussionComment {
    std::string id;  // GraphQL node id
    std::optional<long long> databaseId;
    std::string body;
    User author;
    std::time_t createdAt = 0;
    std::time_t updatedAt = 0;
    std::string url;
    bool isReply = false;
    std::string parentAuthorLogin;

    static DiscussionComment FromGraphql(const json& data, bool isReply = false,
                                         const std::string& parentAuthorLogin = "");
    std::string FormatDisplay() const;
};

struct Discussion {
    std::string id;
    int number = 0;
    std::string title;
    std::string body;
    User author;
    std::string categoryName;
    bool isAnswered = false;
    int commentsCount = 0;
    std::time_t createdAt = 0;
    std::time_t updatedAt = 0;
    std::string url;
    std::vector<DiscussionComment> comments;
    bool commentsHasNextPage = false;
    std::string commentsEndCursor;

    // Comments with their replies flattened in after each (isReply set).
    static std::vector<DiscussionComment> FlattenCommentNodes(const json& nodes);
    static Discussion FromGraphql(const json& data);
};

// --- Commits (models/commit.py) ---
struct CommitAuthor {
    std::string name;
    std::string email;
    std::time_t date = 0;
    static CommitAuthor FromJson(const json& data);
};

struct CommitFile {
    std::string filename;
    std::string status;
    int additions = 0;
    int deletions = 0;
    int changes = 0;
    std::string previousFilename;
    std::string patch;  // the diff, when the API sent it
    static CommitFile FromJson(const json& data);
    std::string FormatDisplay() const;
};

struct Commit {
    std::string sha;
    std::string message;
    CommitAuthor author;
    CommitAuthor committer;
    std::optional<User> githubAuthor;
    std::optional<User> githubCommitter;
    std::string htmlUrl;
    std::vector<std::string> parents;
    int statsAdditions = 0;
    int statsDeletions = 0;
    int statsTotal = 0;
    std::vector<CommitFile> files;

    static Commit FromJson(const json& data);
    std::string ShortSha() const;
    std::string FirstLineOfMessage() const;
    std::string FormatDisplay() const;
};

struct Branch {
    std::string name;
    std::string sha;
    std::time_t lastCommitDate = 0;
    bool isDefault = false;
};

// --- Releases (models/release.py) ---
struct ReleaseAsset {
    long long id = 0;
    std::string name;
    std::string label;
    std::string contentType;
    long long size = 0;
    long long downloadCount = 0;
    std::string browserDownloadUrl;
    std::time_t createdAt = 0;
    std::time_t updatedAt = 0;
    static ReleaseAsset FromJson(const json& data);
    std::string FormatSize() const;
    std::string FormatDisplay() const;
};

struct Release {
    long long id = 0;
    std::string tagName;
    std::string name;
    std::string body;
    bool draft = false;
    bool prerelease = false;
    std::time_t createdAt = 0;
    std::time_t publishedAt = 0;
    std::string htmlUrl;
    std::string tarballUrl;
    std::string zipballUrl;
    std::string authorLogin;
    std::vector<ReleaseAsset> assets;

    static Release FromJson(const json& data);
    std::string GetStatusLabel() const;
    long long TotalDownloads() const;
    std::string FormatDownloads() const;
    std::string FormatDisplay() const;
};

// --- Notifications (models/notification.py) ---
struct NotificationSubject {
    std::string title;
    std::string url;
    std::string type;  // Issue, PullRequest, Commit, Release, Discussion...
    std::string latestCommentUrl;
    static NotificationSubject FromJson(const json& data);
};

struct Notification {
    std::string id;
    bool unread = false;
    std::string reason;
    NotificationSubject subject;
    std::string repositoryFullName;
    std::string repositoryOwner;
    std::string repositoryName;
    std::time_t updatedAt = 0;
    std::time_t lastReadAt = 0;
    std::string url;

    static Notification FromJson(const json& data);
    std::string GetReasonDisplay() const;
    std::string FormatDisplay() const;
    std::string GetWebUrl() const;
};

// --- Actions (models/workflow.py) ---
struct Workflow {
    long long id = 0;
    std::string name;
    std::string path;
    std::string state;
    std::string htmlUrl;
    std::string badgeUrl;
    std::time_t createdAt = 0;
    std::time_t updatedAt = 0;
    static Workflow FromJson(const json& data);
    std::string FormatDisplay() const;
};

struct WorkflowRun {
    long long id = 0;
    std::string name;
    long long workflowId = 0;
    std::string headBranch;
    std::string headSha;
    std::string status;
    std::string conclusion;
    std::string event;
    int runNumber = 0;
    int runAttempt = 0;
    std::string htmlUrl;
    std::time_t createdAt = 0;
    std::time_t updatedAt = 0;
    std::time_t runStartedAt = 0;
    std::string actorLogin;
    std::string actorAvatarUrl;
    std::string triggeringActorLogin;
    std::string displayTitle;  // "display_title"

    static WorkflowRun FromJson(const json& data);
    std::string GetStatusIcon() const;
    std::string GetStatusText() const;
    std::string FormatDisplay() const;
};

struct WorkflowStep {
    std::string name;
    std::string status;
    std::string conclusion;
    int number = 0;
    std::time_t startedAt = 0;
    std::time_t completedAt = 0;
};

struct WorkflowJob {
    long long id = 0;
    long long runId = 0;
    std::string name;
    std::string status;
    std::string conclusion;
    std::time_t startedAt = 0;
    std::time_t completedAt = 0;
    std::string htmlUrl;
    std::string runnerName;
    std::vector<WorkflowStep> steps;

    static WorkflowJob FromJson(const json& data);
    std::string GetStatusIcon() const;
    std::string GetDuration() const;
    std::string FormatDisplay() const;
};

struct Artifact {
    long long id = 0;
    std::string name;
    long long sizeInBytes = 0;
    std::string archiveDownloadUrl;
    bool expired = false;
    std::time_t createdAt = 0;
    std::time_t expiresAt = 0;
    static Artifact FromJson(const json& data);
    std::string FormatSize() const;
    std::string FormatDisplay() const;
};

// --- Activity feed (models/event.py) ---
struct EventActor {
    long long id = 0;
    std::string login;
    std::string avatarUrl;
};

struct EventRepo {
    long long id = 0;
    std::string name;  // "owner/repo"
    std::string url;
};

struct Event {
    std::string id;
    std::string type;
    EventActor actor;
    EventRepo repo;
    json payload = json::object();
    bool isPublic = true;
    std::time_t createdAt = 0;

    static Event FromJson(const json& data);
    std::string GetActionDescription() const;
    std::string FormatDisplay() const;
    std::string GetWebUrl() const;
    std::string GetActorUrl() const;
};

// --- Repository contents (models/content.py) ---
struct ContentItem {
    std::string name;
    std::string path;
    std::string sha;
    long long size = 0;
    std::string type = "file";  // file, dir, symlink, submodule
    std::string downloadUrl;
    std::string htmlUrl;
    std::string content;   // base64, for a single file
    std::string encoding;

    static ContentItem FromJson(const json& data);
    std::string GetDisplayName() const;
    std::string GetSizeStr() const;
};
