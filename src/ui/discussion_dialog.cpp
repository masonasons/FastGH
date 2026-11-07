// A discussion with its comments and replies (a port of GUI/discussions.py).

#include "ui/dialogs.h"
#include "ui/ui_common.h"

#include "core/app.h"
#include "core/github.h"
#include "core/util.h"

#include <memory>
#include <optional>
#include <string>
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

// "[Reply to bob] alice (2024-01-02 03:04): first 60 characters..."
wxString CommentLine(const DiscussionComment& c) {
    std::string when = c.createdAt ? FormatLocalTime(c.createdAt) : "Unknown";
    std::string preview = Truncate(ReplaceAll(ReplaceAll(c.body, "\r", ""), "\n", " "), 63);
    std::string line = c.author.login + " (" + when + "): " + preview;
    if (c.isReply)
        line = "[Reply" + (c.parentAuthorLogin.empty() ? "" : " to " + c.parentAuthorLogin) + "] " + line;
    return U8(line);
}

class DiscussionDialog : public BaseDialog {
public:
    DiscussionDialog(wxWindow* parent, const std::string& owner, const std::string& name,
                     const Discussion& discussion)
        : BaseDialog(parent,
                     wxString::Format("Discussion #%d - %s", discussion.number, U8(discussion.title)),
                     wxSize(880, 720)),
          m_owner(owner), m_name(name), m_discussion(discussion), m_account(app::Current()) {
        m_comments = discussion.comments;
        m_hasNext = discussion.commentsHasNextPage;
        m_endCursor = discussion.commentsEndCursor;

        m_details = ReadOnlyText(m_panel, 110);
        AddLabeled("Discussion &Details:", m_details);
        m_body = ReadOnlyText(m_panel, 130);
        AddLabeled("&Body:", m_body, 1);
        m_list = new wxListBox(m_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddLabeled("&Comments:", m_list, 1);
        m_commentText = ReadOnlyText(m_panel, 90);
        AddLabeled("Comment &Text:", m_commentText);

        m_actions = new ActionBar(m_panel);
        m_actions->Add({"&Add Comment...", [this] { AddComment(); }, true, [this] { return !m_posting; }});
        m_actions->Add({"&Load More Comments", [this] { LoadMore(); }, true,
                        [this] { return m_hasNext && !m_loading; }});
        m_actions->Add({"Open in &Browser", [this] { OpenUrl(m_discussion.url); }, true})
            .Shortcut('O', wxMOD_CONTROL);
        m_actions->Add({"Copy &URL", [this] { CopyToClipboard(U8(m_discussion.url)); }});
        m_actions->Add({"Open Comment in Bro&wser", [this] { if (auto* c = Sel()) OpenUrl(c->url); }, false,
                        [this] { return Sel() != nullptr; }});
        m_actions->AddSeparator();
        m_actions->Add({"&Refresh Comments", [this] { RefreshComments(); }}).Shortcut('R', wxMOD_CONTROL);
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER, 10);
        m_actions->AttachContextMenu(m_list);
        m_list->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) { ShowComment(); });

        m_body->SetValue(m_discussion.body.empty() ? wxString("No description provided.")
                                                   : U8(m_discussion.body));
        ShowDetails();
        ShowComments();
        Finish();
        m_body->SetFocus();
    }

private:
    const DiscussionComment* Sel() const {
        int i = Selected(m_list);
        return i >= 0 && i < static_cast<int>(m_comments.size()) ? &m_comments[i] : nullptr;
    }

    void ShowDetails() {
        const Discussion& d = m_discussion;
        std::string text = "Title: " + d.title + "\nAuthor: " + d.author.login;
        if (!d.categoryName.empty()) text += "\nCategory: " + d.categoryName;
        text += std::string("\nAnswered: ") + (d.isAnswered ? "Yes" : "No");
        text += "\nComments: " + std::to_string(d.commentsCount);
        if (d.createdAt) text += "\nCreated: " + FormatRelativeTime(d.createdAt);
        if (d.updatedAt) text += "\nUpdated: " + FormatRelativeTime(d.updatedAt);
        m_details->SetValue(U8(text));
    }

    void ShowComments() {
        std::vector<wxString> rows;
        for (const auto& c : m_comments) rows.push_back(CommentLine(c));
        if (rows.empty()) rows.push_back("No comments yet");
        SetListItems(m_list, rows);
        ShowComment();
    }

    void ShowComment() {
        const DiscussionComment* c = Sel();
        m_commentText->SetValue(c ? U8(c->body) : wxString());
        m_actions->Update();
    }

    // Fetches a page of comments; `after` empty for the first page (a refresh).
    void FetchPage(const std::string& after) {
        int gen = ++m_generation;
        m_loading = true;
        m_actions->Update();
        auto account = m_account;
        std::string owner = m_owner, name = m_name;
        int number = m_discussion.number;
        RunAsync(this,
                 [account, owner, name, number, after] {
                     auto page = account->GetDiscussionComments(owner, name, number, kPageSize, after);
                     return std::make_pair(page, page ? std::string() : GitHubAccount::LastError());
                 },
                 [this, gen, after](std::pair<std::optional<GitHubAccount::CommentPage>, std::string> r) {
                     if (gen != m_generation) return;
                     m_loading = false;
                     if (!r.first) {
                         if (after.empty()) ShowComments();  // put back what we had
                         m_actions->Update();
                         ShowError(this, WithReason("Could not load comments.", r.second));
                         return;
                     }
                     size_t firstNew = after.empty() ? 0 : m_comments.size();
                     if (after.empty()) m_comments.clear();
                     m_comments.insert(m_comments.end(), r.first->comments.begin(), r.first->comments.end());
                     m_hasNext = r.first->hasNextPage;
                     m_endCursor = r.first->endCursor;
                     ShowComments();
                     // After "load more", land on the first new comment so reading carries on from there.
                     if (firstNew > 0 && firstNew < m_comments.size()) {
                         m_list->SetSelection(static_cast<int>(firstNew));
                         ShowComment();
                         m_list->SetFocus();
                         SetStatus(wxString::Format("%zu more comment%s loaded.", m_comments.size() - firstNew,
                                                    Plural(static_cast<long long>(m_comments.size() - firstNew))));
                     }
                 });
    }

    void RefreshComments() {
        SetListItems(m_list, {"Loading comments..."});
        m_commentText->Clear();
        FetchPage("");
    }

    void LoadMore() {
        if (m_hasNext && !m_loading) FetchPage(m_endCursor);
    }

    // Asks for a comment and posts it; on failure says why and asks again with the text kept.
    void AddComment(const wxString& initial = "") {
        auto text = AskMultilineText(this, "&Comment:", wxString::Format("Comment on Discussion #%d",
                                                                         m_discussion.number), initial);
        if (!text || wxString(*text).Trim().Trim(false).empty()) return;
        std::string body = Trim(ToU8(*text));
        auto account = m_account;
        std::string id = m_discussion.id;
        m_posting = true;
        m_actions->Update();
        SetStatus("Posting comment...");
        RunAsync(this,
                 [account, id, body] {
                     auto c = account->CreateDiscussionComment(id, body);
                     return std::make_pair(c, c ? std::string() : GitHubAccount::LastError());
                 },
                 [this, kept = *text](std::pair<std::optional<DiscussionComment>, std::string> r) {
                     m_posting = false;
                     m_actions->Update();
                     if (!r.first) {
                         SetStatus("Ready");
                         ShowError(this, WithReason("Failed to add comment.", r.second));
                         AddComment(kept);
                         return;
                     }
                     SetStatus("Comment added.");
                     m_comments.push_back(*r.first);
                     m_discussion.commentsCount++;
                     ShowDetails();
                     ShowComments();
                     m_list->SetSelection(static_cast<int>(m_comments.size()) - 1);
                     ShowComment();
                     m_list->SetFocus();
                 });
    }

    std::string m_owner;
    std::string m_name;
    Discussion m_discussion;
    AccountPtr m_account;
    std::vector<DiscussionComment> m_comments;
    bool m_hasNext = false;
    std::string m_endCursor;
    bool m_loading = false;
    bool m_posting = false;
    int m_generation = 0;
    wxTextCtrl* m_details;
    wxTextCtrl* m_body;
    wxListBox* m_list;
    wxTextCtrl* m_commentText;
    ActionBar* m_actions;  // owned by m_panel
};

}  // namespace

void ShowDiscussionDialog(wxWindow* parent, const std::string& owner, const std::string& name,
                          const Discussion& discussion) {
    if (!app::Current()) return;
    ShowModalDialog<DiscussionDialog>(parent, owner, name, discussion);
}

void OpenDiscussion(wxWindow* parent, const std::string& owner, const std::string& name, int number) {
    auto account = app::Current();
    if (!account) return;
    wxWindow* window = parent ? parent : GetActiveOwner();
    SetStatus(wxString::Format("Loading discussion #%d...", number));
    RunAsync(window,
             [account, owner, name, number] {
                 auto d = account->GetDiscussion(owner, name, number, kPageSize);
                 // LastError is per thread: read it here, not on the UI thread.
                 return std::make_pair(d, d ? std::string() : GitHubAccount::LastError());
             },
             [window, owner, name, number](std::pair<std::optional<Discussion>, std::string> r) {
                 SetStatus("Ready");
                 if (r.first)
                     ShowDiscussionDialog(window, owner, name, *r.first);
                 else
                     ShowError(window,
                               WithReason(wxString::Format("Could not load discussion #%d.", number), r.second));
             });
}
