"""Main application class that holds all global state."""

import sys
import platform
import os
import re
import json
import threading
import webbrowser
import tempfile
import shutil
import config
import wx
import requests
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

        # Git clone options
        self.prefs.git_use_org_structure = self.prefs.get("git_use_org_structure", False)
        self.prefs.git_clone_recursive = self.prefs.get("git_clone_recursive", False)

        # OS notification settings
        self.prefs.notify_activity = self.prefs.get("notify_activity", False)
        self.prefs.notify_notifications = self.prefs.get("notify_notifications", False)
        self.prefs.notify_starred = self.prefs.get("notify_starred", False)
        self.prefs.notify_watched = self.prefs.get("notify_watched", False)

        # Auto-refresh interval in minutes (0 = disabled)
        self.prefs.auto_refresh_interval = self.prefs.get("auto_refresh_interval", 0)

        # Check for updates on startup
        self.prefs.check_for_updates = self.prefs.get("check_for_updates", True)

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

    def question_from_thread(self, title, text):
        """Show a question dialog from a background thread. Returns 1 for Yes, 2 for No."""
        result = [None]
        event = threading.Event()
        def show_dialog():
            result[0] = self.question(title, text)
            event.set()
        wx.CallAfter(show_dialog)
        event.wait()
        return result[0]

    def alert_from_thread(self, message, caption=""):
        """Show an alert dialog from a background thread."""
        event = threading.Event()
        def show_dialog():
            self.alert(message, caption)
            event.set()
        wx.CallAfter(show_dialog)
        event.wait()

    def _get_local_build_commit(self):
        """Get the commit SHA from the build_info.txt file."""
        possible_paths = []

        if getattr(sys, 'frozen', False):
            # Frozen app - check _MEIPASS first, then app directory
            if hasattr(sys, '_MEIPASS'):
                possible_paths.append(os.path.join(sys._MEIPASS, 'build_info.txt'))
            possible_paths.append(os.path.join(os.path.dirname(sys.executable), 'build_info.txt'))
        else:
            # Running from source
            possible_paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_info.txt'))

        for path in possible_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        return f.read().strip()
                except:
                    pass
        return None

    def download_file_to(self, url, dest_path, progress_callback=None):
        """Download a file to a specific path with optional progress callback."""
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks
            with open(dest_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)

    def cfu(self, silent=True):
        """Check for updates."""
        # Don't run auto-updater when running from source
        if not getattr(sys, 'frozen', False):
            if not silent:
                self.alert("Auto-updater is only available in compiled builds.\n\nWhen running from source, use git pull to update.", "Update Check")
            return

        try:
            # Get releases from GitHub
            releases = json.loads(requests.get(
                "https://api.github.com/repos/masonasons/FastGH/releases",
                headers={"accept": "application/vnd.github.v3+json"}
            ).content.decode())

            if not releases:
                if not silent:
                    self.alert_from_thread("No releases found.", "Update Check")
                return

            # Get the first release (most recent)
            latest = releases[0]
            body = latest.get('body', '')

            # Parse commit SHA from release body
            commit_match = re.search(r'Automated build from commit\s+([a-f0-9]+)', body)
            release_commit = commit_match.group(1) if commit_match else None

            # Parse version from release body
            version_match = re.search(r'\*\*Version:\*\*\s*(\d+\.\d+\.\d+)', body)
            latest_version = version_match.group(1) if version_match else latest.get('tag_name', 'unknown')

            # Get local build commit
            local_commit = self._get_local_build_commit()

            # Determine if update is available
            update_available = False

            if release_commit and local_commit:
                update_available = release_commit != local_commit
            else:
                # Fallback to version comparison
                def parse_version(v):
                    return tuple(int(x) for x in v.replace('v', '').split('.'))
                try:
                    current_ver = parse_version(version)
                    latest_ver = parse_version(latest_version)
                    update_available = latest_ver > current_ver
                except:
                    pass

            if update_available:
                message = "There is an update available.\n\n"
                message += f"Your version: {version}"
                if local_commit:
                    message += f" (commit {local_commit[:8]})"
                message += f"\nLatest version: {latest_version}"
                if release_commit:
                    message += f" (commit {release_commit[:8]})"
                message += "\n\nDo you want to download and install the update?"

                ud = self.question_from_thread("Update available: " + latest_version, message)
                if ud == 1:
                    for asset in latest['assets']:
                        asset_name = asset['name'].lower()
                        if platform.system() == "Windows" and 'windows' in asset_name and asset_name.endswith('.zip'):
                            threading.Thread(target=self.download_update, args=[asset['browser_download_url']], daemon=True).start()
                            return
                        elif platform.system() == "Darwin" and asset_name.endswith('.dmg'):
                            threading.Thread(target=self.download_update, args=[asset['browser_download_url']], daemon=True).start()
                            return
                    self.alert_from_thread("A download for this version could not be found for your platform.", "Error")
            else:
                if not silent:
                    message = f"You are running the latest version: {version}"
                    if local_commit:
                        message += f" (commit {local_commit[:8]})"
                    self.alert_from_thread("No updates available!\n\n" + message, "No Update Available")
        except Exception as e:
            if not silent:
                self.alert_from_thread(f"Error checking for updates: {e}", "Update Check Error")

    def download_update(self, url):
        """Download and install an update."""
        temp_dir = tempfile.gettempdir()

        if platform.system() == "Windows":
            if getattr(sys, 'frozen', False):
                app_dir = os.path.dirname(sys.executable)
            else:
                app_dir = os.path.dirname(os.path.abspath(__file__))

            zip_path = os.path.join(temp_dir, "FastGH-update.zip")
            final_zip_path = os.path.join(app_dir, "FastGH-update.zip")
            extract_dir = os.path.join(app_dir, "FastGH-update")

            progress_data = {'dialog': None, 'cancelled': False}

            def create_progress_dialog():
                progress_data['dialog'] = wx.ProgressDialog(
                    "Downloading Update",
                    "Downloading FastGH update...",
                    maximum=100,
                    style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME
                )
                progress_data['dialog'].Raise()

            def update_progress(downloaded, total):
                if progress_data['dialog'] and total > 0:
                    percent = int((downloaded / total) * 100)
                    mb_downloaded = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    def do_update():
                        if progress_data['dialog']:
                            cont, _ = progress_data['dialog'].Update(
                                percent,
                                f"Downloading: {mb_downloaded:.1f} MB / {mb_total:.1f} MB"
                            )
                            if not cont:
                                progress_data['cancelled'] = True
                    wx.CallAfter(do_update)

            def close_progress_dialog():
                if progress_data['dialog']:
                    progress_data['dialog'].Destroy()
                    progress_data['dialog'] = None

            event = threading.Event()
            def create_and_signal():
                create_progress_dialog()
                event.set()
            wx.CallAfter(create_and_signal)
            event.wait()

            try:
                # Remove old update files
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                if os.path.exists(final_zip_path):
                    os.remove(final_zip_path)
                if os.path.exists(extract_dir):
                    shutil.rmtree(extract_dir)

                # Download the zip file
                self.download_file_to(url, zip_path, progress_callback=update_progress)

                if progress_data['cancelled']:
                    wx.CallAfter(close_progress_dialog)
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
                    return

                wx.CallAfter(close_progress_dialog)

                # Move from temp to app directory
                shutil.move(zip_path, final_zip_path)

                # Create updater batch script
                batch_path = os.path.join(app_dir, "updater.bat")
                exe_name = "FastGH.exe" if getattr(sys, 'frozen', False) else "python.exe"

                batch_content = f'''@echo off
echo Waiting for FastGH to close...
timeout /t 2 /nobreak >nul

echo Extracting update...
powershell -Command "Expand-Archive -Path '{final_zip_path}' -DestinationPath '{extract_dir}' -Force"

echo Installing update...
rem The zip contains a FastGH folder inside, so copy from there
xcopy /s /y /q "{extract_dir}\\FastGH\\*" "{app_dir}\\"

echo Cleaning up...
rmdir /s /q "{extract_dir}"
del "{final_zip_path}"

echo Starting FastGH...
start "" "{os.path.join(app_dir, exe_name)}"

echo Update complete!
del "%~f0"
'''
                with open(batch_path, 'w') as f:
                    f.write(batch_content)

                self.alert_from_thread("Update ready. FastGH will now restart.", "Update")
                os.startfile(batch_path)
                wx.CallAfter(wx.Exit)

            except Exception as e:
                wx.CallAfter(close_progress_dialog)
                self.alert_from_thread(f"Failed to download or apply update: {e}", "Update Error")

        else:
            # macOS
            progress_data = {'dialog': None, 'cancelled': False}

            def create_progress_dialog():
                progress_data['dialog'] = wx.ProgressDialog(
                    "Downloading Update",
                    "Downloading FastGH update...",
                    maximum=100,
                    style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME
                )
                progress_data['dialog'].Raise()

            def update_progress(downloaded, total):
                if progress_data['dialog'] and total > 0:
                    percent = int((downloaded / total) * 100)
                    mb_downloaded = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    def do_update():
                        if progress_data['dialog']:
                            cont, _ = progress_data['dialog'].Update(
                                percent,
                                f"Downloading: {mb_downloaded:.1f} MB / {mb_total:.1f} MB"
                            )
                            if not cont:
                                progress_data['cancelled'] = True
                    wx.CallAfter(do_update)

            def close_progress_dialog():
                if progress_data['dialog']:
                    progress_data['dialog'].Destroy()
                    progress_data['dialog'] = None

            event = threading.Event()
            def create_and_signal():
                create_progress_dialog()
                event.set()
            wx.CallAfter(create_and_signal)
            event.wait()

            try:
                local_filename = url.split('/')[-1]
                local_filename = os.path.expanduser("~/Downloads/" + local_filename)
                self.download_file_to(url, local_filename, progress_callback=update_progress)

                if progress_data['cancelled']:
                    wx.CallAfter(close_progress_dialog)
                    if os.path.exists(local_filename):
                        os.remove(local_filename)
                    return

                wx.CallAfter(close_progress_dialog)
                self.alert_from_thread(
                    f"FastGH has been downloaded to:\n{local_filename}\n\n"
                    "Please open the DMG file and drag FastGH to your Applications folder to complete the update.",
                    "Update Downloaded"
                )
            except Exception as e:
                wx.CallAfter(close_progress_dialog)
                self.alert_from_thread(f"Failed to download update: {e}", "Download Error")


# Convenience function to get the app instance
def get_app():
    return Application.get_instance()
