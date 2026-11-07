#pragma once

// Helpers shared by FastGH's windows and dialogs.

#include <wx/wx.h>
#include <wx/weakref.h>

#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <thread>
#include <utility>
#include <vector>

// --- Text: the core is UTF-8 std::string, the windows wxString ---
inline wxString U8(const std::string& s) { return wxString::FromUTF8(s.data(), s.size()); }
inline std::string ToU8(const wxString& s) {
    wxScopedCharBuffer buf = s.utf8_str();
    return std::string(buf.data(), buf.length());
}

// --- Work off the UI thread ---
// Runs `work` on a worker thread, then `done` with its result on the UI thread,
// unless `owner` has been destroyed by then (a dialog closed while loading).
//   RunAsync(this, [=] { return account->GetIssues(owner, repo); },
//            [this](std::vector<Issue> issues) { ShowIssues(issues); });
template <typename Work, typename Done>
void RunAsync(wxWindow* owner, Work work, Done done) {
    wxWeakRef<wxWindow> weak(owner);
    // wxWeakRef may only be touched on the UI thread: hand it over in a shared box.
    auto box = std::make_shared<wxWeakRef<wxWindow>>(weak);
    std::thread([work = std::move(work), done = std::move(done), box]() mutable {
        auto result = std::make_shared<decltype(work())>(work());
        wxTheApp->CallAfter([done = std::move(done), box, result]() mutable {
            if (*box) done(std::move(*result));
        });
    }).detach();
}
// For work with no result.
template <typename Work, typename Done>
void RunAsyncVoid(wxWindow* owner, Work work, Done done) {
    auto box = std::make_shared<wxWeakRef<wxWindow>>(owner);
    std::thread([work = std::move(work), done = std::move(done), box]() mutable {
        work();
        wxTheApp->CallAfter([done = std::move(done), box]() mutable {
            if (*box) done();
        });
    }).detach();
}
// Runs `fn` on the UI thread (from any thread).
void RunOnUiThread(std::function<void()> fn);

// --- Windows ---
// The FastGH window that should own a new dialog or message: the active one,
// falling back to the main window.
wxWindow* GetActiveOwner();
// The main window's status bar text (any thread).
void SetStatus(const wxString& text);

// --- Messages ---
void ShowError(wxWindow* parent, const wxString& message, const wxString& title = "Error");
void ShowInfo(wxWindow* parent, const wxString& message, const wxString& title = "FastGH");
// Yes is the default; Escape answers No.
bool AskYesNo(wxWindow* parent, const wxString& question, const wxString& title = "Confirm");
// A single-line text prompt. nullopt when cancelled.
std::optional<wxString> AskText(wxWindow* parent, const wxString& prompt, const wxString& title,
                                const wxString& initial = "");
// A multi-line text prompt (comments, bodies). nullopt when cancelled.
std::optional<wxString> AskMultilineText(wxWindow* parent, const wxString& prompt, const wxString& title,
                                         const wxString& initial = "");
// Save As, with a replace check. Empty when cancelled.
wxString AskSavePath(wxWindow* parent, const wxString& defaultDir, const wxString& defaultName,
                     const wxString& wildcard = "All files (*.*)|*.*");
// A folder. Empty when cancelled.
wxString AskDirectory(wxWindow* parent, const wxString& message, const wxString& initial = "");

// --- System ---
void OpenUrl(const std::string& url);
// Copies and, with `announce`, says so in the status bar (no message box).
bool CopyToClipboard(const wxString& text, bool announce = true);
// Shows the item in Finder / Explorer.
void RevealInFileManager(const wxString& path);

// --- Keys ---
inline bool IsEnterKey(const wxKeyEvent& e) {
    return e.GetKeyCode() == WXK_RETURN || e.GetKeyCode() == WXK_NUMPAD_ENTER;
}

// --- Lists ---
// Replaces a list box's items in one go, keeping the selection (by index) when
// it is still in range, else selecting the first item.
void SetListItems(wxListBox* list, const std::vector<wxString>& items);
// The selected index, or -1.
inline int Selected(const wxListBox* list) {
    int i = list->GetSelection();
    return i == wxNOT_FOUND ? -1 : i;
}

// --- Actions: a few buttons, the rest under "More" ---
//
// A dialog lists what can be done with its item once, as actions. The most
// common get buttons of their own; the rest are in a menu opened by the More
// button (Alt+M, or Space/Enter on it). The list's context menu (right click,
// Shift+F10, the Menu key, VoiceOver's VO+Shift+M) offers all of them, and an
// action's shortcut works from anywhere in the dialog.
//
//   m_actions = new ActionBar(panel);
//   m_actions->Add({"&View", [this] { View(); }, true}).Shortcut(WXK_RETURN);
//   m_actions->Add({"&Comment...", [this] { Comment(); }, true});
//   m_actions->Add({"Open in &Browser", [this] { OpenInBrowser(); }}).Shortcut('O', wxMOD_CONTROL);
//   m_actions->AddSeparator();
//   m_actions->Add({"Copy &URL", [this] { CopyUrl(); }});
//   sizer->Add(m_actions->CreateButtons(), 0, wxALL, 5);
//   m_actions->AttachContextMenu(m_list);
//
// Enabled state and labels are read when a menu opens, while idle, and on
// Update(); call Update() after the selection changes for an immediate refresh.
struct Action {
    wxString label;  // with & for its access key, "..." when it asks for more
    std::function<void()> run;
    bool primary = false;  // a button of its own, else under More
    // Optional: whether it can run now (greyed out when not; hidden from menus when `hideWhenDisabled`).
    std::function<bool()> enabled;
    // Optional: a label that depends on state ("&Star" / "Un&star").
    std::function<wxString()> dynamicLabel;
    bool hideWhenDisabled = false;
};

class ActionBar {
public:
    // `parent` is the panel the buttons go on. The bar belongs to `parent` and is
    // deleted with it: create it with new and never delete it yourself.
    explicit ActionBar(wxWindow* parent);
    ~ActionBar();

    // Returns a handle to set a shortcut on.
    class Handle {
    public:
        // A key that runs the action anywhere in the dialog (Ctrl is Cmd on macOS).
        // WXK_RETURN with no modifiers runs only when a list has the focus.
        // Chain calls to give an action several keys.
        Handle& Shortcut(int keyCode, int modifiers = wxMOD_NONE);
    private:
        friend class ActionBar;
        Handle(ActionBar* bar, size_t index) : m_bar(bar), m_index(index) {}
        ActionBar* m_bar;
        size_t m_index;
    };
    Handle Add(Action action);
    void AddSeparator();  // in menus only

    // The buttons (primary actions, then More when anything is under it, then
    // Close when `withClose`), in a horizontal sizer. Close has wxID_CANCEL, so
    // Escape closes the dialog.
    wxSizer* CreateButtons(bool withClose = true);

    // Right click / context menu key on `window` shows every action.
    void AttachContextMenu(wxWindow* window);
    // Enter / double click on `list` runs the first primary action that is enabled.
    void AttachActivate(wxListBox* list);

    // Re-reads enabled states and dynamic labels for the buttons.
    void Update();
    void ShowMoreMenu();
    void ShowAllMenu(wxWindow* at);

private:
    struct Impl;
    std::unique_ptr<Impl> m;
};

// Makes `label` the name screen readers give `control` (VoiceOver, NVDA, JAWS),
// whichever was created first. AddLabeled does this; use it for labels laid out by hand.
void LabelControl(wxStaticText* label, wxWindow* control);

// A dialog with the usual FastGH setup: a panel and vertical sizer to fill,
// Escape to close, sized and centred over its parent when shown.
class BaseDialog : public wxDialog {
public:
    BaseDialog(wxWindow* parent, const wxString& title, const wxSize& size = wxSize(800, 600));
    wxPanel* Panel() const { return m_panel; }
    wxBoxSizer* Sizer() const { return m_sizer; }
    // Adds the label text (give it its own colon: "&Branch:") and the control under it (screen readers name the
    // control from the label on both systems).
    void AddLabeled(const wxString& label, wxWindow* control, int proportion = 0);
    // Call at the end of the constructor.
    void Finish();

protected:
    wxPanel* m_panel;
    wxBoxSizer* m_sizer;
};

// Shows a dialog modally and destroys it afterwards.
template <typename Dialog, typename... Args>
int ShowModalDialog(Args&&... args) {
    auto* dlg = new Dialog(std::forward<Args>(args)...);
    int result = dlg->ShowModal();
    dlg->Destroy();
    return result;
}

