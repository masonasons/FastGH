#pragma once

// Every FastGH window other than the main one, by what it shows. Each opens
// modally over `parent` (use GetActiveOwner() when there is no better one) and
// returns when it closes. The ones taking names fetch what they need first,
// saying so in the status bar, and report a failure in a message.

#include "core/models.h"

#include <wx/wx.h>

#include <functional>
#include <string>

class ActionBar;
class GitHubAccount;

// --- Repositories (ui/repo_dialog.cpp, ui/repo_lists.cpp) ---
void ShowRepoDialog(wxWindow* parent, const Repository& repo);
void OpenRepo(wxWindow* parent, const std::string& owner, const std::string& name);
void OpenUpstreamRepo(wxWindow* parent, const Repository& repo);
void ShowForksDialog(wxWindow* parent, const Repository& repo);
void ShowStargazersDialog(wxWindow* parent, const Repository& repo);
void ShowRepoSyncDialog(wxWindow* parent, const Repository& repo);
// Clone, or pull when already cloned, into the configured git folder.
void RunGitForRepo(wxWindow* parent, const Repository& repo);
// The repository actions every list of repositories offers (a port of
// GUI/repo_actions.py): view info, open in browser, copy URLs, files, issues,
// pull requests, commits, actions, releases, forks, stargazers, owner.
// `getRepo` returns the selected repository, or nullptr when there is none.
// The first ("&View Repository", Enter) is primary.
void AddRepoActions(ActionBar& bar, wxWindow* parent, std::function<const Repository*()> getRepo);

// --- Issues, pull requests, discussions (ui/issues_dialog.cpp, ui/pulls_dialog.cpp,
//     ui/discussion_dialog.cpp) ---
void ShowIssuesDialog(wxWindow* parent, const Repository& repo);
void ShowIssueDialog(wxWindow* parent, const Repository& repo, const Issue& issue);
void OpenIssue(wxWindow* parent, const std::string& owner, const std::string& name, int number);
void ShowPullRequestsDialog(wxWindow* parent, const Repository& repo);
void ShowPullRequestDialog(wxWindow* parent, const Repository& repo, const PullRequest& pr, bool canMerge);
void OpenPullRequest(wxWindow* parent, const std::string& owner, const std::string& name, int number);
void ShowDiscussionDialog(wxWindow* parent, const std::string& owner, const std::string& name,
                          const Discussion& discussion);
void OpenDiscussion(wxWindow* parent, const std::string& owner, const std::string& name, int number);

// --- Code (ui/commits_dialog.cpp, ui/files_dialog.cpp) ---
void ShowCommitsDialog(wxWindow* parent, const Repository& repo);
void ShowFilesDialog(wxWindow* parent, const Repository& repo);

// --- Actions and releases (ui/actions_dialog.cpp, ui/releases_dialog.cpp) ---
void ShowActionsDialog(wxWindow* parent, const Repository& repo);
void ShowReleasesDialog(wxWindow* parent, const Repository& repo);

// --- People and search (ui/search_dialog.cpp) ---
void ShowSearchDialog(wxWindow* parent);
void ShowUserProfileDialog(wxWindow* parent, const std::string& username);

// --- Settings (ui/accounts_dialog.cpp, ui/options_dialog.cpp) ---
void ShowAccountsDialog(wxWindow* parent);
void ShowOptionsDialog(wxWindow* parent);

// --- Sign in and updates (ui/signin.cpp, ui/updater.cpp) ---
// The device flow for `account`: shows the code, opens the browser, waits.
// True when the account now has a working token.
bool SignIn(wxWindow* parent, GitHubAccount& account);
void CheckForUpdates(bool silent);
