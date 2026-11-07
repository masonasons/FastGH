// The main window: the activity feed, your repositories, starred, watched,
// following and notifications, each a list in a tab.

#include "ui/main_frame.h"
#include "ui/dialogs.h"
#include "ui/paged_list.h"
#include "ui/ui_common.h"

#include "core/app.h"
#include "core/feed_filter.h"
#include "platform/platform.h"
#include "version.h"

#include <wx/notebook.h>
#include <wx/notifmsg.h>
#include <wx/taskbar.h>

#include <map>
#include <optional>
#include <regex>
#include <set>
#include <tuple>

namespace {

enum Tab { kFeed, kRepos, kStarred, kWatched, kFollowing, kNotifications, kPageCount };

enum MenuId {
    ID_ACCOUNTS = wxID_HIGHEST + 1,
    ID_HIDE,
    ID_REFRESH,
    ID_PAGE_FIRST,  // + Tab
    ID_REPO_SYNC = ID_PAGE_FIRST + kPageCount,
    ID_MARK_ALL_READ,
    ID_SEARCH,
    ID_GO_TO_REPO,
    ID_VIEW_USER,
    ID_VIEW_REPO,
    ID_OPEN_URL,
    ID_COPY_URL,
    ID_COPY_CLONE,
    ID_FILES,
    ID_ISSUES,
    ID_PRS,
    ID_COMMITS,
    ID_ACTIONS,
    ID_RELEASES,
    ID_CHECK_UPDATES,
};

using IssueKey = std::tuple<std::string, std::string, int>;

class MainFrame;
MainFrame* g_frame = nullptr;

#ifdef __WXMSW__
class TrayIcon : public wxTaskBarIcon {
public:
    explicit TrayIcon(MainFrame* frame);
    wxMenu* CreatePopupMenu() override;
private:
    MainFrame* m_frame;
};
#endif

class MainFrame : public wxFrame {
public:
    MainFrame();
    ~MainFrame() override;

    void RefreshAll();
    void RenderFeed();
    void ApplyOptions();
    void AccountChanged();
    bool SetGlobalHotkey(const std::string& spec);
    void ShowWindow();
    void HideWindow();
    void ToggleWindow();
    void Notify(const wxString& title, const wxString& message);
    void Exit();

private:
    void BuildMenus();
    void BuildPages();
    wxListBox* AddPage(const wxString& title);
    void OnMenu(wxCommandEvent& event);
    void OnClose(wxCloseEvent& event);

    // Points each tab's list at the current account (page 1 again).
    void LoadAll();
    void LoadNotifications() { m_notifPages->Refresh(); }
    void UpdateStatus();
    void UpdateAccountLabel();

    // Feed rows whose issue or pull request title GitHub left out are filled in
    // a few at a time.
    std::optional<std::pair<bool, IssueKey>> FeedTitleKey(const Event& e) const;
    bool ApplyCachedTitles();
    void StartTitleBackfill();

    void NotifyNewFeed(bool first);
    void NotifyNewNotifications(bool first);
    void NotifyUpdatedRepos(const std::vector<Repository>& repos, std::map<long long, std::time_t>& last,
                            bool& first, bool notify, const char* what, const char* pref);

    int CurrentPage() const { return m_notebook->GetSelection(); }
    const Repository* SelectedRepo() const;
    const Event* SelectedEvent() const;
    const UserProfile* SelectedUser() const;
    const Notification* SelectedNotification() const;
    std::string SelectedUsername() const;
    void FocusCurrentList();

    void OpenFeedEvent();
    void OpenNotification();
    // Fetches the repository, then runs `then` with it.
    void WithRepo(const std::string& owner, const std::string& name, std::function<void(const Repository&)> then);
    void GoToRepo();
    void ViewUser();
    void UnfollowSelected();
    void NotificationAction(const char* verb, std::function<bool(GitHubAccount&, const std::string&)> call);
    void MarkAllRead();
    void RunRepoSync(bool manual);
    void RunRepoAction(int id);

    wxStaticText* m_accountLabel = nullptr;
    wxNotebook* m_notebook = nullptr;
    wxListBox* m_lists[kPageCount] = {};

    // Each tab loads a page at a time (ui/paged_list.h); they belong to their lists.
    PagedList<Event>* m_feedPages = nullptr;
    PagedList<Repository>* m_repoPages[kPageCount] = {};  // kRepos, kStarred, kWatched
    PagedList<UserProfile>* m_followingPages = nullptr;
    PagedList<Notification>* m_notifPages = nullptr;

    std::map<IssueKey, std::string> m_prTitles, m_issueTitles;  // "" caches a miss
    bool m_backfillRunning = false;

    std::optional<std::set<std::string>> m_lastFeedIds, m_lastNotificationIds;
    std::map<long long, std::time_t> m_lastStarred, m_lastWatched;
    bool m_firstStarred = true, m_firstWatched = true;

    wxTimer m_refreshTimer, m_syncTimer;
    bool m_syncRunning = false;
    unsigned m_generation = 0;  // bumped on account change; stale loads are dropped
#ifdef __WXMSW__
    std::unique_ptr<TrayIcon> m_tray;
#endif
};

// --- Construction ---

MainFrame::MainFrame() : wxFrame(nullptr, wxID_ANY, APP_NAME, wxDefaultPosition, wxSize(900, 600)) {
    g_frame = this;
#ifdef __WXMSW__
    SetIcon(wxICON(appicon));
#endif
    BuildMenus();
    BuildPages();
    CreateStatusBar();
    SetStatusText("Ready");
    Centre();

    Bind(wxEVT_MENU, &MainFrame::OnMenu, this);
    Bind(wxEVT_CLOSE_WINDOW, &MainFrame::OnClose, this);
    m_refreshTimer.Bind(wxEVT_TIMER, [this](wxTimerEvent&) { RefreshAll(); });
    m_syncTimer.Bind(wxEVT_TIMER, [this](wxTimerEvent&) { RunRepoSync(false); });

#ifdef __WXMSW__
    m_tray = std::make_unique<TrayIcon>(this);
#endif
    platform::SetMenuBarActions({[this] { ShowWindow(); }, [this] { RefreshAll(); },
                                 [this] { CallAfter([this] { Exit(); }); }});
    ApplyOptions();
    SetGlobalHotkey(app::Prefs().GetString("global_hotkey"));
}

MainFrame::~MainFrame() {
    platform::UnregisterGlobalHotkey(this);
    if (g_frame == this) g_frame = nullptr;
}

void MainFrame::BuildMenus() {
#ifdef __WXOSX__
    // wxWidgets' automatic Window menu takes Cmd+M (Minimize), which is View Commits here.
    wxMenuBar::SetAutoWindowMenu(false);
#endif
    auto* bar = new wxMenuBar();
#ifdef __WXOSX__
    // On macOS, Options and Quit live in the application menu (wxWidgets moves
    // them there), Cmd+H is the system's Hide, and an Edit menu makes Cmd+C,
    // Cmd+V and Cmd+A work in every text field. Keys that the Edit menu, the
    // system or the lists own (Cmd+A, Cmd+C, Return) aren't menu shortcuts.
    static constexpr bool mac = true;  // static: MSVC won't let a lambda use a local constexpr uncaptured
#else
    static constexpr bool mac = false;
#endif
    // Shown in the menu but not bound, where binding it would steal the key.
    auto label = [](const wxString& text, const wxString& key, bool macUnbound = false) {
        if (key.empty()) return text;
        return mac && macUnbound ? text + " (" + key + ")" : text + "\t" + key;
    };

    auto* appMenu = new wxMenu();
    appMenu->Append(ID_ACCOUNTS, mac ? label("&Accounts...", "Ctrl+Shift+A") : label("&Accounts...", "Ctrl+A"));
    appMenu->Append(wxID_PREFERENCES, label("&Options...", "Ctrl+,"));
    if (!mac) {
        appMenu->AppendSeparator();
        appMenu->Append(ID_HIDE, label("&Hide Window", "Ctrl+H"));
    } else {
        appMenu->Append(ID_HIDE, "&Close Window\tCtrl+W");
    }
    appMenu->AppendSeparator();
    appMenu->Append(wxID_EXIT, mac ? wxString("E&xit") : label("E&xit", "Alt+X"));
    bar->Append(appMenu, mac ? "&File" : "&Application");

    if (mac) {
        auto* edit = new wxMenu();
        edit->Append(wxID_UNDO, "&Undo\tCtrl+Z");
        edit->Append(wxID_REDO, "&Redo\tCtrl+Shift+Z");
        edit->AppendSeparator();
        edit->Append(wxID_CUT, "Cu&t\tCtrl+X");
        edit->Append(wxID_COPY, "&Copy\tCtrl+C");
        edit->Append(wxID_PASTE, "&Paste\tCtrl+V");
        edit->Append(wxID_SELECTALL, "Select &All\tCtrl+A");
        bar->Append(edit, "&Edit");
    }

    auto* view = new wxMenu();
    view->Append(ID_REFRESH, label("&Refresh", "F5"));
    view->AppendSeparator();
    const char* pages[kPageCount] = {"Activity &Feed", "Your &Repositories", "&Starred", "&Watched",
                                     "F&ollowing", "&Notifications"};
    for (int i = 0; i < kPageCount; i++)
        view->Append(ID_PAGE_FIRST + i, label(pages[i], wxString::Format("Ctrl+%d", i + 1)));
    view->AppendSeparator();
    view->Append(ID_REPO_SYNC, label("Run Repo S&ync Now", "Ctrl+Shift+Y"));
    view->Append(ID_MARK_ALL_READ, label("&Mark All Notifications Read", "Ctrl+Shift+R"));
    bar->Append(view, "&View");

    auto* search = new wxMenu();
    search->Append(ID_SEARCH, label("&Search GitHub...", "Ctrl+F"));
    search->AppendSeparator();
    search->Append(ID_GO_TO_REPO, label("&Go to Repository...", "Ctrl+L"));
    search->Append(ID_VIEW_USER, label("View &User Profile...", "Ctrl+U"));
    bar->Append(search, "&Search");

    auto* actions = new wxMenu();
    actions->Append(ID_VIEW_REPO, label("&View Repository Info", "Return", true));
    actions->Append(ID_OPEN_URL, label("&Open in Browser", "Ctrl+O"));
    actions->Append(ID_COPY_URL, label("&Copy URL", "Ctrl+C", true));
    actions->Append(ID_COPY_CLONE, label("Copy C&lone URL", "Ctrl+Shift+C"));
    actions->AppendSeparator();
    actions->Append(ID_FILES, label("View &Files", "Ctrl+Shift+F"));
    actions->Append(ID_ISSUES, label("View &Issues", "Ctrl+I"));
    actions->Append(ID_PRS, label("View &Pull Requests", "Ctrl+P"));
    actions->Append(ID_COMMITS, label("View Co&mmits", "Ctrl+M"));
    actions->Append(ID_ACTIONS, label("View &Actions", "Ctrl+G"));
    actions->Append(ID_RELEASES, label("View R&eleases", "Ctrl+R"));
    bar->Append(actions, "A&ctions");

    auto* help = new wxMenu();
    help->Append(ID_CHECK_UPDATES, "Check for &Updates...");
    help->Append(wxID_ABOUT, "&About FastGH");
    bar->Append(help, "&Help");

    SetMenuBar(bar);
}

wxListBox* MainFrame::AddPage(const wxString& title) {
    auto* panel = new wxPanel(m_notebook);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    auto* list = new wxListBox(panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
    list->SetName(title);
    // No visible label (the tab names it), so give the list its name directly.
    list->SetAccessibleName(title);
    sizer->Add(list, 1, wxEXPAND);
    panel->SetSizer(sizer);
    m_notebook->AddPage(panel, title);
    return list;
}

void MainFrame::BuildPages() {
    auto* panel = new wxPanel(this);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    m_accountLabel = new wxStaticText(panel, wxID_ANY, "");
    sizer->Add(m_accountLabel, 0, wxALL, 5);
    m_notebook = new wxNotebook(panel, wxID_ANY);
    const char* titles[kPageCount] = {"Activity Feed", "Your Repositories", "Starred", "Watched", "Following",
                                      "Notifications"};
    for (int i = 0; i < kPageCount; i++) {
        m_lists[i] = AddPage(titles[i]);
    }
    sizer->Add(m_notebook, 1, wxEXPAND | wxALL, 5);
    panel->SetSizer(sizer);

    m_feedPages = new PagedList<Event>(m_lists[kFeed], "activity", [](const Event& e) { return U8(e.FormatDisplay()); });
    m_feedPages->OnLoaded([this](bool first) {
        NotifyNewFeed(first);
        if (ApplyCachedTitles()) m_feedPages->Rerender();
        UpdateStatus();
        StartTitleBackfill();
    });
    const char* repoNouns[kPageCount] = {"", "repositories", "starred repositories", "watched repositories"};
    for (int page : {kRepos, kStarred, kWatched}) {
        m_repoPages[page] = new PagedList<Repository>(m_lists[page], repoNouns[page],
                                                      [](const Repository& r) { return U8(r.FormatSingleLine()); });
        m_repoPages[page]->OnLoaded([this, page](bool first) {
            if (page == kStarred)
                NotifyUpdatedRepos(m_repoPages[page]->AllItems(), m_lastStarred, m_firstStarred, first, "starred",
                                   "notify_starred");
            if (page == kWatched)
                NotifyUpdatedRepos(m_repoPages[page]->AllItems(), m_lastWatched, m_firstWatched, first, "watched",
                                   "notify_watched");
            UpdateStatus();
        });
    }
    m_followingPages = new PagedList<UserProfile>(m_lists[kFollowing], "people followed",
                                                  [](const UserProfile& u) { return U8(u.FormatDisplay()); });
    m_followingPages->OnLoaded([this](bool) { UpdateStatus(); });
    m_notifPages = new PagedList<Notification>(m_lists[kNotifications], "notifications",
                                               [](const Notification& n) { return U8(n.FormatDisplay()); });
    m_notifPages->OnLoaded([this](bool first) {
        NotifyNewNotifications(first);
        UpdateStatus();
    });

    // Each list's context menu and Enter, as actions (ui_common.h).
    auto* feedBar = new ActionBar(m_lists[kFeed]->GetParent());
    feedBar->Add({"&Open", [this] { OpenFeedEvent(); }, true, [this] { return SelectedEvent() != nullptr; }});
    feedBar->Add({"Open in &Browser",
                  [this] {
                      if (auto* e = SelectedEvent()) OpenUrl(e->GetWebUrl());
                  },
                  false, [this] { return SelectedEvent() != nullptr; }});
    feedBar->AddSeparator();
    feedBar->Add({"View &Repository",
                  [this] {
                      if (auto* e = SelectedEvent()) {
                          auto parts = Split(e->repo.name, '/');
                          if (parts.size() == 2) OpenRepo(this, parts[0], parts[1]);
                      }
                  },
                  false, [this] { return SelectedEvent() != nullptr; }});
    feedBar->Add({"View &User Profile",
                  [this] {
                      if (auto* e = SelectedEvent()) ShowUserProfileDialog(this, e->actor.login);
                  },
                  false, [this] { return SelectedEvent() != nullptr; }});
    feedBar->AttachContextMenu(m_lists[kFeed]);
    feedBar->AttachActivate(m_lists[kFeed]);

    for (int page : {kRepos, kStarred, kWatched}) {
        auto* bar = new ActionBar(m_lists[page]->GetParent());
        AddRepoActions(*bar, this, [this] { return SelectedRepo(); });
        bar->AttachContextMenu(m_lists[page]);
        bar->AttachActivate(m_lists[page]);
    }

    auto* userBar = new ActionBar(m_lists[kFollowing]->GetParent());
    auto hasUser = [this] { return SelectedUser() != nullptr; };
    userBar->Add({"&View Profile",
                  [this] {
                      if (auto* u = SelectedUser()) ShowUserProfileDialog(this, u->login);
                  },
                  true, hasUser});
    userBar->Add({"&Open in Browser",
                  [this] {
                      if (auto* u = SelectedUser()) OpenUrl(u->htmlUrl);
                  },
                  false, hasUser});
    userBar->AddSeparator();
    userBar->Add({"&Unfollow", [this] { UnfollowSelected(); }, false, hasUser});
    userBar->AttachContextMenu(m_lists[kFollowing]);
    userBar->AttachActivate(m_lists[kFollowing]);

    auto* notifBar = new ActionBar(m_lists[kNotifications]->GetParent());
    auto hasNotif = [this] { return SelectedNotification() != nullptr; };
    notifBar->Add({"&Open", [this] { OpenNotification(); }, true, hasNotif});
    notifBar->Add({"Open in &Browser",
                   [this] {
                       if (auto* n = SelectedNotification()) OpenUrl(n->GetWebUrl());
                   },
                   false, hasNotif});
    notifBar->AddSeparator();
    Action markRead{"Mark as &Read",
                    [this] {
                        NotificationAction("mark notification as read",
                                           [](GitHubAccount& a, const std::string& id) { return a.MarkThreadRead(id); });
                    },
                    false, [this] {
                        auto* n = SelectedNotification();
                        return n && n->unread;
                    }};
    markRead.hideWhenDisabled = true;
    notifBar->Add(markRead);
    notifBar->Add({"Mark as &Done",
                   [this] {
                       NotificationAction("mark notification as done",
                                          [](GitHubAccount& a, const std::string& id) { return a.MarkThreadDone(id); });
                   },
                   false, hasNotif})
        .Shortcut(WXK_DELETE);
    notifBar->Add({"&Mute Thread",
                   [this] {
                       NotificationAction("mute thread",
                                          [](GitHubAccount& a, const std::string& id) { return a.MuteThread(id); });
                   },
                   false, hasNotif});
    notifBar->AddSeparator();
    notifBar->Add({"View Re&pository",
                   [this] {
                       if (auto* n = SelectedNotification()) OpenRepo(this, n->repositoryOwner, n->repositoryName);
                   },
                   false, hasNotif});
    notifBar->AddSeparator();
    notifBar->Add({"Mark &All as Read", [this] { MarkAllRead(); }});
    notifBar->AttachContextMenu(m_lists[kNotifications]);
    notifBar->AttachActivate(m_lists[kNotifications]);

#ifdef __WXOSX__
    // Cmd+C copies the selected repository's URL, as Ctrl+C does elsewhere (the
    // Edit menu's Copy does nothing in a list).
    for (int page : {kRepos, kStarred, kWatched}) {
        m_lists[page]->Bind(wxEVT_CHAR_HOOK, [this](wxKeyEvent& event) {
            if (event.GetModifiers() == wxMOD_CONTROL && event.GetKeyCode() == 'C') {
                RunRepoAction(ID_COPY_URL);
                return;
            }
            event.Skip();
        });
    }
#endif
    m_notebook->Bind(wxEVT_NOTEBOOK_PAGE_CHANGED, [this](wxBookCtrlEvent& event) {
        event.Skip();
        CallAfter([this] { FocusCurrentList(); });
    });
}

// --- Menus and closing ---

void MainFrame::OnMenu(wxCommandEvent& event) {
    int id = event.GetId();
    if (id >= ID_PAGE_FIRST && id < ID_PAGE_FIRST + kPageCount) {
        m_notebook->SetSelection(id - ID_PAGE_FIRST);
        FocusCurrentList();
        return;
    }
    wxWindow* owner = GetActiveOwner();
    switch (id) {
        case ID_ACCOUNTS: ShowAccountsDialog(owner); break;
        case wxID_PREFERENCES: ShowOptionsDialog(owner); break;
        case ID_HIDE: HideWindow(); break;
        case wxID_EXIT: Exit(); break;
        case ID_REFRESH: RefreshAll(); break;
        case ID_REPO_SYNC: RunRepoSync(true); break;
        case ID_MARK_ALL_READ: MarkAllRead(); break;
        case ID_SEARCH: ShowSearchDialog(owner); break;
        case ID_GO_TO_REPO: GoToRepo(); break;
        case ID_VIEW_USER: ViewUser(); break;
        case ID_CHECK_UPDATES: CheckForUpdates(false); break;
        case wxID_ABOUT:
            ShowInfo(owner, wxString::Format("%s %s\nA fast, accessible GitHub client.", APP_NAME, APP_VERSION),
                     "About FastGH");
            break;
        default:
            if (id >= ID_VIEW_REPO && id <= ID_RELEASES) RunRepoAction(id);
            else event.Skip();
    }
}

void MainFrame::RunRepoAction(int id) {
    const Repository* selected = SelectedRepo();
    if (!selected) {
        SetStatus("Select a repository in Your Repositories, Starred or Watched first.");
        return;
    }
    Repository repo = *selected;
    wxWindow* owner = GetActiveOwner();
    switch (id) {
        case ID_VIEW_REPO: ShowRepoDialog(owner, repo); break;
        case ID_OPEN_URL: OpenUrl(repo.htmlUrl); break;
        case ID_COPY_URL: CopyToClipboard(U8(repo.htmlUrl)); break;
        case ID_COPY_CLONE: CopyToClipboard(U8("https://github.com/" + repo.fullName + ".git")); break;
        case ID_FILES: ShowFilesDialog(owner, repo); break;
        case ID_ISSUES: ShowIssuesDialog(owner, repo); break;
        case ID_PRS: ShowPullRequestsDialog(owner, repo); break;
        case ID_COMMITS: ShowCommitsDialog(owner, repo); break;
        case ID_ACTIONS: ShowActionsDialog(owner, repo); break;
        case ID_RELEASES: ShowReleasesDialog(owner, repo); break;
    }
}

void MainFrame::OnClose(wxCloseEvent& event) {
    // Closing the window keeps FastGH running: hidden to the tray on Windows, and
    // on macOS hidden like any Mac app whose window is closed (the Dock icon
    // brings it back; Quit ends it). Only a forced close (shutdown) exits.
    if (event.CanVeto()) {
        event.Veto();
        HideWindow();
        return;
    }
    Exit();
}

void MainFrame::Exit() {
    platform::UnregisterGlobalHotkey(this);
    m_refreshTimer.Stop();
    m_syncTimer.Stop();
#ifdef __WXMSW__
    if (m_tray) m_tray->RemoveIcon();
    m_tray.reset();
#endif
    Destroy();
}

// --- Showing and hiding ---

void MainFrame::ShowWindow() {
    app::Prefs().Set("window_shown", true);
    platform::ShowApp(this);
    FocusCurrentList();
}

void MainFrame::HideWindow() {
#ifndef __WXOSX__
    // On macOS FastGH always comes back with its window at the next start.
    app::Prefs().Set("window_shown", false);
#endif
    platform::HideApp(this);
}

void MainFrame::ToggleWindow() {
    if (platform::IsAppFrontmost(this)) HideWindow();
    else ShowWindow();
}

void MainFrame::FocusCurrentList() {
    int page = CurrentPage();
    if (page >= 0 && page < kPageCount) m_lists[page]->SetFocus();
}

bool MainFrame::SetGlobalHotkey(const std::string& spec) {
    platform::UnregisterGlobalHotkey(this);
    if (Trim(spec).empty()) return true;
    int mods = 0, key = 0;
    for (std::string part : Split(ToLower(spec), '+')) {
        part = Trim(part);
        if (part == "control" || part == "ctrl" || part == "command" || part == "cmd") mods |= wxMOD_CONTROL;
        else if (part == "alt" || part == "option") mods |= wxMOD_ALT;
        else if (part == "shift") mods |= wxMOD_SHIFT;
        else if (part == "win" || part == "windows") mods |= wxMOD_WIN;
        else if (part.size() == 1) key = std::toupper(static_cast<unsigned char>(part[0]));
        else if (part[0] == 'f' && part.size() <= 3 && std::isdigit(static_cast<unsigned char>(part[1])))
            key = WXK_F1 + std::stoi(part.substr(1)) - 1;
        else if (part == "space") key = WXK_SPACE;
        else if (part == "home") key = WXK_HOME;
        else if (part == "end") key = WXK_END;
        else return false;
    }
    if (!key) return false;
    return platform::RegisterGlobalHotkey(this, mods, key, [this] { ToggleWindow(); });
}

void MainFrame::Notify(const wxString& title, const wxString& message) {
    wxNotificationMessage note(title, message, this);
    note.Show(5);
}

void MainFrame::ApplyOptions() {
    Config& prefs = app::Prefs();
    platform::ApplyAppearance(prefs.GetString("dark_mode", "off"));
    int refresh = prefs.GetInt("auto_refresh_interval", 0);
    if (refresh > 0) m_refreshTimer.Start(refresh * 60 * 1000);
    else m_refreshTimer.Stop();
    int sync = prefs.GetInt("repo_sync_interval_minutes", 0);
    if (prefs.GetBool("repo_sync_enabled", false) && sync > 0) m_syncTimer.Start(sync * 60 * 1000);
    else m_syncTimer.Stop();
}

// --- Loading ---

void MainFrame::UpdateAccountLabel() {
    auto account = app::Current();
    if (!account) {
        m_accountLabel->SetLabel("No account");
        return;
    }
    std::string name = account->DisplayName();
    m_accountLabel->SetLabel(name.empty() ? wxString("Signed in") : "Logged in as: " + U8(name));
}

void MainFrame::AccountChanged() {
    m_generation++;
    m_prTitles.clear();
    m_issueTitles.clear();
    m_lastFeedIds.reset();
    m_lastNotificationIds.reset();
    m_lastStarred.clear();
    m_lastWatched.clear();
    m_firstStarred = m_firstWatched = true;
    LoadAll();
    UpdateAccountLabel();
}

void MainFrame::LoadAll() {
    auto a = app::Current();
    if (!a) return;
    m_feedPages->Load([a](int page) { return a->GetReceivedEventsPage(page); });
    RenderFeed();  // sets the feed filter for this account
    m_repoPages[kRepos]->Load([a](int page) { return a->GetReposPage(page); });
    m_repoPages[kStarred]->Load([a](int page) { return a->GetStarredPage(page); });
    m_repoPages[kWatched]->Load([a](int page) { return a->GetWatchedPage(page); });
    m_followingPages->Load([a](int page) { return a->GetFollowingPage(page); });
    m_notifPages->Load([a](int page) { return a->GetNotificationsPage(page); });
}

void MainFrame::RefreshAll() {
    auto account = app::Current();
    if (!account) return;
    UpdateAccountLabel();
    if (account->Username().empty()) {
        RunAsync(this, [account] { return account->Verify(); },
                 [this](GitHubAccount::VerifyResult) { UpdateAccountLabel(); });
    }
    if (!m_feedPages->HasLoaded() && !m_feedPages->IsLoading()) {
        LoadAll();
        return;
    }
    // Every tab again at once, as far down as each has been read; places are kept.
    SetStatus("Refreshing...");
    m_feedPages->Refresh();
    for (int page : {kRepos, kStarred, kWatched}) m_repoPages[page]->Refresh();
    m_followingPages->Refresh();
    m_notifPages->Refresh();
}

void MainFrame::RenderFeed() {
    auto account = app::Current();
    if (!account) return;
    auto visible = feedfilter::LoadVisibleTypes(account->Prefs());
    auto muted = feedfilter::LoadMutedRepos(account->Prefs());
    auto users = feedfilter::LoadUserFilters(account->Prefs());
    m_feedPages->SetFilter([visible, muted, users](const Event& e) {
        return !feedfilter::FilterFeed({e}, visible, muted, users).empty();
    });
}

void MainFrame::UpdateStatus() {
    int unread = 0;
    for (const auto& n : m_notifPages->Items()) unread += n.unread ? 1 : 0;
    platform::SetBadgeCount(unread);
    auto count = [](size_t n, bool more) { return wxString::Format(more ? "%zu+" : "%zu", n); };
    auto* r = m_repoPages[kRepos];
    auto* st = m_repoPages[kStarred];
    auto* w = m_repoPages[kWatched];
    SetStatusText("Repos: " + count(r->Items().size(), r->HasMore()) +
                  " | Starred: " + count(st->Items().size(), st->HasMore()) +
                  " | Watched: " + count(w->Items().size(), w->HasMore()) +
                  " | Following: " + count(m_followingPages->Items().size(), m_followingPages->HasMore()) +
                  wxString::Format(" | Notifications: %d", unread) + (m_notifPages->HasMore() ? "+" : ""));
}

// --- Feed title backfill ---

std::optional<std::pair<bool, IssueKey>> MainFrame::FeedTitleKey(const Event& e) const {
    static const std::set<std::string> prTypes = {"PullRequestEvent", "PullRequestReviewEvent",
                                                  "PullRequestReviewCommentEvent", "PullRequestReviewThreadEvent"};
    bool isPr = prTypes.count(e.type) > 0;
    if (!isPr && e.type != "IssuesEvent" && e.type != "IssueCommentEvent") return std::nullopt;
    const char* field = isPr ? "pull_request" : "issue";
    if (!e.payload.contains(field) || !e.payload[field].is_object()) return std::nullopt;
    const json& item = e.payload[field];
    int number = 0;
    if (item.contains("number") && item["number"].is_number_integer()) number = item["number"].get<int>();
    auto parts = Split(e.repo.name, '/');
    if (!number || parts.size() != 2) return std::nullopt;
    return std::make_pair(isPr, IssueKey{parts[0], parts[1], number});
}

static bool HasTitle(const json& payload, const char* field) {
    if (!payload.contains(field) || !payload[field].is_object()) return false;
    const json& item = payload[field];
    return item.contains("title") && item["title"].is_string() && !Trim(item["title"].get<std::string>()).empty();
}

bool MainFrame::ApplyCachedTitles() {
    bool updated = false;
    for (auto& e : m_feedPages->AllItems()) {
        auto key = FeedTitleKey(e);
        if (!key) continue;
        const char* field = key->first ? "pull_request" : "issue";
        if (HasTitle(e.payload, field)) continue;
        auto& cache = key->first ? m_prTitles : m_issueTitles;
        auto it = cache.find(key->second);
        if (it == cache.end() || it->second.empty()) continue;
        e.payload[field]["title"] = it->second;
        updated = true;
    }
    return updated;
}

void MainFrame::StartTitleBackfill() {
    if (m_backfillRunning) return;
    std::vector<std::pair<bool, IssueKey>> jobs;
    std::set<std::pair<bool, IssueKey>> seen;
    for (const auto& e : m_feedPages->AllItems()) {
        auto key = FeedTitleKey(e);
        if (!key || !seen.insert(*key).second) continue;
        auto& cache = key->first ? m_prTitles : m_issueTitles;
        if (!HasTitle(e.payload, key->first ? "pull_request" : "issue") && !cache.count(key->second))
            jobs.push_back(*key);
        if (jobs.size() == 8) break;  // keep the calls per refresh low
    }
    auto account = app::Current();
    if (jobs.empty() || !account) return;
    m_backfillRunning = true;
    unsigned generation = m_generation;
    RunAsync(this,
             [account, jobs] {
                 std::vector<std::pair<std::pair<bool, IssueKey>, std::string>> found;
                 for (const auto& [isPr, key] : jobs) {
                     const auto& [owner, repo, number] = key;
                     std::string title;
                     if (isPr) {
                         if (auto pr = account->GetPullRequest(owner, repo, number)) title = Trim(pr->title);
                     } else if (auto issue = account->GetIssue(owner, repo, number)) {
                         title = Trim(issue->title);
                     }
                     found.push_back({{isPr, key}, title});  // misses are cached too
                 }
                 return found;
             },
             [this, generation](std::vector<std::pair<std::pair<bool, IssueKey>, std::string>> found) {
                 m_backfillRunning = false;
                 if (generation != m_generation) return;
                 for (const auto& [job, title] : found) (job.first ? m_prTitles : m_issueTitles)[job.second] = title;
                 if (ApplyCachedTitles()) m_feedPages->Rerender();
                 StartTitleBackfill();
             });
}

// --- System notifications for new things ---

// Only a refresh (page 1 onwards) announces new things; items from scrolling
// further down are remembered without a notification.
void MainFrame::NotifyNewFeed(bool first) {
    const auto& feed = m_feedPages->AllItems();
    bool announce = first && m_lastFeedIds && app::Prefs().GetBool("notify_activity", false);
    if (announce) {
        const Event* newest = nullptr;
        size_t count = 0;
        for (const auto& e : feed) {
            if (m_lastFeedIds->count(e.id)) continue;
            count++;
            if (!newest) newest = &e;
        }
        if (newest)
            Notify(wxString::Format("%zu new activity item%s", count, count > 1 ? "s" : ""),
                   U8(Truncate(newest->FormatDisplay(), 100)));
    }
    if (!m_lastFeedIds) m_lastFeedIds.emplace();
    for (const auto& e : feed) m_lastFeedIds->insert(e.id);
}

void MainFrame::NotifyNewNotifications(bool first) {
    const auto& all = m_notifPages->AllItems();
    bool announce = first && m_lastNotificationIds && app::Prefs().GetBool("notify_notifications", false);
    if (announce) {
        const Notification* newest = nullptr;
        size_t count = 0;
        for (const auto& n : all) {
            if (!n.unread || m_lastNotificationIds->count(n.id)) continue;
            count++;
            if (!newest) newest = &n;
        }
        if (newest)
            Notify(wxString::Format("%zu new GitHub notification%s", count, count > 1 ? "s" : ""),
                   U8(newest->subject.title + " (" + newest->repositoryFullName + ")"));
    }
    if (!m_lastNotificationIds) m_lastNotificationIds.emplace();
    for (const auto& n : all)
        if (n.unread) m_lastNotificationIds->insert(n.id);
}

void MainFrame::NotifyUpdatedRepos(const std::vector<Repository>& repos, std::map<long long, std::time_t>& last,
                                   bool& firstLoad, bool notify, const char* what, const char* pref) {
    std::vector<const Repository*> updated;
    for (const auto& r : repos) {
        auto it = last.find(r.id);
        if (!firstLoad && it != last.end() && it->second != r.pushedAt) updated.push_back(&r);
        last[r.id] = r.pushedAt;
    }
    firstLoad = false;
    if (!notify || updated.empty() || !app::Prefs().GetBool(pref, false)) return;
    size_t count = updated.size();
    wxString message = U8(updated[0]->fullName);
    if (count > 1) message += wxString::Format(" and %zu more", count - 1);
    Notify(wxString::Format("%zu %s repo%s updated", count, what, count > 1 ? "s" : ""), message);
}

// --- Selection ---

const Repository* MainFrame::SelectedRepo() const {
    int page = CurrentPage();
    if (page != kRepos && page != kStarred && page != kWatched) return nullptr;
    return m_repoPages[page]->Selected();
}

const Event* MainFrame::SelectedEvent() const { return m_feedPages->Selected(); }
const UserProfile* MainFrame::SelectedUser() const { return m_followingPages->Selected(); }
const Notification* MainFrame::SelectedNotification() const { return m_notifPages->Selected(); }

std::string MainFrame::SelectedUsername() const {
    switch (CurrentPage()) {
        case kRepos:
        case kStarred:
        case kWatched:
            if (auto* r = SelectedRepo()) return r->owner;
            break;
        case kFeed:
            if (auto* e = SelectedEvent()) {
                auto parts = Split(e->repo.name, '/');
                if (parts.size() == 2) return parts[0];
            }
            break;
        case kFollowing:
            if (auto* u = SelectedUser()) return u->login;
            break;
        case kNotifications:
            if (auto* n = SelectedNotification()) return n->repositoryOwner;
            break;
    }
    return std::string();
}

// --- Opening things ---

static int DiscussionNumberFromUrl(const std::string& url) {
    auto parts = Split(url, '/');
    for (size_t i = 0; i + 1 < parts.size(); i++) {
        if (parts[i] == "discussions") {
            try {
                return std::stoi(parts[i + 1]);
            } catch (...) {
                return 0;
            }
        }
    }
    return 0;
}

void MainFrame::WithRepo(const std::string& owner, const std::string& name,
                         std::function<void(const Repository&)> then) {
    auto account = app::Current();
    if (!account) return;
    SetStatus(U8("Loading " + owner + "/" + name + "..."));
    RunAsync(this, [account, owner, name] { return account->GetRepo(owner, name); },
             [this, then](std::optional<Repository> repo) {
                 SetStatus("Ready");
                 if (repo) then(*repo);
                 else ShowError(this, "Could not load repository");
             });
}

void MainFrame::OpenFeedEvent() {
    const Event* selected = SelectedEvent();
    if (!selected) return;
    Event e = *selected;
    auto parts = Split(e.repo.name, '/');
    if (parts.size() != 2) {
        OpenUrl(e.GetWebUrl());
        return;
    }
    const std::string owner = parts[0], name = parts[1];
    auto number = [&](const char* field) {
        if (e.payload.contains(field) && e.payload[field].is_object() && e.payload[field].contains("number") &&
            e.payload[field]["number"].is_number_integer())
            return e.payload[field]["number"].get<int>();
        return 0;
    };
    const std::string& t = e.type;
    if (t == "IssuesEvent" || t == "IssueCommentEvent") {
        if (int n = number("issue")) return OpenIssue(this, owner, name, n);
    } else if (t == "PullRequestEvent" || t == "PullRequestReviewEvent" || t == "PullRequestReviewCommentEvent" ||
               t == "PullRequestReviewThreadEvent") {
        if (int n = number("pull_request")) return OpenPullRequest(this, owner, name, n);
    } else if (t == "DiscussionEvent" || t == "DiscussionCommentEvent" || t == "Discussion") {
        int n = number("discussion");
        if (!n) {
            std::string url;
            const json& p = e.payload;
            if (p.contains("discussion") && p["discussion"].is_object() && p["discussion"].contains("html_url") &&
                p["discussion"]["html_url"].is_string())
                url = p["discussion"]["html_url"].get<std::string>();
            if (url.empty() && p.contains("comment") && p["comment"].is_object() &&
                p["comment"].contains("html_url") && p["comment"]["html_url"].is_string())
                url = p["comment"]["html_url"].get<std::string>();
            if (url.empty()) url = e.GetWebUrl();
            n = DiscussionNumberFromUrl(url);
        }
        if (n) return OpenDiscussion(this, owner, name, n);
    } else if (t == "PushEvent" || t == "CommitCommentEvent") {
        return WithRepo(owner, name, [this](const Repository& r) { ShowCommitsDialog(this, r); });
    } else if (t == "ReleaseEvent") {
        return WithRepo(owner, name, [this](const Repository& r) { ShowReleasesDialog(this, r); });
    } else if (t == "WatchEvent" || t == "ForkEvent" || t == "CreateEvent" || t == "PublicEvent" ||
               t == "GollumEvent" || t == "MemberEvent") {
        return OpenRepo(this, owner, name);
    }
    OpenUrl(e.GetWebUrl());
}

void MainFrame::OpenNotification() {
    const Notification* selected = SelectedNotification();
    auto account = app::Current();
    if (!selected || !account) return;
    Notification n = *selected;
    std::string id = n.id;
    RunAsyncVoid(this, [account, id] { account->MarkThreadRead(id); }, [this] { LoadNotifications(); });

    int number = 0;
    if (!n.subject.url.empty()) {
        auto parts = Split(n.subject.url, '/');
        if (!parts.empty()) {
            try {
                number = std::stoi(parts.back());
            } catch (...) {
            }
        }
    }
    const std::string& type = n.subject.type;
    if (type == "Discussion" && !number) number = DiscussionNumberFromUrl(n.GetWebUrl());
    const std::string &owner = n.repositoryOwner, &name = n.repositoryName;
    if (type == "Issue" && number) OpenIssue(this, owner, name, number);
    else if (type == "PullRequest" && number) OpenPullRequest(this, owner, name, number);
    else if (type == "Discussion" && number) OpenDiscussion(this, owner, name, number);
    else if (type == "Release") WithRepo(owner, name, [this](const Repository& r) { ShowReleasesDialog(this, r); });
    else if (type == "Commit") WithRepo(owner, name, [this](const Repository& r) { ShowCommitsDialog(this, r); });
    else OpenUrl(n.GetWebUrl());
}

void MainFrame::GoToRepo() {
    auto text = AskText(GetActiveOwner(), "Enter repository URL or owner/repo:", "Go to Repository");
    if (!text) return;
    std::string input = Trim(ToU8(*text));
    if (input.empty()) return;
    static const std::regex urlPattern(R"((?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$)",
                                       std::regex::icase);
    static const std::regex pairPattern(R"(^([^/]+)/([^/]+)$)");
    std::smatch m;
    if (std::regex_match(input, m, urlPattern) || std::regex_match(input, m, pairPattern)) {
        OpenRepo(GetActiveOwner(), m[1].str(), m[2].str());
        return;
    }
    ShowError(GetActiveOwner(),
              "Invalid input. Please enter a GitHub URL or owner/repo format.\n\n"
              "Examples:\n  https://github.com/owner/repo\n  owner/repo",
              "Invalid Input");
}

void MainFrame::ViewUser() {
    auto text = AskText(GetActiveOwner(), "Enter GitHub username:", "View User Profile", U8(SelectedUsername()));
    if (!text) return;
    std::string username = Trim(ToU8(*text));
    if (!username.empty()) ShowUserProfileDialog(GetActiveOwner(), username);
}

void MainFrame::UnfollowSelected() {
    const UserProfile* user = SelectedUser();
    auto account = app::Current();
    if (!user || !account) return;
    std::string login = user->login;
    if (!AskYesNo(this, U8("Unfollow " + login + "?"), "Confirm Unfollow")) return;
    RunAsync(this, [account, login] { return account->UnfollowUser(login); },
             [this](bool ok) {
                 if (ok) m_followingPages->Refresh();
                 else ShowError(this, "Failed to unfollow user.");
             });
}

void MainFrame::NotificationAction(const char* verb,
                                   std::function<bool(GitHubAccount&, const std::string&)> call) {
    const Notification* n = SelectedNotification();
    auto account = app::Current();
    if (!n || !account) return;
    std::string id = n->id;
    std::string what = verb;
    RunAsync(this, [account, id, call] { return call(*account, id); },
             [this, what](bool ok) {
                 if (ok) LoadNotifications();
                 else ShowError(this, U8("Failed to " + what + "."));
             });
}

void MainFrame::MarkAllRead() {
    auto account = app::Current();
    if (!account) return;
    int unread = 0;
    for (const auto& n : m_notifPages->Items()) unread += n.unread ? 1 : 0;
    if (!unread) {
        ShowInfo(this, "No unread notifications.", "Info");
        return;
    }
    if (!AskYesNo(this, wxString::Format("Mark all %d notifications as read?", unread))) return;
    RunAsync(this, [account] { return account->MarkNotificationsRead(); },
             [this](bool ok) {
                 if (ok) LoadNotifications();
                 else ShowError(this, "Failed to mark notifications as read.");
             });
}

void MainFrame::RunRepoSync(bool manual) {
    if (m_syncRunning) return;
    m_syncRunning = true;
    RunAsync(this, [] { return app::RepoSync().SyncAllEnabled(); },
             [this, manual](std::vector<RepoSyncResult> results) {
                 m_syncRunning = false;
                 bool notify = app::Prefs().GetBool("repo_sync_notify", true);
                 if (results.empty()) {
                     SetStatusText("Repo sync: no enabled repositories");
                     if (manual && notify) Notify("Repo Sync", "No enabled repositories configured.");
                     return;
                 }
                 const RepoSyncResult* firstFailure = nullptr;
                 size_t failed = 0;
                 for (const auto& r : results) {
                     if (r.ok) continue;
                     failed++;
                     if (!firstFailure) firstFailure = &r;
                 }
                 wxString summary;
                 if (failed) {
                     summary = wxString::Format("Repo sync: %zu/%zu succeeded", results.size() - failed, results.size());
                     if (notify) Notify("Repo Sync Errors", summary + ". First failure: " + U8(firstFailure->repo));
                 } else {
                     summary = wxString::Format("Repo sync: %zu repositories synced", results.size());
                     if (notify && manual) Notify("Repo Sync Complete", summary);
                 }
                 SetStatusText(summary);
             });
}

#ifdef __WXMSW__
TrayIcon::TrayIcon(MainFrame* frame) : m_frame(frame) {
    SetIcon(wxICON(appicon), APP_NAME);
    Bind(wxEVT_TASKBAR_LEFT_DCLICK, [this](wxTaskBarIconEvent&) { m_frame->ToggleWindow(); });
}

wxMenu* TrayIcon::CreatePopupMenu() {
    auto* menu = new wxMenu();
    menu->Append(1, m_frame->IsShown() ? "&Hide Window" : "&Show Window");
    menu->AppendSeparator();
    menu->Append(2, "&Refresh");
    menu->AppendSeparator();
    menu->Append(3, "E&xit");
    menu->Bind(wxEVT_MENU, [this](wxCommandEvent& e) {
        switch (e.GetId()) {
            case 1: m_frame->ToggleWindow(); break;
            case 2: m_frame->RefreshAll(); break;
            case 3: m_frame->CallAfter([this] { m_frame->Exit(); }); break;
        }
    });
    return menu;
}
#endif

}  // namespace

// --- The main window's public face (main_frame.h) ---

namespace mainwin {

wxFrame* Get() { return g_frame; }
void RefreshAll() { if (g_frame) g_frame->RefreshAll(); }
void RefreshFeedFilters() { if (g_frame) g_frame->RenderFeed(); }
void ApplyOptions() { if (g_frame) g_frame->ApplyOptions(); }
void AccountChanged() { if (g_frame) g_frame->AccountChanged(); }
bool SetGlobalHotkey(const std::string& hotkey) { return g_frame && g_frame->SetGlobalHotkey(hotkey); }
void ShowWindow() { if (g_frame) g_frame->ShowWindow(); }
void HideWindow() { if (g_frame) g_frame->HideWindow(); }
void ToggleWindow() { if (g_frame) g_frame->ToggleWindow(); }
void Notify(const wxString& title, const wxString& message) { if (g_frame) g_frame->Notify(title, message); }

// Created by the app (ui/app.cpp).
wxFrame* Create() { return new MainFrame(); }
void Exit() { if (g_frame) g_frame->Exit(); }

}  // namespace mainwin
