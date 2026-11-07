// Lists of repositories and people around one repository: the shared repository
// actions (GUI/repo_actions.py), forks (GUI/forks.py) and stargazers (GUI/stargazers.py).

#include "ui/dialogs.h"
#include "ui/paged_list.h"
#include "ui/ui_common.h"

#include "core/app.h"
#include "core/util.h"

#include <memory>
#include <string>
#include <utility>
#include <vector>

void AddRepoActions(ActionBar& bar, wxWindow* parent, std::function<const Repository*()> getRepo) {
    // Each action works on a copy taken when it runs, so a list refreshing
    // underneath an open dialog can't pull the repository away.
    auto with = [getRepo](std::function<void(const Repository&)> fn) {
        return [getRepo, fn] {
            if (const Repository* repo = getRepo()) {
                Repository copy = *repo;
                fn(copy);
            }
        };
    };
    auto hasRepo = [getRepo] { return getRepo() != nullptr; };
    auto add = [&](const wxString& label, std::function<void(const Repository&)> fn, bool primary = false) {
        Action action{label, with(std::move(fn)), primary};
        action.enabled = hasRepo;
        return bar.Add(std::move(action));
    };

    // Access keys avoid the letters the search and profile dialogs use for their own
    // controls (as in the Python), and shortcuts match the main window's Actions menu.
    add("&View Repository", [parent](const Repository& r) { ShowRepoDialog(parent, r); }, true)
        .Shortcut(WXK_RETURN);
    add("Open in &Browser", [](const Repository& r) { OpenUrl(r.htmlUrl); }).Shortcut('O', wxMOD_CONTROL);
    add("Copy &URL", [](const Repository& r) { CopyToClipboard(U8(r.htmlUrl)); });
    add("Copy Clo&ne URL", [](const Repository& r) { CopyToClipboard(U8("https://github.com/" + r.fullName + ".git")); })
        .Shortcut('C', wxMOD_CONTROL | wxMOD_SHIFT);
    bar.AddSeparator();
    add("View Fi&les", [parent](const Repository& r) { ShowFilesDialog(parent, r); })
        .Shortcut('F', wxMOD_CONTROL | wxMOD_SHIFT);
    add("View &Issues", [parent](const Repository& r) { ShowIssuesDialog(parent, r); }).Shortcut('I', wxMOD_CONTROL);
    add("View Pull Reques&ts", [parent](const Repository& r) { ShowPullRequestsDialog(parent, r); })
        .Shortcut('P', wxMOD_CONTROL);
    add("View Co&mmits", [parent](const Repository& r) { ShowCommitsDialog(parent, r); }).Shortcut('M', wxMOD_CONTROL);
    add("View &Actions", [parent](const Repository& r) { ShowActionsDialog(parent, r); }).Shortcut('G', wxMOD_CONTROL);
    add("View R&eleases", [parent](const Repository& r) { ShowReleasesDialog(parent, r); })
        .Shortcut('R', wxMOD_CONTROL);
    add("View For&ks", [parent](const Repository& r) { ShowForksDialog(parent, r); });
    add("View Starga&zers", [parent](const Repository& r) { ShowStargazersDialog(parent, r); });
    add("View O&wner", [parent](const Repository& r) { ShowUserProfileDialog(parent, r.owner); });

    Action upstream{"View U&pstream", with([parent](const Repository& r) { OpenUpstreamRepo(parent, r); })};
    upstream.enabled = [getRepo] {
        const Repository* repo = getRepo();
        return repo && repo->isFork;
    };
    upstream.hideWhenDisabled = true;
    bar.Add(std::move(upstream));
}

namespace {

// Both lists load a page at a time (PagedList): the first page shows at once and
// the next is fetched when the selection reaches the end.

// --- Forks ---

class ForksDialog : public BaseDialog {
public:
    ForksDialog(wxWindow* parent, const Repository& repo)
        : BaseDialog(parent, "Forks of " + U8(repo.fullName), wxSize(700, 500)), m_repo(repo) {
        m_sizer->Add(new wxStaticText(m_panel, wxID_ANY,
                                      wxString::Format("Repository has %lld fork(s)", repo.forks)),
                     0, wxALL, 10);
        m_list = new wxListBox(m_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddLabeled("F&orks", m_list, 1);
        m_forks = new PagedList<Repository>(m_list, "forks", [](const Repository& fork) {
            return U8(fork.fullName + " - " + std::to_string(fork.stars) + " stars | Pushed " +
                      FormatRelativeTime(fork.pushedAt));
        });
        m_forks->FocusWhenLoaded();

        m_actions = new ActionBar(m_panel);  // owned by the panel
        AddRepoActions(*m_actions, this, [this] { return m_forks->Selected(); });
        m_actions->AddSeparator();
        Action refresh{"&Refresh", [this] { m_forks->Refresh(); }, true};
        refresh.enabled = [this] { return m_forks->HasLoaded() && !m_forks->IsLoading(); };
        m_actions->Add(std::move(refresh)).Shortcut(WXK_F5);
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER, 5);
        m_actions->AttachContextMenu(m_list);
        m_actions->AttachActivate(m_list);
        m_forks->OnSelect([this] { m_actions->Update(); });
        m_forks->OnLoaded([this](bool) { m_actions->Update(); });

        Finish();
        m_list->SetFocus();

        auto account = app::Current();
        if (!account) {
            SetListItems(m_list, {"Not signed in"});
            return;
        }
        std::string owner = repo.owner, name = repo.name;
        m_forks->Load([account, owner, name](int page) { return account->GetForksPage(owner, name, "newest", page); });
    }

private:
    Repository m_repo;
    wxListBox* m_list;
    PagedList<Repository>* m_forks;  // owned by m_list
    ActionBar* m_actions;
};

// --- Stargazers ---

class StargazersDialog : public BaseDialog {
public:
    StargazersDialog(wxWindow* parent, const Repository& repo)
        : BaseDialog(parent, "Stargazers of " + U8(repo.fullName), wxSize(700, 500)), m_repo(repo) {
        m_sizer->Add(new wxStaticText(m_panel, wxID_ANY,
                                      wxString::Format("Repository has %lld star(s)", repo.stars)),
                     0, wxALL, 10);
        m_list = new wxListBox(m_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddLabeled("&Stargazers", m_list, 1);
        m_stargazers = new PagedList<Stargazer>(m_list, "stargazers",
                                                [](const Stargazer& s) { return U8(s.FormatDisplay()); });
        m_stargazers->FocusWhenLoaded();

        m_actions = new ActionBar(m_panel);  // owned by the panel
        Action view{"&View Profile", [this] {
                        if (const Stargazer* s = m_stargazers->Selected()) ShowUserProfileDialog(this, s->login);
                    }, true};
        view.enabled = [this] { return m_stargazers->Selected() != nullptr; };
        m_actions->Add(std::move(view)).Shortcut(WXK_RETURN);
        Action open{"Open in &Browser", [this] {
                        if (const Stargazer* s = m_stargazers->Selected()) OpenUrl(s->htmlUrl);
                    }, true};
        open.enabled = [this] { return m_stargazers->Selected() != nullptr; };
        m_actions->Add(std::move(open)).Shortcut('O', wxMOD_CONTROL);
        m_sizer->Add(m_actions->CreateButtons(), 0, wxALL | wxALIGN_CENTER, 5);
        m_actions->AttachContextMenu(m_list);
        m_actions->AttachActivate(m_list);
        m_stargazers->OnSelect([this] { m_actions->Update(); });

        Finish();
        m_list->SetFocus();

        auto account = app::Current();
        if (!account) {
            SetListItems(m_list, {"Not signed in"});
            return;
        }
        std::string owner = repo.owner, name = repo.name;
        m_stargazers->Load([account, owner, name](int page) {
            auto result = account->GetStargazers(owner, name, page, kPageSize);
            return Page<Stargazer>{std::move(result.first), result.second};
        });
    }

private:
    Repository m_repo;
    wxListBox* m_list;
    PagedList<Stargazer>* m_stargazers;  // owned by m_list
    ActionBar* m_actions;
};

}  // namespace

void ShowForksDialog(wxWindow* parent, const Repository& repo) {
    ShowModalDialog<ForksDialog>(parent, repo);
}

void ShowStargazersDialog(wxWindow* parent, const Repository& repo) {
    ShowModalDialog<StargazersDialog>(parent, repo);
}
