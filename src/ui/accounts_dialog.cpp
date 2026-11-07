// Managing signed-in GitHub accounts (a port of GUI/accounts.py).
//
// As in the Python app, which account is current is not saved: FastGH starts
// on the first account.

#include "ui/dialogs.h"

#include "core/app.h"
#include "core/github.h"
#include "ui/main_frame.h"
#include "ui/ui_common.h"

#include <memory>
#include <string>
#include <vector>

namespace {

class AccountsDialog : public BaseDialog {
public:
    explicit AccountsDialog(wxWindow* parent) : BaseDialog(parent, "Accounts", wxSize(450, 350)) {
        m_list = new wxListBox(Panel(), wxID_ANY, wxDefaultPosition, wxDefaultSize, 0, nullptr, wxLB_SINGLE);
        AddLabeled("&Accounts:", m_list, 1);

        m_actions = new ActionBar(Panel());
        Action switchTo{"&Switch To", [this] { SwitchTo(); }, true};
        switchTo.enabled = [this] {
            auto account = SelectedAccount();
            return account && account != app::Current();
        };
        m_actions->Add(switchTo).Shortcut(WXK_RETURN);
        m_actions->Add({"A&dd Account...", [this] { AddAccount(); }, true});
        Action remove{"&Remove...", [this] { Remove(); }, true};
        remove.enabled = [this] { return SelectedAccount() != nullptr; };
        m_actions->Add(remove).Shortcut(WXK_DELETE);
        Sizer()->Add(m_actions->CreateButtons(), 0, wxALL, 10);
        m_actions->AttachContextMenu(m_list);
        m_actions->AttachActivate(m_list);

        m_list->Bind(wxEVT_LISTBOX, [this](wxCommandEvent&) { m_actions->Update(); });

        Fill(-1);
        Finish();
        m_list->SetFocus();
        LoadMissingNames();
    }

private:
    static wxString Label(const GitHubAccount& account) {
        std::string name = account.DisplayName();
        if (name.empty()) name = account.Username();
        if (name.empty()) return wxString::Format("Account %d (not signed in)", account.Index() + 1);
        return U8(name);
    }

    // Lists the accounts, selecting `select` (by position), or the current one when -1.
    void Fill(int select) {
        const auto& accounts = app::Accounts();
        auto current = app::Current();
        m_list->Clear();
        for (size_t i = 0; i < accounts.size(); i++) {
            wxString label = Label(*accounts[i]);
            if (accounts[i] == current) {
                label += " (current)";
                if (select < 0) select = static_cast<int>(i);
            }
            m_list->Append(label);
        }
        if (select >= 0 && select < static_cast<int>(m_list->GetCount())) m_list->SetSelection(select);
        else if (!m_list->IsEmpty()) m_list->SetSelection(0);
        m_actions->Update();
    }

    // Accounts reloaded after a removal (or never verified) have no name yet: fetch them.
    void LoadMissingNames() {
        std::vector<std::shared_ptr<GitHubAccount>> missing;
        for (const auto& account : app::Accounts())
            if (account->HasToken() && account->Username().empty()) missing.push_back(account);
        if (missing.empty()) return;
        RunAsyncVoid(this, [missing] {
            for (const auto& account : missing) account->Verify();
        }, [this] { Fill(Selected(m_list)); });
    }

    std::shared_ptr<GitHubAccount> SelectedAccount() const {
        int i = Selected(m_list);
        const auto& accounts = app::Accounts();
        return i >= 0 && i < static_cast<int>(accounts.size()) ? accounts[i] : nullptr;
    }

    void SwitchTo() {
        auto account = SelectedAccount();
        if (!account || account == app::Current()) return;
        app::SetCurrent(account);
        Fill(-1);
        mainwin::AccountChanged();
    }

    void AddAccount() {
        auto account = app::AddAccount();
        if (!SignIn(this, *account)) {
            // Cancelled or failed: don't leave an empty account behind.
            const auto& accounts = app::Accounts();
            for (size_t i = 0; i < accounts.size(); i++) {
                if (accounts[i] == account) {
                    app::RemoveAccount(static_cast<int>(i));
                    break;
                }
            }
            Fill(-1);
            return;
        }
        // As in Python, the new account is added but not switched to; it is
        // selected so Enter switches.
        const auto& accounts = app::Accounts();
        int index = -1;
        for (size_t i = 0; i < accounts.size(); i++)
            if (accounts[i] == account) index = static_cast<int>(i);
        bool becameCurrent = app::Current() == account;  // the first account
        Fill(index);
        if (becameCurrent) mainwin::AccountChanged();
    }

    void Remove() {
        int index = Selected(m_list);
        auto account = SelectedAccount();
        if (!account) return;
        if (app::Accounts().size() <= 1) {
            ShowError(this, "Cannot remove the only account.");
            return;
        }
        if (!AskYesNo(this, "Remove account '" + Label(*account) + "'?", "Confirm Removal")) return;
        if (!app::RemoveAccount(index)) {
            ShowError(this, "Could not remove the account.");
            return;
        }
        account.reset();
        Fill(-1);
        mainwin::AccountChanged();
        LoadMissingNames();
    }

    wxListBox* m_list;
    ActionBar* m_actions;  // owned by the panel
};

}  // namespace

void ShowAccountsDialog(wxWindow* parent) {
    ShowModalDialog<AccountsDialog>(parent);
}
