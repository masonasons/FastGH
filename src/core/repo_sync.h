#pragma once

// Repository auto-sync (a port of repo_sync.py): per-repository settings kept in
// the app config under "repo_sync_configs", and git fetch / pull / push runs.

#include "core/config.h"

#include <string>
#include <utility>
#include <vector>

struct RepoSyncConfig {
    bool enabled = false;
    bool autoPull = true;
    bool autoPush = false;
    std::string path;
};

struct RepoSyncResult {
    std::string repo;
    bool ok = false;
    std::string message;
};

class RepoSyncManager {
public:
    explicit RepoSyncManager(Config& prefs);

    RepoSyncConfig GetRepoConfig(const std::string& fullName, const std::string& defaultPath = "") const;
    void SetRepoConfig(const std::string& fullName, const RepoSyncConfig& config);
    std::vector<std::pair<std::string, RepoSyncConfig>> GetEnabledRepos() const;

    // Blocking: run on a worker thread.
    std::vector<RepoSyncResult> SyncAllEnabled();
    RepoSyncResult SyncOne(const std::string& fullName);
    RepoSyncResult SyncOne(const std::string& fullName, const RepoSyncConfig& config);
    // The external ".GITHUB" bootstrap helper, when configured. Throws std::runtime_error on failure.
    void RunRepoUpdate(const std::string& repoPath);

private:
    Config& m_prefs;
};
