#pragma once

// Application-wide state (a port of application.py): the preferences, the
// signed-in accounts and which one is current, and repository sync.

#include "core/config.h"
#include "core/github.h"
#include "core/repo_sync.h"

#include <memory>
#include <string>
#include <vector>

class FastGHApp;  // the wxApp, in ui/app.cpp

namespace app {

// Loads the preferences and fills in their defaults (the same keys and
// defaults as the Python app). Call once at startup.
void LoadPrefs();
Config& Prefs();
RepoSyncManager& RepoSync();

// Accounts that have been loaded (a token, verified or not yet).
std::vector<std::shared_ptr<GitHubAccount>>& Accounts();
// The account the windows work with. Null before sign-in.
std::shared_ptr<GitHubAccount> Current();
void SetCurrent(const std::shared_ptr<GitHubAccount>& account);
// Adds account <index> (the next free index when -1) to Accounts() and the
// "accounts" count. Does not sign in.
std::shared_ptr<GitHubAccount> AddAccount(int index = -1);
// Removes the account and its config folder, shifting later folders down.
bool RemoveAccount(int index);

// Preference keys, defaults applied by LoadPrefs():
//   accounts (1), dark_mode ("off"), window_shown (true),
//   repoTemplate, download_location (~/Downloads), global_hotkey ("control+alt+g"),
//   git_path (~/git), git_use_org_structure (false), git_clone_recursive (false),
//   git_lfs_enabled (true), notify_activity/notifications/starred/watched (false),
//   auto_refresh_interval (0 minutes), repo_sync_enabled (false),
//   repo_sync_interval_minutes (0), repo_sync_configs ({}),
//   repo_sync_use_github_tools (true), repo_sync_notify (true),
//   repo_sync_github_tools_path, check_for_updates (true)

}  // namespace app
