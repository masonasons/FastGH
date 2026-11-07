// Signing in with GitHub's device flow: show a code, the user enters it on
// github.com, FastGH polls until it is authorised.

#include "ui/dialogs.h"
#include "ui/ui_common.h"

#include "core/github.h"

namespace {

class SignInDialog : public BaseDialog {
public:
    SignInDialog(wxWindow* parent, GitHubAccount& account)
        : BaseDialog(parent, "Sign in to GitHub", wxSize(480, 260)), m_account(account) {
        m_text = new wxTextCtrl(m_panel, wxID_ANY, "Asking GitHub for a sign-in code...", wxDefaultPosition,
                                wxSize(-1, 110), wxTE_MULTILINE | wxTE_READONLY);
        AddLabeled("&Status:", m_text, 1);
        auto* buttons = new wxBoxSizer(wxHORIZONTAL);
        m_copy = new wxButton(m_panel, wxID_ANY, "&Copy Code");
        m_open = new wxButton(m_panel, wxID_ANY, "&Open GitHub");
        buttons->Add(m_copy, 0, wxRIGHT, 5);
        buttons->Add(m_open, 0, wxRIGHT, 5);
        buttons->Add(new wxButton(m_panel, wxID_CANCEL, "Cancel"));
        m_sizer->Add(buttons, 0, wxALL, 5);
        m_copy->Disable();
        m_open->Disable();
        m_copy->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { CopyToClipboard(U8(m_code.userCode)); });
        m_open->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { OpenUrl(m_code.verificationUri); });
        m_timer.Bind(wxEVT_TIMER, [this](wxTimerEvent&) { Poll(); });
        Finish();
        m_text->SetFocus();

        RunAsync(this,
                 [] {
                     std::string error;
                     auto code = RequestDeviceCode(&error);
                     return std::make_pair(code, error);
                 },
                 [this](std::pair<std::optional<DeviceCode>, std::string> result) {
                     if (!result.first) {
                         ShowError(this, U8("Failed to get a sign-in code: " + result.second), "Authentication Error");
                         EndModal(wxID_CANCEL);
                         return;
                     }
                     m_code = *result.first;
                     m_text->SetValue(U8("Enter this code on GitHub and authorize FastGH:\n\nCode: " +
                                         m_code.userCode + "\nURL: " + m_code.verificationUri +
                                         "\n\nThe code has been copied, and GitHub opened in your browser."));
                     m_copy->Enable();
                     m_open->Enable();
                     CopyToClipboard(U8(m_code.userCode), false);
                     OpenUrl(m_code.verificationUri);
                     m_deadline = wxGetLocalTime() + m_code.expiresIn;
                     m_timer.StartOnce(m_code.interval * 1000);
                 });
    }

private:
    void Poll() {
        if (wxGetLocalTime() > m_deadline) {
            ShowError(this, "Authorization timed out. Please try again.", "Authentication Error");
            EndModal(wxID_CANCEL);
            return;
        }
        DeviceCode code = m_code;
        RunAsync(this,
                 [code] {
                     std::string token, error;
                     DevicePollResult r = PollDeviceToken(code, &token, &error);
                     return std::make_tuple(r, token, error);
                 },
                 [this](std::tuple<DevicePollResult, std::string, std::string> result) {
                     auto [status, token, error] = result;
                     switch (status) {
                         case DevicePollResult::Success:
                             m_account.SetToken(token);
                             EndModal(wxID_OK);
                             return;
                         case DevicePollResult::Expired:
                             ShowError(this, "Authorization expired. Please try again.", "Authentication Error");
                             EndModal(wxID_CANCEL);
                             return;
                         case DevicePollResult::Denied:
                             ShowError(this, "Authorization denied.", "Authentication Error");
                             EndModal(wxID_CANCEL);
                             return;
                         case DevicePollResult::Error:
                             ShowError(this, U8("Sign-in failed: " + error), "Authentication Error");
                             EndModal(wxID_CANCEL);
                             return;
                         case DevicePollResult::SlowDown:
                             m_code.interval += 5;
                             [[fallthrough]];
                         case DevicePollResult::Pending:
                             m_timer.StartOnce(m_code.interval * 1000);
                             return;
                     }
                 });
    }

    GitHubAccount& m_account;
    DeviceCode m_code;
    long m_deadline = 0;
    wxTextCtrl* m_text;
    wxButton* m_copy;
    wxButton* m_open;
    wxTimer m_timer;
};

}  // namespace

bool SignIn(wxWindow* parent, GitHubAccount& account) {
    if (ShowModalDialog<SignInDialog>(parent, account) != wxID_OK) return false;
    // Fills in the account's name; a failure here still leaves a token to try later.
    account.Verify();
    return account.HasToken();
}
