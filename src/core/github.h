#pragma once

// The GitHub REST and GraphQL API for one signed-in account: a port of the
// Python github_api.GitHubAccount. Every call blocks, so run them on a worker
// thread (see RunAsync in ui/ui_common.h); calls may run on several threads at
// once. Failures return empty lists / nullopt / false, and LastError() (per
// thread) says why.
//
// Faster than the Python client:
// - lists of many pages fetch page 1, read the last page number from the Link
//   header, then fetch the remaining pages in parallel;
// - list GETs are conditional (If-None-Match with the ETag of the previous
//   identical request), so an unchanged refresh costs a 304 and no rate limit.

#include "core/config.h"
#include "core/models.h"

#include <atomic>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <utility>
#include <vector>

// The OAuth app FastGH signs in with (device flow).
extern const char* const kGitHubClientId;

// Sign-in through the device flow: show userCode and verificationUri, then poll.
struct DeviceCode {
    std::string deviceCode;
    std::string userCode;
    std::string verificationUri;
    int expiresIn = 900;
    int interval = 5;
};
// Asks GitHub for a code. nullopt (with *error set) on failure.
std::optional<DeviceCode> RequestDeviceCode(std::string* error);
enum class DevicePollResult { Pending, SlowDown, Success, Expired, Denied, Error };
// One poll; on Success, *token is the access token.
DevicePollResult PollDeviceToken(const DeviceCode& code, std::string* token, std::string* error);

// One page of a list, and whether more follow. Lists load a page at a time: the
// first shows at once, the next when the reader reaches the end (ui/paged_list.h).
template <typename T>
struct Page {
    std::vector<T> items;
    bool hasMore = false;
};
// Items per page for paged lists.
constexpr int kPageSize = 50;

// Progress for downloads: bytes so far, total (0 if unknown). Return false to cancel.
using ProgressFn = std::function<bool(uint64_t received, uint64_t total)>;

class GitHubAccount {
public:
    // Loads <AccountConfigDir(index)>/config.json. Does no network work.
    explicit GitHubAccount(int index);

    int Index() const { return m_index; }
    Config& Prefs() { return *m_prefs; }
    bool HasToken() const;
    void SetToken(const std::string& token);  // saved to the account's config

    enum class VerifyResult { Ok, Unauthorized, Failed };
    // GET /user, filling Me(). Unauthorized means the token is no good.
    VerifyResult Verify();
    json Me() const;
    std::string Username() const;     // login
    std::string DisplayName() const;  // name, else login

    static std::string LastError();

    // --- Repositories ---
    std::vector<Repository> GetRepos(const std::string& sort = "pushed");
    std::vector<Repository> GetStarred();   // sorted by pushedAt, newest first
    std::vector<Repository> GetWatched();   // sorted by pushedAt, newest first
    std::optional<Repository> GetRepo(const std::string& owner, const std::string& repo);
    std::vector<Repository> GetForks(const std::string& owner, const std::string& repo,
                                     const std::string& sort = "newest");
    // One page; second is whether more remain.
    std::pair<std::vector<Stargazer>, bool> GetStargazers(const std::string& owner, const std::string& repo,
                                                          int page = 1, int perPage = 100);
    // "admin", "maintain", "write", "triage", "read", or "" if unknown.
    std::string GetRepoPermission(const std::string& owner, const std::string& repo);
    bool CanMerge(const std::string& owner, const std::string& repo);

    bool IsStarred(const std::string& owner, const std::string& repo);
    bool StarRepo(const std::string& owner, const std::string& repo);
    bool UnstarRepo(const std::string& owner, const std::string& repo);
    bool IsWatching(const std::string& owner, const std::string& repo);
    bool WatchRepo(const std::string& owner, const std::string& repo);
    bool UnwatchRepo(const std::string& owner, const std::string& repo);

    // --- Issues ---
    std::vector<Issue> GetIssues(const std::string& owner, const std::string& repo, const std::string& state = "open");
    std::optional<Issue> GetIssue(const std::string& owner, const std::string& repo, int number);
    std::optional<Issue> CreateIssue(const std::string& owner, const std::string& repo, const std::string& title,
                                     const std::string& body = "", const std::vector<std::string>& labels = {});
    // Empty optional fields are left unchanged.
    std::optional<Issue> UpdateIssue(const std::string& owner, const std::string& repo, int number,
                                     const std::optional<std::string>& title, const std::optional<std::string>& body,
                                     const std::optional<std::string>& state);
    bool CloseIssue(const std::string& owner, const std::string& repo, int number);
    bool ReopenIssue(const std::string& owner, const std::string& repo, int number);
    std::vector<Comment> GetIssueComments(const std::string& owner, const std::string& repo, int number);
    std::optional<Comment> CreateIssueComment(const std::string& owner, const std::string& repo, int number,
                                              const std::string& body);
    bool DeleteIssueComment(const std::string& owner, const std::string& repo, long long commentId);

    // --- Pull requests ---
    std::vector<PullRequest> GetPullRequests(const std::string& owner, const std::string& repo,
                                             const std::string& state = "open");
    std::optional<PullRequest> GetPullRequest(const std::string& owner, const std::string& repo, int number);
    std::optional<PullRequest> CreatePullRequest(const std::string& owner, const std::string& repo,
                                                 const std::string& title, const std::string& head,
                                                 const std::string& base, const std::string& body = "",
                                                 bool draft = false);
    std::optional<PullRequest> UpdatePullRequest(const std::string& owner, const std::string& repo, int number,
                                                 const std::optional<std::string>& title,
                                                 const std::optional<std::string>& body,
                                                 const std::optional<std::string>& state);
    // mergeMethod: "merge", "squash" or "rebase". Empty title/message: GitHub's default.
    bool MergePullRequest(const std::string& owner, const std::string& repo, int number,
                          const std::string& commitTitle = "", const std::string& commitMessage = "",
                          const std::string& mergeMethod = "merge");
    bool ClosePullRequest(const std::string& owner, const std::string& repo, int number);
    std::vector<Comment> GetPrReviewComments(const std::string& owner, const std::string& repo, int number);
    // Issue comments and review comments together, oldest first.
    std::vector<Comment> GetPrComments(const std::string& owner, const std::string& repo, int number);
    std::optional<Comment> CreatePrComment(const std::string& owner, const std::string& repo, int number,
                                           const std::string& body);

    // --- Discussions (GraphQL) ---
    std::optional<Discussion> GetDiscussion(const std::string& owner, const std::string& repo, int number,
                                            int commentsFirst = 50);
    struct CommentPage {
        std::vector<DiscussionComment> comments;
        bool hasNextPage = false;
        std::string endCursor;
    };
    std::optional<CommentPage> GetDiscussionComments(const std::string& owner, const std::string& repo, int number,
                                                     int first = 50, const std::string& after = "");
    std::optional<DiscussionComment> CreateDiscussionComment(const std::string& discussionId, const std::string& body);

    // --- Commits and branches ---
    // One page; second is whether more remain. `sha`: branch or SHA, empty for the default branch.
    std::pair<std::vector<Commit>, bool> GetCommits(const std::string& owner, const std::string& repo,
                                                    const std::string& sha = "", int page = 1, int perPage = 50);
    std::optional<Commit> GetCommit(const std::string& owner, const std::string& repo, const std::string& sha);
    // Sorted by last commit date, newest first (GraphQL, REST fallback).
    std::vector<Branch> GetBranches(const std::string& owner, const std::string& repo);

    // --- Search and users ---
    std::vector<Repository> SearchRepos(const std::string& query, const std::string& sort = "best-match",
                                        int perPage = 30);
    std::vector<UserProfile> SearchUsers(const std::string& query, const std::string& sort = "best-match",
                                         int perPage = 30);
    std::optional<UserProfile> GetUser(const std::string& username);
    std::vector<Repository> GetUserRepos(const std::string& username, const std::string& sort = "pushed");
    std::vector<UserProfile> GetFollowing();
    bool IsFollowing(const std::string& username);
    bool FollowUser(const std::string& username);
    bool UnfollowUser(const std::string& username);

    // --- Actions ---
    std::vector<Workflow> GetWorkflows(const std::string& owner, const std::string& repo);
    // 0 / empty filters mean "any".
    std::vector<WorkflowRun> GetWorkflowRuns(const std::string& owner, const std::string& repo,
                                             long long workflowId = 0, const std::string& branch = "",
                                             const std::string& status = "", int perPage = 30);
    std::optional<WorkflowRun> GetWorkflowRun(const std::string& owner, const std::string& repo, long long runId);
    std::vector<WorkflowJob> GetWorkflowRunJobs(const std::string& owner, const std::string& repo, long long runId);
    bool RerunWorkflow(const std::string& owner, const std::string& repo, long long runId);
    bool RerunFailedJobs(const std::string& owner, const std::string& repo, long long runId);
    bool CancelWorkflowRun(const std::string& owner, const std::string& repo, long long runId);
    std::string GetWorkflowRunLogsUrl(const std::string& owner, const std::string& repo, long long runId);
    std::optional<std::string> GetJobLogs(const std::string& owner, const std::string& repo, long long jobId);
    std::vector<Artifact> GetRunArtifacts(const std::string& owner, const std::string& repo, long long runId);
    bool DownloadArtifact(const std::string& owner, const std::string& repo, long long artifactId,
                          const std::string& destPath, const ProgressFn& progress = nullptr);

    // --- Releases ---
    std::vector<Release> GetReleases(const std::string& owner, const std::string& repo, int perPage = 30);
    std::optional<Release> GetRelease(const std::string& owner, const std::string& repo, long long releaseId);
    std::optional<Release> GetLatestRelease(const std::string& owner, const std::string& repo);
    std::optional<Release> GetReleaseByTag(const std::string& owner, const std::string& repo, const std::string& tag);
    bool DownloadAsset(const std::string& owner, const std::string& repo, long long assetId,
                       const std::string& destPath, const ProgressFn& progress = nullptr);
    // Any URL (zipball/tarball), with this account's token.
    bool DownloadUrl(const std::string& url, const std::string& destPath, const ProgressFn& progress = nullptr);

    // --- Notifications ---
    std::vector<Notification> GetNotifications(bool all = false, bool participating = false);
    std::vector<Notification> GetRepoNotifications(const std::string& owner, const std::string& repo,
                                                   bool all = false, bool participating = false);
    // Empty lastReadAt: now.
    bool MarkNotificationsRead(const std::string& lastReadAt = "");
    bool MarkRepoNotificationsRead(const std::string& owner, const std::string& repo,
                                   const std::string& lastReadAt = "");
    bool MarkThreadRead(const std::string& threadId);
    bool MarkThreadDone(const std::string& threadId);
    std::optional<json> GetThreadSubscription(const std::string& threadId);
    bool SubscribeToThread(const std::string& threadId);
    bool UnsubscribeFromThread(const std::string& threadId);
    bool MuteThread(const std::string& threadId);

    // --- Events ---
    std::vector<Event> GetReceivedEvents(int perPage = 100, int maxPages = 3);
    std::vector<Event> GetUserEvents(const std::string& username, int perPage = 30);
    std::vector<Event> GetRepoEvents(const std::string& owner, const std::string& repo, int perPage = 30);
    std::vector<Event> GetOrgEvents(const std::string& org, int perPage = 30);

    // --- Contents ---
    // A directory's items; a single file comes back as one item with its content.
    std::optional<std::vector<ContentItem>> GetContents(const std::string& owner, const std::string& repo,
                                                        const std::string& path = "", const std::string& ref = "");
    // Decoded text of a file.
    std::optional<std::string> GetFileContent(const std::string& owner, const std::string& repo,
                                              const std::string& path, const std::string& ref = "");
    std::optional<std::string> GetReadme(const std::string& owner, const std::string& repo,
                                         const std::string& ref = "");

    // --- Single pages (1-based), for lists that load as the reader goes ---
    Page<Repository> GetReposPage(int page, const std::string& sort = "pushed");
    Page<Repository> GetStarredPage(int page);  // most recently pushed first
    Page<Repository> GetWatchedPage(int page);
    Page<UserProfile> GetFollowingPage(int page);
    Page<Notification> GetNotificationsPage(int page, bool all = false, bool participating = false);
    Page<Event> GetReceivedEventsPage(int page);  // GitHub keeps 300 events: 3 pages of 100
    Page<Issue> GetIssuesPage(const std::string& owner, const std::string& repo, const std::string& state, int page);
    Page<PullRequest> GetPullRequestsPage(const std::string& owner, const std::string& repo,
                                          const std::string& state, int page);
    Page<Repository> GetForksPage(const std::string& owner, const std::string& repo, const std::string& sort,
                                  int page);
    Page<Repository> GetUserReposPage(const std::string& username, const std::string& sort, int page);
    Page<Release> GetReleasesPage(const std::string& owner, const std::string& repo, int page);
    Page<WorkflowRun> GetWorkflowRunsPage(const std::string& owner, const std::string& repo, long long workflowId,
                                          const std::string& branch, const std::string& status, int page);
    Page<Repository> SearchReposPage(const std::string& query, const std::string& sort, int page);
    Page<UserProfile> SearchUsersPage(const std::string& query, const std::string& sort, int page);

    // --- Low level, for anything not covered above ---
    struct ApiResponse {
        long status = 0;
        json data;  // parsed body (null when empty or not JSON)
        std::string raw;
        std::map<std::string, std::string> headers;
        bool ok() const { return status >= 200 && status < 300; }
    };
    // `path` is "/repos/..." (or a full https:// URL). `body` is sent as JSON when not null.
    ApiResponse Request(const std::string& method, const std::string& path, const json& body = json(),
                        const std::vector<std::string>& extraHeaders = {});
    // GraphQL data, or nullopt with LastError() set.
    std::optional<json> Graphql(const std::string& query, const json& variables = json::object());

private:
    int m_index;
    std::unique_ptr<Config> m_prefs;
    mutable std::mutex m_meMutex;
    json m_me;
    // ETag cache for conditional GETs: url -> (etag, body)
    std::mutex m_etagMutex;
    std::map<std::string, std::pair<std::string, std::string>> m_etags;
};
