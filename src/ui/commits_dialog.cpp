// The commits of a repository, a page at a time, and one commit in full
// (a port of GUI/commits.py).

#include "ui/dialogs.h"
#include "ui/ui_common.h"

#include "core/app.h"
#include "core/github.h"
#include "core/models.h"
#include "core/util.h"

#include <map>
#include <memory>
#include <string>
#include <vector>

namespace {

constexpr int kCommitsPerPage = 50;  // github_api.COMMITS_PER_PAGE

wxString JoinLines(const std::vector<std::string>& lines) {
    std::string out;
    for (size_t i = 0; i < lines.size(); ++i) {
        if (i) out += '\n';
        out += lines[i];
    }
    return U8(out);
}

// Full commits (with files) fetched so far, shared by a commits dialog and the
// details dialogs it opens, so reopening a commit is instant.
using CommitCache = std::map<std::string, Commit>;

// --- One commit: information, message, files changed and the selected file's patch ---
class CommitDetailsDialog : public BaseDialog {
public:
    CommitDetailsDialog(wxWindow* parent, const Repository& repo, const Commit& commit,
                        std::shared_ptr<CommitCache> cache)
        : BaseDialog(parent, U8("Commit " + commit.ShortSha()), wxSize(850, 750)),
          m_repo(repo), m_commit(commit), m_cache(std::move(cache)) {
        wxPanel* p = Panel();
        m_info = new wxTextCtrl(p, wxID_ANY, "", wxDefaultPosition, wxSize(-1, 110),
                                wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2 | wxTE_DONTWRAP);
        AddLabeled("Commit &information:", m_info);
        m_message = new wxTextCtrl(p, wxID_ANY, "", wxDefaultPosition, wxSize(-1, 120),
                                   wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2);
        AddLabeled("&Message:", m_message);
        m_files = new wxListBox(p, wxID_ANY, wxDefaultPosition, wxSize(-1, 140), 0, nullptr, wxLB_SINGLE);
        AddLabeled("&Files changed:", m_files, 1);
        m_patch = new wxTextCtrl(p, wxID_ANY, "", wxDefaultPosition, wxSize(-1, 160),
                                 wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2 | wxTE_DONTWRAP);
        m_patch->SetFont(wxFont(wxFontInfo(11).Family(wxFONTFAMILY_TELETYPE)));
        AddLabeled("&Patch:", m_patch, 1);

        auto hasFile = [this] { return SelectedFile() != nullptr; };
        auto hasPatch = [this] {
            const CommitFile* f = SelectedFile();
            return f && !f->patch.empty();
        };
        m_actions = new ActionBar(p);  // as documented in ui_common.h
        m_actions->Add({"Copy &SHA", [this] { CopyToClipboard(U8(m_commit.sha)); }, true});
        m_actions->Add({"Copy M&essage", [this] { CopyToClipboard(U8(m_commit.message)); }, true});
        m_actions->Add({"&Open in Browser", [this] { OpenUrl(m_commit.htmlUrl); }, true,
                        [this] { return !m_commit.htmlUrl.empty(); }})
            .Shortcut('O', wxMOD_CONTROL);
        m_actions->Add({"Copy File&name",
                        [this] {
                            if (const CommitFile* f = SelectedFile()) CopyToClipboard(U8(f->filename));
                        },
                        false, hasFile});
        m_actions->Add({"Copy Pa&tch",
                        [this] {
                            if (const CommitFile* f = SelectedFile()) CopyToClipboard(U8(f->patch));
                        },
                        false, hasPatch});
        m_actions->AddSeparator();
        m_actions->Add({"Copy &URL", [this] { CopyToClipboard(U8(m_commit.htmlUrl)); }, false,
                        [this] { return !m_commit.htmlUrl.empty(); }});
        Sizer()->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER_HORIZONTAL, 5);
        m_actions->AttachContextMenu(m_files);
        m_actions->AttachContextMenu(m_message);

        m_files->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) {
            ShowPatch();
            m_actions->Update();
        });

        ShowCommit();
        Finish();
        m_message->SetFocus();

        // The list endpoint leaves out the files; fetch the full commit once.
        if (m_commit.files.empty()) LoadFullCommit();
    }

private:
    const CommitFile* SelectedFile() const {
        int i = Selected(m_files);
        return i >= 0 && i < (int)m_commit.files.size() ? &m_commit.files[i] : nullptr;
    }

    void ShowCommit() {
        const Commit& c = m_commit;
        std::vector<std::string> lines;
        lines.push_back("SHA: " + c.sha);
        lines.push_back("Author: " + c.author.name + " <" + c.author.email + ">");
        if (c.githubAuthor) lines.push_back("GitHub User: " + c.githubAuthor->login);
        if (c.author.date)
            lines.push_back("Date: " + FormatLocalTime(c.author.date, "%Y-%m-%d %H:%M:%S") + " (" +
                            FormatRelativeTime(c.author.date) + ")");
        if (c.author.name != c.committer.name || c.author.email != c.committer.email)
            lines.push_back("Committer: " + c.committer.name + " <" + c.committer.email + ">");
        if (!c.parents.empty()) {
            std::string parents;
            for (const auto& p : c.parents) parents += (parents.empty() ? "" : ", ") + p.substr(0, 7);
            lines.push_back("Parents: " + parents);
        }
        if (c.statsTotal)
            lines.push_back("Changes: +" + std::to_string(c.statsAdditions) + " -" +
                            std::to_string(c.statsDeletions) + " (" + std::to_string(c.statsTotal) + " total)");
        m_info->ChangeValue(JoinLines(lines));
        m_message->ChangeValue(U8(c.message));

        std::vector<wxString> rows;
        for (const auto& f : c.files) rows.push_back(U8(f.FormatDisplay()));
        if (rows.empty()) {
            SetListItems(m_files, {m_filesPlaceholder});
        } else {
            SetListItems(m_files, rows);
        }
        ShowPatch();
        m_actions->Update();
    }

    void ShowPatch() {
        const CommitFile* f = SelectedFile();
        if (!f)
            m_patch->ChangeValue("");
        else if (f->patch.empty())
            m_patch->ChangeValue("No patch available for this file (binary, renamed without changes, "
                                 "or too large to show).");
        else
            m_patch->ChangeValue(U8(f->patch));
    }

    void LoadFullCommit() {
        if (m_cache) {
            auto it = m_cache->find(m_commit.sha);
            if (it != m_cache->end()) {
                m_commit = it->second;
                ShowCommit();
                return;
            }
        }
        m_filesPlaceholder = "Loading...";
        ShowCommit();
        auto account = app::Current();
        if (!account) return;
        std::string owner = m_repo.owner, name = m_repo.name, sha = m_commit.sha;
        RunAsync(
            this,
            [=]() -> std::pair<std::optional<Commit>, std::string> {
                auto c = account->GetCommit(owner, name, sha);
                return {c, c ? "" : GitHubAccount::LastError()};
            },
            [this](std::pair<std::optional<Commit>, std::string> r) {
                if (!r.first) {
                    m_filesPlaceholder = "Failed to load the files: " + U8(r.second);
                    ShowCommit();
                    return;
                }
                m_commit = *r.first;
                if (m_cache) (*m_cache)[m_commit.sha] = m_commit;
                m_filesPlaceholder = "No files changed";
                ShowCommit();
            });
    }

    Repository m_repo;
    Commit m_commit;
    std::shared_ptr<CommitCache> m_cache;
    wxString m_filesPlaceholder = "No files changed";
    wxTextCtrl* m_info;
    wxTextCtrl* m_message;
    wxListBox* m_files;
    wxTextCtrl* m_patch;
    ActionBar* m_actions;
};

// --- A repository's commits on a branch ---
class CommitsDialog : public BaseDialog {
public:
    CommitsDialog(wxWindow* parent, const Repository& repo)
        : BaseDialog(parent, U8("Commits - " + repo.fullName), wxSize(900, 650)), m_repo(repo) {
        wxPanel* p = Panel();
        m_filter = new wxTextCtrl(p, wxID_ANY);
        m_filter->SetHint("Search branches...");
        AddLabeled("&Filter branches:", m_filter);
        m_branch = new wxChoice(p, wxID_ANY);
        m_branch->Append("Loading...");
        m_branch->SetSelection(0);
        AddLabeled("&Branch:", m_branch);
        m_list = new wxListBox(p, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddLabeled("Comm&its:", m_list, 1);
        m_preview = new wxTextCtrl(p, wxID_ANY, "", wxDefaultPosition, wxSize(-1, 120),
                                   wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2);
        AddLabeled("Commit &details:", m_preview);

        auto hasCommit = [this] { return SelectedCommit() != nullptr; };
        m_actions = new ActionBar(p);  // as documented in ui_common.h
        m_actions->Add({"&View Details", [this] { ViewDetails(); }, true, hasCommit});
        m_actions->Add({"Copy &SHA",
                        [this] {
                            if (const Commit* c = SelectedCommit()) CopyToClipboard(U8(c->sha));
                        },
                        true, hasCommit});
        m_actions->Add({"&Open in Browser",
                        [this] {
                            if (const Commit* c = SelectedCommit()) OpenUrl(c->htmlUrl);
                        },
                        true, hasCommit})
            .Shortcut('O', wxMOD_CONTROL);
        m_actions->Add({"&Refresh", [this] { LoadCommits(); }, true}).Shortcut(WXK_F5);
        m_actions->Add({"Copy &Message",
                        [this] {
                            if (const Commit* c = SelectedCommit()) CopyToClipboard(U8(c->message));
                        },
                        false, hasCommit});
        m_actions->Add({"Copy &URL",
                        [this] {
                            if (const Commit* c = SelectedCommit()) CopyToClipboard(U8(c->htmlUrl));
                        },
                        false, hasCommit});
        Sizer()->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER_HORIZONTAL, 5);
        m_actions->AttachContextMenu(m_list);
        m_actions->AttachActivate(m_list);

        m_list->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) { OnSelection(); });
        m_filter->Bind(wxEVT_TEXT, [this](wxCommandEvent&) { PopulateBranches(); });
        m_branch->Bind(wxEVT_CHOICE, [this](wxCommandEvent&) {
            int i = m_branch->GetSelection();
            if (i == wxNOT_FOUND || i >= (int)m_shownBranches.size()) return;
            std::string ref = RefFor(m_shownBranches[i]);
            if (ref == m_ref && !m_commits.empty()) return;  // already showing it
            m_ref = ref;
            LoadCommits();
        });

        Finish();
        m_list->SetFocus();

        // Branches and the default branch's first page at the same time: the
        // commits don't need to wait for the branch list.
        LoadBranches();
        LoadCommits();
    }

private:
    // Empty for the default branch, so the first page can start before the
    // branches are known.
    static std::string RefFor(const Branch& b) { return b.isDefault ? "" : b.name; }

    const Commit* SelectedCommit() const {
        int i = Selected(m_list);
        return i >= 0 && i < (int)m_commits.size() ? &m_commits[i] : nullptr;
    }

    void LoadBranches() {
        auto account = app::Current();
        if (!account) return;
        std::string owner = m_repo.owner, name = m_repo.name;
        RunAsync(this, [=] { return account->GetBranches(owner, name); },
                 [this](std::vector<Branch> branches) {
                     // Mark the default when GitHub's answer didn't (REST fallback).
                     bool anyDefault = false;
                     for (const auto& b : branches) anyDefault |= b.isDefault;
                     if (!anyDefault) {
                         for (auto& b : branches) {
                             if (b.name == m_repo.defaultBranch ||
                                 (m_repo.defaultBranch.empty() && (b.name == "main" || b.name == "master"))) {
                                 b.isDefault = true;
                                 break;
                             }
                         }
                     }
                     m_branches = std::move(branches);
                     PopulateBranches();
                 });
    }

    // Fills the branch choice with the branches matching the filter, keeping
    // the shown branch selected when it matches.
    void PopulateBranches() {
        std::string filter = ToLower(Trim(ToU8(m_filter->GetValue())));
        m_shownBranches.clear();
        for (const auto& b : m_branches)
            if (filter.empty() || ToLower(b.name).find(filter) != std::string::npos) m_shownBranches.push_back(b);

        wxArrayString names;
        int select = -1;
        for (size_t i = 0; i < m_shownBranches.size(); ++i) {
            names.Add(U8(m_shownBranches[i].name));
            if (select < 0 && RefFor(m_shownBranches[i]) == m_ref) select = (int)i;
        }
        m_branch->Freeze();
        m_branch->Clear();
        if (names.empty()) {
            m_branch->Append(m_branches.empty() ? "(no branches)" : "(no matching branches)");
            m_branch->SetSelection(0);
        } else {
            m_branch->Append(names);
            // A filtered list without the shown branch: select the first match;
            // choosing it (or another) loads it.
            m_branch->SetSelection(select >= 0 ? select : 0);
        }
        m_branch->Thaw();
    }

    // Starts again from the first page of the current branch.
    void LoadCommits() {
        ++m_loadToken;
        m_commits.clear();
        m_nextPage = 1;
        m_hasMore = false;
        m_loading = false;
        m_statusShown = false;
        m_preview->ChangeValue("");
        m_list->Clear();
        AppendStatus("Loading...");
        m_list->SetSelection(0);
        m_actions->Update();
        FetchPage();
    }

    void FetchPage() {
        auto account = app::Current();
        if (!account) {
            RemoveStatus();
            AppendStatus("Not signed in");
            return;
        }
        m_loading = true;
        int page = m_nextPage, token = m_loadToken;
        std::string owner = m_repo.owner, name = m_repo.name, ref = m_ref;
        struct Page {
            std::vector<Commit> commits;
            bool more = false;
            std::string error;
        };
        RunAsync(
            this,
            [=] {
                auto r = account->GetCommits(owner, name, ref, page, kCommitsPerPage);
                Page out{std::move(r.first), r.second, ""};
                if (out.commits.empty() && !out.more) out.error = GitHubAccount::LastError();
                return out;
            },
            [this, token](Page page) {
                if (token != m_loadToken) return;  // a page for an earlier branch or refresh
                ShowPage(std::move(page.commits), page.more, page.error);
            });
    }

    void AppendStatus(const wxString& text) {
        m_list->Append(text);
        m_statusShown = true;
    }

    // Removes the trailing status row; true when it was selected.
    bool RemoveStatus() {
        if (!m_statusShown) return false;
        m_statusShown = false;
        int last = (int)m_list->GetCount() - 1;
        bool wasSelected = last >= 0 && m_list->GetSelection() == last;
        if (last >= 0) m_list->Delete(last);
        return wasSelected;
    }

    void ShowPage(std::vector<Commit> commits, bool more, const std::string& error) {
        m_loading = false;
        ++m_nextPage;
        m_hasMore = more;

        size_t firstNew = m_commits.size();
        bool wasOnStatus = RemoveStatus();
        wxArrayString rows;
        for (const auto& c : commits) rows.Add(U8(c.FormatDisplay()));
        m_commits.insert(m_commits.end(), std::make_move_iterator(commits.begin()),
                         std::make_move_iterator(commits.end()));

        if (firstNew == 0) {
            // First page: replace the list in one go.
            std::vector<wxString> items(rows.begin(), rows.end());
            if (items.empty())
                items.push_back(error.empty() ? wxString("No commits found") : "Failed to load commits: " + U8(error));
            m_statusShown = m_commits.empty();
            SetListItems(m_list, items);
            m_list->SetSelection(0);
            OnSelection();
            if (m_focusList) {
                // The first page of the first load: put the reader in the list, as Python did.
                m_focusList = false;
                wxWindow* focus = wxWindow::FindFocus();
                if (!focus || wxGetTopLevelParent(focus) == this) m_list->SetFocus();
            }
            return;
        }
        if (!rows.empty()) m_list->Append(rows);
        if (!error.empty() && rows.empty()) AppendStatus("Failed to load more commits: " + U8(error));
        if (wasOnStatus && !rows.empty()) {
            // They had arrowed onto "Loading more..."; land them on the first new commit.
            m_list->SetSelection((int)firstNew);
            OnSelection();
        } else {
            m_actions->Update();
        }
    }

    void OnSelection() {
        m_actions->Update();
        if (const Commit* c = SelectedCommit()) ShowPreview(*c);
        MaybeLoadMore();
    }

    // The next page, once the selection reaches the last commit.
    void MaybeLoadMore() {
        if (m_loading || !m_hasMore || m_commits.empty()) return;
        int i = Selected(m_list);
        if (i < 0 || i < (int)m_commits.size() - 1) return;
        AppendStatus("Loading more commits...");
        FetchPage();
    }

    void ShowPreview(const Commit& c) {
        std::vector<std::string> lines;
        lines.push_back("SHA: " + c.sha);
        lines.push_back("Author: " + c.author.name + " <" + c.author.email + ">");
        if (c.author.date) lines.push_back("Date: " + FormatLocalTime(c.author.date, "%Y-%m-%d %H:%M:%S"));
        lines.push_back("");
        lines.push_back(c.message);
        m_preview->ChangeValue(JoinLines(lines));
    }

    void ViewDetails() {
        const Commit* c = SelectedCommit();
        if (!c) return;
        Commit commit = *c;
        auto it = m_cache->find(commit.sha);
        if (it != m_cache->end()) commit = it->second;
        ShowModalDialog<CommitDetailsDialog>(this, m_repo, commit, m_cache);
    }

    Repository m_repo;
    std::vector<Branch> m_branches;
    std::vector<Branch> m_shownBranches;
    std::string m_ref;  // the branch shown; empty for the default
    std::vector<Commit> m_commits;
    std::shared_ptr<CommitCache> m_cache = std::make_shared<CommitCache>();
    int m_nextPage = 1;
    bool m_hasMore = false;
    bool m_loading = false;
    int m_loadToken = 0;
    bool m_statusShown = false;  // a status row follows the commits
    bool m_focusList = true;     // focus the list when the first page arrives

    wxTextCtrl* m_filter;
    wxChoice* m_branch;
    wxListBox* m_list;
    wxTextCtrl* m_preview;
    ActionBar* m_actions;
};

}  // namespace

void ShowCommitsDialog(wxWindow* parent, const Repository& repo) {
    ShowModalDialog<CommitsDialog>(parent, repo);
}
