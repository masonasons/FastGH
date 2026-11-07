// Releases: the list of a repository's releases and one release's notes and
// assets (a port of GUI/releases.py).

#include "ui/dialogs.h"

#include "core/app.h"
#include "core/github.h"
#include "core/models.h"
#include "core/util.h"
#include "ui/paged_list.h"
#include "ui/ui_common.h"

#include <wx/filefn.h>
#include <wx/progdlg.h>

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
// (The same helper is in actions_dialog.cpp; it belongs in ui_common once the
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

// --- Shared release actions -------------------------------------------------------

// Downloads the release's source as a zip or tarball into the download folder.
// (The Python app sent these to the browser; here they get the same progress
// and "show in Finder" as every other download.)
void DownloadSource(wxWindow* parent, const Repository& repo, const Release& release, bool zip) {
    std::string url = zip ? release.zipballUrl : release.tarballUrl;
    if (url.empty()) {
        ShowError(parent, "This release has no source archive.");
        return;
    }
    auto dir = GetDownloadDir(parent);
    if (!dir) return;
    std::string tag = ReplaceAll(ReplaceAll(release.tagName, "/", "-"), "\\", "-");
    std::string dest = JoinPath(*dir, SafeFileName(repo.name + "-" + tag + (zip ? ".zip" : ".tar.gz")));
    if (PathExists(dest) && !AskYesNo(parent, "File already exists:\n" + U8(dest) + "\n\nOverwrite?", "File Exists"))
        return;
    auto account = app::Current();
    DownloadJob job{U8(SafeFileName(dest)), dest,
                    [=](const ProgressFn& p) { return account->DownloadUrl(url, dest, p); }};
    RunDownloads(parent, zip ? "Downloading ZIP" : "Downloading Tarball", {job});
}

// --- One release -----------------------------------------------------------------

class ReleaseDialog : public BaseDialog {
public:
    ReleaseDialog(wxWindow* parent, const Repository& repo, const Release& release)
        : BaseDialog(parent, "Release " + U8(release.tagName), wxSize(900, 700)), m_repo(repo), m_release(release) {
        m_info = new wxTextCtrl(m_panel, wxID_ANY, InfoText(), wxDefaultPosition, wxSize(-1, 110),
                                wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2 | wxTE_DONTWRAP);
        AddLabeled("Release &Information", m_info);
        m_notes = new wxTextCtrl(m_panel, wxID_ANY,
                                 release.body.empty() ? wxString("No release notes") : U8(release.body),
                                 wxDefaultPosition, wxSize(-1, 180), wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2);
        AddLabeled("Release &Notes", m_notes, 1);
        m_assets = new wxListBox(m_panel, wxID_ANY);
        AddLabeled("&Assets", m_assets, 1);
        std::vector<wxString> rows;
        for (const auto& a : release.assets) rows.push_back(U8(a.FormatDisplay()));
        if (rows.empty()) rows.push_back("No assets");
        SetListItems(m_assets, rows);

        m_actions = new ActionBar(m_panel);
        auto hasAsset = [this] { return Current() != nullptr; };
        auto hasAssets = [this] { return !m_release.assets.empty(); };
        m_actions->Add(MakeAction("&Download", [this] { Download(); }, true, hasAsset)).Shortcut(WXK_RETURN);
        m_actions->Add(MakeAction("Download A&ll Assets", [this] { DownloadAll(); }, true, hasAssets));
        m_actions->Add(MakeAction("Open in &Browser", [this] { OpenUrl(m_release.htmlUrl); }, true))
            .Shortcut('O', wxMOD_CONTROL);
        m_actions->Add(MakeAction("Copy Asset &URL", [this] { CopyAssetUrl(); }, false, hasAsset));
        m_actions->Add(MakeAction("Copy &Release URL", [this] { CopyToClipboard(U8(m_release.htmlUrl)); }));
        m_actions->AddSeparator();
        m_actions->Add(MakeAction("Download Source &ZIP", [this] { DownloadSource(this, m_repo, m_release, true); },
                                  false, [this] { return !m_release.zipballUrl.empty(); }));
        m_actions->Add(MakeAction("Download Source &Tarball",
                                  [this] { DownloadSource(this, m_repo, m_release, false); }, false,
                                  [this] { return !m_release.tarballUrl.empty(); }));
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL, 5);
        m_actions->AttachContextMenu(m_assets);

        m_assets->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) { m_actions->Update(); });
        m_assets->Bind(wxEVT_LISTBOX_DCLICK, [this](wxCommandEvent&) { CallAfter([this] { Download(); }); });

        Finish();
        // The notes are what people open a release for.
        m_notes->SetFocus();
        m_notes->SetInsertionPoint(0);
    }

private:
    const ReleaseAsset* Current() const {
        int i = Selected(m_assets);
        return i >= 0 && i < static_cast<int>(m_release.assets.size()) ? &m_release.assets[i] : nullptr;
    }

    wxString InfoText() const {
        const Release& r = m_release;
        wxString t;
        t << "Tag: " << U8(r.tagName);
        if (r.name != r.tagName) t << "\nName: " << U8(r.name);
        t << "\nType: " << U8(r.GetStatusLabel());
        t << "\nAuthor: " << U8(r.authorLogin);
        if (r.publishedAt)
            t << "\nPublished: " << FormatTime(r.publishedAt);
        else if (r.createdAt)
            t << "\nCreated: " << FormatTime(r.createdAt);
        if (!r.assets.empty())
            t << "\nDownloads: " << U8(FormatThousands(r.TotalDownloads())) << " across " << r.assets.size()
              << " asset" << Plural(r.assets.size());
        return t;
    }

    DownloadJob MakeJob(const std::string& dir, const ReleaseAsset& a) const {
        auto account = app::Current();
        std::string owner = m_repo.owner, name = m_repo.name, dest = JoinPath(dir, SafeFileName(a.name));
        long long id = a.id;
        return {U8(a.name), dest,
                [=](const ProgressFn& p) { return account->DownloadAsset(owner, name, id, dest, p); }};
    }

    void Download() {
        const ReleaseAsset* a = Current();
        if (!a) return;
        auto dir = GetDownloadDir(this);
        if (!dir) return;
        DownloadJob job = MakeJob(*dir, *a);
        if (PathExists(job.dest) &&
            !AskYesNo(this, "File already exists:\n" + U8(job.dest) + "\n\nOverwrite?", "File Exists"))
            return;
        RunDownloads(this, "Downloading Asset", {job});
    }

    void DownloadAll() {
        size_t count = m_release.assets.size();
        if (!count) return;
        if (!AskYesNo(this, wxString::Format("Download all %zu asset%s?", count, Plural(count)), "Confirm Download"))
            return;
        auto dir = GetDownloadDir(this);
        if (!dir) return;
        std::vector<DownloadJob> jobs;
        size_t existing = 0;
        for (const auto& a : m_release.assets) {
            jobs.push_back(MakeJob(*dir, a));
            if (PathExists(jobs.back().dest)) ++existing;
        }
        if (existing && !AskYesNo(this, wxString::Format("%zu file%s already exist. Overwrite?", existing,
                                                         Plural(existing)),
                                  "Files Exist"))
            return;
        RunDownloads(this, "Downloading Assets", std::move(jobs));
    }

    void CopyAssetUrl() {
        if (const ReleaseAsset* a = Current())
            if (CopyToClipboard(U8(a->browserDownloadUrl), false))
                ShowInfo(this, "Copied: " + U8(a->browserDownloadUrl), "Copied");
    }

    Repository m_repo;
    Release m_release;
    wxTextCtrl* m_info;
    wxTextCtrl* m_notes;
    wxListBox* m_assets;
    ActionBar* m_actions;  // owned by m_panel
};

// --- The list of releases ----------------------------------------------------------

class ReleasesDialog : public BaseDialog {
public:
    ReleasesDialog(wxWindow* parent, const Repository& repo)
        : BaseDialog(parent, "Releases - " + U8(repo.fullName), wxSize(900, 600)), m_repo(repo) {
        m_list = new wxListBox(m_panel, wxID_ANY);
        AddLabeled("&Releases", m_list, 1);
        m_releases = new PagedList<Release>(m_list, "releases", [](const Release& r) { return U8(r.FormatDisplay()); });
        m_releases->FocusWhenLoaded();
        m_details = new wxTextCtrl(m_panel, wxID_ANY, "", wxDefaultPosition, wxSize(-1, 120),
                                   wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2);
        AddLabeled("Release &Details", m_details);

        m_actions = new ActionBar(m_panel);
        auto has = [this] { return Current() != nullptr; };
        m_actions->Add(MakeAction("&View Details", [this] { View(); }, true, has)).Shortcut(WXK_RETURN);
        m_actions->Add(MakeAction("Open in &Browser", [this] {
            if (const Release* r = Current()) OpenUrl(r->htmlUrl);
        }, true, has)).Shortcut('O', wxMOD_CONTROL);
        m_actions->Add(MakeAction("Download &ZIP", [this] {
            if (const Release* r = Current()) DownloadSource(this, m_repo, *r, true);
        }, false, has));
        m_actions->Add(MakeAction("Download &Tarball", [this] {
            if (const Release* r = Current()) DownloadSource(this, m_repo, *r, false);
        }, false, has));
        m_actions->AddSeparator();
        m_actions->Add(MakeAction("Copy &URL", [this] {
            if (const Release* r = Current()) CopyToClipboard(U8(r->htmlUrl));
        }, false, has));
        m_actions->Add(MakeAction("R&efresh", [this] { RefreshReleases(); })).Shortcut('R', wxMOD_CONTROL);
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL, 5);
        m_actions->AttachContextMenu(m_list);

        m_releases->OnSelect([this] { OnSelect(); });
        m_releases->OnLoaded([this](bool first) {
            if (first && m_keepId) {
                // A new release pushes the others down: stay on the same one.
                const auto& items = m_releases->Items();
                for (size_t i = 0; i < items.size(); ++i)
                    if (items[i].id == m_keepId) m_list->SetSelection(static_cast<int>(i));
            }
            m_keepId = 0;
            OnSelect();
        });
        m_list->Bind(wxEVT_LISTBOX_DCLICK, [this](wxCommandEvent&) { CallAfter([this] { View(); }); });

        Finish();
        m_list->SetFocus();
        auto account = app::Current();
        std::string owner = m_repo.owner, name = m_repo.name;
        m_releases->Load([=](int page) { return account->GetReleasesPage(owner, name, page); });
    }

private:
    const Release* Current() const { return m_releases->Selected(); }

    void RefreshReleases() {
        m_keepId = Current() ? Current()->id : 0;
        m_releases->Refresh();
    }

    void OnSelect() {
        m_actions->Update();
        const Release* r = Current();
        if (!r) {
            m_details->Clear();
            return;
        }
        wxString t;
        t << "Tag: " << U8(r->tagName);
        if (r->name != r->tagName) t << "\nName: " << U8(r->name);
        t << "\nType: " << U8(r->GetStatusLabel());
        t << "\nAuthor: " << U8(r->authorLogin);
        if (r->publishedAt) t << "\nPublished: " << U8(FormatLocalTime(r->publishedAt, "%Y-%m-%d %H:%M"));
        t << "\nAssets: " << r->assets.size();
        if (!r->assets.empty()) t << "\nDownloads: " << U8(FormatThousands(r->TotalDownloads()));
        if (!r->body.empty()) t << "\n\n" << U8(Truncate(r->body, 200));
        m_details->SetValue(t);
    }

    void View() {
        if (const Release* r = Current()) {
            Release copy = *r;  // a refresh can't pull it from under the dialog
            ShowModalDialog<ReleaseDialog>(this, m_repo, copy);
        }
    }

    Repository m_repo;
    PagedList<Release>* m_releases;  // owned by m_list
    long long m_keepId = 0;          // the release to reselect after a refresh
    wxListBox* m_list;
    wxTextCtrl* m_details;
    ActionBar* m_actions;  // owned by m_panel
};

}  // namespace

void ShowReleasesDialog(wxWindow* parent, const Repository& repo) {
    if (!app::Current()) {
        ShowError(parent, "Sign in to GitHub first.");
        return;
    }
    ShowModalDialog<ReleasesDialog>(parent, repo);
}
