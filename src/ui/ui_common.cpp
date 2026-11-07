#include "ui/ui_common.h"
#include "ui/main_frame.h"
#include "platform/platform.h"

#include <wx/clipbrd.h>
#include <wx/dirdlg.h>
#include <wx/filedlg.h>
#include <wx/filename.h>
#include <wx/textdlg.h>
#include <wx/utils.h>
#ifdef __WXOSX__
#include <wx/osx/private.h>
#endif

#include <algorithm>
#include <cctype>
#include <set>

// --- Threads and windows ---

void RunOnUiThread(std::function<void()> fn) {
    if (wxTheApp) wxTheApp->CallAfter(std::move(fn));
}

wxWindow* GetActiveOwner() {
    if (wxWindow* active = wxGetActiveWindow()) {
        wxWindow* top = wxGetTopLevelParent(active);
        if (top && top->IsShown()) return top;
    }
    return mainwin::Get();
}

void SetStatus(const wxString& text) {
    auto apply = [text]() {
        if (wxFrame* frame = mainwin::Get()) {
            if (wxStatusBar* bar = frame->GetStatusBar()) bar->SetStatusText(text);
        }
    };
    if (wxThread::IsMain()) apply();
    else RunOnUiThread(apply);
}

// --- Messages ---

void ShowError(wxWindow* parent, const wxString& message, const wxString& title) {
    wxMessageDialog(parent, message, title, wxOK | wxICON_ERROR).ShowModal();
}

void ShowInfo(wxWindow* parent, const wxString& message, const wxString& title) {
    wxMessageDialog(parent, message, title, wxOK | wxICON_INFORMATION).ShowModal();
}

bool AskYesNo(wxWindow* parent, const wxString& question, const wxString& title) {
    wxMessageDialog dlg(parent, question, title, wxYES_NO | wxYES_DEFAULT | wxICON_QUESTION);
    return dlg.ShowModal() == wxID_YES;
}

std::optional<wxString> AskText(wxWindow* parent, const wxString& prompt, const wxString& title,
                                const wxString& initial) {
    wxTextEntryDialog dlg(parent, prompt, title, initial);
    if (dlg.ShowModal() != wxID_OK) return std::nullopt;
    return dlg.GetValue();
}

std::optional<wxString> AskMultilineText(wxWindow* parent, const wxString& prompt, const wxString& title,
                                         const wxString& initial) {
    wxTextEntryDialog dlg(parent, prompt, title, initial, wxTextEntryDialogStyle | wxTE_MULTILINE);
    dlg.SetSize(wxSize(560, 380));
    dlg.CentreOnParent();
    if (dlg.ShowModal() != wxID_OK) return std::nullopt;
    return dlg.GetValue();
}

wxString AskSavePath(wxWindow* parent, const wxString& defaultDir, const wxString& defaultName,
                     const wxString& wildcard) {
    wxFileDialog dlg(parent, "Save As", defaultDir, defaultName, wildcard, wxFD_SAVE | wxFD_OVERWRITE_PROMPT);
    return dlg.ShowModal() == wxID_OK ? dlg.GetPath() : wxString();
}

wxString AskDirectory(wxWindow* parent, const wxString& message, const wxString& initial) {
    wxDirDialog dlg(parent, message, initial, wxDD_DEFAULT_STYLE);
    return dlg.ShowModal() == wxID_OK ? dlg.GetPath() : wxString();
}

// --- System ---

void OpenUrl(const std::string& url) {
    if (!url.empty()) wxLaunchDefaultBrowser(U8(url));
}

bool CopyToClipboard(const wxString& text, bool announce) {
    wxClipboardLocker locker;
    if (!locker) return false;
    bool ok = wxTheClipboard->SetData(new wxTextDataObject(text));
    if (ok && announce) {
        SetStatus("Copied: " + text);
        // The status bar is out of reach while a dialog is open: say it too.
        platform::Announce(ToU8("Copied " + (text.length() > 80 ? text.Left(77) + "..." : text)));
    }
    return ok;
}

void RevealInFileManager(const wxString& path) {
#ifdef __WXMSW__
    wxExecute("explorer.exe /select,\"" + path + "\"", wxEXEC_ASYNC);
#elif defined(__WXOSX__)
    const char* argv[] = {"open", "-R", nullptr, nullptr};
    wxScopedCharBuffer p = path.utf8_str();
    argv[2] = p.data();
    wxExecute(argv, wxEXEC_ASYNC);
#else
    wxLaunchDefaultApplication(wxFileName(path).GetPath());
#endif
}

// --- Lists ---

void SetListItems(wxListBox* list, const std::vector<wxString>& items) {
    // An unchanged refresh must not touch the list: screen readers would re-read it.
    if (list->GetCount() == items.size()) {
        bool same = true;
        for (unsigned i = 0; i < items.size() && same; i++) same = list->GetString(i) == items[i];
        if (same) return;
    }
    int selection = list->GetSelection();
    wxArrayString array;
    array.reserve(items.size());
    for (const auto& item : items) array.push_back(item);
    list->Set(array);
    if (items.empty()) return;
    list->SetSelection(selection != wxNOT_FOUND && selection < static_cast<int>(items.size()) ? selection : 0);
}

// --- ActionBar ---

namespace {

// The letter after '&' in a label, lowercased, or 0.
int AccessKey(const wxString& label) {
    for (size_t i = 0; i + 1 < label.size(); i++) {
        if (label[i] == '&') {
            if (label[i + 1] == '&') {
                i++;
                continue;
            }
            return std::tolower(static_cast<int>(label[i + 1].GetValue()));
        }
    }
    return 0;
}

// "&More" with the first letter of `word` no other label uses; plain `word` if none is free.
wxString WithFreeAccessKey(const wxString& word, const std::set<int>& used) {
    for (size_t i = 0; i < word.size(); i++) {
        int c = std::tolower(static_cast<int>(word[i].GetValue()));
        if (std::isalpha(c) && !used.count(c)) return word.substr(0, i) + "&" + word.substr(i);
    }
    return word;
}

}  // namespace

struct ActionBar::Impl {
    struct Entry {
        Action action;
        bool separator = false;
        std::vector<std::pair<int, int>> keys;  // (key code, modifiers)
        wxButton* button = nullptr;
    };
    wxWindow* parent;
    std::vector<Entry> entries;
    wxButton* more = nullptr;

    wxString Label(const Entry& e) const { return e.action.dynamicLabel ? e.action.dynamicLabel() : e.action.label; }
    bool Enabled(const Entry& e) const { return !e.action.enabled || e.action.enabled(); }

    // Runs after the current event, so a modal dialog never opens from inside a
    // key or menu handler (which crashes Cocoa).
    void Run(size_t index) {
        if (index >= entries.size() || !Enabled(entries[index])) return;
        auto fn = entries[index].action.run;
        if (fn) parent->CallAfter([fn] { fn(); });
    }

    void ShowMenu(wxWindow* at, bool primaryToo, const wxPoint& pos) {
        wxMenu menu;
        bool pendingSeparator = false;
        bool any = false;
        for (size_t i = 0; i < entries.size(); i++) {
            const Entry& e = entries[i];
            if (e.separator) {
                pendingSeparator = any;
                continue;
            }
            if (!primaryToo && e.action.primary) continue;
            bool enabled = Enabled(e);
            if (!enabled && e.action.hideWhenDisabled) continue;
            if (pendingSeparator) menu.AppendSeparator();
            pendingSeparator = false;
            wxString label = Label(e);
            if (!e.keys.empty()) {
                wxAcceleratorEntry accel(e.keys[0].second, e.keys[0].first);
                // Shown, not bound: the menu bar must not take these keys from the dialog.
                label += "\t" + accel.ToString();
            }
            wxMenuItem* item = menu.Append(static_cast<int>(1000 + i), label);
            item->Enable(enabled);
            any = true;
        }
        if (!any) return;
        int id = at->GetPopupMenuSelectionFromUser(menu, pos);
        if (id >= 1000) Run(static_cast<size_t>(id - 1000));
    }

    int ActivateIndex() const {
        for (size_t i = 0; i < entries.size(); i++) {
            const Entry& e = entries[i];
            for (const auto& [key, mods] : e.keys)
                if (key == WXK_RETURN && mods == wxMOD_NONE && Enabled(e)) return static_cast<int>(i);
        }
        for (size_t i = 0; i < entries.size(); i++) {
            if (entries[i].action.primary && !entries[i].separator && Enabled(entries[i])) return static_cast<int>(i);
        }
        return -1;
    }

    void OnCharHook(wxKeyEvent& event) {
        int code = event.GetKeyCode();
        if (code == WXK_NUMPAD_ENTER) code = WXK_RETURN;
        int mods = event.GetModifiers();
        for (size_t i = 0; i < entries.size(); i++) {
            const Entry& e = entries[i];
            bool match = false;
            for (const auto& key : e.keys) match = match || (key.first == code && key.second == mods);
            if (!match) continue;
            // Plain Enter belongs to buttons and text fields; only a list hands it over.
            if (code == WXK_RETURN && mods == wxMOD_NONE && !wxDynamicCast(wxWindow::FindFocus(), wxListBox))
                continue;
            if (!Enabled(e)) continue;
            Run(i);
            return;
        }
        event.Skip();
    }
};

ActionBar::ActionBar(wxWindow* parent) : m(std::make_unique<Impl>()) {
    m->parent = parent;
    parent->Bind(wxEVT_DESTROY, [this, parent](wxWindowDestroyEvent& event) {
        event.Skip();
        if (event.GetEventObject() == parent) delete this;
    });
    if (wxWindow* top = wxGetTopLevelParent(parent)) {
        top->Bind(wxEVT_CHAR_HOOK, [this](wxKeyEvent& event) { m->OnCharHook(event); });
    }
}

ActionBar::~ActionBar() = default;

ActionBar::Handle& ActionBar::Handle::Shortcut(int keyCode, int modifiers) {
    auto& e = m_bar->m->entries[m_index];
    e.keys.emplace_back(keyCode >= 'a' && keyCode <= 'z' ? keyCode - 'a' + 'A' : keyCode, modifiers);
    return *this;
}

ActionBar::Handle ActionBar::Add(Action action) {
    Impl::Entry e;
    e.action = std::move(action);
    m->entries.push_back(std::move(e));
    return Handle(this, m->entries.size() - 1);
}

void ActionBar::AddSeparator() {
    Impl::Entry e;
    e.separator = true;
    m->entries.push_back(std::move(e));
}

wxSizer* ActionBar::CreateButtons(bool withClose) {
    auto* sizer = new wxBoxSizer(wxHORIZONTAL);
    std::set<int> used;
    bool anyMore = false;
    for (auto& e : m->entries) {
        if (e.separator) continue;
        if (!e.action.primary) {
            anyMore = true;
            continue;
        }
        wxString label = m->Label(e);
        used.insert(AccessKey(label));
        e.button = new wxButton(m->parent, wxID_ANY, label);
        sizer->Add(e.button, 0, wxRIGHT, 5);
        size_t index = &e - &m->entries[0];
        e.button->Bind(wxEVT_BUTTON, [this, index](wxCommandEvent&) { m->Run(index); });
        e.button->Bind(wxEVT_UPDATE_UI, [this, index](wxUpdateUIEvent& ev) {
            const auto& entry = m->entries[index];
            ev.Enable(m->Enabled(entry));
            if (entry.action.dynamicLabel) ev.SetText(entry.action.dynamicLabel());
        });
    }
    if (anyMore) {
        m->more = new wxButton(m->parent, wxID_ANY, WithFreeAccessKey("More", used) + "...");
        used.insert(AccessKey(m->more->GetLabel()));
        sizer->Add(m->more, 0, wxRIGHT, 5);
        m->more->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { ShowMoreMenu(); });
    }
    if (withClose) {
        wxString label = used.count('o') ? wxString("Close") : wxString("Cl&ose");
        sizer->Add(new wxButton(m->parent, wxID_CANCEL, label), 0);
    }
    return sizer;
}

void ActionBar::AttachContextMenu(wxWindow* window) {
    window->Bind(wxEVT_CONTEXT_MENU, [this, window](wxContextMenuEvent& event) {
        wxPoint pos = event.GetPosition();
        // From the keyboard there is no mouse position: put it at the selected row.
        pos = pos == wxDefaultPosition ? wxPoint(10, 10) : window->ScreenToClient(pos);
        m->ShowMenu(window, true, pos);
    });
}

void ActionBar::AttachActivate(wxListBox* list) {
    list->Bind(wxEVT_LISTBOX_DCLICK, [this](wxCommandEvent&) {
        int i = m->ActivateIndex();
        if (i >= 0) m->Run(static_cast<size_t>(i));
    });
    list->Bind(wxEVT_CHAR_HOOK, [this](wxKeyEvent& event) {
        if (IsEnterKey(event) && event.GetModifiers() == wxMOD_NONE) {
            int i = m->ActivateIndex();
            if (i >= 0) {
                m->Run(static_cast<size_t>(i));
                return;
            }
        }
        event.Skip();
    });
}

void ActionBar::Update() {
    for (auto& e : m->entries) {
        if (!e.button) continue;
        e.button->Enable(m->Enabled(e));
        if (e.action.dynamicLabel) {
            wxString label = e.action.dynamicLabel();
            if (e.button->GetLabel() != label) e.button->SetLabel(label);
        }
    }
}

void ActionBar::ShowMoreMenu() {
    wxWindow* at = m->more ? static_cast<wxWindow*>(m->more) : m->parent;
    wxPoint pos = m->more ? wxPoint(0, m->more->GetSize().y) : wxDefaultPosition;
    m->ShowMenu(at, false, pos);
}

void ActionBar::ShowAllMenu(wxWindow* at) {
    m->ShowMenu(at, true, wxDefaultPosition);
}

// --- BaseDialog ---

BaseDialog::BaseDialog(wxWindow* parent, const wxString& title, const wxSize& size)
    : wxDialog(parent, wxID_ANY, title, wxDefaultPosition, size, wxDEFAULT_DIALOG_STYLE | wxRESIZE_BORDER) {
    m_panel = new wxPanel(this);
    m_sizer = new wxBoxSizer(wxVERTICAL);
    SetEscapeId(wxID_CANCEL);
}

void LabelControl(wxStaticText* label, wxWindow* control) {
    // Screen readers name a control after the label just before it among its
    // siblings; this label was made after its control, so put it first (Windows
    // reads that order, and so does Tab).
    label->MoveBeforeInTabOrder(control);
#ifdef __WXOSX__
    // On macOS the link is made once, when the control is created, to whatever
    // label preceded it then (the previous control's): point it at its own.
    if (wxOSXWidgetImpl* peer = control->GetPeer()) {
        if (wxOSXWidgetImpl* labelPeer = label->GetLabelPeer()) peer->SetAccessibilityTitleElement(labelPeer);
    }
#endif
}

void BaseDialog::AddLabeled(const wxString& label, wxWindow* control, int proportion) {
    auto* text = new wxStaticText(m_panel, wxID_ANY, label);
    LabelControl(text, control);
    m_sizer->Add(text, 0, wxLEFT | wxRIGHT | wxTOP, 5);
    m_sizer->Add(control, proportion, wxEXPAND | wxALL, 5);
}

void BaseDialog::Finish() {
    m_panel->SetSizer(m_sizer);
    auto* outer = new wxBoxSizer(wxVERTICAL);
    outer->Add(m_panel, 1, wxEXPAND);
    SetSizer(outer);
    CentreOnParent();
}
