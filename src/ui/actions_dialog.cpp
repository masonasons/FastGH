// GitHub Actions: workflow runs, a run's jobs and steps, job logs and run
// artifacts (a port of GUI/actions.py).

#include "ui/dialogs.h"

#include "core/app.h"
#include "core/github.h"
#include "core/models.h"
#include "core/util.h"
#include "ui/paged_list.h"
#include "ui/ui_common.h"

#include <wx/choice.h>
#include <wx/filefn.h>
#include <wx/progdlg.h>
#include <wx/wupdlock.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <memory>
#include <optional>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {

Action MakeAction(const wxString& label, std::function<void()> run, bool primary = false,
                  std::function<bool()> enabled = nullptr) {
    Action a;
    a.label = label;
    a.run = std::move(run);
    a.primary = primary;
    a.enabled = std::move(enabled);
    return a;
}

// What a worker fetched, with the reason when it came back empty.
template <typename T>
struct Fetched {
    T value{};
    std::string error;
};

// After a refresh, selects the item with `id` again if it is still listed.
template <typename T>
void KeepSelection(wxListBox* list, const PagedList<T>& paged, long long id) {
    if (!id) return;
    const auto& items = paged.Items();
    for (size_t i = 0; i < items.size(); ++i)
        if (items[i].id == id) {
            list->SetSelection(static_cast<int>(i));
            return;
        }
}

wxString FormatTime(std::time_t t) { return U8(FormatLocalTime(t, "%Y-%m-%d %H:%M:%S")); }

wxString FileManagerName() {
#if defined(__WXOSX__)
    return "Finder";
#elif defined(__WXMSW__)
    return "File Explorer";
#else
    return "the file manager";
#endif
}

// --- Downloads ---------------------------------------------------------------
// (The same helper is in releases_dialog.cpp; it belongs in ui_common once the
// header can change.)

struct DownloadJob {
    wxString name;     // shown while it downloads
    std::string dest;  // full path
    // Runs on the worker thread; false on failure or when cancelled.
    std::function<bool(const ProgressFn&)> fetch;
};

// The download folder from the preferences, created if needed. nullopt (after
// saying why) when it can't be made.
std::optional<std::string> GetDownloadDir(wxWindow* parent) {
    std::string dir = app::Prefs().GetString("download_location", JoinPath(HomeDir(), "Downloads"));
    if (!IsDirectory(dir) && !MakeDirs(dir)) {
        ShowError(parent, "Could not create the download folder:\n" + U8(dir));
        return std::nullopt;
    }
    return dir;
}

// The last path component of a name from the API, so a download can't land
// outside the download folder.
std::string SafeFileName(const std::string& name) {
    size_t slash = name.find_last_of("/\\");
    std::string base = slash == std::string::npos ? name : name.substr(slash + 1);
    if (base.empty() || base == "." || base == "..") base = "download";
    return base;
}

// Shared between the worker and the UI thread. `dialog` and `owner` are touched
// on the UI thread only.
struct DownloadState {
    std::atomic<bool> cancelled{false};
    std::atomic<bool> updatePending{false};
    std::atomic<uint64_t> received{0};
    std::atomic<uint64_t> total{0};
    std::atomic<size_t> index{0};
    std::vector<wxString> names;
    wxProgressDialog* dialog = nullptr;
    wxWeakRef<wxWindow> owner;
    wxWeakRef<wxWindow> focus;
};

void UpdateDownloadProgress(const std::shared_ptr<DownloadState>& st) {
    st->updatePending = false;
    if (!st->dialog || st->cancelled) return;
    size_t i = std::min(st->index.load(), st->names.size() - 1);
    uint64_t got = st->received, total = st->total;
    wxString msg = "Downloading " + st->names[i];
    if (st->names.size() > 1) msg += wxString::Format(" (%zu of %zu)", i + 1, st->names.size());
    msg += "\n" + U8(FormatSize(got));
    if (total) msg += " of " + U8(FormatSize(total));
    bool keepGoing;
    if (total) {
        // Held below the maximum: reaching it would finish the dialog early.
        int pct = static_cast<int>(std::min<uint64_t>(got * 100 / total, 99));
        keepGoing = st->dialog->Update(pct, msg);
    } else {
        keepGoing = st->dialog->Pulse(msg);
    }
    if (!keepGoing) st->cancelled = true;
}

// Downloads `jobs` one after another on a worker thread behind a cancellable
// progress dialog, then reports and offers to show the result.
void RunDownloads(wxWindow* parent, const wxString& title, std::vector<DownloadJob> jobs) {
    if (jobs.empty()) return;
    auto st = std::make_shared<DownloadState>();
    for (const auto& j : jobs) st->names.push_back(j.name);
    st->owner = parent;
    st->focus = wxWindow::FindFocus();
    wxString first = "Downloading " + jobs[0].name;
    if (jobs.size() > 1) first += wxString::Format(" (1 of %zu)", jobs.size());
    st->dialog = new wxProgressDialog(title, first + "\n ", 100, parent,
                                      wxPD_APP_MODAL | wxPD_CAN_ABORT | wxPD_ELAPSED_TIME);

    std::thread([st, jobs = std::move(jobs)]() {
        using Clock = std::chrono::steady_clock;
        auto lastPost = Clock::now() - std::chrono::seconds(1);
        std::vector<std::string> done;
        std::vector<wxString> failed;
        std::string lastError;
        for (size_t i = 0; i < jobs.size() && !st->cancelled; ++i) {
            st->index = i;
            st->received = 0;
            st->total = 0;
            ProgressFn progress = [st, &lastPost](uint64_t got, uint64_t total) {
                st->received = got;
                st->total = total;
                auto now = Clock::now();
                // A few updates a second is plenty, and keeps the UI queue short.
                if (now - lastPost >= std::chrono::milliseconds(250) && !st->updatePending.exchange(true)) {
                    lastPost = now;
                    wxTheApp->CallAfter([st] { UpdateDownloadProgress(st); });
                }
                return !st->cancelled.load();
            };
            if (jobs[i].fetch(progress)) {
                done.push_back(jobs[i].dest);
            } else {
                // A cancelled or failed download leaves a partial file behind.
                wxRemoveFile(U8(jobs[i].dest));
                if (!st->cancelled) {
                    failed.push_back(jobs[i].name);
                    lastError = GitHubAccount::LastError();
                }
            }
        }
        size_t total = jobs.size();
        wxTheApp->CallAfter([st, done, failed, lastError, total] {
            delete st->dialog;
            st->dialog = nullptr;
            wxWindow* owner = st->owner ? st->owner.get() : GetActiveOwner();
            if (st->cancelled) {
                SetStatus(done.empty() ? wxString("Download cancelled")
                                       : wxString::Format("Download cancelled after %zu file%s", done.size(),
                                                          Plural(done.size())));
            } else if (failed.empty()) {
                wxString what = total == 1 ? "Downloaded:\n" + U8(done[0])
                                           : wxString::Format("Downloaded %zu files to:\n", done.size()) +
                                                 wxPathOnly(U8(done[0]));
                if (AskYesNo(owner, what + "\n\nShow in " + FileManagerName() + "?", "Download Complete"))
                    RevealInFileManager(U8(done[0]));
            } else if (done.empty()) {
                wxString what = failed.size() == 1 ? "Failed to download " + failed[0] + "."
                                                   : wxString::Format("All %zu downloads failed.", failed.size());
                if (!lastError.empty()) what += "\n\n" + U8(lastError);
                ShowError(owner, what);
            } else {
                wxString what = wxString::Format("Downloaded %zu file%s, %zu failed:\n", done.size(),
                                                 Plural(done.size()), failed.size());
                for (const auto& f : failed) what += f + "\n";
                if (!lastError.empty()) what += "\n" + U8(lastError) + "\n";
                what += "\nLocation: " + wxPathOnly(U8(done[0]));
                if (AskYesNo(owner, what + "\n\nShow in " + FileManagerName() + "?", "Download Complete"))
                    RevealInFileManager(U8(done[0]));
            }
            if (st->focus) st->focus->SetFocus();
        });
    }).detach();
}

// --- Shared run text -----------------------------------------------------------

bool CanRerun(const WorkflowRun& r) { return r.status == "completed"; }
bool CanRerunFailed(const WorkflowRun& r) { return r.status == "completed" && r.conclusion == "failure"; }
bool CanCancel(const WorkflowRun& r) { return r.status == "in_progress" || r.status == "queued"; }

wxString RunLabel(const WorkflowRun& r) { return wxString::Format("'%s' #%d", U8(r.name), r.runNumber); }

// Confirms, then re-runs / re-runs failed jobs / cancels `run`, reporting the
// result and calling `after` on success.
enum class RunOp { Rerun, RerunFailed, Cancel };
void DoRunOp(wxWindow* parent, const Repository& repo, const WorkflowRun& run, RunOp op,
             std::function<void()> after) {
    wxString question, title;
    switch (op) {
        case RunOp::Rerun:
            question = "Re-run workflow " + RunLabel(run) + "?";
            title = "Confirm Re-run";
            break;
        case RunOp::RerunFailed:
            question = "Re-run failed jobs for " + RunLabel(run) + "?";
            title = "Confirm Re-run Failed Jobs";
            break;
        case RunOp::Cancel:
            question = "Cancel workflow run " + RunLabel(run) + "?";
            title = "Confirm Cancel";
            break;
    }
    if (!AskYesNo(parent, question, title)) return;
    auto account = app::Current();
    std::string owner = repo.owner, name = repo.name;
    long long id = run.id;
    SetStatus(op == RunOp::Cancel ? "Cancelling workflow run..." : "Starting re-run...");
    RunAsync(
        parent,
        [=]() -> Fetched<bool> {
            bool ok = op == RunOp::Rerun         ? account->RerunWorkflow(owner, name, id)
                      : op == RunOp::RerunFailed ? account->RerunFailedJobs(owner, name, id)
                                                 : account->CancelWorkflowRun(owner, name, id);
            return {ok, ok ? "" : GitHubAccount::LastError()};
        },
        [parent, op, after](Fetched<bool> r) {
            SetStatus("");
            if (r.value) {
                ShowInfo(parent, op == RunOp::Cancel ? "Workflow run cancelled!" : "Workflow re-run started!",
                         "Success");
                if (after) after();
            } else {
                wxString msg = op == RunOp::Cancel ? "Failed to cancel workflow run." : "Failed to re-run workflow.";
                if (!r.error.empty()) msg += "\n\n" + U8(r.error);
                ShowError(parent, msg);
            }
        });
}

// --- Artifacts -----------------------------------------------------------------

class ArtifactsDialog : public BaseDialog {
public:
    ArtifactsDialog(wxWindow* parent, const Repository& repo, const WorkflowRun& run)
        : BaseDialog(parent, wxString::Format("Artifacts - Run #%d", run.runNumber), wxSize(700, 500)),
          m_repo(repo),
          m_run(run) {
        m_list = new wxListBox(m_panel, wxID_ANY);
        AddLabeled("&Artifacts", m_list, 1);

        m_actions = new ActionBar(m_panel);
        auto hasSelection = [this] { return Current() != nullptr; };
        m_actions->Add(MakeAction("&Download", [this] { Download(); }, true, hasSelection)).Shortcut(WXK_RETURN);
        m_actions->Add(MakeAction("Download A&ll", [this] { DownloadAll(); }, true, [this] {
            return std::any_of(m_artifacts.begin(), m_artifacts.end(), [](const Artifact& a) { return !a.expired; });
        }));
        m_actions->Add(MakeAction("R&efresh", [this] { Load(); })).Shortcut('R', wxMOD_CONTROL);
        m_actions->Add(MakeAction("Open Run in &Browser", [this] { OpenUrl(m_run.htmlUrl); }))
            .Shortcut('O', wxMOD_CONTROL);
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL, 5);
        m_actions->AttachContextMenu(m_list);

        m_list->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) { m_actions->Update(); });
        m_list->Bind(wxEVT_LISTBOX_DCLICK, [this](wxCommandEvent&) { CallAfter([this] { Download(); }); });

        Finish();
        m_list->SetFocus();
        Load();
    }

private:
    const Artifact* Current() const {
        int i = Selected(m_list);
        return i >= 0 && i < static_cast<int>(m_artifacts.size()) ? &m_artifacts[i] : nullptr;
    }

    void Load() {
        m_artifacts.clear();
        SetListItems(m_list, {"Loading..."});
        m_actions->Update();
        auto account = app::Current();
        std::string owner = m_repo.owner, name = m_repo.name;
        long long id = m_run.id;
        RunAsync(
            this,
            [=]() -> Fetched<std::vector<Artifact>> {
                auto items = account->GetRunArtifacts(owner, name, id);
                return {items, items.empty() ? GitHubAccount::LastError() : ""};
            },
            [this](Fetched<std::vector<Artifact>> r) {
                m_artifacts = std::move(r.value);
                std::vector<wxString> rows;
                for (const auto& a : m_artifacts) rows.push_back(U8(a.FormatDisplay()));
                if (rows.empty())
                    rows.push_back(r.error.empty() ? "No artifacts found" : "Could not load artifacts: " + U8(r.error));
                SetListItems(m_list, rows);
                m_actions->Update();
            });
    }

    std::string DestPath(const std::string& dir, const Artifact& a) const {
        // Artifacts always arrive as zips.
        std::string name = SafeFileName(a.name);
        if (!EndsWith(ToLower(name), ".zip")) name += ".zip";
        return JoinPath(dir, name);
    }

    DownloadJob MakeJob(const std::string& dir, const Artifact& a) const {
        auto account = app::Current();
        std::string owner = m_repo.owner, name = m_repo.name, dest = DestPath(dir, a);
        long long id = a.id;
        return {U8(a.name), dest, [=](const ProgressFn& p) {
                    return account->DownloadArtifact(owner, name, id, dest, p);
                }};
    }

    void Download() {
        const Artifact* a = Current();
        if (!a) return;
        if (a->expired) {
            ShowError(this, "This artifact has expired and can no longer be downloaded.", "Artifact Expired");
            return;
        }
        auto dir = GetDownloadDir(this);
        if (!dir) return;
        DownloadJob job = MakeJob(*dir, *a);
        if (PathExists(job.dest) &&
            !AskYesNo(this, "File already exists:\n" + U8(job.dest) + "\n\nOverwrite?", "File Exists"))
            return;
        RunDownloads(this, "Downloading Artifact", {job});
    }

    void DownloadAll() {
        std::vector<Artifact> todo;
        for (const auto& a : m_artifacts)
            if (!a.expired) todo.push_back(a);
        if (todo.empty()) return;
        if (!AskYesNo(this, wxString::Format("Download %zu artifact%s?", todo.size(), Plural(todo.size())),
                      "Confirm Download"))
            return;
        auto dir = GetDownloadDir(this);
        if (!dir) return;
        std::vector<DownloadJob> jobs;
        size_t existing = 0;
        for (const auto& a : todo) {
            jobs.push_back(MakeJob(*dir, a));
            if (PathExists(jobs.back().dest)) ++existing;
        }
        if (existing && !AskYesNo(this, wxString::Format("%zu file%s already exist. Overwrite?", existing,
                                                         Plural(existing)),
                                  "Files Exist"))
            return;
        RunDownloads(this, "Downloading Artifacts", std::move(jobs));
    }

    Repository m_repo;
    WorkflowRun m_run;
    std::vector<Artifact> m_artifacts;
    wxListBox* m_list;
    ActionBar* m_actions;  // owned by m_panel
};

// --- Job logs ------------------------------------------------------------------

// Drops ANSI colour codes (ESC [ digits/semicolons m), which screen readers
// would otherwise read out.
std::string StripAnsi(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '\x1b' && i + 1 < s.size() && s[i + 1] == '[') {
            size_t j = i + 2;
            while (j < s.size() && (isdigit(static_cast<unsigned char>(s[j])) || s[j] == ';')) ++j;
            if (j < s.size() && s[j] == 'm') {
                i = j;
                continue;
            }
        }
        out += s[i];
    }
    return out;
}

class JobLogsDialog : public BaseDialog {
public:
    JobLogsDialog(wxWindow* parent, const Repository& repo, const WorkflowJob& job)
        : BaseDialog(parent, "Logs - " + U8(job.name), wxSize(1000, 700)), m_repo(repo), m_job(job) {
        std::string status = job.conclusion.empty() ? ReplaceAll(job.status, "_", " ") : job.conclusion;
        m_sizer->Add(new wxStaticText(m_panel, wxID_ANY, "Job: " + U8(job.name) + " (" + U8(status) + ")"), 0,
                     wxALL, 5);

        m_text = new wxTextCtrl(m_panel, wxID_ANY, "", wxDefaultPosition, wxDefaultSize,
                                wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2 | wxHSCROLL);
        m_text->SetFont(wxFont(wxFontInfo().Family(wxFONTFAMILY_TELETYPE)));
        AddLabeled("&Logs", m_text, 1);

        m_actions = new ActionBar(m_panel);
        m_actions->Add(MakeAction("&Refresh", [this] { Load(); }, true)).Shortcut('R', wxMOD_CONTROL);
        m_actions->Add(MakeAction("&Copy All", [this] { CopyAll(); }, true));
        m_actions->Add(MakeAction("Open in &Browser", [this] { OpenUrl(m_job.htmlUrl); }, true))
            .Shortcut('O', wxMOD_CONTROL);
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL, 5);

        Finish();
        m_text->SetFocus();
        Load();
    }

private:
    void Load() {
        m_text->SetValue("Loading logs...");
        auto account = app::Current();
        std::string owner = m_repo.owner, name = m_repo.name;
        long long id = m_job.id;
        RunAsync(
            this,
            [=]() -> Fetched<wxString> {
                auto logs = account->GetJobLogs(owner, name, id);
                if (!logs || logs->empty()) return {wxString(), logs ? "" : GitHubAccount::LastError()};
                // Converted here: big logs take a while.
                return {U8(StripAnsi(*logs)), ""};
            },
            [this](Fetched<wxString> r) {
                if (!r.value.empty()) {
                    m_text->SetValue(r.value);
                } else {
                    wxString msg =
                        "No logs available.\n\nLogs may not be available if:\n- The job hasn't started yet\n"
                        "- The job is still in progress\n- The logs have expired";
                    if (!r.error.empty()) msg += "\n\nError: " + U8(r.error);
                    m_text->SetValue(msg);
                }
                m_text->SetInsertionPoint(0);
            });
    }

    void CopyAll() {
        wxString logs = m_text->GetValue();
        if (logs.empty()) return;
        if (CopyToClipboard(logs, false)) ShowInfo(this, "Logs copied to clipboard.", "Copied");
    }

    Repository m_repo;
    WorkflowJob m_job;
    wxTextCtrl* m_text;
    ActionBar* m_actions;  // owned by m_panel
};

// --- Run details ---------------------------------------------------------------

wxString StepIcon(const WorkflowStep& s) {
    if (s.status == "completed") {
        if (s.conclusion == "success") return wxString::FromUTF8("✓");
        if (s.conclusion == "failure") return wxString::FromUTF8("✗");
        if (s.conclusion == "skipped") return wxString::FromUTF8("⊘");
        return "?";
    }
    if (s.status == "in_progress") return wxString::FromUTF8("●");
    if (s.status == "queued") return wxString::FromUTF8("○");
    return "?";
}

class RunDetailsDialog : public BaseDialog {
public:
    RunDetailsDialog(wxWindow* parent, const Repository& repo, const WorkflowRun& run)
        : BaseDialog(parent, wxString::Format("Workflow Run #%d", run.runNumber), wxSize(900, 700)),
          m_repo(repo),
          m_run(run) {
        m_info = new wxTextCtrl(m_panel, wxID_ANY, "", wxDefaultPosition, wxSize(-1, 140),
                                wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2 | wxTE_DONTWRAP);
        AddLabeled("Run &Information", m_info);
        m_jobs = new wxListBox(m_panel, wxID_ANY);
        AddLabeled("&Jobs", m_jobs, 1);
        m_steps = new wxListBox(m_panel, wxID_ANY);
        AddLabeled("&Steps", m_steps, 1);

        m_actions = new ActionBar(m_panel);
        auto hasJob = [this] { return CurrentJob() != nullptr; };
        m_actions->Add(MakeAction("View &Logs", [this] { ViewLogs(); }, true, hasJob)).Shortcut(WXK_RETURN);
        m_actions->Add(MakeAction("Re-r&un All", [this] { Op(RunOp::Rerun); }, true,
                                  [this] { return CanRerun(m_run); }));
        m_actions->Add(MakeAction("&Artifacts...", [this] { ShowModalDialog<ArtifactsDialog>(this, m_repo, m_run); },
                                  true));
        m_actions->Add(MakeAction("Rerun &Failed Jobs", [this] { Op(RunOp::RerunFailed); }, false,
                                  [this] { return CanRerunFailed(m_run); }));
        m_actions->Add(MakeAction("Ca&ncel Run", [this] { Op(RunOp::Cancel); }, false,
                                  [this] { return CanCancel(m_run); }));
        m_actions->AddSeparator();
        m_actions->Add(MakeAction("Open Run in &Browser", [this] { OpenUrl(m_run.htmlUrl); }))
            .Shortcut('O', wxMOD_CONTROL);
        m_actions->Add(MakeAction("Open &Job in Browser", [this] {
            if (auto* j = CurrentJob()) OpenUrl(j->htmlUrl);
        }, false, hasJob)).Shortcut('O', wxMOD_CONTROL | wxMOD_SHIFT);
        m_actions->Add(MakeAction("Cop&y Run URL", [this] { CopyToClipboard(U8(m_run.htmlUrl)); }));
        m_actions->AddSeparator();
        m_actions->Add(MakeAction("R&efresh", [this] { Reload(); })).Shortcut('R', wxMOD_CONTROL);
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL, 5);
        m_actions->AttachContextMenu(m_jobs);
        m_actions->AttachContextMenu(m_steps);

        m_jobs->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) {
            ShowSteps();
            m_actions->Update();
        });
        m_jobs->Bind(wxEVT_LISTBOX_DCLICK, [this](wxCommandEvent&) { CallAfter([this] { ViewLogs(); }); });

        ShowInfoText();
        Finish();
        m_jobs->SetFocus();
        LoadJobs();
    }

private:
    const WorkflowJob* CurrentJob() const {
        int i = Selected(m_jobs);
        return i >= 0 && i < static_cast<int>(m_jobList.size()) ? &m_jobList[i] : nullptr;
    }

    void ShowInfoText() {
        const WorkflowRun& r = m_run;
        wxString t;
        t << "Workflow: " << U8(r.name) << "\n";
        t << "Run Number: #" << r.runNumber << " (attempt " << r.runAttempt << ")\n";
        t << "Status: " << U8(r.GetStatusText()) << "\n";
        t << "Event: " << U8(r.event) << "\n";
        t << "Branch: " << U8(r.headBranch) << "\n";
        t << "Commit: " << U8(r.headSha) << "\n";
        t << "Actor: " << U8(r.actorLogin);
        if (!r.triggeringActorLogin.empty() && r.triggeringActorLogin != r.actorLogin)
            t << "\nTriggered by: " << U8(r.triggeringActorLogin);
        if (r.createdAt) t << "\nCreated: " << FormatTime(r.createdAt);
        if (r.runStartedAt) t << "\nStarted: " << FormatTime(r.runStartedAt);
        if (r.updatedAt) t << "\nUpdated: " << FormatTime(r.updatedAt);
        m_info->SetValue(t);
    }

    void ShowSteps() {
        std::vector<wxString> rows;
        if (const WorkflowJob* job = CurrentJob()) {
            for (const auto& s : job->steps)
                rows.push_back(StepIcon(s) + " " + (s.name.empty() ? wxString("Unknown step") : U8(s.name)));
            if (rows.empty()) rows.push_back("No steps");
        }
        SetListItems(m_steps, rows);
    }

    void LoadJobs() {
        long long keepId = CurrentJob() ? CurrentJob()->id : 0;
        if (m_jobList.empty()) SetListItems(m_jobs, {"Loading..."});
        auto account = app::Current();
        std::string owner = m_repo.owner, name = m_repo.name;
        long long id = m_run.id;
        RunAsync(
            this,
            [=]() -> Fetched<std::vector<WorkflowJob>> {
                auto jobs = account->GetWorkflowRunJobs(owner, name, id);
                return {jobs, jobs.empty() ? GitHubAccount::LastError() : ""};
            },
            [this, keepId](Fetched<std::vector<WorkflowJob>> r) {
                m_jobList = std::move(r.value);
                std::vector<wxString> rows;
                for (const auto& j : m_jobList) rows.push_back(U8(j.FormatDisplay()));
                if (rows.empty())
                    rows.push_back(r.error.empty() ? "No jobs found" : "Could not load jobs: " + U8(r.error));
                SetListItems(m_jobs, rows);
                // Stay on the same job across a refresh.
                for (size_t i = 0; i < m_jobList.size(); ++i)
                    if (m_jobList[i].id == keepId) m_jobs->SetSelection(static_cast<int>(i));
                ShowSteps();
                m_actions->Update();
            });
    }

    // The run and its jobs again, at the same time (after a re-run or cancel).
    void Reload() {
        auto account = app::Current();
        std::string owner = m_repo.owner, name = m_repo.name;
        long long id = m_run.id;
        RunAsync(
            this, [=] { return account->GetWorkflowRun(owner, name, id); },
            [this](std::optional<WorkflowRun> run) {
                if (!run) return;
                m_run = *run;
                ShowInfoText();
                m_actions->Update();
            });
        LoadJobs();
    }

    void Op(RunOp op) {
        DoRunOp(this, m_repo, m_run, op, [this] { Reload(); });
    }

    void ViewLogs() {
        if (const WorkflowJob* job = CurrentJob()) {
            WorkflowJob copy = *job;  // the list may refresh while the logs are open
            ShowModalDialog<JobLogsDialog>(this, m_repo, copy);
        }
    }

    Repository m_repo;
    WorkflowRun m_run;
    std::vector<WorkflowJob> m_jobList;
    wxTextCtrl* m_info;
    wxListBox* m_jobs;
    wxListBox* m_steps;
    ActionBar* m_actions;  // owned by m_panel
};

// --- Workflow runs -------------------------------------------------------------

class ActionsDialog : public BaseDialog {
public:
    ActionsDialog(wxWindow* parent, const Repository& repo)
        : BaseDialog(parent, "Actions - " + U8(repo.fullName), wxSize(950, 650)), m_repo(repo) {
        m_workflowChoice = new wxChoice(m_panel, wxID_ANY);
        m_workflowChoice->Append("All Workflows");
        m_workflowChoice->SetSelection(0);
        AddLabeled("&Workflow", m_workflowChoice);
        m_statusChoice = new wxChoice(m_panel, wxID_ANY);
        for (const char* s : {"All", "Completed", "In Progress", "Queued"}) m_statusChoice->Append(s);
        m_statusChoice->SetSelection(0);
        AddLabeled("&Status", m_statusChoice);

        m_list = new wxListBox(m_panel, wxID_ANY);
        AddLabeled("Workflow &Runs", m_list, 1);
        m_runs = new PagedList<WorkflowRun>(m_list, "workflow runs",
                                            [](const WorkflowRun& r) { return U8(r.FormatDisplay()); });
        m_runs->FocusWhenLoaded();
        m_details = new wxTextCtrl(m_panel, wxID_ANY, "", wxDefaultPosition, wxSize(-1, 110),
                                   wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2 | wxTE_DONTWRAP);
        AddLabeled("Run &Details", m_details);

        m_actions = new ActionBar(m_panel);
        auto has = [this] { return Current() != nullptr; };
        auto when = [this](bool (*test)(const WorkflowRun&)) {
            return [this, test] { return Current() && test(*Current()); };
        };
        m_actions->Add(MakeAction("&View Details", [this] { View(); }, true, has)).Shortcut(WXK_RETURN);
        m_actions->Add(MakeAction("Re-r&un", [this] { Op(RunOp::Rerun); }, true, when(CanRerun)));
        m_actions->Add(MakeAction("R&efresh", [this] { RefreshRuns(); }, true)).Shortcut('R', wxMOD_CONTROL);
        m_actions->Add(MakeAction("Rerun &Failed Jobs", [this] { Op(RunOp::RerunFailed); }, false,
                                  when(CanRerunFailed)));
        m_actions->Add(MakeAction("Ca&ncel Run", [this] { Op(RunOp::Cancel); }, false, when(CanCancel)));
        m_actions->AddSeparator();
        m_actions->Add(MakeAction("&Artifacts...", [this] {
            if (const WorkflowRun* r = Current()) {
                WorkflowRun run = *r;
                ShowModalDialog<ArtifactsDialog>(this, m_repo, run);
            }
        }, false, has));
        m_actions->Add(MakeAction("Open in &Browser", [this] {
            if (const WorkflowRun* r = Current()) OpenUrl(r->htmlUrl);
        }, false, has)).Shortcut('O', wxMOD_CONTROL);
        m_actions->Add(MakeAction("Cop&y URL", [this] {
            if (const WorkflowRun* r = Current()) CopyToClipboard(U8(r->htmlUrl));
        }, false, has));
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL, 5);
        m_actions->AttachContextMenu(m_list);

        m_runs->OnSelect([this] { OnSelect(); });
        m_runs->OnLoaded([this](bool first) {
            if (first) KeepSelection(m_list, *m_runs, m_keepId);
            m_keepId = 0;
            OnSelect();
        });
        m_list->Bind(wxEVT_LISTBOX_DCLICK, [this](wxCommandEvent&) { CallAfter([this] { View(); }); });
        m_workflowChoice->Bind(wxEVT_CHOICE, [this](wxCommandEvent&) { LoadRuns(); });
        m_statusChoice->Bind(wxEVT_CHOICE, [this](wxCommandEvent&) { LoadRuns(); });

        Finish();
        m_list->SetFocus();
        // Workflows (for the filter) and runs at once: the runs don't need them
        // while the filter is still "All Workflows".
        LoadWorkflows();
        LoadRuns();
    }

private:
    const WorkflowRun* Current() const { return m_runs->Selected(); }

    void LoadWorkflows() {
        auto account = app::Current();
        std::string owner = m_repo.owner, name = m_repo.name;
        RunAsync(
            this, [=] { return account->GetWorkflows(owner, name); },
            [this](std::vector<Workflow> workflows) {
                m_workflows = std::move(workflows);
                wxWindowUpdateLocker lock(m_workflowChoice);
                int sel = m_workflowChoice->GetSelection();
                m_workflowChoice->Clear();
                m_workflowChoice->Append("All Workflows");
                for (const auto& w : m_workflows) m_workflowChoice->Append(U8(w.name));
                m_workflowChoice->SetSelection(sel > 0 && sel <= static_cast<int>(m_workflows.size()) ? sel : 0);
            });
    }

    // From page 1 with the current filters.
    void LoadRuns() {
        int wf = m_workflowChoice->GetSelection();
        long long workflowId = wf > 0 && wf <= static_cast<int>(m_workflows.size()) ? m_workflows[wf - 1].id : 0;
        static const char* const kStatus[] = {"", "completed", "in_progress", "queued"};
        int st = m_statusChoice->GetSelection();
        std::string status = st > 0 && st < 4 ? kStatus[st] : "";
        m_keepId = 0;
        m_details->Clear();
        auto account = app::Current();
        std::string owner = m_repo.owner, name = m_repo.name;
        m_runs->Load([=](int page) {
            return account->GetWorkflowRunsPage(owner, name, workflowId, "", status, page);
        });
        m_actions->Update();
    }

    // The pages already shown again, staying on the same run even when new
    // runs pushed it down.
    void RefreshRuns() {
        if (!m_runs->HasLoaded()) return LoadRuns();
        m_keepId = Current() ? Current()->id : 0;
        m_runs->Refresh();
    }

    void OnSelect() {
        m_actions->Update();
        const WorkflowRun* r = Current();
        if (!r) {
            m_details->Clear();
            return;
        }
        wxString t;
        t << "Workflow: " << U8(r->name) << "\n";
        t << "Run: #" << r->runNumber << " (attempt " << r->runAttempt << ")\n";
        t << "Status: " << U8(r->GetStatusText()) << "\n";
        t << "Event: " << U8(r->event) << "\n";
        t << "Branch: " << U8(r->headBranch) << " (" << U8(r->headSha) << ")\n";
        t << "Actor: " << U8(r->actorLogin);
        if (r->createdAt) t << "\nStarted: " << FormatTime(r->createdAt);
        m_details->SetValue(t);
    }

    void View() {
        const WorkflowRun* r = Current();
        if (!r) return;
        WorkflowRun run = *r;
        ShowModalDialog<RunDetailsDialog>(this, m_repo, run);
        RefreshRuns();  // its status may have changed meanwhile
    }

    void Op(RunOp op) {
        if (const WorkflowRun* r = Current()) DoRunOp(this, m_repo, *r, op, [this] { RefreshRuns(); });
    }

    Repository m_repo;
    std::vector<Workflow> m_workflows;
    PagedList<WorkflowRun>* m_runs;  // owned by m_list
    long long m_keepId = 0;          // the run to reselect after a refresh
    wxChoice* m_workflowChoice;
    wxChoice* m_statusChoice;
    wxListBox* m_list;
    wxTextCtrl* m_details;
    ActionBar* m_actions;  // owned by m_panel
};

}  // namespace

void ShowActionsDialog(wxWindow* parent, const Repository& repo) {
    if (!app::Current()) {
        ShowError(parent, "Sign in to GitHub first.");
        return;
    }
    ShowModalDialog<ActionsDialog>(parent, repo);
}
