// Issues: a repository's list, one issue with its comments, new issue (a port of GUI/issues.py).

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
#include <utility>
#include <vector>

namespace {

using AccountPtr = std::shared_ptr<GitHubAccount>;

// "message\n\nReason: why", or just the message when GitHub gave no reason.
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

// One readable line per comment: "login (2024-01-02 03:04): first 50 characters..."
wxString CommentLine(const Comment& c) {
    std::string when = c.createdAt ? FormatLocalTime(c.createdAt) : "Unknown";
    std::string preview = ReplaceAll(ReplaceAll(c.body, "\r", ""), "\n", " ");
    return U8(c.user.login + " (" + when + "): " + Truncate(preview, 53));
}

wxString IssueDetails(const Issue& issue) {
    std::vector<std::string> lines;
    lines.push_back("Title: " + issue.title);
    lines.push_back("State: " + Upper(issue.state));
    lines.push_back("Author: " + issue.user.login);
    if (!issue.labels.empty()) {
        std::string s;
        for (const auto& l : issue.labels) s += (s.empty() ? "" : ", ") + l.name;
        lines.push_back("Labels: " + s);
    }
    if (!issue.assignees.empty()) {
        std::string s;
        for (const auto& a : issue.assignees) s += (s.empty() ? "" : ", ") + a.login;
        lines.push_back("Assignees: " + s);
    }
    lines.push_back("Comments: " + std::to_string(issue.commentsCount));
    if (issue.createdAt) lines.push_back("Created: " + FormatRelativeTime(issue.createdAt));
    if (issue.updatedAt) lines.push_back("Updated: " + FormatRelativeTime(issue.updatedAt));
    if (issue.state == "closed" && issue.closedAt)
        lines.push_back("Closed: " + FormatRelativeTime(issue.closedAt));
    std::string text;
    for (const auto& l : lines) text += (text.empty() ? "" : "\n") + l;
    return U8(text);
}

// Asks for a comment and posts it in the background. On failure it says why and
// asks again with the text kept, so a long comment is never lost.
void PromptAndPostComment(wxWindow* owner, AccountPtr account, const Repository& repo, int number,
                          std::function<void(const Comment&)> posted, const wxString& initial = "") {
    wxString title = wxString::Format("Comment on Issue #%d", number);
    auto text = AskMultilineText(owner, "&Comment:", title, initial);
    if (!text || wxString(*text).Trim().Trim(false).empty()) return;
    std::string body = ToU8(*text), owner_ = repo.owner, name = repo.name;
    SetStatus("Posting comment...");
    RunAsync(owner,
             [account, owner_, name, number, body] {
                 auto c = account->CreateIssueComment(owner_, name, number, body);
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

// Closes or reopens the issue in the background; `changed` runs after it worked.
void SetIssueState(wxWindow* owner, AccountPtr account, const Repository& repo, int number, bool reopen,
                   std::function<void()> changed) {
    SetStatus(reopen ? "Reopening issue..." : "Closing issue...");
    std::string owner_ = repo.owner, name = repo.name;
    RunAsync(owner,
             [account, owner_, name, number, reopen] {
                 bool ok = reopen ? account->ReopenIssue(owner_, name, number)
                                  : account->CloseIssue(owner_, name, number);
                 return std::make_pair(ok, ok ? std::string() : GitHubAccount::LastError());
             },
             [owner, reopen, changed](std::pair<bool, std::string> r) {
                 SetStatus("Ready");
                 if (r.first)
                     changed();
                 else
                     ShowError(owner, WithReason(reopen ? "Failed to reopen issue." : "Failed to close issue.",
                                                 r.second));
             });
}

// --- New issue ---

class NewIssueDialog : public BaseDialog {
public:
    NewIssueDialog(wxWindow* parent, const Repository& repo)
        : BaseDialog(parent, "New Issue - " + U8(repo.fullName), wxSize(600, 450)),
          m_repo(repo), m_account(app::Current()) {
        m_title = new wxTextCtrl(m_panel, wxID_ANY);
        AddLabeled("&Title:", m_title);
        m_body = new wxTextCtrl(m_panel, wxID_ANY, "", wxDefaultPosition, wxDefaultSize, wxTE_MULTILINE);
        AddLabeled("&Body:", m_body, 1);

        auto* buttons = new wxBoxSizer(wxHORIZONTAL);
        m_create = new wxButton(m_panel, wxID_OK, "C&reate Issue");
        buttons->Add(m_create, 0, wxRIGHT, 5);
        buttons->Add(new wxButton(m_panel, wxID_CANCEL, "Cancel"), 0);
        m_sizer->Add(buttons, 0, wxALL | wxALIGN_CENTER, 10);
        m_create->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { Create(); });

        Finish();
        m_title->SetFocus();
    }

private:
    void Create() {
        std::string title = Trim(ToU8(m_title->GetValue()));
        if (title.empty()) {
            ShowError(this, "Please enter a title.");
            m_title->SetFocus();
            return;
        }
        std::string body = ToU8(m_body->GetValue()), owner = m_repo.owner, name = m_repo.name;
        auto account = m_account;
        m_create->Disable();
        SetStatus("Creating issue...");
        RunAsync(this,
                 [account, owner, name, title, body] {
                     auto issue = account->CreateIssue(owner, name, title, body);
                     return std::make_pair(issue, issue ? std::string() : GitHubAccount::LastError());
                 },
                 [this](std::pair<std::optional<Issue>, std::string> r) {
                     SetStatus("Ready");
                     m_create->Enable();
                     if (!r.first) {
                         ShowError(this, WithReason("Failed to create issue.", r.second));
                         return;
                     }
                     ShowInfo(this, wxString::Format("Issue #%d created successfully!", r.first->number),
                              "Success");
                     EndModal(wxID_OK);
                 });
    }

    Repository m_repo;
    AccountPtr m_account;
    wxTextCtrl* m_title;
    wxTextCtrl* m_body;
    wxButton* m_create;
};

// --- One issue with its comments ---

class IssueDialog : public BaseDialog {
public:
    IssueDialog(wxWindow* parent, const Repository& repo, const Issue& issue)
        : BaseDialog(parent, wxString::Format("Issue #%d - %s", issue.number, U8(issue.title)), wxSize(800, 650)),
          m_repo(repo), m_issue(issue), m_account(app::Current()) {
        m_details = ReadOnlyText(m_panel, 110);
        AddLabeled("Issue &Details:", m_details);
        m_body = ReadOnlyText(m_panel, 130);
        AddLabeled("&Body:", m_body, 1);
        m_list = new wxListBox(m_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddLabeled("&Comments:", m_list, 1);
        m_commentText = ReadOnlyText(m_panel, 90);
        AddLabeled("Comment &Text:", m_commentText);

        m_actions = new ActionBar(m_panel);
        m_actions->Add({"&Add Comment...", [this] { AddComment(); }, true});
        m_actions->Add({"C&lose Issue", [this] { ToggleState(); }, true, nullptr,
                        [this] { return wxString(IsOpen() ? "C&lose Issue" : "&Reopen Issue"); }});
        m_actions->Add({"Open in &Browser", [this] { OpenUrl(m_issue.htmlUrl); }, true})
            .Shortcut('O', wxMOD_CONTROL);
        m_actions->Add({"Copy &URL", [this] { CopyToClipboard(U8(m_issue.htmlUrl)); }});
        m_actions->Add({"Open Comment in Bro&wser", [this] { if (auto* c = Sel()) OpenUrl(c->htmlUrl); }, false,
                        [this] { return Sel() != nullptr; }});
        m_actions->AddSeparator();
        m_actions->Add({"Re&fresh Comments", [this] { LoadComments(); }}).Shortcut('R', wxMOD_CONTROL);
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER, 10);
        m_actions->AttachContextMenu(m_list);
        m_list->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) { ShowComment(); });

        m_details->SetValue(IssueDetails(m_issue));
        m_body->SetValue(m_issue.body.empty() ? wxString("No description provided.") : U8(m_issue.body));
        LoadComments();
        Finish();
        m_body->SetFocus();
    }

private:
    bool IsOpen() const { return m_issue.state == "open"; }
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
        int number = m_issue.number;
        RunAsync(this,
                 [account, owner, name, number] {
                     auto comments = account->GetIssueComments(owner, name, number);
                     return std::make_pair(comments, comments.empty() ? GitHubAccount::LastError() : "");
                 },
                 [this, gen](std::pair<std::vector<Comment>, std::string> r) {
                     if (gen != m_generation) return;
                     m_comments = std::move(r.first);
                     if (m_comments.empty() && !r.second.empty()) {
                         SetListItems(m_list, {"Could not load comments: " + U8(r.second)});
                     } else {
                         m_issue.commentsCount = static_cast<int>(m_comments.size());
                         m_details->SetValue(IssueDetails(m_issue));
                         ShowComments();
                     }
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
        PromptAndPostComment(this, m_account, m_repo, m_issue.number, [this](const Comment& c) {
            // Add it to what we have rather than fetching every comment again.
            m_comments.push_back(c);
            m_issue.commentsCount = static_cast<int>(m_comments.size());
            m_details->SetValue(IssueDetails(m_issue));
            ShowComments();
            m_list->SetSelection(static_cast<int>(m_comments.size()) - 1);
            ShowComment();
            m_list->SetFocus();
        });
    }

    void ToggleState() {
        bool reopen = !IsOpen();
        SetIssueState(this, m_account, m_repo, m_issue.number, reopen, [this, reopen] {
            m_issue.state = reopen ? "open" : "closed";
            m_issue.closedAt = reopen ? 0 : std::time(nullptr);
            m_details->SetValue(IssueDetails(m_issue));
            m_actions->Update();
            ShowInfo(this, reopen ? "Issue reopened." : "Issue closed.", "Success");
        });
    }

    Repository m_repo;
    Issue m_issue;
    AccountPtr m_account;
    std::vector<Comment> m_comments;
    int m_generation = 0;
    wxTextCtrl* m_details;
    wxTextCtrl* m_body;
    wxListBox* m_list;
    wxTextCtrl* m_commentText;
    ActionBar* m_actions;  // owned by m_panel
};

// --- A repository's issues ---

class IssuesDialog : public BaseDialog {
public:
    IssuesDialog(wxWindow* parent, const Repository& repo)
        : BaseDialog(parent, "Issues - " + U8(repo.fullName), wxSize(800, 600)),
          m_repo(repo), m_account(app::Current()) {
        const wxString filters[] = {"Open", "Closed", "All"};
        m_filter = new wxChoice(m_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, 3, filters);
        m_filter->SetSelection(0);
        AddLabeled("&Filter:", m_filter);
        m_list = new wxListBox(m_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddLabeled("I&ssues:", m_list, 1);
        m_issues = new PagedList<Issue>(m_list, "issues", [](const Issue& x) { return U8(x.FormatDisplay()); });
        m_issues->FocusWhenLoaded();

        auto has = [this] { return Sel() != nullptr; };
        m_actions = new ActionBar(m_panel);
        m_actions->Add({"&View Issue", [this] { View(); }, true, has});
        m_actions->Add({"&Comment...", [this] { Comment(); }, true, has});
        m_actions->Add({"&New Issue...", [this] { NewIssue(); }, true}).Shortcut('N', wxMOD_CONTROL);
        m_actions->Add({"C&lose Issue", [this] { ToggleState(); }, false, has, [this] {
                            const Issue* i = Sel();
                            return wxString(i && i->state != "open" ? "R&eopen Issue" : "C&lose Issue");
                        }});
        m_actions->Add({"Open in &Browser", [this] { if (auto* i = Sel()) OpenUrl(i->htmlUrl); }, false, has})
            .Shortcut('O', wxMOD_CONTROL);
        m_actions->Add({"Copy &URL", [this] { if (auto* i = Sel()) CopyToClipboard(U8(i->htmlUrl)); },
                        false, has});
        m_actions->AddSeparator();
        m_actions->Add({"&Refresh", [this] { Reload(); }}).Shortcut('R', wxMOD_CONTROL).Shortcut(WXK_F5);
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER, 10);
        m_actions->AttachContextMenu(m_list);
        m_actions->AttachActivate(m_list);  // Enter / double click views, as in Python

        m_issues->OnSelect([this] { m_actions->Update(); });
        m_issues->OnLoaded([this](bool first) { Loaded(first); });
        m_filter->Bind(wxEVT_CHOICE, [this](wxCommandEvent&) { Load(); });

        Load();
        Finish();
        m_list->SetFocus();
    }

private:
    const Issue* Sel() const { return m_issues->Selected(); }

    // Starts again from page 1 (a new filter); the selected item stays selected if it is still there.
    void Load(bool keepSelection = true) {
        static const char* const kStates[] = {"open", "closed", "all"};
        m_keep = keepSelection && Sel() ? Sel()->number : 0;
        int f = m_filter->GetSelection();
        std::string state = kStates[f >= 0 && f < 3 ? f : 0];
        auto account = m_account;
        std::string owner = m_repo.owner, name = m_repo.name;
        m_issues->Load([account, owner, name, state](int page) {
            return account->GetIssuesPage(owner, name, state, page);
        });
        m_actions->Update();
    }

    // Fetches the pages already loaded again, keeping the reader's place (by number when it moved).
    void Reload() {
        m_keep = Sel() ? Sel()->number : 0;
        m_issues->Refresh();
    }

    void Loaded(bool first) {
        if (first && m_keep) {
            const auto& items = m_issues->Items();
            for (size_t i = 0; i < items.size(); ++i)
                if (items[i].number == m_keep) m_list->SetSelection(static_cast<int>(i));
            m_keep = 0;
        }
        m_actions->Update();
    }

    void View() {
        const Issue* i = Sel();
        if (!i) return;
        Issue issue = *i;
        ShowIssueDialog(this, m_repo, issue);
        Reload();  // its state or comments may have changed
    }

    void Comment() {
        const Issue* i = Sel();
        if (!i) return;
        PromptAndPostComment(this, m_account, m_repo, i->number, [this](const ::Comment&) {
            ShowInfo(this, "Comment added successfully!", "Success");
        });
    }

    void NewIssue() {
        if (ShowModalDialog<NewIssueDialog>(this, m_repo) == wxID_OK) Load(false);  // the new issue is first
    }

    void ToggleState() {
        const Issue* i = Sel();
        if (!i) return;
        bool reopen = i->state != "open";
        wxString question = wxString::Format("%s issue #%d: %s?", reopen ? "Reopen" : "Close", i->number,
                                             U8(i->title));
        if (!AskYesNo(this, question, reopen ? "Confirm Reopen" : "Confirm Close")) return;
        SetIssueState(this, m_account, m_repo, i->number, reopen, [this] { Reload(); });
    }

    Repository m_repo;
    AccountPtr m_account;
    PagedList<Issue>* m_issues;  // owned by m_list
    int m_keep = 0;  // number to reselect after a load
    wxChoice* m_filter;
    wxListBox* m_list;
    ActionBar* m_actions;  // owned by m_panel
};

}  // namespace

void ShowIssuesDialog(wxWindow* parent, const Repository& repo) {
    if (!app::Current()) return;
    ShowModalDialog<IssuesDialog>(parent, repo);
}

void ShowIssueDialog(wxWindow* parent, const Repository& repo, const Issue& issue) {
    if (!app::Current()) return;
    ShowModalDialog<IssueDialog>(parent, repo, issue);
}

void OpenIssue(wxWindow* parent, const std::string& owner, const std::string& name, int number) {
    auto account = app::Current();
    if (!account) return;
    wxWindow* window = parent ? parent : GetActiveOwner();
    SetStatus(wxString::Format("Loading issue #%d...", number));
    RunAsync(window,
             [account, owner, name, number] {
                 // The issue and its repository at once.
                 auto repo = std::async(std::launch::async, [=] { return account->GetRepo(owner, name); });
                 auto issue = account->GetIssue(owner, name, number);
                 std::string reason = issue ? "" : GitHubAccount::LastError();
                 return std::make_tuple(issue, repo.get(), reason);
             },
             [window, number](std::tuple<std::optional<Issue>, std::optional<Repository>, std::string> r) {
                 SetStatus("Ready");
                 auto& [issue, repo, reason] = r;
                 if (issue && repo)
                     ShowIssueDialog(window, *repo, *issue);
                 else
                     ShowError(window, WithReason(wxString::Format("Could not load issue #%d", number), reason));
             });
}
