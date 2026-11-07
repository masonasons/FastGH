// The application: startup, sign-in, and the macOS Dock.

#include "ui/dialogs.h"
#include "ui/main_frame.h"
#include "ui/ui_common.h"

#include "core/app.h"
#include "version.h"

#include <wx/snglinst.h>
#include <wx/utils.h>

#include <memory>

namespace {

// wxWidgets reports some things it considers worth a message box (a hotkey another
// program owns, a failed clipboard); FastGH says what matters itself.
class SilentLog : public wxLog {
protected:
    void DoLogText(const wxString&) override {}
};

}  // namespace

class FastGHApp : public wxApp {
public:
    bool OnInit() override;
#ifdef __WXOSX__
    // Clicking the Dock icon brings back a hidden or closed window.
    void MacReopenApp() override { mainwin::ShowWindow(); }
#endif

private:
    void VerifyAccounts();
    std::unique_ptr<wxSingleInstanceChecker> m_instance;
};

bool FastGHApp::OnInit() {
    wxDISABLE_ASSERTS_IN_RELEASE_BUILD();
    delete wxLog::SetActiveTarget(new SilentLog());
    SetAppName(APP_NAME);

#ifndef __WXOSX__
    // macOS keeps one copy running itself.
    m_instance = std::make_unique<wxSingleInstanceChecker>("FastGH-" + wxGetUserId());
    if (m_instance->IsAnotherRunning()) {
        wxMessageBox("Another instance of FastGH is already running.", APP_NAME, wxOK | wxICON_WARNING);
        return false;
    }
#endif

    app::LoadPrefs();
#ifdef __WXMSW__
    std::string dark = app::Prefs().GetString("dark_mode", "off");
    if (dark != "off") MSWEnableDarkMode(dark == "on" ? DarkMode_Always : DarkMode_Auto);
#endif

    // Account 0 always exists; later ones only when they were signed in.
    int count = std::max(1, app::Prefs().GetInt("accounts", 1));
    for (int i = 0; i < count; i++) {
        auto account = std::make_shared<GitHubAccount>(i);
        if (i > 0 && !account->HasToken()) continue;
        app::Accounts().push_back(account);
    }
    app::SetCurrent(app::Accounts().front());
    if (!app::Current()->HasToken() && !SignIn(nullptr, *app::Current())) return false;

    wxFrame* frame = mainwin::Create();
    SetTopWindow(frame);
#ifdef __WXOSX__
    frame->Show();
#else
    if (app::Prefs().GetBool("window_shown", true)) frame->Show();
#endif
    // The lists start loading at once; names and token checks happen alongside.
    mainwin::RefreshAll();
    VerifyAccounts();
    if (app::Prefs().GetBool("check_for_updates", true)) CheckForUpdates(true);
    return true;
}

void FastGHApp::VerifyAccounts() {
    for (const auto& account : app::Accounts()) {
        std::shared_ptr<GitHubAccount> a = account;
        RunAsync(mainwin::Get(), [a] { return a->Verify(); },
                 [a](GitHubAccount::VerifyResult result) {
                     if (result != GitHubAccount::VerifyResult::Unauthorized) {
                         if (a == app::Current()) mainwin::RefreshAll();
                         return;
                     }
                     // The token was revoked or expired: sign in again.
                     a->SetToken("");
                     if (SignIn(GetActiveOwner(), *a) && a == app::Current()) mainwin::AccountChanged();
                 });
    }
}

wxIMPLEMENT_APP(FastGHApp);
