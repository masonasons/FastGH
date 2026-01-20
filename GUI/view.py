"""Repository view dialog for FastGH."""

import wx
import webbrowser
import platform
import threading
import subprocess
import os
import re
from application import get_app
from models.repository import Repository
from . import theme

text_box_size = (700, 150)


class GitProgressDialog(wx.Dialog):
    """Dialog for showing git operation progress."""

    def __init__(self, parent, title, operation):
        wx.Dialog.__init__(self, parent, title=title, size=(500, 200),
                          style=wx.DEFAULT_DIALOG_STYLE)
        self.operation = operation
        self.process = None
        self.cancelled = False

        self.init_ui()
        theme.apply_theme(self)

    def init_ui(self):
        """Initialize UI."""
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Status label
        self.status_label = wx.StaticText(panel, label=f"Starting {self.operation}...")
        sizer.Add(self.status_label, 0, wx.ALL | wx.EXPAND, 10)

        # Progress gauge (indeterminate)
        self.gauge = wx.Gauge(panel, range=100, style=wx.GA_HORIZONTAL)
        self.gauge.Pulse()
        sizer.Add(self.gauge, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)

        # Output text
        self.output_text = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            size=(-1, 80)
        )
        sizer.Add(self.output_text, 1, wx.ALL | wx.EXPAND, 10)

        # Cancel button
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.cancel_btn = wx.Button(panel, wx.ID_CANCEL, "&Cancel")
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        btn_sizer.Add(self.cancel_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER)

        panel.SetSizer(sizer)

        # Timer for pulsing gauge
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(50)

    def on_timer(self, event):
        """Pulse the gauge."""
        if not self.cancelled:
            self.gauge.Pulse()

    def on_cancel(self, event):
        """Cancel the operation."""
        self.cancelled = True
        if self.process:
            try:
                self.process.terminate()
            except:
                pass
        self.EndModal(wx.ID_CANCEL)

    def update_status(self, text):
        """Update status label."""
        self.status_label.SetLabel(text)

    def append_output(self, text):
        """Append text to output."""
        self.output_text.AppendText(text)

    def finish(self, success, message=""):
        """Finish the dialog."""
        self.timer.Stop()
        if success:
            self.gauge.SetValue(100)
        self.EndModal(wx.ID_OK if success else wx.ID_CANCEL)


class ViewRepoDialog(wx.Dialog):
    """Dialog for viewing repository details."""

    def __init__(self, parent, repo: Repository):
        self.repo = repo
        self.app = get_app()
        self.account = self.app.currentAccount
        self.is_starred = False
        self.is_watched = False

        title = f"View Repository: {repo.full_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(800, 550))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Check star/watch status in background
        self.check_status()

    def init_ui(self):
        """Initialize UI."""
        self.panel = wx.Panel(self)
        self.main_box = wx.BoxSizer(wx.VERTICAL)

        # Description
        self.desc_label = wx.StaticText(self.panel, -1, "&Description")
        self.main_box.Add(self.desc_label, 0, wx.LEFT | wx.TOP, 10)
        self.desc_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=text_box_size,
            name="Description"
        )
        self.main_box.Add(self.desc_text, 0, wx.EXPAND | wx.ALL, 10)
        self.desc_text.SetValue(self.repo.description or "No description")
        self.desc_text.SetFocus()

        # Details
        self.details_label = wx.StaticText(self.panel, -1, "Repository &Details")
        self.main_box.Add(self.details_label, 0, wx.LEFT | wx.TOP, 10)
        self.details_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_DONTWRAP,
            size=text_box_size,
            name="Repository Details"
        )
        self.main_box.Add(self.details_text, 0, wx.EXPAND | wx.ALL, 10)

        # Build details
        details = []
        details.append(f"Name: {self.repo.full_name}")
        details.append(f"Owner: {self.repo.owner}")
        details.append(f"Language: {self.repo.language or 'Not specified'}")
        details.append(f"Stars: {self.repo.stars}")
        details.append(f"Forks: {self.repo.forks}")
        details.append(f"Open Issues: {self.repo.open_issues}")
        details.append(f"Visibility: {'Private' if self.repo.private else 'Public'}")
        if self.repo.pushed_at:
            details.append(f"Last Push: {self.repo._format_relative_time()} ({self.repo.pushed_at.strftime('%Y-%m-%d %H:%M')})")
        details.append(f"URL: {self.repo.html_url}")

        separator = "\r\n" if platform.system() != "Darwin" else "\n"
        self.details_text.SetValue(separator.join(details))

        # Buttons - first row (star/watch)
        btn_row1 = wx.BoxSizer(wx.HORIZONTAL)

        self.star_btn = wx.Button(self.panel, -1, "&Star")
        btn_row1.Add(self.star_btn, 0, wx.RIGHT, 5)

        self.watch_btn = wx.Button(self.panel, -1, "&Watch")
        btn_row1.Add(self.watch_btn, 0, wx.RIGHT, 5)

        self.open_btn = wx.Button(self.panel, -1, "&Open in Browser")
        btn_row1.Add(self.open_btn, 0, wx.RIGHT, 5)

        self.copy_url_btn = wx.Button(self.panel, -1, "Copy &URL")
        btn_row1.Add(self.copy_url_btn, 0, wx.RIGHT, 5)

        self.copy_clone_btn = wx.Button(self.panel, -1, "Copy &Clone URL")
        btn_row1.Add(self.copy_clone_btn, 0, wx.RIGHT, 5)

        # Git button - will show Clone or Pull based on whether repo exists
        self.git_btn = wx.Button(self.panel, -1, "&Git...")
        btn_row1.Add(self.git_btn, 0)

        self.main_box.Add(btn_row1, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # Buttons - second row
        btn_row2 = wx.BoxSizer(wx.HORIZONTAL)

        self.files_btn = wx.Button(self.panel, -1, "View &Files")
        btn_row2.Add(self.files_btn, 0, wx.RIGHT, 5)

        self.issues_btn = wx.Button(self.panel, -1, "View &Issues")
        btn_row2.Add(self.issues_btn, 0, wx.RIGHT, 5)

        self.prs_btn = wx.Button(self.panel, -1, "View &Pull Requests")
        btn_row2.Add(self.prs_btn, 0, wx.RIGHT, 5)

        self.commits_btn = wx.Button(self.panel, -1, "View Co&mmits")
        btn_row2.Add(self.commits_btn, 0, wx.RIGHT, 5)

        self.actions_btn = wx.Button(self.panel, -1, "View &Actions")
        btn_row2.Add(self.actions_btn, 0, wx.RIGHT, 5)

        self.releases_btn = wx.Button(self.panel, -1, "View &Releases")
        btn_row2.Add(self.releases_btn, 0, wx.RIGHT, 5)

        self.forks_btn = wx.Button(self.panel, -1, "View F&orks")
        btn_row2.Add(self.forks_btn, 0, wx.RIGHT, 5)

        self.owner_btn = wx.Button(self.panel, -1, "View O&wner")
        btn_row2.Add(self.owner_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CANCEL, "Cl&ose")
        btn_row2.Add(self.close_btn, 0)

        self.main_box.Add(btn_row2, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        self.panel.SetSizer(self.main_box)
        self.panel.Layout()

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.star_btn.Bind(wx.EVT_BUTTON, self.on_toggle_star)
        self.watch_btn.Bind(wx.EVT_BUTTON, self.on_toggle_watch)
        self.open_btn.Bind(wx.EVT_BUTTON, self.on_open)
        self.copy_url_btn.Bind(wx.EVT_BUTTON, self.on_copy_url)
        self.copy_clone_btn.Bind(wx.EVT_BUTTON, self.on_copy_clone)
        self.git_btn.Bind(wx.EVT_BUTTON, self.on_git)
        self.files_btn.Bind(wx.EVT_BUTTON, self.on_view_files)
        self.issues_btn.Bind(wx.EVT_BUTTON, self.on_view_issues)
        self.prs_btn.Bind(wx.EVT_BUTTON, self.on_view_prs)
        self.commits_btn.Bind(wx.EVT_BUTTON, self.on_view_commits)
        self.actions_btn.Bind(wx.EVT_BUTTON, self.on_view_actions)
        self.releases_btn.Bind(wx.EVT_BUTTON, self.on_view_releases)
        self.forks_btn.Bind(wx.EVT_BUTTON, self.on_view_forks)
        self.owner_btn.Bind(wx.EVT_BUTTON, self.on_view_owner)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def check_status(self):
        """Check star/watch status in background."""
        def do_check():
            is_starred = self.account.is_starred(self.repo.owner, self.repo.name)
            is_watched = self.account.is_watching(self.repo.owner, self.repo.name)
            wx.CallAfter(self.update_status, is_starred, is_watched)

        threading.Thread(target=do_check, daemon=True).start()

        # Check git status
        self.update_git_button()

    def get_repo_path(self):
        """Get the local path for this repository."""
        git_path = self.app.prefs.git_path
        if self.app.prefs.git_use_org_structure:
            return os.path.join(git_path, self.repo.owner, self.repo.name)
        return os.path.join(git_path, self.repo.name)

    def repo_exists_locally(self):
        """Check if the repository exists locally."""
        repo_path = self.get_repo_path()
        return os.path.isdir(os.path.join(repo_path, ".git"))

    def update_git_button(self):
        """Update git button label based on whether repo exists."""
        try:
            if self.repo_exists_locally():
                self.git_btn.SetLabel("&Pull")
            else:
                self.git_btn.SetLabel("C&lone")
        except RuntimeError:
            pass  # Dialog was destroyed

    def update_status(self, is_starred: bool, is_watched: bool):
        """Update button labels based on status."""
        self.is_starred = is_starred
        self.is_watched = is_watched

        # Check if dialog/buttons still exist (may be destroyed if closed quickly)
        try:
            if is_starred:
                self.star_btn.SetLabel("Un&star")
            else:
                self.star_btn.SetLabel("&Star")

            if is_watched:
                self.watch_btn.SetLabel("Un&watch")
            else:
                self.watch_btn.SetLabel("&Watch")
        except RuntimeError:
            pass  # Dialog was destroyed

    def on_toggle_star(self, event):
        """Star or unstar the repository."""
        if self.is_starred:
            if self.account.unstar_repo(self.repo.owner, self.repo.name):
                self.is_starred = False
                self.star_btn.SetLabel("&Star")
                wx.MessageBox(f"Unstarred {self.repo.full_name}", "Success", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Failed to unstar repository.", "Error", wx.OK | wx.ICON_ERROR)
        else:
            if self.account.star_repo(self.repo.owner, self.repo.name):
                self.is_starred = True
                self.star_btn.SetLabel("Un&star")
                wx.MessageBox(f"Starred {self.repo.full_name}", "Success", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Failed to star repository.", "Error", wx.OK | wx.ICON_ERROR)

    def on_toggle_watch(self, event):
        """Watch or unwatch the repository."""
        if self.is_watched:
            if self.account.unwatch_repo(self.repo.owner, self.repo.name):
                self.is_watched = False
                self.watch_btn.SetLabel("&Watch")
                wx.MessageBox(f"Unwatched {self.repo.full_name}", "Success", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Failed to unwatch repository.", "Error", wx.OK | wx.ICON_ERROR)
        else:
            if self.account.watch_repo(self.repo.owner, self.repo.name):
                self.is_watched = True
                self.watch_btn.SetLabel("Un&watch")
                wx.MessageBox(f"Now watching {self.repo.full_name}", "Success", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Failed to watch repository.", "Error", wx.OK | wx.ICON_ERROR)

    def on_open(self, event):
        """Open repository in browser."""
        webbrowser.open(self.repo.html_url)

    def on_copy_url(self, event):
        """Copy repository URL to clipboard."""
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.repo.html_url))
            wx.TheClipboard.Close()
            wx.MessageBox(f"Copied: {self.repo.html_url}", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_copy_clone(self, event):
        """Copy git clone URL to clipboard."""
        clone_url = f"https://github.com/{self.repo.full_name}.git"
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(clone_url))
            wx.TheClipboard.Close()
            wx.MessageBox(f"Copied: {clone_url}", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_git(self, event):
        """Clone or pull the repository."""
        git_path = self.app.prefs.git_path

        # Ensure git path exists
        if not os.path.isdir(git_path):
            try:
                os.makedirs(git_path)
            except OSError as e:
                wx.MessageBox(
                    f"Failed to create git path: {git_path}\n\n{e}",
                    "Error",
                    wx.OK | wx.ICON_ERROR
                )
                return

        if self.repo_exists_locally():
            self.do_git_pull()
        else:
            self.do_git_clone()

    def do_git_clone(self):
        """Clone the repository."""
        git_path = self.app.prefs.git_path
        clone_url = f"https://github.com/{self.repo.full_name}.git"
        use_org_structure = self.app.prefs.git_use_org_structure
        use_recursive = self.app.prefs.git_clone_recursive

        # If using org structure, create owner directory and clone into it
        if use_org_structure:
            clone_dir = os.path.join(git_path, self.repo.owner)
            try:
                os.makedirs(clone_dir, exist_ok=True)
            except OSError as e:
                wx.MessageBox(
                    f"Failed to create directory: {clone_dir}\n\n{e}",
                    "Error",
                    wx.OK | wx.ICON_ERROR
                )
                return
        else:
            clone_dir = git_path

        # Create progress dialog
        progress_dlg = GitProgressDialog(self, f"Cloning {self.repo.name}", "clone")

        cmd = ["git", "clone", "--progress"]
        if use_recursive:
            cmd.append("--recursive")
        cmd.append(clone_url)

        self._run_git_with_progress(progress_dlg, cmd, clone_dir, "clone")

    def do_git_pull(self):
        """Pull the latest changes."""
        repo_path = self.get_repo_path()

        # Create progress dialog
        progress_dlg = GitProgressDialog(self, f"Pulling {self.repo.name}", "pull")

        cmd = ["git", "pull", "--progress"]

        self._run_git_with_progress(progress_dlg, cmd, repo_path, "pull")

    def _run_git_with_progress(self, progress_dlg, cmd, cwd, operation):
        """Run a git command with progress dialog."""
        success = [False]
        error_message = [""]
        final_output = [""]

        def run_git():
            try:
                creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                process = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=creationflags
                )
                progress_dlg.process = process

                # Read stderr (where git outputs progress) in real-time
                output_lines = []
                while True:
                    if progress_dlg.cancelled:
                        process.terminate()
                        break

                    line = process.stderr.readline()
                    if not line and process.poll() is not None:
                        break
                    if line:
                        output_lines.append(line)
                        # Update dialog on main thread
                        wx.CallAfter(progress_dlg.append_output, line)
                        # Update status with progress info
                        line_stripped = line.strip()
                        if line_stripped:
                            wx.CallAfter(progress_dlg.update_status, line_stripped[:60])

                # Also get stdout
                stdout, remaining_stderr = process.communicate()
                if stdout:
                    output_lines.append(stdout)
                    wx.CallAfter(progress_dlg.append_output, stdout)
                if remaining_stderr:
                    output_lines.append(remaining_stderr)
                    wx.CallAfter(progress_dlg.append_output, remaining_stderr)

                final_output[0] = "".join(output_lines)
                success[0] = process.returncode == 0 and not progress_dlg.cancelled

                if not success[0] and not progress_dlg.cancelled:
                    error_message[0] = final_output[0]

            except FileNotFoundError:
                error_message[0] = "Git is not installed or not in PATH."
            except Exception as e:
                error_message[0] = str(e)

            # Close dialog on main thread
            wx.CallAfter(progress_dlg.finish, success[0])

        # Start git operation in background
        threading.Thread(target=run_git, daemon=True).start()

        # Show dialog modally
        result = progress_dlg.ShowModal()
        progress_dlg.Destroy()

        # Update button state
        self.update_git_button()

        # Show result message
        if progress_dlg.cancelled:
            wx.MessageBox(
                f"{operation.capitalize()} was cancelled.",
                f"{operation.capitalize()} Cancelled",
                wx.OK | wx.ICON_INFORMATION
            )
        elif success[0]:
            if operation == "clone":
                wx.MessageBox(
                    f"Successfully cloned {self.repo.full_name} to:\n{self.get_repo_path()}",
                    "Clone Complete",
                    wx.OK | wx.ICON_INFORMATION
                )
            else:
                message = final_output[0].strip() if final_output[0] else "Already up to date."
                wx.MessageBox(
                    f"Pull complete:\n\n{message}",
                    "Pull Complete",
                    wx.OK | wx.ICON_INFORMATION
                )
        else:
            wx.MessageBox(
                f"Failed to {operation}:\n\n{error_message[0]}",
                f"{operation.capitalize()} Failed",
                wx.OK | wx.ICON_ERROR
            )

    def on_view_files(self, event):
        """Open file browser dialog."""
        from GUI.files import FileBrowserDialog
        dlg = FileBrowserDialog(self, self.repo)
        dlg.ShowModal()
        dlg.Destroy()

    def on_view_issues(self, event):
        """Open issues dialog."""
        from GUI.issues import IssuesDialog
        dlg = IssuesDialog(self, self.repo)
        dlg.ShowModal()
        dlg.Destroy()

    def on_view_prs(self, event):
        """Open pull requests dialog."""
        from GUI.pullrequests import PullRequestsDialog
        dlg = PullRequestsDialog(self, self.repo)
        dlg.ShowModal()
        dlg.Destroy()

    def on_view_commits(self, event):
        """Open commits dialog."""
        from GUI.commits import CommitsDialog
        dlg = CommitsDialog(self, self.repo)
        dlg.ShowModal()
        dlg.Destroy()

    def on_view_actions(self, event):
        """Open actions dialog."""
        from GUI.actions import ActionsDialog
        dlg = ActionsDialog(self, self.repo)
        dlg.ShowModal()
        dlg.Destroy()

    def on_view_releases(self, event):
        """Open releases dialog."""
        from GUI.releases import ReleasesDialog
        dlg = ReleasesDialog(self, self.repo)
        dlg.ShowModal()
        dlg.Destroy()

    def on_view_forks(self, event):
        """Open forks dialog."""
        from GUI.forks import ForksDialog
        dlg = ForksDialog(self, self.repo)
        dlg.ShowModal()
        dlg.Destroy()

    def on_view_owner(self, event):
        """View owner profile."""
        from GUI.search import UserProfileDialog
        dlg = UserProfileDialog(self, self.repo.owner)
        dlg.ShowModal()
        dlg.Destroy()

    def on_close(self, event):
        self.Destroy()
