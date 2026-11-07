#include "core/app.h"
#include "core/util.h"

#include <mutex>

namespace app {

namespace {

std::unique_ptr<Config> g_prefs;
std::unique_ptr<RepoSyncManager> g_repoSync;
std::vector<std::shared_ptr<GitHubAccount>> g_accounts;
std::mutex g_currentMutex;
std::shared_ptr<GitHubAccount> g_current;

}  // namespace

void LoadPrefs() {
    g_prefs = std::make_unique<Config>(AppConfigDir());
    Config& p = *g_prefs;
    const std::string home = HomeDir();

    p.SetDefault("accounts", 1);
    p.SetDefault("dark_mode", std::string("off"));
    p.SetDefault("window_shown", true);
    p.SetDefault("repoTemplate",
                 std::string("$full_name$ - $description$ | Stars: $stars$ | Forks: $forks$ | Issues: "
                             "$open_issues$ | $language$ | Updated $updated_at$"));
    p.SetDefault("download_location", JoinPath(home, "Downloads"));
    p.SetDefault("global_hotkey", std::string("control+alt+g"));
    p.SetDefault("git_path", JoinPath(home, "git"));
    p.SetDefault("git_use_org_structure", false);
    p.SetDefault("git_clone_recursive", false);
    p.SetDefault("git_lfs_enabled", true);
    p.SetDefault("notify_activity", false);
    p.SetDefault("notify_notifications", false);
    p.SetDefault("notify_starred", false);
    p.SetDefault("notify_watched", false);
    p.SetDefault("auto_refresh_interval", 0);
    p.SetDefault("repo_sync_enabled", false);
    p.SetDefault("repo_sync_interval_minutes", 0);
    p.SetDefault("repo_sync_configs", json::object());
    p.SetDefault("repo_sync_use_github_tools", true);
    p.SetDefault("repo_sync_notify", true);
#ifdef _WIN32
    p.SetDefault("repo_sync_github_tools_path", JoinPath(JoinPath(JoinPath(home, "dev"), "apps"), ".GITHUB"));
#else
    p.SetDefault("repo_sync_github_tools_path", JoinPath(home, "DEV/APPS/.GITHUB"));
#endif
    p.SetDefault("check_for_updates", true);

    g_repoSync = std::make_unique<RepoSyncManager>(p);
}

Config& Prefs() {
    return *g_prefs;
}

RepoSyncManager& RepoSync() {
    return *g_repoSync;
}

std::vector<std::shared_ptr<GitHubAccount>>& Accounts() {
    return g_accounts;
}

std::shared_ptr<GitHubAccount> Current() {
    std::lock_guard<std::mutex> lock(g_currentMutex);
    return g_current;
}

void SetCurrent(const std::shared_ptr<GitHubAccount>& account) {
    std::lock_guard<std::mutex> lock(g_currentMutex);
    g_current = account;
}

std::shared_ptr<GitHubAccount> AddAccount(int index) {
    if (index < 0) index = static_cast<int>(g_accounts.size());
    auto account = std::make_shared<GitHubAccount>(index);
    g_accounts.push_back(account);
    if (Prefs().GetInt("accounts", 1) < static_cast<int>(g_accounts.size()))
        Prefs().Set("accounts", static_cast<int>(g_accounts.size()));
    if (!Current()) SetCurrent(account);
    return account;
}

bool RemoveAccount(int index) {
    if (index < 0 || index >= static_cast<int>(g_accounts.size())) return false;
    auto removed = g_accounts[index];
    g_accounts.erase(g_accounts.begin() + index);

    // Folders are numbered by position: delete this one, shift the later ones down.
    int count = Prefs().GetInt("accounts", 1);
    RemoveTree(AccountConfigDir(index));
    for (int j = index + 1; j < count; j++) {
        if (PathExists(AccountConfigDir(j))) RenamePath(AccountConfigDir(j), AccountConfigDir(j - 1));
    }
    Prefs().Set("accounts", count > 0 ? count - 1 : 0);

    // The remaining account objects now point at renumbered folders: reload them.
    for (size_t i = static_cast<size_t>(index); i < g_accounts.size(); i++) {
        bool wasCurrent = g_accounts[i] == Current();
        auto reloaded = std::make_shared<GitHubAccount>(static_cast<int>(i));
        g_accounts[i] = reloaded;
        if (wasCurrent) SetCurrent(reloaded);
    }
    if (Current() == removed) SetCurrent(g_accounts.empty() ? nullptr : g_accounts.front());
    return true;
}

}  // namespace app
