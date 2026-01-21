"""Commits dialog for FastGH."""

import wx
import webbrowser
import platform
import threading
from application import get_app
from models.repository import Repository
from models.commit import Commit
from . import theme


class CommitsDialog(wx.Dialog):
    """Dialog for viewing repository commits."""

    def __init__(self, parent, repo: Repository):
        self.repo = repo
        self.app = get_app()
        self.account = self.app.currentAccount
        self.owner = repo.owner
        self.repo_name = repo.name
        self.commits = []
        self.branches = []
        self.current_branch = None

        title = f"Commits - {repo.full_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(900, 600))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load branches first, then commits
        self.load_branches()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Branch selection
        branch_sizer = wx.BoxSizer(wx.HORIZONTAL)
        branch_label = wx.StaticText(self.panel, label="&Branch:")
        branch_sizer.Add(branch_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.branch_choice = wx.Choice(self.panel, choices=["Loading..."])
        self.branch_choice.SetSelection(0)
        branch_sizer.Add(self.branch_choice, 1, wx.RIGHT, 10)

        self.refresh_btn = wx.Button(self.panel, label="&Refresh")
        branch_sizer.Add(self.refresh_btn, 0)

        main_sizer.Add(branch_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Commits list
        list_label = wx.StaticText(self.panel, label="&Commits:")
        main_sizer.Add(list_label, 0, wx.LEFT, 10)

        self.commits_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.commits_list, 1, wx.EXPAND | wx.ALL, 10)

        # Commit details
        details_label = wx.StaticText(self.panel, label="Commit &Details:")
        main_sizer.Add(details_label, 0, wx.LEFT, 10)

        self.details_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(850, 120)
        )
        main_sizer.Add(self.details_text, 0, wx.EXPAND | wx.ALL, 10)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.view_btn = wx.Button(self.panel, label="&View Details")
        btn_sizer.Add(self.view_btn, 0, wx.RIGHT, 5)

        self.copy_sha_btn = wx.Button(self.panel, label="Copy &SHA")
        btn_sizer.Add(self.copy_sha_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.branch_choice.Bind(wx.EVT_CHOICE, self.on_branch_change)
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        self.view_btn.Bind(wx.EVT_BUTTON, self.on_view)
        self.copy_sha_btn.Bind(wx.EVT_BUTTON, self.on_copy_sha)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        self.commits_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view)
        self.commits_list.Bind(wx.EVT_LISTBOX, self.on_selection_change)
        self.commits_list.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def load_branches(self):
        """Load branches in background."""
        def do_load():
            branches = self.account.get_branches(self.owner, self.repo_name)
            wx.CallAfter(self.update_branches, branches)

        threading.Thread(target=do_load, daemon=True).start()

    def update_branches(self, branches):
        """Update branches dropdown (branches are sorted by last commit date)."""
        self.branches = branches
        self.branch_choice.Clear()

        if not branches:
            self.branch_choice.Append("(no branches)")
            self.branch_choice.SetSelection(0)
        else:
            # Branches are sorted by last updated, but prefer main/master as default
            default_idx = 0
            main_idx = None
            for i, branch in enumerate(branches):
                name = branch.get('name', '')
                self.branch_choice.Append(name)
                if name in ('main', 'master') and main_idx is None:
                    main_idx = i

            # Use main/master if found, otherwise use first (most recently updated)
            if main_idx is not None:
                default_idx = main_idx

            self.branch_choice.SetSelection(default_idx)
            self.current_branch = branches[default_idx].get('name') if branches else None

        # Load commits for selected branch
        self.load_commits()

    def load_commits(self):
        """Load commits in background."""
        self.commits_list.Clear()
        self.commits_list.Append("Loading...")
        self.commits = []
        self.details_text.SetValue("")

        branch = self.branch_choice.GetStringSelection()
        if not branch or branch == "(no branches)":
            self.commits_list.Clear()
            self.commits_list.Append("No branch selected")
            return

        def do_load():
            max_commits = self.app.prefs.get("commit_limit", 0)
            commits = self.account.get_commits(self.owner, self.repo_name, sha=branch, max_commits=max_commits)
            wx.CallAfter(self.update_list, commits)

        threading.Thread(target=do_load, daemon=True).start()

    def update_list(self, commits):
        """Update the commits list."""
        self.commits = commits
        self.commits_list.Clear()

        if not commits:
            self.commits_list.Append("No commits found")
        else:
            for commit in commits:
                self.commits_list.Append(commit.format_display())

        # Focus on commits list
        self.commits_list.SetFocus()

        self.update_buttons()

    def update_buttons(self):
        """Update button states based on selection."""
        commit = self.get_selected_commit()
        has_selection = commit is not None

        self.view_btn.Enable(has_selection)
        self.copy_sha_btn.Enable(has_selection)
        self.open_browser_btn.Enable(has_selection)

    def get_selected_commit(self) -> Commit | None:
        """Get the currently selected commit."""
        selection = self.commits_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.commits):
            return self.commits[selection]
        return None

    def on_branch_change(self, event):
        """Handle branch change."""
        self.load_commits()

    def on_refresh(self, event):
        """Refresh the commits list."""
        self.load_commits()

    def on_view(self, event):
        """View commit details in a dialog."""
        commit = self.get_selected_commit()
        if commit:
            dlg = ViewCommitDialog(self, self.repo, commit)
            dlg.ShowModal()
            dlg.Destroy()

    def on_copy_sha(self, event):
        """Copy commit SHA to clipboard."""
        commit = self.get_selected_commit()
        if commit:
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(commit.sha))
                wx.TheClipboard.Close()
                wx.MessageBox(f"Copied: {commit.short_sha}", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_open_browser(self, event):
        """Open commit in browser."""
        commit = self.get_selected_commit()
        if commit:
            webbrowser.open(commit.html_url)

    def on_selection_change(self, event):
        """Handle selection change - show commit details."""
        self.update_buttons()
        commit = self.get_selected_commit()
        if commit:
            self.show_commit_preview(commit)

    def show_commit_preview(self, commit: Commit):
        """Show commit preview in details text."""
        lines = []
        lines.append(f"SHA: {commit.sha}")
        lines.append(f"Author: {commit.author.name} <{commit.author.email}>")
        if commit.author.date:
            lines.append(f"Date: {commit.author.date.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append(commit.message)

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.details_text.SetValue(sep.join(lines))

    def on_key(self, event):
        """Handle key events."""
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN:
            self.on_view(None)
        else:
            event.Skip()

    def on_close(self, event):
        """Close the dialog."""
        self.EndModal(wx.ID_CLOSE)


class ViewCommitDialog(wx.Dialog):
    """Dialog for viewing full commit details."""

    def __init__(self, parent, repo: Repository, commit: Commit):
        self.repo = repo
        self.commit = commit
        self.app = get_app()
        self.account = self.app.currentAccount

        title = f"Commit {commit.short_sha}"
        wx.Dialog.__init__(self, parent, title=title, size=(850, 700))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load full commit details if needed
        if not commit.files:
            self.load_full_commit()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Commit info
        info_label = wx.StaticText(self.panel, label="Commit &Information:")
        main_sizer.Add(info_label, 0, wx.LEFT | wx.TOP, 10)

        self.info_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_DONTWRAP,
            size=(800, 100)
        )
        main_sizer.Add(self.info_text, 0, wx.EXPAND | wx.ALL, 10)

        # Build info
        self.update_info_text()

        # Commit message
        msg_label = wx.StaticText(self.panel, label="&Message:")
        main_sizer.Add(msg_label, 0, wx.LEFT, 10)

        self.message_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(800, 120)
        )
        self.message_text.SetValue(self.commit.message)
        main_sizer.Add(self.message_text, 0, wx.EXPAND | wx.ALL, 10)

        # Files changed
        files_label = wx.StaticText(self.panel, label="&Files Changed:")
        main_sizer.Add(files_label, 0, wx.LEFT, 10)

        self.files_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.files_list, 1, wx.EXPAND | wx.ALL, 10)

        # Update files list
        self.update_files_list()

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.copy_sha_btn = wx.Button(self.panel, label="Copy &SHA")
        btn_sizer.Add(self.copy_sha_btn, 0, wx.RIGHT, 5)

        self.copy_msg_btn = wx.Button(self.panel, label="Copy M&essage")
        btn_sizer.Add(self.copy_msg_btn, 0, wx.RIGHT, 5)

        self.copy_filename_btn = wx.Button(self.panel, label="Copy &Filename")
        btn_sizer.Add(self.copy_filename_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)
        self.message_text.SetFocus()

    def update_info_text(self):
        """Update the info text."""
        c = self.commit
        lines = []
        lines.append(f"SHA: {c.sha}")

        author_name = c.github_author.login if c.github_author else c.author.name
        lines.append(f"Author: {c.author.name} <{c.author.email}>")
        if c.github_author:
            lines.append(f"GitHub User: {c.github_author.login}")

        if c.author.date:
            lines.append(f"Date: {c.author.date.strftime('%Y-%m-%d %H:%M:%S')} ({c._format_relative_time(c.author.date)})")

        if c.author.name != c.committer.name or c.author.email != c.committer.email:
            lines.append(f"Committer: {c.committer.name} <{c.committer.email}>")

        if c.parents:
            parents_str = ", ".join(p[:7] for p in c.parents)
            lines.append(f"Parents: {parents_str}")

        if c.stats_total:
            lines.append(f"Changes: +{c.stats_additions} -{c.stats_deletions} ({c.stats_total} total)")

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.info_text.SetValue(sep.join(lines))

    def load_full_commit(self):
        """Load full commit details."""
        def do_load():
            full_commit = self.account.get_commit(self.repo.owner, self.repo.name, self.commit.sha)
            if full_commit:
                wx.CallAfter(self.update_commit, full_commit)

        threading.Thread(target=do_load, daemon=True).start()

    def update_files_list(self):
        """Update the files list."""
        self.files_list.Clear()

        if not self.commit.files:
            self.files_list.Append("Loading files...")
        else:
            for f in self.commit.files:
                self.files_list.Append(f.format_display())

    def update_commit(self, commit: Commit):
        """Update with full commit details."""
        self.commit = commit
        self.update_info_text()
        self.update_files_list()

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.copy_sha_btn.Bind(wx.EVT_BUTTON, self.on_copy_sha)
        self.copy_msg_btn.Bind(wx.EVT_BUTTON, self.on_copy_message)
        self.copy_filename_btn.Bind(wx.EVT_BUTTON, self.on_copy_filename)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def on_copy_sha(self, event):
        """Copy SHA to clipboard."""
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.commit.sha))
            wx.TheClipboard.Close()
            wx.MessageBox(f"Copied: {self.commit.short_sha}", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_copy_message(self, event):
        """Copy commit message to clipboard."""
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.commit.message))
            wx.TheClipboard.Close()
            wx.MessageBox("Commit message copied!", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_copy_filename(self, event):
        """Copy selected filename to clipboard."""
        selection = self.files_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.commit.files):
            filename = self.commit.files[selection].filename
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(filename))
                wx.TheClipboard.Close()
                wx.MessageBox(f"Copied: {filename}", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_open_browser(self, event):
        """Open in browser."""
        webbrowser.open(self.commit.html_url)

    def on_close(self, event):
        """Close dialog."""
        self.EndModal(wx.ID_CLOSE)
