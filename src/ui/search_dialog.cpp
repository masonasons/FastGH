// Searching GitHub, and a user's profile (a port of GUI/search.py).

#include "ui/dialogs.h"

#include "core/app.h"
#include "core/github.h"
#include "core/util.h"
#include "ui/paged_list.h"
#include "ui/ui_common.h"

#include <wx/choice.h>

#include <algorithm>
#include <memory>
#include <optional>
#include <utility>
#include <string>
#include <vector>

namespace {

// --- Search ---

// The sort choices for each kind of search, as shown and as the API wants them.
struct SortOption {
    const char* label;
    const char* value;
};
const SortOption kRepoSorts[] = {
    {"Best Match", "best-match"}, {"Stars", "stars"}, {"Forks", "forks"}, {"Updated", "updated"}};
const SortOption kUserSorts[] = {
    {"Best Match", "best-match"}, {"Followers", "followers"}, {"Repositories", "repositories"}, {"Joined", "joined"}};

class SearchDialog : public BaseDialog {
public:
    explicit SearchDialog(wxWindow* parent) : BaseDialog(parent, "Search GitHub", wxSize(900, 600)) {
        wxWindow* p = Panel();

        // The query row: each control with its label above it.
        auto* row = new wxBoxSizer(wxHORIZONTAL);
        auto column = [&](const wxString& label, wxWindow* (*make)(wxWindow*), int proportion) {
            auto* col = new wxBoxSizer(wxVERTICAL);
            col->Add(new wxStaticText(p, wxID_ANY, label), 0, wxBOTTOM, 2);
            wxWindow* control = make(p);  // created after its label, so it is named by it
            col->Add(control, 0, wxEXPAND);
            row->Add(col, proportion, wxRIGHT | wxALIGN_BOTTOM, 10);
            return control;
        };
        m_type = static_cast<wxChoice*>(column("Search &for:", [](wxWindow* parent) -> wxWindow* {
            wxArrayString kinds;
            kinds.Add("Repositories");
            kinds.Add("Users");
            auto* c = new wxChoice(parent, wxID_ANY, wxDefaultPosition, wxDefaultSize, kinds);
            c->SetSelection(0);
            return c;
        }, 0));
        m_query = static_cast<wxTextCtrl*>(column("&Query:", [](wxWindow* parent) -> wxWindow* {
            return new wxTextCtrl(parent, wxID_ANY, "", wxDefaultPosition, wxSize(300, -1), wxTE_PROCESS_ENTER);
        }, 1));
        m_sort = static_cast<wxChoice*>(column("&Sort:", [](wxWindow* parent) -> wxWindow* {
            return new wxChoice(parent, wxID_ANY);
        }, 0));
        auto* searchButton = new wxButton(p, wxID_ANY, "Searc&h");
        row->Add(searchButton, 0, wxALIGN_BOTTOM);
        Sizer()->Add(row, 0, wxEXPAND | wxALL, 10);

        // One list per kind of result, each with its own label; only the one for
        // the chosen kind is shown. Each PagedList belongs to its list box.
        auto addList = [&](wxStaticText*& label, wxListBox*& list) {
            label = new wxStaticText(p, wxID_ANY, "&Results:");
            Sizer()->Add(label, 0, wxLEFT | wxRIGHT | wxTOP, 10);
            list = new wxListBox(p, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
            Sizer()->Add(list, 1, wxEXPAND | wxLEFT | wxRIGHT | wxTOP, 10);
        };
        addList(m_repoLabel, m_repoList);
        addList(m_userLabel, m_userList);
        m_repos = new PagedList<Repository>(m_repoList, "repositories",
                                            [](const Repository& r) { return U8(r.FormatSingleLine()); });
        m_users = new PagedList<UserProfile>(m_userList, "users",
                                             [](const UserProfile& u) { return U8(u.FormatDisplay()); });

        // Users: their own view and browser actions (hidden for repositories).
        // Repositories: the shared repository actions.
        m_actions = new ActionBar(p);
        Action viewProfile{"&View Profile", [this] { ViewProfile(); }, true};
        viewProfile.enabled = [this] { return SelectedUser() != nullptr; };
        viewProfile.hideWhenDisabled = true;
        m_actions->Add(viewProfile);
        Action openProfile{"Open in &Browser", [this] {
            if (auto* u = SelectedUser()) OpenUrl(u->htmlUrl);
        }};
        openProfile.enabled = [this] { return SelectedUser() != nullptr; };
        openProfile.hideWhenDisabled = true;
        m_actions->Add(openProfile);
        AddRepoActions(*m_actions, this, [this] { return SelectedRepo(); });
        Sizer()->Add(m_actions->CreateButtons(), 0, wxALL, 10);
        for (wxListBox* list : {m_repoList, m_userList}) {
            m_actions->AttachContextMenu(list);
            m_actions->AttachActivate(list);
        }
        m_repos->OnSelect([this] { m_actions->Update(); });
        m_users->OnSelect([this] { m_actions->Update(); });

        FillSorts();
        ShowListForType();
        m_type->Bind(wxEVT_CHOICE, [this](wxCommandEvent&) { OnTypeChanged(); });
        m_query->Bind(wxEVT_TEXT_ENTER, [this](wxCommandEvent&) { Search(); });
        searchButton->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { Search(); });

        Finish();
        m_actions->Update();
        m_query->SetFocus();
    }

private:
    bool SearchingUsers() const { return m_type->GetSelection() == 1; }

    void FillSorts() {
        m_sort->Clear();
        if (SearchingUsers()) {
            for (const auto& s : kUserSorts) m_sort->Append(s.label);
        } else {
            for (const auto& s : kRepoSorts) m_sort->Append(s.label);
        }
        m_sort->SetSelection(0);
    }

    void ShowListForType() {
        bool users = SearchingUsers();
        m_repoLabel->Show(!users);
        m_repoList->Show(!users);
        m_userLabel->Show(users);
        m_userList->Show(users);
        Panel()->Layout();
        m_actions->Update();
    }

    void OnTypeChanged() {
        FillSorts();
        ShowListForType();
    }

    void Search() {
        std::string query = Trim(ToU8(m_query->GetValue()));
        if (query.empty()) return;
        auto account = app::Current();
        if (!account) return;

        int sortIndex = std::max(0, m_sort->GetSelection());
        if (SearchingUsers()) {
            std::string sort = kUserSorts[sortIndex].value;
            m_users->Load([account, query, sort](int page) { return account->SearchUsersPage(query, sort, page); });
        } else {
            std::string sort = kRepoSorts[sortIndex].value;
            m_repos->Load([account, query, sort](int page) { return account->SearchReposPage(query, sort, page); });
        }
        m_actions->Update();
    }

    const Repository* SelectedRepo() const { return SearchingUsers() ? nullptr : m_repos->Selected(); }
    const UserProfile* SelectedUser() const { return SearchingUsers() ? m_users->Selected() : nullptr; }

    void ViewProfile() {
        if (const UserProfile* u = SelectedUser()) {
            std::string login = u->login;  // the list may change while the profile is open
            ShowUserProfileDialog(this, login);
        }
    }

    wxChoice* m_type;
    wxTextCtrl* m_query;
    wxChoice* m_sort;
    wxStaticText* m_repoLabel;
    wxListBox* m_repoList;
    wxStaticText* m_userLabel;
    wxListBox* m_userList;
    PagedList<Repository>* m_repos;   // owned by m_repoList
    PagedList<UserProfile>* m_users;  // owned by m_userList
    ActionBar* m_actions;             // owned by the panel
};

// --- User profile ---

class UserProfileDialog : public BaseDialog {
public:
    UserProfileDialog(wxWindow* parent, const std::string& username)
        : BaseDialog(parent, "User: " + U8(username), wxSize(900, 650)), m_username(username) {
        m_account = app::Current();
        m_isSelf = m_account && ToLower(m_account->Username()) == ToLower(username);
        wxWindow* p = Panel();

        m_info = new wxTextCtrl(p, wxID_ANY, "Loading...", wxDefaultPosition, wxSize(-1, 150),
                                wxTE_READONLY | wxTE_MULTILINE | wxTE_DONTWRAP);
        AddLabeled("&Profile:", m_info);

        m_repoList = new wxListBox(p, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddLabeled("&Repositories:", m_repoList, 1);
        m_repos = new PagedList<Repository>(m_repoList, "public repositories",
                                            [](const Repository& r) { return U8(r.FormatSingleLine()); });

        // The repository actions come first so Enter views the selected repository;
        // the profile's own actions follow.
        m_actions = new ActionBar(p);
        AddRepoActions(*m_actions, this, [this] { return SelectedRepo(); });
        m_actions->AddSeparator();
        Action follow{"&Follow", [this] { ToggleFollow(); }, true};
        follow.enabled = [this] { return !m_isSelf && m_user && m_followKnown && !m_busy; };
        follow.dynamicLabel = [this] { return m_following ? wxString("&Unfollow") : wxString("&Follow"); };
        follow.hideWhenDisabled = m_isSelf;  // you can't follow yourself
        m_actions->Add(follow);
        Action openProfile{"Open Profile on &GitHub", [this] {
            if (m_user) OpenUrl(m_user->htmlUrl);
        }, true};
        openProfile.enabled = [this] { return m_user.has_value(); };
        m_actions->Add(openProfile);
        Sizer()->Add(m_actions->CreateButtons(), 0, wxALL, 10);
        m_actions->AttachContextMenu(m_repoList);
        m_actions->AttachActivate(m_repoList);

        m_repos->OnSelect([this] { m_actions->Update(); });
        m_repos->OnLoaded([](bool first) {
            if (first) SetStatus("");
        });

        Finish();
        m_actions->Update();
        m_info->SetFocus();
        Load();
    }

private:
    void Load() {
        auto account = m_account;
        if (!account) {
            m_info->SetValue("Not signed in");
            return;
        }
        std::string username = m_username;
        SetStatus("Loading " + U8(username) + "...");
        RunAsync(this,
                 [account, username]() -> std::pair<std::optional<UserProfile>, std::string> {
                     auto user = account->GetUser(username);
                     return {user, user ? "" : GitHubAccount::LastError()};
                 },
                 [this](std::pair<std::optional<UserProfile>, std::string> result) {
                     if (!result.first) {
                         SetStatus("");
                         wxString why = result.second.empty() ? wxString() : "\n\n" + U8(result.second);
                         ShowError(this, "Could not load the user " + U8(m_username) + "." + why);
                         if (IsModal()) EndModal(wxID_CANCEL);
                         return;
                     }
                     ShowUser(*result.first);
                     LoadRepos();
                     LoadFollowing();
                 });
    }

    void LoadRepos() {
        auto account = m_account;
        std::string username = m_username;
        m_repos->Load([account, username](int page) { return account->GetUserReposPage(username, "pushed", page); });
    }

    void LoadFollowing() {
        if (m_isSelf) return;
        auto account = m_account;
        std::string username = m_username;
        RunAsync(this, [account, username] { return account->IsFollowing(username); },
                 [this](bool following) {
                     m_following = following;
                     m_followKnown = true;
                     m_actions->Update();
                 });
    }

    void ShowUser(const UserProfile& user) {
        m_user = user;
        if (!user.name.empty())
            SetTitle("User: " + U8(user.name) + " (@" + U8(user.login) + ")");
        else
            SetTitle("User: @" + U8(user.login));

        std::vector<std::string> lines;
        lines.push_back("Username: " + user.login);
        if (!user.name.empty()) lines.push_back("Name: " + user.name);
        lines.push_back("Type: " + user.type);
        if (!user.bio.empty()) lines.push_back("Bio: " + user.bio);
        if (!user.company.empty()) lines.push_back("Company: " + user.company);
        if (!user.location.empty()) lines.push_back("Location: " + user.location);
        if (!user.email.empty()) lines.push_back("Email: " + user.email);
        if (!user.blog.empty()) lines.push_back("Website: " + user.blog);
        if (!user.twitterUsername.empty()) lines.push_back("Twitter: @" + user.twitterUsername);
        lines.push_back("");
        lines.push_back("Public Repos: " + std::to_string(user.publicRepos) +
                        " | Gists: " + std::to_string(user.publicGists));
        lines.push_back("Followers: " + std::to_string(user.followers) +
                        " | Following: " + std::to_string(user.following));
        if (user.createdAt)
            lines.push_back("Joined: " + FormatLocalTime(user.createdAt, "%Y-%m-%d") + " (" +
                            FormatRelativeTime(user.createdAt) + ")");

#ifdef __WXMSW__
        const char* sep = "\r\n";  // the Windows edit control wants CRLF
#else
        const char* sep = "\n";
#endif
        std::string text;
        for (size_t i = 0; i < lines.size(); i++) {
            if (i) text += sep;
            text += lines[i];
        }
        m_info->SetValue(U8(text));
        m_actions->Update();
    }

    void ToggleFollow() {
        if (m_isSelf || !m_user || m_busy) return;
        auto account = m_account;
        std::string username = m_username;
        bool unfollow = m_following;
        m_busy = true;
        m_actions->Update();
        RunAsync(this,
                 [account, username, unfollow] {
                     return unfollow ? account->UnfollowUser(username) : account->FollowUser(username);
                 },
                 [this, unfollow](bool ok) {
                     m_busy = false;
                     if (ok) m_following = !unfollow;
                     m_actions->Update();
                     if (!ok)
                         ShowError(this, unfollow ? "Failed to unfollow user." : "Failed to follow user.");
                     else
                         ShowInfo(this, (unfollow ? "Unfollowed " : "Now following ") + U8(m_username),
                                  "Success");
                 });
    }

    const Repository* SelectedRepo() const { return m_repos->Selected(); }

    std::string m_username;
    std::shared_ptr<GitHubAccount> m_account;
    bool m_isSelf = false;
    std::optional<UserProfile> m_user;
    bool m_following = false;
    bool m_followKnown = false;  // until IsFollowing answers, Follow could be wrong
    bool m_busy = false;
    wxTextCtrl* m_info;
    wxListBox* m_repoList;
    PagedList<Repository>* m_repos;  // owned by m_repoList
    ActionBar* m_actions;            // owned by the panel
};

}  // namespace

void ShowSearchDialog(wxWindow* parent) {
    ShowModalDialog<SearchDialog>(parent);
}

void ShowUserProfileDialog(wxWindow* parent, const std::string& username) {
    if (username.empty()) return;
    ShowModalDialog<UserProfileDialog>(parent, username);
}
