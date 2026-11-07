// The repository window and what hangs off it (a port of GUI/view.py): repository
// info, star/watch, git clone or pull with progress, and per-repository auto sync.

#include "ui/dialogs.h"
#include "ui/ui_common.h"

#include "core/app.h"
#include "core/process.h"
#include "core/repo_sync.h"
#include "core/util.h"

#include <wx/gauge.h>
#include <wx/timer.h>

#include <algorithm>
#include <atomic>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

// --- Where repositories live locally ---

std::string ExpandHome(const std::string& path) {
    if (path == "~") return HomeDir();
    if (StartsWith(path, "~/") || StartsWith(path, "~\\")) return JoinPath(HomeDir(), path.substr(2));
    return path;
}

std::string GitRoot() {
    return ExpandHome(app::Prefs().GetString("git_path", JoinPath(HomeDir(), "git")));
}

// <git_path>/<name>, or <git_path>/<owner>/<name> with the org structure option.
std::string LocalRepoPath(const Repository& repo) {
    std::string root = GitRoot();
    if (app::Prefs().GetBool("git_use_org_structure", false)) return JoinPath(JoinPath(root, repo.owner), repo.name);
    return JoinPath(root, repo.name);
}

bool IsClonedLocally(const Repository& repo) {
    return IsDirectory(JoinPath(LocalRepoPath(repo), ".git"));
}

std::string CloneUrl(const Repository& repo) { return "https://github.com/" + repo.fullName + ".git"; }

std::string Capitalize(std::string s) {
    if (!s.empty() && s[0] >= 'a' && s[0] <= 'z') s[0] = static_cast<char>(s[0] - 'a' + 'A');
    return s;
}

// --- Upstream lookup, shared by the repo window and OpenUpstreamRepo ---

struct UpstreamResult {
    std::string parentFullName;
    std::optional<Repository> parent;
};

// `parent` is only returned by the single-repo endpoint, so a repository from a
// list has isFork set but no parent name until its details are fetched.
UpstreamResult ResolveUpstream(const std::shared_ptr<GitHubAccount>& account, const Repository& repo) {
    UpstreamResult result;
    result.parentFullName = repo.parentFullName;
    if (result.parentFullName.empty()) {
        if (auto detail = account->GetRepo(repo.owner, repo.name)) result.parentFullName = detail->parentFullName;
    }
    auto slash = result.parentFullName.find('/');
    if (slash != std::string::npos)
        result.parent = account->GetRepo(result.parentFullName.substr(0, slash), result.parentFullName.substr(slash + 1));
    return result;
}

// Shows the upstream found by ResolveUpstream, or says why there is none.
void ShowUpstreamResult(wxWindow* parent, const UpstreamResult& result) {
    if (result.parentFullName.find('/') == std::string::npos) {
        ShowError(parent, "Could not determine the upstream repository.", "No Upstream");
    } else if (!result.parent) {
        ShowError(parent, "Upstream repository '" + U8(result.parentFullName) + "' not found or not accessible.",
                  "Repository Not Found");
    } else {
        ShowRepoDialog(parent, *result.parent);
    }
}

// --- Git progress ---

// One chunk of git's output, cleaned up for the window: whole lines for the
// text, and the latest progress line (git rewrites those with \r) for the status.
struct GitChunk {
    std::string lines;
    std::string status;
};

// Splits git's output into lines; \r-terminated progress updates only go to the
// status line, so the text isn't flooded with "Receiving objects: 1%..." lines.
class GitOutputSplitter {
public:
    GitChunk Feed(const std::string& data) {
        GitChunk chunk;
        for (char c : data) {
            if (c == '\n') {
                if (m_lastWasCr && m_pending.empty()) {
                    // "\r\n": the line was already taken at the \r; keep it in the text too.
                    if (!m_lastProgress.empty()) chunk.lines += m_lastProgress + "\n";
                } else {
                    chunk.lines += m_pending + "\n";
                    if (!Trim(m_pending).empty()) chunk.status = m_pending;
                }
                m_pending.clear();
                m_lastWasCr = false;
            } else if (c == '\r') {
                m_lastProgress = m_pending;
                if (!Trim(m_pending).empty()) chunk.status = m_pending;
                m_pending.clear();
                m_lastWasCr = true;
            } else {
                m_pending += c;
                m_lastWasCr = false;
            }
        }
        m_all += chunk.lines;
        return chunk;
    }
    GitChunk Flush() {
        GitChunk chunk;
        if (!m_pending.empty()) {
            chunk.lines = m_pending + "\n";
            chunk.status = m_pending;
            m_all += chunk.lines;
            m_pending.clear();
        }
        return chunk;
    }
    const std::string& All() const { return m_all; }

private:
    std::string m_pending;
    std::string m_lastProgress;
    std::string m_all;
    bool m_lastWasCr = false;
};

class GitProgressDialog : public BaseDialog {
public:
    GitProgressDialog(wxWindow* parent, const wxString& title, const wxString& operation)
        : BaseDialog(parent, title, wxSize(560, 360)), m_timer(this) {
        m_status = new wxStaticText(m_panel, wxID_ANY, "Starting " + operation + "...", wxDefaultPosition,
                                    wxDefaultSize, wxST_NO_AUTORESIZE | wxST_ELLIPSIZE_END);
        m_sizer->Add(m_status, 0, wxALL | wxEXPAND, 10);
        m_gauge = new wxGauge(m_panel, wxID_ANY, 100);
        m_sizer->Add(m_gauge, 0, wxLEFT | wxRIGHT | wxEXPAND, 10);
        m_output = new wxTextCtrl(m_panel, wxID_ANY, "", wxDefaultPosition, wxDefaultSize,
                                  wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2 | wxHSCROLL);
        AddLabeled("Git &output", m_output, 1);
        // wxID_CANCEL: the button and Escape both end the dialog; the caller treats
        // any ending before Done() as a cancel.
        auto* cancel = new wxButton(m_panel, wxID_CANCEL, "&Cancel");
        m_sizer->Add(cancel, 0, wxALL | wxALIGN_CENTER, 10);

        Bind(wxEVT_TIMER, [this](wxTimerEvent&) { m_gauge->Pulse(); });
        m_timer.Start(100);
        Finish();
        m_output->SetFocus();
    }

    void AddChunk(const GitChunk& chunk) {
        if (!chunk.lines.empty()) m_output->AppendText(U8(chunk.lines));
        if (!chunk.status.empty()) m_status->SetLabel(U8(Truncate(Trim(chunk.status), 80)));
    }

    void Done() {
        m_timer.Stop();
        m_gauge->SetValue(100);
        m_done = true;
        if (IsModal()) EndModal(wxID_OK);
        else CallAfter([this] { if (IsModal()) EndModal(wxID_OK); });
    }
    bool IsDone() const { return m_done; }

private:
    wxStaticText* m_status;
    wxGauge* m_gauge;
    wxTextCtrl* m_output;
    wxTimer m_timer;
    bool m_done = false;
};

struct GitOutcome {
    bool started = true;
    bool ok = false;
    std::string output;  // cleaned-up git output
    std::string error;
};

// Runs `git lfs install --local` and `git lfs pull` after a clone or pull. A
// missing git-lfs is not an error (as in the Python app).
std::pair<bool, std::string> RunLfsPostSync(const std::string& repoPath) {
    if (!IsDirectory(JoinPath(repoPath, ".git"))) return {false, "LFS skipped: repo path not found: " + repoPath};
    auto run = [&](std::vector<std::string> args) {
        args.insert(args.begin(), "git");
        return RunProcess(args, repoPath);
    };
    if (run({"lfs", "version"}).exitCode != 0) return {true, "Git LFS not installed; continuing without LFS objects."};
    auto install = run({"lfs", "install", "--local"});
    if (install.exitCode != 0) return {false, "git lfs install failed:\n" + Trim(install.output)};
    auto pull = run({"lfs", "pull"});
    if (pull.exitCode != 0) return {false, "git lfs pull failed:\n" + Trim(pull.output)};
    std::string message = "Git LFS sync completed.";
    if (!Trim(pull.output).empty()) message += "\n" + Trim(pull.output);
    return {true, message};
}

// --- Auto sync settings ---

class RepoSyncDialog : public BaseDialog {
public:
    RepoSyncDialog(wxWindow* parent, const Repository& repo)
        : BaseDialog(parent, "Auto Sync: " + U8(repo.fullName), wxSize(620, 360)), m_key(repo.fullName) {
        RepoSyncConfig cfg = app::RepoSync().GetRepoConfig(m_key, LocalRepoPath(repo));

        m_enabled = new wxCheckBox(m_panel, wxID_ANY, "&Enable auto sync for this repository");
        m_enabled->SetValue(cfg.enabled);
        m_sizer->Add(m_enabled, 0, wxALL, 10);
        m_pull = new wxCheckBox(m_panel, wxID_ANY, "Auto &pull (git pull --ff-only)");
        m_pull->SetValue(cfg.autoPull);
        m_sizer->Add(m_pull, 0, wxLEFT | wxRIGHT | wxBOTTOM, 10);
        m_push = new wxCheckBox(m_panel, wxID_ANY, "Auto p&ush (push only when branch is ahead and clean)");
        m_push->SetValue(cfg.autoPush);
        m_sizer->Add(m_push, 0, wxLEFT | wxRIGHT | wxBOTTOM, 10);

        m_path = new wxTextCtrl(m_panel, wxID_ANY, U8(cfg.path.empty() ? LocalRepoPath(repo) : cfg.path));
        AddLabeled("&Local path", m_path);

        auto* row = new wxBoxSizer(wxHORIZONTAL);
        auto* browse = new wxButton(m_panel, wxID_ANY, "&Browse...");
        m_runSync = new wxButton(m_panel, wxID_ANY, "Run Sync &Now");
        m_runUpdate = new wxButton(m_panel, wxID_ANY, "Run .GITHUB Repo &Update");
        row->Add(browse, 0, wxRIGHT, 6);
        row->Add(m_runSync, 0, wxRIGHT, 6);
        row->Add(m_runUpdate, 0);
        m_sizer->Add(row, 0, wxALL, 10);
        m_sizer->AddStretchSpacer();

        auto* buttons = new wxBoxSizer(wxHORIZONTAL);
        auto* save = new wxButton(m_panel, wxID_OK, "&Save");
        save->SetDefault();
        buttons->Add(save, 0, wxRIGHT, 8);
        buttons->Add(new wxButton(m_panel, wxID_CANCEL, "&Cancel"), 0);
        m_sizer->Add(buttons, 0, wxALL | wxALIGN_CENTER, 10);

        browse->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { Browse(); });
        m_runSync->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { RunSyncNow(); });
        m_runUpdate->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { RunRepoUpdate(); });
        save->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
            app::RepoSync().SetRepoConfig(m_key, Current());
            EndModal(wxID_OK);
        });

        Finish();
        m_enabled->SetFocus();
    }

private:
    RepoSyncConfig Current() const {
        RepoSyncConfig cfg;
        cfg.enabled = m_enabled->GetValue();
        cfg.autoPull = m_pull->GetValue();
        cfg.autoPush = m_push->GetValue();
        cfg.path = Trim(ToU8(m_path->GetValue()));
        return cfg;
    }

    void Browse() {
        std::string current = Trim(ToU8(m_path->GetValue()));
        if (current.empty() || !IsDirectory(current)) current = HomeDir();
        wxString path = AskDirectory(this, "Select Local Repository Path", U8(current));
        if (!path.empty()) m_path->SetValue(path);
    }

    void SetRunning(bool running) {
        m_runSync->Enable(!running);
        m_runUpdate->Enable(!running);
    }

    // Both runs are git work that can take a while: off the UI thread.
    void RunSyncNow() {
        RepoSyncConfig cfg = Current();
        std::string key = m_key;
        SetRunning(true);
        SetStatus("Syncing " + U8(key) + "...");
        RunAsync(this, [key, cfg] { return app::RepoSync().SyncOne(key, cfg); },
                 [this](RepoSyncResult result) {
                     SetRunning(false);
                     SetStatus("");
                     if (result.ok) ShowInfo(this, U8(result.message), "Repo Sync");
                     else ShowError(this, U8(result.message), "Repo Sync Failed");
                 });
    }

    void RunRepoUpdate() {
        std::string path = Current().path;
        if (path.empty()) {
            ShowError(this, "Set a local path first.", "Missing Path");
            return;
        }
        SetRunning(true);
        SetStatus("Running repo update...");
        RunAsync(this,
                 [path]() -> std::optional<std::string> {
                     try {
                         app::RepoSync().RunRepoUpdate(path);
                         return std::nullopt;
                     } catch (const std::exception& e) {
                         return std::string(e.what());
                     }
                 },
                 [this](std::optional<std::string> error) {
                     SetRunning(false);
                     SetStatus("");
                     if (error) ShowError(this, U8(*error), "Repo Update Failed");
                     else ShowInfo(this, "Repo update completed.", "Repo Update");
                 });
    }

    std::string m_key;
    wxCheckBox* m_enabled;
    wxCheckBox* m_pull;
    wxCheckBox* m_push;
    wxTextCtrl* m_path;
    wxButton* m_runSync;
    wxButton* m_runUpdate;
};

// --- The repository window ---

class RepoDialog : public BaseDialog {
public:
    RepoDialog(wxWindow* parent, const Repository& repo)
        : BaseDialog(parent, "Repository: " + U8(repo.fullName), wxSize(800, 550)),
          m_repo(repo), m_account(app::Current()) {
        m_info = new wxTextCtrl(m_panel, wxID_ANY, "", wxDefaultPosition, wxDefaultSize,
                                wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2);
        AddLabeled("Repository &details", m_info, 1);
        RenderInfo();

        m_actions = new ActionBar(m_panel);  // owned by the panel
        AddActions();
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER, 5);
        m_actions->AttachContextMenu(m_info);

        Finish();
        m_info->SetFocus();
        m_info->SetInsertionPoint(0);
        LoadStatus();
    }

private:
    // Access keys are unique across all actions, since the context menu lists them together.
    void AddActions() {
        auto& bar = *m_actions;
        // Primary: what people open a repository for most.
        bar.Add({"View &Issues", [this] { ShowIssuesDialog(this, m_repo); }, true}).Shortcut('I', wxMOD_CONTROL);
        bar.Add({"View &Pull Requests", [this] { ShowPullRequestsDialog(this, m_repo); }, true})
            .Shortcut('P', wxMOD_CONTROL);
        bar.Add({"View &Files", [this] { ShowFilesDialog(this, m_repo); }, true})
            .Shortcut('F', wxMOD_CONTROL | wxMOD_SHIFT);
        Action git{"", [this] { Git(); }, true};
        git.dynamicLabel = [this] { return IsClonedLocally(m_repo) ? wxString("Git Pu&ll") : wxString("Git C&lone"); };
        bar.Add(git);

        // More: the repository itself.
        Action star{"", [this] { ToggleStar(); }};
        star.dynamicLabel = [this] { return m_starred ? wxString("Un&star") : wxString("&Star"); };
        star.enabled = [this] { return m_statusKnown && !m_busy; };
        bar.Add(star);
        Action watch{"", [this] { ToggleWatch(); }};
        watch.dynamicLabel = [this] { return m_watched ? wxString("Un&watch") : wxString("&Watch"); };
        watch.enabled = [this] { return m_statusKnown && !m_busy; };
        bar.Add(watch);
        bar.Add({"Open in &Browser", [this] { OpenUrl(m_repo.htmlUrl); }}).Shortcut('O', wxMOD_CONTROL);
        bar.Add({"Copy &URL", [this] { CopyToClipboard(U8(m_repo.htmlUrl)); }});
        bar.Add({"Copy Clo&ne URL", [this] { CopyToClipboard(U8(CloneUrl(m_repo))); }})
            .Shortcut('C', wxMOD_CONTROL | wxMOD_SHIFT);
        bar.Add({"Auto S&ync...", [this] { ShowRepoSyncDialog(this, m_repo); }});
        bar.AddSeparator();

        // More: the other views.
        bar.Add({"View Co&mmits", [this] { ShowCommitsDialog(this, m_repo); }}).Shortcut('M', wxMOD_CONTROL);
        bar.Add({"View &Actions", [this] { ShowActionsDialog(this, m_repo); }}).Shortcut('G', wxMOD_CONTROL);
        bar.Add({"View R&eleases", [this] { ShowReleasesDialog(this, m_repo); }}).Shortcut('R', wxMOD_CONTROL);
        bar.Add({"View F&orks", [this] { ShowForksDialog(this, m_repo); }});
        bar.Add({"View Starga&zers", [this] { ShowStargazersDialog(this, m_repo); }});
        bar.Add({"View Owne&r", [this] { ShowUserProfileDialog(this, m_repo.owner); }});
        Action upstream{"View Ups&tream", [this] { ViewUpstream(); }};
        upstream.enabled = [this] { return m_repo.isFork && !m_resolvingUpstream; };
        bar.Add(upstream);
    }

    void RenderInfo() {
        const Repository& r = m_repo;
        std::string text;
        text += r.description.empty() ? "No description" : r.description;
        text += "\n\n";
        text += "Name: " + r.fullName + "\n";
        text += "Owner: " + r.owner + "\n";
        text += "Language: " + (r.language.empty() ? std::string("Not specified") : r.language) + "\n";
        text += "Stars: " + std::to_string(r.stars) + "\n";
        text += "Forks: " + std::to_string(r.forks) + "\n";
        text += "Open Issues: " + std::to_string(r.openIssues) + "\n";
        text += std::string("Visibility: ") + (r.isPrivate ? "Private" : "Public") + "\n";
        if (r.isFork) text += r.parentFullName.empty() ? "Fork: Yes\n" : "Forked from: " + r.parentFullName + "\n";
        if (r.pushedAt)
            text += "Last Push: " + FormatRelativeTime(r.pushedAt) + " (" + FormatLocalTime(r.pushedAt) + ")\n";
        text += "URL: " + r.htmlUrl;

        // Keep the reader's place when re-rendering after the upstream is resolved.
        long pos = m_info->GetInsertionPoint();
        m_info->ChangeValue(U8(text));
        m_info->SetInsertionPoint(std::min(pos, m_info->GetLastPosition()));
    }

    void LoadStatus() {
        auto account = m_account;
        if (!account) return;
        std::string owner = m_repo.owner, name = m_repo.name;
        RunAsync(this,
                 [account, owner, name] {
                     return std::make_pair(account->IsStarred(owner, name), account->IsWatching(owner, name));
                 },
                 [this](std::pair<bool, bool> status) {
                     m_starred = status.first;
                     m_watched = status.second;
                     m_statusKnown = true;
                     m_actions->Update();
                 });

        // Best effort: on failure "Fork: Yes" stays, and View Upstream reports the error.
        if (m_repo.isFork && m_repo.parentFullName.empty()) {
            RunAsync(this,
                     [account, owner, name]() -> std::string {
                         auto detail = account->GetRepo(owner, name);
                         return detail ? detail->parentFullName : std::string();
                     },
                     [this](std::string parent) {
                         if (parent.empty() || !m_repo.parentFullName.empty()) return;
                         m_repo.parentFullName = parent;
                         RenderInfo();
                     });
        }
    }

    void ToggleStar() {
        auto account = m_account;
        if (!account || m_busy) return;
        bool star = !m_starred;
        std::string owner = m_repo.owner, name = m_repo.name;
        m_busy = true;
        m_actions->Update();
        RunAsync(this,
                 [account, owner, name, star] {
                     return star ? account->StarRepo(owner, name) : account->UnstarRepo(owner, name);
                 },
                 [this, star](bool ok) {
                     m_busy = false;
                     if (ok) m_starred = star;
                     m_actions->Update();
                     if (!ok) ShowError(this, star ? "Failed to star repository." : "Failed to unstar repository.");
                     else ShowInfo(this, (star ? "Starred " : "Unstarred ") + U8(m_repo.fullName), "Success");
                 });
    }

    void ToggleWatch() {
        auto account = m_account;
        if (!account || m_busy) return;
        bool watch = !m_watched;
        std::string owner = m_repo.owner, name = m_repo.name;
        m_busy = true;
        m_actions->Update();
        RunAsync(this,
                 [account, owner, name, watch] {
                     return watch ? account->WatchRepo(owner, name) : account->UnwatchRepo(owner, name);
                 },
                 [this, watch](bool ok) {
                     m_busy = false;
                     if (ok) m_watched = watch;
                     m_actions->Update();
                     if (!ok) ShowError(this, watch ? "Failed to watch repository." : "Failed to unwatch repository.");
                     else ShowInfo(this, (watch ? "Now watching " : "Unwatched ") + U8(m_repo.fullName), "Success");
                 });
    }

    void Git() {
        RunGitForRepo(this, m_repo);
        m_actions->Update();  // Clone becomes Pull
    }

    void ViewUpstream() {
        auto account = m_account;
        if (!account) return;
        Repository repo = m_repo;
        m_resolvingUpstream = true;  // feedback, and no duplicate fetch while it loads
        m_actions->Update();
        SetStatus("Loading upstream of " + U8(repo.fullName) + "...");
        RunAsync(this, [account, repo] { return ResolveUpstream(account, repo); },
                 [this](UpstreamResult result) {
                     m_resolvingUpstream = false;
                     m_actions->Update();
                     SetStatus("");
                     if (m_repo.parentFullName.empty() && result.parentFullName.find('/') != std::string::npos) {
                         m_repo.parentFullName = result.parentFullName;
                         RenderInfo();
                     }
                     ShowUpstreamResult(this, result);
                 });
    }

    Repository m_repo;
    std::shared_ptr<GitHubAccount> m_account;
    wxTextCtrl* m_info;
    ActionBar* m_actions;
    bool m_statusKnown = false;
    bool m_starred = false;
    bool m_watched = false;
    bool m_busy = false;
    bool m_resolvingUpstream = false;
};

}  // namespace

void ShowRepoDialog(wxWindow* parent, const Repository& repo) {
    ShowModalDialog<RepoDialog>(parent, repo);
}

void OpenRepo(wxWindow* parent, const std::string& owner, const std::string& name) {
    auto account = app::Current();
    if (!account) {
        ShowError(parent, "You are not signed in.");
        return;
    }
    wxWindow* owner_window = parent ? parent : GetActiveOwner();
    wxString fullName = U8(owner + "/" + name);
    SetStatus("Loading " + fullName + "...");
    RunAsync(owner_window,
             [account, owner, name] {
                 auto repo = account->GetRepo(owner, name);
                 return std::make_pair(repo, repo ? std::string() : GitHubAccount::LastError());
             },
             [owner_window, fullName](std::pair<std::optional<Repository>, std::string> result) {
                 SetStatus("");
                 if (result.first) {
                     ShowRepoDialog(owner_window, *result.first);
                     return;
                 }
                 wxString message = "Repository '" + fullName + "' not found or you don't have access.";
                 if (!result.second.empty()) message += "\n\n" + U8(result.second);
                 ShowError(owner_window, message, "Repository Not Found");
             });
}

void OpenUpstreamRepo(wxWindow* parent, const Repository& repo) {
    if (!repo.isFork) {
        ShowInfo(parent, U8(repo.fullName) + " is not a fork.", "No Upstream");
        return;
    }
    auto account = app::Current();
    if (!account) {
        ShowError(parent, "You are not signed in.");
        return;
    }
    wxWindow* owner_window = parent ? parent : GetActiveOwner();
    SetStatus("Loading upstream of " + U8(repo.fullName) + "...");
    RunAsync(owner_window, [account, repo] { return ResolveUpstream(account, repo); },
             [owner_window](UpstreamResult result) {
                 SetStatus("");
                 ShowUpstreamResult(owner_window, result);
             });
}

void ShowRepoSyncDialog(wxWindow* parent, const Repository& repo) {
    ShowModalDialog<RepoSyncDialog>(parent, repo);
}

void RunGitForRepo(wxWindow* parent, const Repository& repo) {
    std::string root = GitRoot();
    if (!IsDirectory(root) && !MakeDirs(root)) {
        ShowError(parent, "Failed to create git path: " + U8(root));
        return;
    }

    const std::string repoPath = LocalRepoPath(repo);
    const bool pull = IsClonedLocally(repo);
    const std::string operation = pull ? "pull" : "clone";
    std::vector<std::string> args;
    std::string cwd;
    if (pull) {
        args = {"git", "pull", "--progress"};
        cwd = repoPath;
    } else {
        cwd = app::Prefs().GetBool("git_use_org_structure", false) ? JoinPath(root, repo.owner) : root;
        if (!IsDirectory(cwd) && !MakeDirs(cwd)) {
            ShowError(parent, "Failed to create directory: " + U8(cwd));
            return;
        }
        args = {"git", "clone", "--progress"};
        if (app::Prefs().GetBool("git_clone_recursive", false)) args.push_back("--recursive");
        args.push_back(CloneUrl(repo));
    }
    const bool lfs = app::Prefs().GetBool("git_lfs_enabled", true);

    auto* dlg = new GitProgressDialog(parent, (pull ? "Pulling " : "Cloning ") + U8(repo.name), U8(operation));
    auto cancelled = std::make_shared<std::atomic<bool>>(false);
    auto outcome = std::make_shared<std::optional<GitOutcome>>();
    // Chunks are posted to the dialog through a weak reference made here, on the UI thread.
    auto weak = std::make_shared<wxWeakRef<wxWindow>>(dlg);
    auto post = [weak](GitChunk chunk) {
        if (chunk.lines.empty() && chunk.status.empty()) return;
        wxTheApp->CallAfter([weak, chunk] {
            if (*weak) static_cast<GitProgressDialog*>(weak->get())->AddChunk(chunk);
        });
    };

    RunAsync(dlg,
             [args, cwd, repoPath, lfs, cancelled, post]() {
                 GitOutcome result;
                 GitOutputSplitter splitter;
                 ProcessResult proc =
                     RunProcess(args, cwd, [&](const std::string& data) { post(splitter.Feed(data)); });
                 post(splitter.Flush());
                 result.output = splitter.All();
                 if (!proc.started) {
                     result.started = false;
                     result.error = "Git is not installed or not in PATH.";
                     return result;
                 }
                 result.ok = proc.exitCode == 0 && !*cancelled;
                 if (result.ok && lfs) {
                     auto [lfsOk, lfsMessage] = RunLfsPostSync(repoPath);
                     if (!lfsMessage.empty()) post({"\n" + lfsMessage + "\n", FirstLine(lfsMessage)});
                     if (!lfsOk) {
                         result.ok = false;
                         result.error = lfsMessage.empty() ? "git lfs operation failed" : lfsMessage;
                     }
                 }
                 if (!result.ok && result.error.empty()) result.error = Trim(result.output);
                 return result;
             },
             [dlg, outcome](GitOutcome result) {
                 *outcome = std::move(result);
                 dlg->Done();
             });

    dlg->ShowModal();
    bool finished = dlg->IsDone() && outcome->has_value();
    dlg->Destroy();

    wxString op = U8(Capitalize(operation));
    if (!finished) {
        // RunProcess can't stop git, so say what is true: we stopped waiting.
        *cancelled = true;
        SetStatus(op + " cancelled");
        ShowInfo(parent, op + " was cancelled. Git may still finish in the background.", op + " Cancelled");
        return;
    }
    const GitOutcome& result = **outcome;
    if (result.ok) {
        SetStatus(op + " complete: " + U8(repo.fullName));
        if (!pull) {
            ShowInfo(parent, "Successfully cloned " + U8(repo.fullName) + " to:\n" + U8(repoPath), "Clone Complete");
        } else {
            std::string message = Trim(result.output);
            if (message.empty()) message = "Already up to date.";
            ShowInfo(parent, "Pull complete:\n\n" + U8(message), "Pull Complete");
        }
    } else {
        SetStatus(op + " failed: " + U8(repo.fullName));
        ShowError(parent, "Failed to " + U8(operation) + ":\n\n" + U8(result.error), op + " Failed");
    }
}
