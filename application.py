"""Main application class that holds all global state."""

import sys
import platform
import os
import threading
import webbrowser
import config
import wx
from version import APP_NAME, APP_SHORTNAME, APP_VERSION, APP_AUTHOR

shortname = APP_SHORTNAME
name = APP_NAME
version = APP_VERSION
author = APP_AUTHOR


class Application:
    """Main application class that holds all global state and utility methods."""

    _instance = None

    def __init__(self):
        self.accounts = []
        self.prefs = None
        self.confpath = ""
        self.errors = []
        self.currentAccount = None
        self._initialized = False

    @classmethod
    def get_instance(cls):
        """Get the singleton application instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self):
        """Initialize the application - load preferences and accounts."""
        if self._initialized:
            return

        from GUI import main
        import github_api

        self.prefs = config.Config(name="FastGH", autosave=True)
        # In portable mode, userdata folder is already app-specific, don't add /FastGH
        if config.is_portable_mode():
            self.confpath = self.prefs._user_config_home
        else:
            self.confpath = self.prefs._user_config_home + "/FastGH"

        # Redirect stderr to log file on Windows
        if platform.system() != "Darwin":
            try:
                f = open(os.path.join(self.confpath, "errors.log"), "a")
                sys.stderr = f
            except:
                pass

        # Load preferences with defaults
        self.prefs.accounts = self.prefs.get("accounts", 1)
        self.prefs.dark_mode = self.prefs.get("dark_mode", "off")
        self.prefs.window_shown = self.prefs.get("window_shown", True)

        # Repository display template
        self.prefs.repoTemplate = self.prefs.get(
            "repoTemplate",
            "$full_name$ - $description$ | Stars: $stars$ | Forks: $forks$ | Issues: $open_issues$ | $language$ | Updated $updated_at$"
        )

        # Commit limit (0 = all)
        self.prefs.commit_limit = self.prefs.get("commit_limit", 0)

        # Download location (default to user's Downloads folder)
        import os
        default_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        self.prefs.download_location = self.prefs.get("download_location", default_downloads)

        # Global hotkey for show/hide window (default Ctrl+Alt+G)
        self.prefs.global_hotkey = self.prefs.get("global_hotkey", "control+alt+g")

        # Git path for cloning repositories (default to user's home directory)
        default_git_path = os.path.join(os.path.expanduser("~"), "git")
        self.prefs.git_path = self.prefs.get("git_path", default_git_path)

        # OS notification settings
        self.prefs.notify_activity = self.prefs.get("notify_activity", False)
        self.prefs.notify_notifications = self.prefs.get("notify_notifications", False)
        self.prefs.notify_starred = self.prefs.get("notify_starred", False)
        self.prefs.notify_watched = self.prefs.get("notify_watched", False)

        # Auto-refresh interval in minutes (0 = disabled)
        self.prefs.auto_refresh_interval = self.prefs.get("auto_refresh_interval", 0)

        # Load accounts
        if self.prefs.accounts > 0:
            # First account must be on main thread (handles auth dialogs)
            self.add_session()

            # Load remaining accounts
            if self.prefs.accounts > 1:
                for i in range(1, self.prefs.accounts):
                    if self._is_account_configured(i):
                        self.add_session(i)
                    else:
                        self.add_session(i)

        self._initialized = True

    def add_session(self, index=None):
        """Add a new GitHub account session."""
        import github_api
        import wx
        if index is None:
            index = len(self.accounts)
        try:
            account = github_api.GitHubAccount(self, index)
            self.accounts.append(account)
            if self.currentAccount is None:
                self.currentAccount = account
        except github_api.AccountSetupCancelled:
            # User cancelled account setup - exit gracefully if no accounts
            if len(self.accounts) == 0:
                wx.CallAfter(wx.Exit)
                return

    def _is_account_configured(self, index):
        """Check if an account has credentials saved."""
        try:
            if config.is_portable_mode():
                prefs = config.Config(name="account" + str(index), autosave=False, save_on_exit=False)
            else:
                prefs = config.Config(name="FastGH/account" + str(index), autosave=False, save_on_exit=False)
            return bool(prefs.get("access_token", ""))
        except:
            return False

    def remove_account(self, index):
        """Remove an account by index."""
        import shutil
        if index < 0 or index >= len(self.accounts):
            return False

        # Remove from accounts list
        removed = self.accounts.pop(index)

        # Delete config folder
        if config.is_portable_mode():
            config_path = os.path.join(self.confpath, f"account{index}")
        else:
            config_path = os.path.join(self.confpath, f"account{index}")

        if os.path.exists(config_path):
            shutil.rmtree(config_path)

        # Shift remaining account folders down
        for j in range(index + 1, self.prefs.accounts):
            old_path = os.path.join(self.confpath, f"account{j}")
            new_path = os.path.join(self.confpath, f"account{j-1}")
            if os.path.exists(old_path):
                shutil.move(old_path, new_path)

        self.prefs.accounts -= 1

        # Update current account if needed
        if self.currentAccount == removed:
            self.currentAccount = self.accounts[0] if self.accounts else None

        return True

    def question(self, title, text, parent=None):
        """Show a yes/no question dialog."""
        dlg = wx.MessageDialog(parent, text, title, wx.YES_NO | wx.ICON_QUESTION)
        dlg.Raise()
        dlg.RequestUserAttention()
        result = dlg.ShowModal()
        dlg.Destroy()
        return 1 if result == wx.ID_YES else 2

    def alert(self, message, caption="", parent=None):
        """Show an alert dialog."""
        dlg = wx.MessageDialog(parent, message, caption, wx.OK)
        dlg.Raise()
        dlg.RequestUserAttention()
        dlg.ShowModal()
        dlg.Destroy()

    def handle_error(self, error, name="Unknown"):
        """Handle errors."""
        error_msg = str(error)
        self.errors.append(f"Error in {name}: {error_msg}")
        print(f"Error in {name}: {error_msg}")

    def openURL(self, url):
        """Open a URL in the default browser."""
        if platform.system() != "Darwin":
            webbrowser.open(url)
        else:
            os.system(f"open {url}")


# Convenience function to get the app instance
def get_app():
    return Application.get_instance()
