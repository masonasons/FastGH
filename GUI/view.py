"""Repository view dialog for FastGH."""

import wx
import webbrowser
import platform
import threading
from application import get_app
from models.repository import Repository
from . import theme

text_box_size = (700, 150)


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
        if self.repo.updated_at:
            details.append(f"Last Updated: {self.repo._format_relative_time()} ({self.repo.updated_at.strftime('%Y-%m-%d %H:%M')})")
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
        btn_row1.Add(self.copy_clone_btn, 0)

        self.main_box.Add(btn_row1, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        # Buttons - second row
        btn_row2 = wx.BoxSizer(wx.HORIZONTAL)

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
        self.star_btn.Bind(wx.EVT_BUTTON, self.on_toggle_star)
        self.watch_btn.Bind(wx.EVT_BUTTON, self.on_toggle_watch)
        self.open_btn.Bind(wx.EVT_BUTTON, self.on_open)
        self.copy_url_btn.Bind(wx.EVT_BUTTON, self.on_copy_url)
        self.copy_clone_btn.Bind(wx.EVT_BUTTON, self.on_copy_clone)
        self.issues_btn.Bind(wx.EVT_BUTTON, self.on_view_issues)
        self.prs_btn.Bind(wx.EVT_BUTTON, self.on_view_prs)
        self.commits_btn.Bind(wx.EVT_BUTTON, self.on_view_commits)
        self.actions_btn.Bind(wx.EVT_BUTTON, self.on_view_actions)
        self.releases_btn.Bind(wx.EVT_BUTTON, self.on_view_releases)
        self.owner_btn.Bind(wx.EVT_BUTTON, self.on_view_owner)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def check_status(self):
        """Check star/watch status in background."""
        def do_check():
            is_starred = self.account.is_starred(self.repo.owner, self.repo.name)
            is_watched = self.account.is_watching(self.repo.owner, self.repo.name)
            wx.CallAfter(self.update_status, is_starred, is_watched)

        threading.Thread(target=do_check, daemon=True).start()

    def update_status(self, is_starred: bool, is_watched: bool):
        """Update button labels based on status."""
        self.is_starred = is_starred
        self.is_watched = is_watched

        if is_starred:
            self.star_btn.SetLabel("Un&star")
        else:
            self.star_btn.SetLabel("&Star")

        if is_watched:
            self.watch_btn.SetLabel("Un&watch")
        else:
            self.watch_btn.SetLabel("&Watch")

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

    def on_view_owner(self, event):
        """View owner profile."""
        from GUI.search import UserProfileDialog
        dlg = UserProfileDialog(self, self.repo.owner)
        dlg.ShowModal()
        dlg.Destroy()

    def on_close(self, event):
        self.Destroy()
