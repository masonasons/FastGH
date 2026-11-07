#include "core/repo_sync.h"
#include "core/process.h"
#include "core/util.h"

#include <stdexcept>

namespace {

const char* kConfigs = "repo_sync_configs";

std::string Join(const std::vector<std::string>& args) {
    std::string out;
    for (const auto& a : args) out += (out.empty() ? "" : " ") + a;
    return out;
}

// Runs git in the repository; throws with git's message when it fails.
std::string Git(const std::string& repoPath, const std::vector<std::string>& args) {
    std::vector<std::string> cmd = {"git"};
    cmd.insert(cmd.end(), args.begin(), args.end());
    ProcessResult r = RunProcess(cmd, repoPath);
    if (!r.started) throw std::runtime_error("git could not be run. Is it installed?");
    if (r.exitCode != 0) throw std::runtime_error(Join(cmd) + " failed for " + repoPath + "\n" + Trim(r.output));
    return Trim(r.output);
}

bool GitAllowFail(const std::string& repoPath, const std::vector<std::string>& args) {
    std::vector<std::string> cmd = {"git"};
    cmd.insert(cmd.end(), args.begin(), args.end());
    ProcessResult r = RunProcess(cmd, repoPath);
    return r.started && r.exitCode == 0;
}

RepoSyncConfig FromJson(const json& j, const std::string& defaultPath) {
    RepoSyncConfig c;
    if (!j.is_object()) {
        c.path = defaultPath;
        return c;
    }
    c.enabled = j.value("enabled", false);
    c.autoPull = j.value("auto_pull", true);
    c.autoPush = j.value("auto_push", false);
    c.path = j.contains("path") && j["path"].is_string() ? j["path"].get<std::string>() : "";
    if (c.path.empty()) c.path = defaultPath;
    return c;
}

}  // namespace

RepoSyncManager::RepoSyncManager(Config& prefs) : m_prefs(prefs) {}

RepoSyncConfig RepoSyncManager::GetRepoConfig(const std::string& fullName, const std::string& defaultPath) const {
    json configs = m_prefs.GetJson(kConfigs, json::object());
    return FromJson(configs.is_object() && configs.contains(fullName) ? configs[fullName] : json(), defaultPath);
}

void RepoSyncManager::SetRepoConfig(const std::string& fullName, const RepoSyncConfig& config) {
    json configs = m_prefs.GetJson(kConfigs, json::object());
    if (!configs.is_object()) configs = json::object();
    configs[fullName] = {{"enabled", config.enabled},
                         {"auto_pull", config.autoPull},
                         {"auto_push", config.autoPush},
                         {"path", config.path}};
    m_prefs.SetJson(kConfigs, configs);
}

std::vector<std::pair<std::string, RepoSyncConfig>> RepoSyncManager::GetEnabledRepos() const {
    std::vector<std::pair<std::string, RepoSyncConfig>> out;
    json configs = m_prefs.GetJson(kConfigs, json::object());
    if (!configs.is_object()) return out;
    for (auto it = configs.begin(); it != configs.end(); ++it) {
        RepoSyncConfig c = FromJson(it.value(), "");
        if (c.enabled) out.emplace_back(it.key(), c);
    }
    return out;
}

std::vector<RepoSyncResult> RepoSyncManager::SyncAllEnabled() {
    std::vector<RepoSyncResult> results;
    if (!m_prefs.GetBool("repo_sync_enabled", false)) return results;
    for (const auto& [repo, config] : GetEnabledRepos()) results.push_back(SyncOne(repo, config));
    return results;
}

RepoSyncResult RepoSyncManager::SyncOne(const std::string& fullName) {
    return SyncOne(fullName, GetRepoConfig(fullName));
}

RepoSyncResult RepoSyncManager::SyncOne(const std::string& fullName, const RepoSyncConfig& config) {
    const std::string& path = config.path;
    if (path.empty()) return {fullName, false, "No local path configured."};
    if (!IsDirectory(path)) return {fullName, false, "Missing path: " + path};
    if (!IsDirectory(JoinPath(path, ".git"))) return {fullName, false, "Not a git repo: " + path};

    try {
        RunRepoUpdate(path);
        Git(path, {"fetch", "--all", "--prune"});
        if (config.autoPull) {
            Git(path, {"pull", "--ff-only"});
            if (m_prefs.GetBool("git_lfs_enabled", true) && GitAllowFail(path, {"lfs", "version"})) {
                Git(path, {"lfs", "install", "--local"});
                Git(path, {"lfs", "pull"});
            }
        }
        std::string push = "push disabled";
        if (config.autoPush) {
            if (!Git(path, {"status", "--porcelain"}).empty()) {
                push = "skipped push (dirty working tree)";
            } else {
                std::string branch = Git(path, {"rev-parse", "--abbrev-ref", "HEAD"});
                if (branch.empty() || branch == "HEAD") {
                    push = "skipped push (detached HEAD)";
                } else if (!GitAllowFail(path, {"rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"})) {
                    Git(path, {"push", "-u", "origin", branch});
                    push = "pushed (set upstream)";
                } else {
                    int ahead = 0;
                    try {
                        ahead = std::stoi(Git(path, {"rev-list", "--count", "@{u}..HEAD"}));
                    } catch (const std::invalid_argument&) {
                    }
                    if (ahead <= 0) {
                        push = "push not needed";
                    } else {
                        Git(path, {"push"});
                        push = "pushed (" + std::to_string(ahead) + " commit(s) ahead)";
                    }
                }
            }
        }
        return {fullName, true, "sync complete (" + push + ")"};
    } catch (const std::exception& e) {
        return {fullName, false, e.what()};
    }
}

void RepoSyncManager::RunRepoUpdate(const std::string& repoPath) {
    if (!m_prefs.GetBool("repo_sync_use_github_tools", true)) return;
    std::string tools = m_prefs.GetString("repo_sync_github_tools_path");
    if (tools.empty() || !IsDirectory(tools)) return;

    std::vector<std::string> cmd;
#ifdef _WIN32
    std::string batch = JoinPath(JoinPath(tools, "raywonder-repo-bootstrap"), "run-repo-update.bat");
    if (!PathExists(batch)) return;
    cmd = {"cmd", "/c", batch, repoPath};
#else
    std::string script = JoinPath(tools, "raywonder-repo-bootstrap/scripts/pull_and_fix_repo.ps1");
    if (!PathExists(script)) return;
    std::string shell = FindOnPath("pwsh");
    if (shell.empty()) shell = FindOnPath("powershell");
    if (shell.empty()) return;
    cmd = {shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-RepoRoot", repoPath};
#endif
    ProcessResult r = RunProcess(cmd, tools);
    if (!r.started || r.exitCode != 0)
        throw std::runtime_error("Repo bootstrap failed: " + Join(cmd) + "\n" + Trim(r.output));
}
