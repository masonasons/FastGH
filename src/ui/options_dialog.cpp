// The Options dialog (a port of GUI/options.py): application settings on
// notebook pages, and the current account's activity feed filters.
//
// The feed filter is no longer a wall of checkboxes: one checkable list of
// event types (checked = every action shown) and, beside it, a checkable list
// of the selected type's actions. The per-user filter dialog uses the same pair.

#include "ui/dialogs.h"

#include "core/app.h"
#include "core/feed_filter.h"
#include "core/util.h"
#include "ui/main_frame.h"
#include "ui/ui_common.h"

#include <wx/checklst.h>
#include <wx/choice.h>
#include <wx/notebook.h>
#include <wx/spinctrl.h>

#include <algorithm>
#include <iterator>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace {

// --- Names for event types and actions (as GUI/options.py showed them) ---

std::string EventTypeName(const std::string& type) {
    static const std::map<std::string, std::string> names = {
        {"PullRequestEvent", "Pull Requests"},
        {"PullRequestReviewEvent", "Pull Request Reviews"},
        {"PullRequestReviewCommentEvent", "Pull Request Review Comments"},
        {"PullRequestReviewThreadEvent", "Pull Request Review Threads"},
        {"IssuesEvent", "Issues"},
        {"IssueCommentEvent", "Issue Comments"},
        {"CreateEvent", "Create"},
        {"DeleteEvent", "Delete"},
        {"ReleaseEvent", "Releases"},
        {"DiscussionEvent", "Discussions"},
        {"DiscussionCommentEvent", "Discussion Comments"},
        {"MemberEvent", "Member"},
        {"SponsorshipEvent", "Sponsorship"},
        {"PushEvent", "Push (commits)"},
        {"CommitCommentEvent", "Commit Comment"},
        {"ForkEvent", "Fork"},
        {"WatchEvent", "Star (watch event)"},
        {"GollumEvent", "Wiki page updated"},
        {"PublicEvent", "Repo made Public"},
    };
    auto it = names.find(type);
    return it == names.end() ? type : it->second;
}

std::string ActionName(const std::string& action) {
    static const std::map<std::string, std::string> names = {
        {"opened", "Opened"},       {"closed", "Closed"},
        {"merged", "Merged"},       {"reopened", "Reopened"},
        {"labeled", "Labeled"},     {"unlabeled", "Unlabeled"},
        {"assigned", "Assigned"},   {"unassigned", "Unassigned"},
        {"locked", "Locked"},       {"unlocked", "Unlocked"},
        {"approved", "Approved"},   {"changes_requested", "Changes requested"},
        {"commented", "Commented"}, {"created", "Created"},
        {"edited", "Edited"},       {"deleted", "Deleted"},
        {"resolved", "Resolved"},   {"unresolved", "Unresolved"},
        {"published", "Published"}, {"prereleased", "Pre-released"},
        {"branch", "Branch"},       {"tag", "Tag"},
        {"repository", "Repository"}, {"added", "Added"},
        {"removed", "Removed"},     {"answered", "Answered"},
        {"category_changed", "Category changed"}, {"cancelled", "Cancelled"},
    };
    auto it = names.find(action);
    return it == names.end() ? action : it->second;
}

// One filterable event type and its visibility keys: "Type" when it has no
// actions, else "Type:action" for each.
struct FilterType {
    std::string type;
    std::string name;
    std::vector<std::string> actions;
    std::vector<std::string> keys;
};

const std::vector<FilterType>& FilterTypes() {
    static const std::vector<FilterType> types = [] {
        std::vector<FilterType> out;
        for (const auto& group : feedfilter::kFilterGroups) {
            for (const auto& type : group.second) {
                FilterType t;
                t.type = type;
                t.name = EventTypeName(type);
                auto it = feedfilter::kEventTypeActions.find(type);
                if (it != feedfilter::kEventTypeActions.end()) t.actions = it->second;
                if (t.actions.empty()) t.keys.push_back(type);
                for (const auto& a : t.actions) t.keys.push_back(type + ":" + a);
                out.push_back(std::move(t));
            }
        }
        return out;
    }();
    return types;
}

std::set<std::string> AllFilterKeys() {
    std::set<std::string> all;
    for (const auto& t : FilterTypes()) all.insert(t.keys.begin(), t.keys.end());
    return all;
}

// --- Layout helpers for notebook pages ---
// Labels are created before their controls so screen readers name the controls from them.

wxStaticText* AddLabel(wxWindow* page, wxSizer* sizer, const wxString& label) {
    auto* text = new wxStaticText(page, wxID_ANY, label);
    sizer->Add(text, 0, wxLEFT | wxRIGHT | wxTOP, 10);
    return text;
}

void AddControl(wxSizer* sizer, wxWindow* control, int proportion = 0) {
    sizer->Add(control, proportion, wxEXPAND | wxLEFT | wxRIGHT | wxTOP, 10);
}

wxCheckBox* AddCheck(wxWindow* page, wxSizer* sizer, const wxString& label, bool value) {
    auto* check = new wxCheckBox(page, wxID_ANY, label);
    check->SetValue(value);
    sizer->Add(check, 0, wxLEFT | wxRIGHT | wxTOP, 10);
    return check;
}

// A labelled folder field with its Browse button.
wxTextCtrl* AddFolderRow(wxWindow* page, wxSizer* sizer, const wxString& label, const wxString& browseLabel,
                         const wxString& dialogTitle, const std::string& value) {
    AddLabel(page, sizer, label);
    auto* row = new wxBoxSizer(wxHORIZONTAL);
    auto* text = new wxTextCtrl(page, wxID_ANY, U8(value));
    row->Add(text, 1, wxRIGHT | wxALIGN_CENTER_VERTICAL, 5);
    auto* browse = new wxButton(page, wxID_ANY, browseLabel);
    row->Add(browse, 0, wxALIGN_CENTER_VERTICAL);
    sizer->Add(row, 0, wxEXPAND | wxLEFT | wxRIGHT | wxTOP, 10);
    browse->Bind(wxEVT_BUTTON, [page, text, dialogTitle](wxCommandEvent&) {
        wxString current = text->GetValue();
        if (current.empty() || !wxDirExists(current)) current = U8(HomeDir());
        wxString dir = AskDirectory(wxGetTopLevelParent(page), dialogTitle, current);
        if (!dir.empty()) text->SetValue(dir);
    });
    return text;
}

wxSpinCtrl* AddSpin(wxWindow* page, wxSizer* sizer, const wxString& label, int max, int value) {
    AddLabel(page, sizer, label);
    auto* spin = new wxSpinCtrl(page, wxID_ANY, "", wxDefaultPosition, wxDefaultSize, wxSP_ARROW_KEYS, 0, max,
                                value);
    sizer->Add(spin, 0, wxLEFT | wxRIGHT | wxTOP, 10);
#ifdef __WXOSX__
    // macOS builds this from a text field and a stepper, and the label before it
    // names neither: name the text field VoiceOver lands on.
    spin->GetText()->SetAccessibleName(wxStripMenuCodes(label));
#endif
    return spin;
}

// --- The event type / action editor ---

class FilterEditor : public wxPanel {
public:
    explicit FilterEditor(wxWindow* parent) : wxPanel(parent) {
        auto* sizer = new wxBoxSizer(wxVERTICAL);
        auto* lists = new wxBoxSizer(wxHORIZONTAL);

        auto* typeCol = new wxBoxSizer(wxVERTICAL);
        typeCol->Add(new wxStaticText(this, wxID_ANY, "Event &types (checked: shown):"), 0, wxBOTTOM, 4);
        m_types = new wxCheckListBox(this, wxID_ANY);
        typeCol->Add(m_types, 1, wxEXPAND);
        lists->Add(typeCol, 3, wxEXPAND | wxRIGHT, 10);

        auto* actionCol = new wxBoxSizer(wxVERTICAL);
        actionCol->Add(new wxStaticText(this, wxID_ANY, "A&ctions shown for this type:"), 0, wxBOTTOM, 4);
        m_actionList = new wxCheckListBox(this, wxID_ANY);
        actionCol->Add(m_actionList, 1, wxEXPAND);
        lists->Add(actionCol, 2, wxEXPAND);
        sizer->Add(lists, 1, wxEXPAND);

        m_bar = new ActionBar(this);
        m_bar->Add({"Show &All Events", [this] { SetAll(true); }});
        m_bar->Add({"Show &No Events", [this] { SetAll(false); }});
        m_bar->AddSeparator();
        Action allOfType{"Show All Actions of This &Type", [this] { SetType(Selected(m_types), true); }};
        allOfType.enabled = [this] { return Selected(m_types) >= 0; };
        m_bar->Add(allOfType);
        Action noneOfType{"&Hide This Type", [this] { SetType(Selected(m_types), false); }};
        noneOfType.enabled = [this] { return Selected(m_types) >= 0; };
        m_bar->Add(noneOfType);
        sizer->Add(m_bar->CreateButtons(false), 0, wxTOP, 8);
        m_bar->AttachContextMenu(m_types);
        m_bar->AttachContextMenu(m_actionList);

        for (const auto& t : FilterTypes()) m_types->Append(U8(t.name));

        m_types->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) { FillActions(); });
        m_types->Bind(wxEVT_CHECKLISTBOX, [this](wxCommandEvent& e) {
            int i = e.GetInt();
            SetType(i, m_types->IsChecked(i));
        });
        m_actionList->Bind(wxEVT_CHECKLISTBOX, [this](wxCommandEvent& e) {
            int i = e.GetInt();
            if (i < 0 || i >= static_cast<int>(m_actionKeys.size())) return;
            if (m_actionList->IsChecked(i)) m_visible.insert(m_actionKeys[i]);
            else m_visible.erase(m_actionKeys[i]);
            RefreshType(Selected(m_types));
        });

        SetSizer(sizer);
    }

    void SetVisible(const std::set<std::string>& visible) {
        m_visible = visible;
        for (int i = 0; i < static_cast<int>(FilterTypes().size()); i++) RefreshType(i);
        if (Selected(m_types) < 0 && !m_types->IsEmpty()) m_types->SetSelection(0);
        FillActions();
    }
    // Only the keys the editor knows, so stale ones don't linger in the settings.
    std::set<std::string> GetVisible() const {
        std::set<std::string> out;
        std::set<std::string> all = AllFilterKeys();
        for (const auto& k : m_visible)
            if (all.count(k)) out.insert(k);
        return out;
    }

    wxWindow* FirstControl() const { return m_types; }

private:
    void SetAll(bool shown) {
        m_visible = shown ? AllFilterKeys() : std::set<std::string>();
        SetVisible(m_visible);
    }

    void SetType(int index, bool shown) {
        if (index < 0 || index >= static_cast<int>(FilterTypes().size())) return;
        for (const auto& k : FilterTypes()[index].keys) {
            if (shown) m_visible.insert(k);
            else m_visible.erase(k);
        }
        RefreshType(index);
        if (index == Selected(m_types)) FillActions();
    }

    // The row reads "Issues" when every action shows, "Issues (3 of 9 actions shown)"
    // when some do; it is checked only when all do.
    void RefreshType(int index) {
        if (index < 0 || index >= static_cast<int>(FilterTypes().size())) return;
        const FilterType& t = FilterTypes()[index];
        size_t shown = 0;
        for (const auto& k : t.keys) shown += m_visible.count(k);
        wxString label = U8(t.name);
        if (shown > 0 && shown < t.keys.size())
            label += wxString::Format(" (%zu of %zu actions shown)", shown, t.keys.size());
        if (m_types->GetString(index) != label) m_types->SetString(index, label);
        m_types->Check(index, shown == t.keys.size());
    }

    // The selected type's actions; a type without actions gets one item for itself.
    void FillActions() {
        m_actionList->Clear();
        m_actionKeys.clear();
        int index = Selected(m_types);
        if (index < 0 || index >= static_cast<int>(FilterTypes().size())) return;
        const FilterType& t = FilterTypes()[index];
        if (t.actions.empty()) {
            m_actionList->Append(U8(t.name) + " events");
            m_actionKeys.push_back(t.type);
        } else {
            for (const auto& a : t.actions) {
                m_actionList->Append(U8(ActionName(a)));
                m_actionKeys.push_back(t.type + ":" + a);
            }
        }
        for (size_t i = 0; i < m_actionKeys.size(); i++)
            m_actionList->Check(static_cast<unsigned>(i), m_visible.count(m_actionKeys[i]) > 0);
        m_actionList->SetSelection(0);
        m_bar->Update();
    }

    wxCheckListBox* m_types;
    wxCheckListBox* m_actionList;
    std::vector<std::string> m_actionKeys;  // per row of m_actionList
    std::set<std::string> m_visible;
    ActionBar* m_bar;  // owned by this panel
};

// --- Add / edit one user's filter ---

class UserFilterDialog : public BaseDialog {
public:
    // `visible`: nullopt for a new user (nothing checked), empty for a muted user.
    UserFilterDialog(wxWindow* parent, const std::string& username,
                     const std::optional<std::set<std::string>>& visible)
        : BaseDialog(parent, username.empty() ? "Add User Filter" : "Edit User Filter", wxSize(650, 550)) {
        wxWindow* p = Panel();
        m_username = new wxTextCtrl(p, wxID_ANY, U8(username));
        AddLabeled("GitHub &username:", m_username);
        Sizer()->Add(new wxStaticText(p, wxID_ANY,
                                      "Check the event types you want to see from this user.\n"
                                      "Leave all unchecked to hide their events entirely."),
                     0, wxLEFT | wxRIGHT | wxTOP, 10);
        m_mute = new wxCheckBox(p, wxID_ANY, "&Mute this user entirely (hide all their events)");
        Sizer()->Add(m_mute, 0, wxALL, 10);
        m_editor = new FilterEditor(p);
        Sizer()->Add(m_editor, 1, wxEXPAND | wxLEFT | wxRIGHT, 10);

        auto* buttons = new wxBoxSizer(wxHORIZONTAL);
        auto* ok = new wxButton(p, wxID_OK, "OK");
        ok->SetDefault();
        buttons->Add(ok, 0, wxRIGHT, 5);
        buttons->Add(new wxButton(p, wxID_CANCEL, "Cancel"), 0);
        Sizer()->Add(buttons, 0, wxALL | wxALIGN_RIGHT, 10);

        m_editor->SetVisible(visible ? *visible : std::set<std::string>());
        if (visible && visible->empty()) {
            m_mute->SetValue(true);
            m_editor->Enable(false);
        }
        m_mute->Bind(wxEVT_CHECKBOX, [this](wxCommandEvent&) { m_editor->Enable(!m_mute->GetValue()); });
        ok->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
            if (Trim(ToU8(m_username->GetValue())).empty()) {
                ShowError(this, "Please enter a GitHub username.", "Required");
                m_username->SetFocus();
                return;
            }
            EndModal(wxID_OK);
        });

        Finish();
        m_username->SetFocus();
    }

    std::string Username() const { return ToLower(Trim(ToU8(m_username->GetValue()))); }
    // Empty: muted.
    std::set<std::string> Visible() const {
        return m_mute->GetValue() ? std::set<std::string>() : m_editor->GetVisible();
    }

private:
    wxTextCtrl* m_username;
    wxCheckBox* m_mute;
    FilterEditor* m_editor;
};

// --- The Options dialog ---

const char* const kDarkModeValues[] = {"off", "auto", "on"};

class OptionsDialog : public BaseDialog {
public:
    explicit OptionsDialog(wxWindow* parent) : BaseDialog(parent, "Options", wxSize(700, 620)) {
        m_account = app::Current();
        m_book = new wxNotebook(Panel(), wxID_ANY);
        BuildGeneral();
        BuildNotifications();
        BuildGit();
        BuildRepoSync();
        BuildFeedFilter();
        BuildMutedRepos();
        BuildUserFilters();
        Sizer()->Add(m_book, 1, wxEXPAND | wxALL, 5);

        auto* buttons = new wxBoxSizer(wxHORIZONTAL);
        auto* ok = new wxButton(Panel(), wxID_OK, "OK");
        ok->SetDefault();  // Enter saves and closes, as in Python
        buttons->Add(ok, 0, wxRIGHT, 5);
        buttons->Add(new wxButton(Panel(), wxID_CANCEL, "Cancel"), 0, wxRIGHT, 5);
        auto* apply = new wxButton(Panel(), wxID_APPLY, "&Apply");
        buttons->Add(apply, 0);
        Sizer()->Add(buttons, 0, wxALL | wxALIGN_RIGHT, 10);
        ok->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
            if (Save()) EndModal(wxID_OK);
        });
        apply->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { Save(); });

        LoadFilters();
        Finish();
        m_book->SetFocus();
    }

private:
    static Config& P() { return app::Prefs(); }

    wxPanel* NewPage(const wxString& title, wxBoxSizer*& sizer) {
        auto* page = new wxPanel(m_book);
        sizer = new wxBoxSizer(wxVERTICAL);
        page->SetSizer(sizer);
        m_book->AddPage(page, title);
        return page;
    }

    void BuildGeneral() {
        wxBoxSizer* s;
        wxPanel* page = NewPage("General", s);
        m_downloadPath = AddFolderRow(page, s, "&Download location:", "&Browse...", "Select Download Location",
                                      P().GetString("download_location"));
        m_downloadPath->SetToolTip("Default folder for downloading release artifacts");

        AddLabel(page, s, "Dar&k mode:");
        wxArrayString modes;
        modes.Add("Off");
        modes.Add("Auto (follow system)");
        modes.Add("On");
        m_darkMode = new wxChoice(page, wxID_ANY, wxDefaultPosition, wxDefaultSize, modes);
        std::string dark = P().GetString("dark_mode", "off");
        m_darkMode->SetSelection(dark == "auto" ? 1 : dark == "on" ? 2 : 0);
        s->Add(m_darkMode, 0, wxLEFT | wxRIGHT | wxTOP, 10);

        AddLabel(page, s, "Show/&hide window hotkey:");
        auto* row = new wxBoxSizer(wxHORIZONTAL);
        m_hotkey = new wxTextCtrl(page, wxID_ANY, U8(P().GetString("global_hotkey")));
        row->Add(m_hotkey, 1, wxRIGHT | wxALIGN_CENTER_VERTICAL, 5);
        auto* clear = new wxButton(page, wxID_ANY, "C&lear");
        row->Add(clear, 0, wxALIGN_CENTER_VERTICAL);
        s->Add(row, 0, wxEXPAND | wxLEFT | wxRIGHT | wxTOP, 10);
        clear->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
            m_hotkey->Clear();
            m_hotkey->SetFocus();
        });
        wxString hint = "Format: control+alt+g, win+shift+h, etc. Leave empty to disable.";
#ifdef __WXOSX__
        hint += "\nOn macOS, control means Command.";
#endif
        s->Add(new wxStaticText(page, wxID_ANY, hint), 0, wxLEFT | wxRIGHT | wxTOP, 10);

        m_checkUpdates = AddCheck(page, s, "Check for &updates on startup", P().GetBool("check_for_updates", true));
    }

    void BuildNotifications() {
        wxBoxSizer* s;
        wxPanel* page = NewPage("Notifications", s);
        m_notifyActivity = AddCheck(page, s, "Notify on new a&ctivity feed items", P().GetBool("notify_activity"));
        m_notifyNotifications =
            AddCheck(page, s, "Notify on new GitHub &notifications", P().GetBool("notify_notifications"));
        m_notifyStarred =
            AddCheck(page, s, "Notify on &starred repository updates", P().GetBool("notify_starred"));
        m_notifyWatched =
            AddCheck(page, s, "Notify on &watched repository updates", P().GetBool("notify_watched"));
        m_notifyRepoSync =
            AddCheck(page, s, "Notify on repository s&ync results", P().GetBool("repo_sync_notify", true));
        m_refreshInterval = AddSpin(page, s, "Auto-&refresh interval in minutes (0 = disabled):", 60,
                                    P().GetInt("auto_refresh_interval", 0));
    }

    void BuildGit() {
        wxBoxSizer* s;
        wxPanel* page = NewPage("Git", s);
        m_gitPath = AddFolderRow(page, s, "&Git repositories path:", "&Browse...", "Select Git Repositories Path",
                                 P().GetString("git_path"));
        m_gitPath->SetToolTip("Folder where repositories will be cloned");
        m_gitOrg = AddCheck(page, s, "Clone into &owner/repo folder structure", P().GetBool("git_use_org_structure"));
        m_gitOrg->SetToolTip("When enabled, repositories are cloned to owner/repo\n"
                             "(e.g., masonasons/FastGH instead of just FastGH)");
        m_gitRecursive =
            AddCheck(page, s, "Clone rec&ursively (include submodules)", P().GetBool("git_clone_recursive"));
        m_gitLfs = AddCheck(page, s, "Enable Git &LFS support for clone/pull/sync", P().GetBool("git_lfs_enabled", true));
        m_gitLfs->SetToolTip("Runs git lfs install/pull after clone/pull and during scheduled sync.\n"
                             "If git-lfs is not installed, operations continue with a warning.");
    }

    void BuildRepoSync() {
        wxBoxSizer* s;
        wxPanel* page = NewPage("Repo Sync", s);
        m_syncEnabled = AddCheck(page, s, "&Enable scheduled auto sync for configured repositories",
                                 P().GetBool("repo_sync_enabled"));
        m_syncInterval = AddSpin(page, s, "Sync &interval in minutes (0 = disabled):", 240,
                                 P().GetInt("repo_sync_interval_minutes", 0));
        m_syncUseTools = AddCheck(page, s, "&Use .GITHUB repo bootstrap updater before git sync",
                                  P().GetBool("repo_sync_use_github_tools", true));
        m_syncToolsPath = AddFolderRow(page, s, ".GITHUB &tools path:", "&Browse...", "Select .GITHUB Tools Path",
                                       P().GetString("repo_sync_github_tools_path"));
    }

    void BuildFeedFilter() {
        wxBoxSizer* s;
        wxPanel* page = NewPage("Feed Filter", s);
        s->Add(new wxStaticText(page, wxID_ANY,
                                "Choose which event types and actions appear in your activity feed. "
                                "These settings belong to the current account."),
               0, wxEXPAND | wxALL, 10);
        m_filterEditor = new FilterEditor(page);
        s->Add(m_filterEditor, 1, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
        if (!m_account) page->Enable(false);
    }

    void BuildMutedRepos() {
        wxBoxSizer* s;
        wxPanel* page = NewPage("Muted Repositories", s);
        s->Add(new wxStaticText(page, wxID_ANY,
                                "Events from muted repositories are always hidden, regardless of event type."),
               0, wxEXPAND | wxLEFT | wxRIGHT | wxTOP, 10);

        AddLabel(page, s, "&Muted repositories:");
        m_mutedList = new wxListBox(page, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddControl(s, m_mutedList, 1);
        m_mutedBar = new ActionBar(page);
        Action remove{"R&emove", [this] { RemoveMuted(); }, true};
        remove.enabled = [this] { return Selected(m_mutedList) >= 0 && !m_muted.empty(); };
        m_mutedBar->Add(remove);
        s->Add(m_mutedBar->CreateButtons(false), 0, wxLEFT | wxRIGHT | wxTOP, 10);
        m_mutedBar->AttachContextMenu(m_mutedList);

        AddLabel(page, s, "Add &repository (owner/repo):");
        auto* row = new wxBoxSizer(wxHORIZONTAL);
        m_mutedEntry = new wxTextCtrl(page, wxID_ANY, "", wxDefaultPosition, wxDefaultSize, wxTE_PROCESS_ENTER);
        m_mutedEntry->SetHint("e.g. torvalds/linux");
        row->Add(m_mutedEntry, 1, wxRIGHT | wxALIGN_CENTER_VERTICAL, 5);
        auto* add = new wxButton(page, wxID_ANY, "A&dd");
        row->Add(add, 0, wxALIGN_CENTER_VERTICAL);
        s->Add(row, 0, wxEXPAND | wxALL, 10);

        add->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { AddMuted(); });
        m_mutedEntry->Bind(wxEVT_TEXT_ENTER, [this](wxCommandEvent&) { AddMuted(); });
        m_mutedList->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) { m_mutedBar->Update(); });
        m_mutedList->Bind(wxEVT_KEY_DOWN, [this](wxKeyEvent& e) {
            if (e.GetKeyCode() == WXK_DELETE || e.GetKeyCode() == WXK_BACK) RemoveMuted();
            else e.Skip();
        });
        if (!m_account) page->Enable(false);
    }

    void BuildUserFilters() {
        wxBoxSizer* s;
        wxPanel* page = NewPage("User Filters", s);
        s->Add(new wxStaticText(page, wxID_ANY,
                                "Per-user rules override the event type filter for that user. "
                                "Muted users are hidden entirely regardless of event type."),
               0, wxEXPAND | wxLEFT | wxRIGHT | wxTOP, 10);
        AddLabel(page, s, "&User filters:");
        m_userList = new wxListBox(page, wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddControl(s, m_userList, 1);

        m_userBar = new ActionBar(page);
        // Edit comes first so Enter / double click edits the selected rule.
        Action edit{"&Edit...", [this] { EditUserFilter(); }, true};
        edit.enabled = [this] { return SelectedUserFilter() != nullptr; };
        m_userBar->Add(edit);
        m_userBar->Add({"A&dd User...", [this] { AddUserFilter(); }, true});
        Action remove{"Re&move", [this] { RemoveUserFilter(); }, true};
        remove.enabled = [this] { return SelectedUserFilter() != nullptr; };
        m_userBar->Add(remove);
        s->Add(m_userBar->CreateButtons(false), 0, wxALL, 10);
        m_userBar->AttachContextMenu(m_userList);
        m_userBar->AttachActivate(m_userList);

        m_userList->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) { m_userBar->Update(); });
        m_userList->Bind(wxEVT_KEY_DOWN, [this](wxKeyEvent& e) {
            if (e.GetKeyCode() == WXK_DELETE || e.GetKeyCode() == WXK_BACK) RemoveUserFilter();
            else e.Skip();
        });
        if (!m_account) page->Enable(false);
    }

    // --- Feed filters: loaded once, compared on save so unchanged settings are left alone ---

    void LoadFilters() {
        if (!m_account) {
            m_filterEditor->SetVisible(AllFilterKeys());
            return;
        }
        Config& prefs = m_account->Prefs();
        auto visible = feedfilter::LoadVisibleTypes(prefs);
        m_savedVisible = visible ? *visible : AllFilterKeys();
        m_filterEditor->SetVisible(m_savedVisible);
        auto muted = feedfilter::LoadMutedRepos(prefs);
        m_savedMuted = m_muted = muted ? *muted : std::set<std::string>();
        auto users = feedfilter::LoadUserFilters(prefs);
        m_savedUsers = m_userFilters = users ? *users : std::map<std::string, std::set<std::string>>();
        FillMuted("");
        FillUsers("");
    }

    void FillMuted(const std::string& select) {
        std::vector<wxString> lines;
        int index = -1, i = 0;
        for (const auto& r : m_muted) {
            if (r == select) index = i;
            lines.push_back(U8(r));
            i++;
        }
        if (lines.empty()) lines.push_back("No muted repositories");
        SetListItems(m_mutedList, lines);
        if (index >= 0) m_mutedList->SetSelection(index);
        m_mutedBar->Update();
    }

    void AddMuted() {
        std::string repo = ToLower(Trim(ToU8(m_mutedEntry->GetValue())));
        if (repo.empty()) return;
        if (repo.find('/') == std::string::npos || StartsWith(repo, "/") || EndsWith(repo, "/")) {
            ShowError(this, "Please enter a repository in owner/repo format.\nExample: torvalds/linux",
                      "Invalid Format");
            m_mutedEntry->SetFocus();
            return;
        }
        m_muted.insert(repo);
        m_mutedEntry->Clear();
        FillMuted(repo);
        SetStatus("Muted " + U8(repo));
    }

    void RemoveMuted() {
        int i = Selected(m_mutedList);
        if (i < 0 || i >= static_cast<int>(m_muted.size())) return;
        auto it = std::next(m_muted.begin(), i);
        wxString name = U8(*it);
        m_muted.erase(it);
        FillMuted("");
        if (!m_muted.empty()) m_mutedList->SetSelection(std::min(i, static_cast<int>(m_muted.size()) - 1));
        m_mutedBar->Update();
        SetStatus("Unmuted " + name);
    }

    static wxString UserFilterLine(const std::string& user, const std::set<std::string>& visible) {
        std::string line = user + " \xE2\x80\x94 ";  // an em dash, as in Python
        if (visible.empty()) line += "muted";
        else line += std::to_string(visible.size()) + " type(s)";
        return U8(line);
    }

    void FillUsers(const std::string& select) {
        std::vector<wxString> lines;
        int index = -1, i = 0;
        for (const auto& [user, visible] : m_userFilters) {
            if (user == select) index = i;
            lines.push_back(UserFilterLine(user, visible));
            i++;
        }
        if (lines.empty()) lines.push_back("No user filters");
        SetListItems(m_userList, lines);
        if (index >= 0) m_userList->SetSelection(index);
        m_userBar->Update();
    }

    const std::pair<const std::string, std::set<std::string>>* SelectedUserFilter() const {
        int i = Selected(m_userList);
        if (i < 0 || i >= static_cast<int>(m_userFilters.size())) return nullptr;
        return &*std::next(m_userFilters.begin(), i);
    }

    void AddUserFilter() {
        UserFilterDialog dlg(this, "", std::nullopt);
        if (dlg.ShowModal() != wxID_OK) return;
        std::string user = dlg.Username();
        if (user.empty()) return;
        m_userFilters[user] = dlg.Visible();  // replaces an existing rule for the same user
        FillUsers(user);
    }

    void EditUserFilter() {
        auto* entry = SelectedUserFilter();
        if (!entry) return;
        std::string oldUser = entry->first;
        UserFilterDialog dlg(this, oldUser, entry->second);
        if (dlg.ShowModal() != wxID_OK) return;
        std::string user = dlg.Username();
        if (user.empty()) return;
        m_userFilters.erase(oldUser);  // the name may have been changed
        m_userFilters[user] = dlg.Visible();
        FillUsers(user);
    }

    void RemoveUserFilter() {
        auto* entry = SelectedUserFilter();
        if (!entry) return;
        int i = Selected(m_userList);
        m_userFilters.erase(entry->first);
        FillUsers("");
        if (!m_userFilters.empty())
            m_userList->SetSelection(std::min(i, static_cast<int>(m_userFilters.size()) - 1));
        m_userBar->Update();
    }

    // --- Saving ---

    // True when everything was saved; false keeps the dialog open (a bad or refused hotkey).
    bool Save() {
        // Check the hotkey before saving anything, as a typo should not half-apply the dialog.
        std::string oldHotkey = P().GetString("global_hotkey");
        std::string hotkey = ToLower(Trim(ToU8(m_hotkey->GetValue())));
        if (!hotkey.empty()) {
            std::vector<std::string> parts = Split(hotkey, '+');
            static const std::set<std::string> modifiers = {"control", "ctrl", "alt", "shift", "win"};
            bool hasModifier = false;
            for (const auto& part : parts) hasModifier = hasModifier || modifiers.count(Trim(part)) > 0;
            if (!hasModifier || parts.size() < 2) {
                m_book->SetSelection(0);
                ShowError(this,
                          "Invalid hotkey format.\n\nPlease use format: modifier+key\nExample: control+alt+g",
                          "Invalid Hotkey");
                m_hotkey->SetFocus();
                return false;
            }
        }

        P().Set("download_location", ToU8(m_downloadPath->GetValue()));
        P().Set("git_path", ToU8(m_gitPath->GetValue()));
        P().Set("git_use_org_structure", m_gitOrg->GetValue());
        P().Set("git_clone_recursive", m_gitRecursive->GetValue());
        P().Set("git_lfs_enabled", m_gitLfs->GetValue());
        P().Set("repo_sync_enabled", m_syncEnabled->GetValue());
        P().Set("repo_sync_interval_minutes", m_syncInterval->GetValue());
        P().Set("repo_sync_use_github_tools", m_syncUseTools->GetValue());
        P().Set("repo_sync_github_tools_path", Trim(ToU8(m_syncToolsPath->GetValue())));
        P().Set("notify_activity", m_notifyActivity->GetValue());
        P().Set("notify_notifications", m_notifyNotifications->GetValue());
        P().Set("notify_starred", m_notifyStarred->GetValue());
        P().Set("notify_watched", m_notifyWatched->GetValue());
        P().Set("repo_sync_notify", m_notifyRepoSync->GetValue());
        P().Set("auto_refresh_interval", m_refreshInterval->GetValue());
        int dark = m_darkMode->GetSelection();
        P().Set("dark_mode", std::string(kDarkModeValues[dark >= 0 && dark < 3 ? dark : 0]));
        P().Set("check_for_updates", m_checkUpdates->GetValue());

        // The hotkey is saved only once the system accepted it, so ApplyOptions
        // never re-registers one that was refused.
        bool hotkeyOk = true;
        if (hotkey != oldHotkey) {
            if (mainwin::SetGlobalHotkey(hotkey) || hotkey.empty()) {
                P().Set("global_hotkey", hotkey);
            } else {
                hotkeyOk = false;
                if (!oldHotkey.empty()) mainwin::SetGlobalHotkey(oldHotkey);  // keep the old one working
            }
        }
        mainwin::ApplyOptions();

        if (m_account && SaveFilters()) mainwin::RefreshFeedFilters();

        if (!hotkeyOk) {
            m_book->SetSelection(0);
            ShowError(this,
                      "Failed to register hotkey: " + U8(hotkey) +
                          "\n\nThe hotkey may already be in use by another application.",
                      "Hotkey Error");
            m_hotkey->SetFocus();
        }
        return hotkeyOk;
    }

    // Saves what changed; true when anything did.
    bool SaveFilters() {
        Config& prefs = m_account->Prefs();
        bool changed = false;
        std::set<std::string> visible = m_filterEditor->GetVisible();
        if (visible != m_savedVisible) {
            feedfilter::SaveVisibleTypes(prefs, visible);
            m_savedVisible = visible;
            changed = true;
        }
        if (m_muted != m_savedMuted) {
            feedfilter::SaveMutedRepos(prefs, m_muted);
            m_savedMuted = m_muted;
            changed = true;
        }
        if (m_userFilters != m_savedUsers) {
            feedfilter::SaveUserFilters(prefs, m_userFilters);
            m_savedUsers = m_userFilters;
            changed = true;
        }
        return changed;
    }

    std::shared_ptr<GitHubAccount> m_account;
    wxNotebook* m_book;

    wxTextCtrl* m_downloadPath;
    wxChoice* m_darkMode;
    wxTextCtrl* m_hotkey;
    wxCheckBox* m_checkUpdates;

    wxCheckBox* m_notifyActivity;
    wxCheckBox* m_notifyNotifications;
    wxCheckBox* m_notifyStarred;
    wxCheckBox* m_notifyWatched;
    wxCheckBox* m_notifyRepoSync;
    wxSpinCtrl* m_refreshInterval;

    wxTextCtrl* m_gitPath;
    wxCheckBox* m_gitOrg;
    wxCheckBox* m_gitRecursive;
    wxCheckBox* m_gitLfs;

    wxCheckBox* m_syncEnabled;
    wxSpinCtrl* m_syncInterval;
    wxCheckBox* m_syncUseTools;
    wxTextCtrl* m_syncToolsPath;

    FilterEditor* m_filterEditor;
    wxListBox* m_mutedList;
    wxTextCtrl* m_mutedEntry;
    ActionBar* m_mutedBar;  // owned by its page
    wxListBox* m_userList;
    ActionBar* m_userBar;   // owned by its page

    // What the dialog edits, and what is saved (to tell whether anything changed).
    std::set<std::string> m_muted, m_savedMuted;
    std::map<std::string, std::set<std::string>> m_userFilters, m_savedUsers;
    std::set<std::string> m_savedVisible;
};

}  // namespace

void ShowOptionsDialog(wxWindow* parent) {
    ShowModalDialog<OptionsDialog>(parent);
}
