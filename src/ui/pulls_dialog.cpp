// Pull requests: a repository's list, one pull request with its comments, merging
// (a port of GUI/pullrequests.py).

#include "ui/dialogs.h"
#include "ui/paged_list.h"
#include "ui/ui_common.h"

#include "core/app.h"
#include "core/github.h"
#include "core/util.h"

#include <future>
#include <memory>
#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace {

using AccountPtr = std::shared_ptr<GitHubAccount>;

wxString WithReason(const wxString& message, const std::string& reason) {
    return reason.empty() ? message : message + "\n\nReason: " + U8(reason);
}

wxTextCtrl* ReadOnlyText(wxWindow* parent, int height) {
    return new wxTextCtrl(parent, wxID_ANY, "", wxDefaultPosition, wxSize(-1, height),
                          wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2);
}

std::string Upper(std::string s) {
    for (auto& c : s) c = static_cast<char>(toupper(static_cast<unsigned char>(c)));
    return s;
}

// Merging and closing need write access and a pull request that is still open.
bool CanAct(const PullRequest& pr, bool canMerge) { return canMerge && pr.state == "open" && !pr.merged; }

wxString CommentLine(const Comment& c) {
    std::string when = c.createdAt ? FormatLocalTime(c.createdAt) : "Unknown";
    std::string preview = ReplaceAll(ReplaceAll(c.body, "\r", ""), "\n", " ");
    std::string source = c.kind == "review" ? "[Review] " : "";
    return U8(c.user.login + " (" + when + "): " + source + Truncate(preview, 53));
}

wxString PrDetails(const PullRequest& pr) {
    std::vector<std::string> lines;
    lines.push_back("Title: " + pr.title);
    lines.push_back("State: " + (pr.merged ? std::string("MERGED") : pr.draft ? "DRAFT" : Upper(pr.state)));
    lines.push_back("Author: " + pr.user.login);
    lines.push_back("Branch: " + pr.headRef + " -> " + pr.baseRef);
    if (!pr.labels.empty()) {
        std::string s;
        for (const auto& l : pr.labels) s += (s.empty() ? "" : ", ") + l.name;
        lines.push_back("Labels: " + s);
    }
    if (!pr.assignees.empty()) {
        std::string s;
        for (const auto& a : pr.assignees) s += (s.empty() ? "" : ", ") + a.login;
        lines.push_back("Assignees: " + s);
    }
    lines.push_back("Changes: +" + std::to_string(pr.additions) + " -" + std::to_string(pr.deletions) + " in " +
                    std::to_string(pr.changedFiles) + " file(s)");
    lines.push_back("Commits: " + std::to_string(pr.commitsCount) + " | Comments: " +
                    std::to_string(pr.commentsCount));
    if (pr.mergeable) {
        std::string m = *pr.mergeable ? "Yes" : "No";
        if (!pr.mergeableState.empty()) m += " (" + pr.mergeableState + ")";
        lines.push_back("Mergeable: " + m);
    }
    if (pr.createdAt) lines.push_back("Created: " + FormatRelativeTime(pr.createdAt));
    if (pr.mergedAt && pr.mergedBy)
        lines.push_back("Merged: " + FormatRelativeTime(pr.mergedAt) + " by " + pr.mergedBy->login);
    std::string text;
    for (const auto& l : lines) text += (text.empty() ? "" : "\n") + l;
    return U8(text);
}

// Asks for a comment and posts it; on failure says why and asks again with the text kept.
void PromptAndPostComment(wxWindow* owner, AccountPtr account, const Repository& repo, int number,
                          std::function<void(const Comment&)> posted, const wxString& initial = "") {
    auto text = AskMultilineText(owner, "&Comment:", wxString::Format("Comment on PR #%d", number), initial);
    if (!text || wxString(*text).Trim().Trim(false).empty()) return;
    std::string body = ToU8(*text), owner_ = repo.owner, name = repo.name;
    SetStatus("Posting comment...");
    RunAsync(owner,
             [account, owner_, name, number, body] {
                 auto c = account->CreatePrComment(owner_, name, number, body);
                 return std::make_pair(c, c ? std::string() : GitHubAccount::LastError());
             },
             [owner, account, repo, number, posted,
              kept = *text](std::pair<std::optional<Comment>, std::string> r) {
                 if (r.first) {
                     SetStatus("Comment added.");
                     posted(*r.first);
                     return;
                 }
                 SetStatus("Ready");
                 ShowError(owner, WithReason("Failed to add comment.", r.second));
                 PromptAndPostComment(owner, account, repo, number, posted, kept);
             });
}

// --- Merge options ---

class MergeDialog : public BaseDialog {
public:
    explicit MergeDialog(wxWindow* parent, const PullRequest& pr)
        : BaseDialog(parent, wxString::Format("Merge PR #%d", pr.number), wxSize(500, 380)) {
        m_sizer->Add(new wxStaticText(m_panel, wxID_ANY, "Merging: " + U8(pr.title)), 0, wxALL, 10);
        m_sizer->Add(new wxStaticText(m_panel, wxID_ANY, U8(pr.headRef + " -> " + pr.baseRef)), 0,
                     wxLEFT | wxBOTTOM, 10);
        const wxString methods[] = {"Create a merge commit", "Squash and merge", "Rebase and merge"};
        m_method = new wxChoice(m_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, 3, methods);
        m_method->SetSelection(0);
        AddLabeled("Merge Metho&d:", m_method);
        m_title = new wxTextCtrl(m_panel, wxID_ANY,
                                 wxString::Format("Merge pull request #%d from %s", pr.number, U8(pr.headRef)));
        AddLabeled("Commit &Title (optional):", m_title);
        m_message = new wxTextCtrl(m_panel, wxID_ANY, U8(pr.title), wxDefaultPosition, wxSize(-1, 80),
                                   wxTE_MULTILINE);
        AddLabeled("Commit M&essage (optional):", m_message, 1);

        auto* buttons = new wxBoxSizer(wxHORIZONTAL);
        buttons->Add(new wxButton(m_panel, wxID_OK, "&Merge"), 0, wxRIGHT, 5);
        buttons->Add(new wxButton(m_panel, wxID_CANCEL, "Cancel"), 0);
        m_sizer->Add(buttons, 0, wxALL | wxALIGN_CENTER, 10);
        Finish();
        m_method->SetFocus();
    }

    std::string Method() const {
        static const char* const kMethods[] = {"merge", "squash", "rebase"};
        int i = m_method->GetSelection();
        return kMethods[i >= 0 && i < 3 ? i : 0];
    }
    std::string CommitTitle() const { return Trim(ToU8(m_title->GetValue())); }
    std::string CommitMessage() const { return Trim(ToU8(m_message->GetValue())); }

private:
    wxChoice* m_method;
    wxTextCtrl* m_title;
    wxTextCtrl* m_message;
};

// Asks how to merge, then merges in the background; `merged` runs after it worked.
void MergePr(wxWindow* owner, AccountPtr account, const Repository& repo, const PullRequest& pr,
             std::function<void()> merged) {
    MergeDialog dlg(owner, pr);
    if (dlg.ShowModal() != wxID_OK) return;
    std::string method = dlg.Method(), title = dlg.CommitTitle(), message = dlg.CommitMessage();
    std::string owner_ = repo.owner, name = repo.name;
    int number = pr.number;
    SetStatus(wxString::Format("Merging pull request #%d...", number));
    RunAsync(owner,
             [account, owner_, name, number, title, message, method] {
                 bool ok = account->MergePullRequest(owner_, name, number, title, message, method);
                 return std::make_pair(ok, ok ? std::string() : GitHubAccount::LastError());
             },
             [owner, number, merged](std::pair<bool, std::string> r) {
                 SetStatus("Ready");
                 if (!r.first) {
                     ShowError(owner, WithReason("Failed to merge pull request. It may have conflicts or not be "
                                                 "mergeable.",
                                                 r.second));
                     return;
                 }
                 ShowInfo(owner, wxString::Format("Pull request #%d merged successfully!", number), "Success");
                 merged();
             });
}

// Confirms, then closes without merging; `closed` runs after it worked.
void ClosePr(wxWindow* owner, AccountPtr account, const Repository& repo, const PullRequest& pr,
             std::function<void()> closed) {
    wxString question =
        wxString::Format("Close pull request #%d: %s without merging?", pr.number, U8(pr.title));
    if (!AskYesNo(owner, question, "Confirm Close")) return;
    std::string owner_ = repo.owner, name = repo.name;
    int number = pr.number;
    SetStatus("Closing pull request...");
    RunAsync(owner,
             [account, owner_, name, number] {
                 bool ok = account->ClosePullRequest(owner_, name, number);
                 return std::make_pair(ok, ok ? std::string() : GitHubAccount::LastError());
             },
             [owner, closed](std::pair<bool, std::string> r) {
                 SetStatus("Ready");
                 if (r.first)
                     closed();
                 else
                     ShowError(owner, WithReason("Failed to close pull request.", r.second));
             });
}

// --- One pull request with its comments ---

class PullRequestDialog : public BaseDialog {
public:
    PullRequestDialog(wxWindow* parent, const Repository& repo, const PullRequest& pr, bool canMerge)
        : BaseDialog(parent, wxString::Format("PR #%d - %s", pr.number, U8(pr.title)), wxSize(850, 700)),
          m_repo(repo), m_pr(pr), m_canMerge(canMerge), m_account(app::Current()) {
        m_details = ReadOnlyText(m_panel, 140);
        AddLabeled("PR &Details:", m_details);
        m_body = ReadOnlyText(m_panel, 110);
        AddLabeled("D&escription:", m_body, 1);
        m_list = new wxListBox(m_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddLabeled("&Comments:", m_list, 1);
        m_commentText = ReadOnlyText(m_panel, 90);
        AddLabeled("Comment &Text:", m_commentText);

        auto canAct = [this] { return CanAct(m_pr, m_canMerge); };
        m_actions = new ActionBar(m_panel);
        m_actions->Add({"&Add Comment...", [this] { AddComment(); }, true});
        m_actions->Add({"&Merge PR...", [this] { Merge(); }, true, canAct});
        m_actions->Add({"Open in &Browser", [this] { OpenUrl(m_pr.htmlUrl); }, true}).Shortcut('O', wxMOD_CONTROL);
        m_actions->Add({"C&lose PR", [this] { ClosePullRequest(); }, false, canAct});
        m_actions->Add({"Copy &URL", [this] { CopyToClipboard(U8(m_pr.htmlUrl)); }});
        m_actions->Add({"Open Comment in Bro&wser", [this] { if (auto* c = Sel()) OpenUrl(c->htmlUrl); }, false,
                        [this] { return Sel() != nullptr; }});
        m_actions->AddSeparator();
        m_actions->Add({"Re&fresh Comments", [this] { LoadComments(); }}).Shortcut('R', wxMOD_CONTROL);
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER, 10);
        m_actions->AttachContextMenu(m_list);
        m_list->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) { ShowComment(); });

        m_details->SetValue(PrDetails(m_pr));
        m_body->SetValue(m_pr.body.empty() ? wxString("No description provided.") : U8(m_pr.body));
        LoadComments();
        Finish();
        m_body->SetFocus();
    }

private:
    const Comment* Sel() const {
        int i = Selected(m_list);
        return i >= 0 && i < static_cast<int>(m_comments.size()) ? &m_comments[i] : nullptr;
    }

    void LoadComments() {
        int gen = ++m_generation;
        m_comments.clear();
        SetListItems(m_list, {"Loading comments..."});
        m_commentText->Clear();
        m_actions->Update();
        auto account = m_account;
        std::string owner = m_repo.owner, name = m_repo.name;
        int number = m_pr.number;
        RunAsync(this,
                 [account, owner, name, number] {
                     auto comments = account->GetPrComments(owner, name, number);
                     return std::make_pair(comments, comments.empty() ? GitHubAccount::LastError() : "");
                 },
                 [this, gen](std::pair<std::vector<Comment>, std::string> r) {
                     if (gen != m_generation) return;
                     m_comments = std::move(r.first);
                     if (m_comments.empty() && !r.second.empty())
                         SetListItems(m_list, {"Could not load comments: " + U8(r.second)});
                     else
                         ShowComments();
                     m_actions->Update();
                 });
    }

    void ShowComments() {
        std::vector<wxString> rows;
        for (const auto& c : m_comments) rows.push_back(CommentLine(c));
        if (rows.empty()) rows.push_back("No comments yet");
        SetListItems(m_list, rows);
        ShowComment();
    }

    void ShowComment() {
        const Comment* c = Sel();
        m_commentText->SetValue(c ? U8(c->body) : wxString());
        m_actions->Update();
    }

    void AddComment() {
        PromptAndPostComment(this, m_account, m_repo, m_pr.number, [this](const Comment& c) {
            // Add it to what we have rather than fetching every comment again.
            m_comments.push_back(c);
            m_pr.commentsCount++;
            m_details->SetValue(PrDetails(m_pr));
            ShowComments();
            m_list->SetSelection(static_cast<int>(m_comments.size()) - 1);
            ShowComment();
            m_list->SetFocus();
        });
    }

    void Merge() {
        MergePr(this, m_account, m_repo, m_pr, [this] {
            m_pr.merged = true;
            m_pr.state = "closed";
            m_pr.mergedAt = std::time(nullptr);
            if (auto me = m_account->Username(); !me.empty()) m_pr.mergedBy = User{me, 0, ""};
            m_details->SetValue(PrDetails(m_pr));
            m_actions->Update();
        });
    }

    void ClosePullRequest() {
        ClosePr(this, m_account, m_repo, m_pr, [this] {
            m_pr.state = "closed";
            m_pr.closedAt = std::time(nullptr);
            m_details->SetValue(PrDetails(m_pr));
            m_actions->Update();
            ShowInfo(this, "Pull request closed.", "Success");
        });
    }

    Repository m_repo;
    PullRequest m_pr;
    bool m_canMerge;
    AccountPtr m_account;
    std::vector<Comment> m_comments;
    int m_generation = 0;
    wxTextCtrl* m_details;
    wxTextCtrl* m_body;
    wxListBox* m_list;
    wxTextCtrl* m_commentText;
    ActionBar* m_actions;  // owned by m_panel
};

// --- A repository's pull requests ---

class PullRequestsDialog : public BaseDialog {
public:
    PullRequestsDialog(wxWindow* parent, const Repository& repo)
        : BaseDialog(parent, "Pull Requests - " + U8(repo.fullName), wxSize(850, 600)),
          m_repo(repo), m_account(app::Current()) {
        const wxString filters[] = {"Open", "Closed", "All"};
        m_filter = new wxChoice(m_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, 3, filters);
        m_filter->SetSelection(0);
        AddLabeled("&Filter:", m_filter);
        m_list = new wxListBox(m_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddLabeled("&Pull Requests:", m_list, 1);
        m_prs = new PagedList<PullRequest>(m_list, "pull requests",
                                           [](const PullRequest& x) { return U8(x.FormatDisplay()); });
        m_prs->FocusWhenLoaded();

        auto has = [this] { return Sel() != nullptr; };
        auto canAct = [this] { return Sel() && CanAct(*Sel(), m_canMerge); };
        m_actions = new ActionBar(m_panel);
        m_actions->Add({"&View PR", [this] { View(); }, true, has});
        m_actions->Add({"&Comment...", [this] { Comment(); }, true, has});
        m_actions->Add({"Mer&ge...", [this] { Merge(); }, true, canAct});
        m_actions->Add({"C&lose PR", [this] { ClosePullRequest(); }, false, canAct});
        m_actions->Add({"Open in &Browser", [this] { if (auto* p = Sel()) OpenUrl(p->htmlUrl); }, false, has})
            .Shortcut('O', wxMOD_CONTROL);
        m_actions->Add({"Copy &URL", [this] { if (auto* p = Sel()) CopyToClipboard(U8(p->htmlUrl)); },
                        false, has});
        m_actions->AddSeparator();
        m_actions->Add({"&Refresh", [this] { Reload(); }}).Shortcut('R', wxMOD_CONTROL).Shortcut(WXK_F5);
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER, 10);
        m_actions->AttachContextMenu(m_list);
        m_actions->AttachActivate(m_list);  // Enter / double click views, as in Python

        m_prs->OnSelect([this] { m_actions->Update(); });
        m_prs->OnLoaded([this](bool first) { Loaded(first); });
        m_filter->Bind(wxEVT_CHOICE, [this](wxCommandEvent&) { Load(); });

        // The merge permission and the list at once.
        auto account = m_account;
        std::string owner = m_repo.owner, name = m_repo.name;
        RunAsync(this, [account, owner, name] { return account->CanMerge(owner, name); }, [this](bool can) {
            m_canMerge = can;
            m_actions->Update();
        });
        Load();
        Finish();
        m_list->SetFocus();
    }

private:
    const PullRequest* Sel() const { return m_prs->Selected(); }

    // Starts again from page 1 (a new filter); the selected item stays selected if it is still there.
    void Load(bool keepSelection = true) {
        static const char* const kStates[] = {"open", "closed", "all"};
        m_keep = keepSelection && Sel() ? Sel()->number : 0;
        int f = m_filter->GetSelection();
        std::string state = kStates[f >= 0 && f < 3 ? f : 0];
        auto account = m_account;
        std::string owner = m_repo.owner, name = m_repo.name;
        m_prs->Load([account, owner, name, state](int page) {
            return account->GetPullRequestsPage(owner, name, state, page);
        });
        m_actions->Update();
    }

    // Fetches the pages already loaded again, keeping the reader's place (by number when it moved).
    void Reload() {
        m_keep = Sel() ? Sel()->number : 0;
        m_prs->Refresh();
    }

    void Loaded(bool first) {
        if (first && m_keep) {
            const auto& items = m_prs->Items();
            for (size_t i = 0; i < items.size(); ++i)
                if (items[i].number == m_keep) m_list->SetSelection(static_cast<int>(i));
            m_keep = 0;
        }
        m_actions->Update();
    }

    void View() {
        const PullRequest* p = Sel();
        if (!p) return;
        PullRequest pr = *p;
        ShowPullRequestDialog(this, m_repo, pr, m_canMerge);
        Reload();  // it may have been merged, closed or commented on
    }

    void Comment() {
        const PullRequest* p = Sel();
        if (!p) return;
        PromptAndPostComment(this, m_account, m_repo, p->number, [this](const ::Comment&) {
            ShowInfo(this, "Comment added successfully!", "Success");
        });
    }

    void Merge() {
        const PullRequest* p = Sel();
        if (!p) return;
        PullRequest pr = *p;
        MergePr(this, m_account, m_repo, pr, [this] { Reload(); });
    }

    void ClosePullRequest() {
        const PullRequest* p = Sel();
        if (!p) return;
        PullRequest pr = *p;
        ClosePr(this, m_account, m_repo, pr, [this] { Reload(); });
    }

    Repository m_repo;
    AccountPtr m_account;
    bool m_canMerge = false;
    PagedList<PullRequest>* m_prs;  // owned by m_list
    int m_keep = 0;  // number to reselect after a load
    wxChoice* m_filter;
    wxListBox* m_list;
    ActionBar* m_actions;  // owned by m_panel
};

}  // namespace

void ShowPullRequestsDialog(wxWindow* parent, const Repository& repo) {
    if (!app::Current()) return;
    ShowModalDialog<PullRequestsDialog>(parent, repo);
}

void ShowPullRequestDialog(wxWindow* parent, const Repository& repo, const PullRequest& pr, bool canMerge) {
    if (!app::Current()) return;
    ShowModalDialog<PullRequestDialog>(parent, repo, pr, canMerge);
}

void OpenPullRequest(wxWindow* parent, const std::string& owner, const std::string& name, int number) {
    auto account = app::Current();
    if (!account) return;
    wxWindow* window = parent ? parent : GetActiveOwner();
    SetStatus(wxString::Format("Loading PR #%d...", number));
    RunAsync(window,
             [account, owner, name, number] {
                 // The pull request, its repository and the merge permission at once.
                 auto repo = std::async(std::launch::async, [=] { return account->GetRepo(owner, name); });
                 auto canMerge = std::async(std::launch::async, [=] { return account->CanMerge(owner, name); });
                 auto pr = account->GetPullRequest(owner, name, number);
                 std::string reason = pr ? "" : GitHubAccount::LastError();
                 return std::make_tuple(pr, repo.get(), canMerge.get(), reason);
             },
             [window, number](
                 std::tuple<std::optional<PullRequest>, std::optional<Repository>, bool, std::string> r) {
                 SetStatus("Ready");
                 auto& [pr, repo, canMerge, reason] = r;
                 if (pr && repo)
                     ShowPullRequestDialog(window, *repo, *pr, canMerge);
                 else
                     ShowError(window, WithReason(wxString::Format("Could not load PR #%d", number), reason));
             });
}
